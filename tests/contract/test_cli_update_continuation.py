"""The updater survives without importing the replaced CLI distribution."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from ai_stp_cli.self_update import helper


@pytest.mark.parametrize("wrong_version", [False, True])
def test_standalone_continuation_installs_once_and_requires_the_observed_version(
    tmp_path: Path,
    wrong_version: bool,
) -> None:
    executable = tmp_path / "version"
    executable.write_text(
        "import json\nfrom pathlib import Path\n"
        "print(json.dumps({'ok': True, 'data': {'cli_version': Path('installed').read_text()}}))\n",
        encoding="utf-8",
    )
    (tmp_path / "installed").write_text("old", encoding="utf-8")
    wheel = tmp_path / "candidate.whl"
    wheel.write_bytes(b"exact staged bytes")
    journal = tmp_path / "journal.json"
    journal.write_text(
        json.dumps({"plan_digest": "exact-plan", "direction": "update", "state": "pending"})
    )
    installer = (
        "from pathlib import Path; "
        f"Path('installed').write_text({'wrong' if wrong_version else 'new'!r}); "
        "p=Path('installer-count'); p.write_text(str(int(p.read_text())+1) if p.exists() else '1')"
    )
    job: dict[str, Any] = {
        "journal": str(journal),
        "lock": str(tmp_path / "lock"),
        "environment": {},
        "plan_digest": "exact-plan",
        "direction": "update",
        "executable": sys.executable,
        "target_version": "new",
        "source_version": "old",
        "rollback_digest": "rollback",
        "wheel": str(wheel),
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "argv": [sys.executable, "-c", installer],
    }
    job_path = tmp_path / "job.json"
    payload = json.dumps(job).encode()
    job_path.write_bytes(payload)
    copied = tmp_path / "continuation.py"
    copied.write_bytes(Path(helper.__file__).read_bytes())
    environment = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
    arguments = [
        sys.executable,
        "-I",
        str(copied),
        str(job_path),
        hashlib.sha256(payload).hexdigest(),
    ]
    completed = subprocess.run(
        arguments,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    state = json.loads(journal.read_text())["state"]
    assert state == ("recovery_required" if wrong_version else "verified")
    assert (tmp_path / "installer-count").read_text() == "1"
    if not wrong_version:
        repeated = subprocess.run(
            arguments,
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert repeated.returncode == 0, repeated.stderr
        assert (tmp_path / "installer-count").read_text() == "1"
