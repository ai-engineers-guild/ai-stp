"""Standalone updater continuation; copied outside the replaced Python prefix.

This file intentionally imports only the standard library. It must finish even
when the old CLI distribution and all of its third-party imports are gone.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast


def _write(path: Path, document: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    handle = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(document, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _lock(path: Path) -> Generator[None]:
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt

            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)  # type: ignore[attr-defined]
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined, possibly-undefined]
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)  # type: ignore[possibly-undefined]


def _version(executable: str, environment: dict[str, str]) -> str:
    try:
        result = subprocess.run(
            [executable, "version", "--json"],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return "unknown"
        envelope = json.loads(result.stdout)
        if not isinstance(envelope, dict):
            return "unknown"
        document = cast(dict[str, Any], envelope)
        if document.get("ok") is not True:
            return "unknown"
        data = document.get("data")
        if not isinstance(data, dict):
            return "unknown"
        return str(cast(dict[str, Any], data).get("cli_version", "unknown"))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return "unknown"


def execute(job_path: Path, expected_digest: str) -> None:
    payload = job_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_digest:
        raise ValueError("update continuation changed before execution")
    job = json.loads(payload)
    journal_path = Path(job["journal"])
    environment = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
    for key, value in job["environment"].items():
        if key not in {"UV_TOOL_DIR", "UV_TOOL_BIN_DIR", "PIPX_HOME", "PIPX_BIN_DIR"}:
            raise ValueError("unsupported installer binding")
        environment[key] = value
    with _lock(Path(job["lock"])):
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        if (
            journal.get("plan_digest") != job["plan_digest"]
            or journal.get("direction") != job["direction"]
        ):
            return
        try:
            wheel = Path(job["wheel"])
            if (
                wheel.is_symlink()
                or hashlib.sha256(wheel.read_bytes()).hexdigest() != job["wheel_sha256"]
            ):
                raise ValueError("staged update bytes changed before execution")
            observed = _version(job["executable"], environment)
            if observed not in {job["target_version"], job["source_version"], "unknown"}:
                raise RuntimeError("installation changed after the planned handoff")
            if observed != job["target_version"]:
                completed = subprocess.run(
                    job["argv"],
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=300,
                    check=False,
                )
                if completed.returncode != 0:
                    raise RuntimeError(f"installer exited with code {completed.returncode}")
                observed = _version(job["executable"], environment)
            if observed != job["target_version"]:
                raise RuntimeError("installed version does not match the planned replacement")
            journal.update(
                state="rolled_back" if job["direction"] == "rollback" else "verified",
                rollback_digest=job["rollback_digest"],
                target_version=job["target_version"],
                reason="the planned version is verified in a new process",
            )
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
            journal.update(
                state="recovery_required",
                reason=(
                    f"update continuation: {error}"
                    if isinstance(error, RuntimeError)
                    else f"update continuation: {type(error).__name__}"
                ),
            )
        journal["updated_at"] = datetime.now(UTC).isoformat()
        _write(journal_path, journal)


if __name__ == "__main__":
    execute(Path(sys.argv[1]), sys.argv[2])
