"""Public registry verification compares complete inventories and actual downloaded bytes."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TypedDict

import pytest
from release_scripts.cli_artifacts import PLATFORMS, names
from tests.contract.test_source_qualification import workflow

CURL = r"""
import json
import sys
from pathlib import Path

root = Path.cwd()
args = sys.argv[1:]
url = next(arg for arg in args if arg.startswith("https://"))
if url == "https://pypi.org/pypi/ai-stp/1.2.3/json":
    print((root / "public.json").read_text())
else:
    name = url.rsplit("/", 1)[-1]
    data = (root / "release" / name).read_bytes()
    if (root / "bad-bytes").exists():
        data += b"altered public payload"
    Path(args[args.index("--output") + 1]).write_bytes(data)
"""


class FileRecord(TypedDict):
    filename: str
    digests: dict[str, str]
    url: str


def execute_public_verification(
    tmp_path: Path, kind: str, *, failure: str | None = None
) -> subprocess.CompletedProcess[str]:
    release = tmp_path / "release"
    release.mkdir()
    payloads = (
        sorted(
            name for target in PLATFORMS for name in names("1.2.3", target) if name.endswith(".whl")
        )
        if kind == "pypi"
        else ["ai-stp-cli-1.2.3.crate"]
    )
    records: list[FileRecord] = []
    for name in payloads:
        data = f"Qualified {name}\n".encode()
        (release / name).write_bytes(data)
        records.append(
            {
                "filename": name,
                "digests": {"sha256": hashlib.sha256(data).hexdigest()},
                "url": "https://files.pythonhosted.org/packages/" + name,
            }
        )
    if failure == "missing":
        records.pop()
    elif failure == "extra":
        extra = records[0].copy()
        extra["filename"] = "unqualified.whl"
        records.append(extra)
    elif failure == "duplicate":
        records[-1] = records[0]
    elif failure == "host":
        records[0]["url"] = "https://example.invalid/untrusted.whl"
    elif failure == "digest":
        records[0]["digests"]["sha256"] = "0" * 64
    elif failure == "bytes":
        (tmp_path / "bad-bytes").touch()
    (tmp_path / "public.json").write_text(json.dumps({"urls": records}))
    program = tmp_path / "curl"
    program.write_text(f"#!{sys.executable}\n" + CURL)
    program.chmod(0o755)
    code = workflow(f"publish-{kind}.yml")["jobs"]["verify-public"]["steps"][-1]["run"]
    return subprocess.run(
        ["bash", "-c", code],
        cwd=tmp_path,
        env={
            "PATH": str(tmp_path) + os.pathsep + os.environ.get("PATH", os.defpath),
            "VERSION": "1.2.3",
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )


@pytest.mark.parametrize(
    "failure", [None, "missing", "extra", "duplicate", "host", "digest", "bytes"]
)
def test_public_wheels_require_all_three_original_names_and_bytes(
    tmp_path: Path, failure: str | None
) -> None:
    result = execute_public_verification(tmp_path, "pypi", failure=failure)
    assert (result.returncode == 0) == (failure is None), result.stderr


@pytest.mark.parametrize("failure", [None, "bytes"])
def test_public_crate_must_equal_the_attested_original(tmp_path: Path, failure: str | None) -> None:
    result = execute_public_verification(tmp_path, "crates", failure=failure)
    assert (result.returncode == 0) == (failure is None), result.stderr
