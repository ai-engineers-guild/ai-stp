"""Standalone updater continuation; copied outside the replaced Python prefix.

This file intentionally imports only the standard library. It must finish even
when the old CLI distribution and all of its third-party imports are gone.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import zipfile
from collections.abc import Generator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast


class RegistryCompatibilityError(RuntimeError):
    """The retained reader cannot safely read the current registry."""


def wheel_schema_version(wheel: Path) -> int:
    """Read the retained wheel's schema declaration without executing its code."""
    member = "ai_stp_cli/local/database.py"
    try:
        with zipfile.ZipFile(wheel) as archive:
            if (
                archive.namelist().count(member) != 1
                or archive.getinfo(member).file_size > 1024 * 1024
            ):
                raise ValueError("missing or oversized schema declaration")
            source = ast.parse(archive.read(member))
        values: dict[str, ast.expr] = {}
        for node in source.body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
                values[node.target.id] = node.value
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        values[target.id] = node.value
        schema = values.get("SCHEMA_VERSION")
        if isinstance(schema, ast.Constant) and type(schema.value) is int and schema.value >= 0:
            return schema.value
        expected = ast.parse("MIGRATIONS[-1].version", mode="eval").body
        migrations = values.get("MIGRATIONS")
        if (
            schema is None
            or ast.dump(schema) != ast.dump(expected)
            or not isinstance(migrations, ast.Tuple)
        ):
            raise ValueError("unsupported schema declaration")
        versions: list[int] = []
        for item in migrations.elts:
            if (
                not isinstance(item, ast.Call)
                or not isinstance(item.func, ast.Name)
                or item.func.id != "Migration"
            ):
                raise ValueError("unsupported migration declaration")
            declared = ([item.args[0]] if item.args else []) + [
                keyword.value for keyword in item.keywords if keyword.arg == "version"
            ]
            if (
                len(declared) != 1
                or not isinstance(declared[0], ast.Constant)
                or type(declared[0].value) is not int
            ):
                raise ValueError("unsupported migration version")
            versions.append(declared[0].value)
        if not versions or versions != sorted(set(versions)) or versions[0] < 1:
            raise ValueError("invalid migration order")
        return versions[-1]
    except (
        OSError,
        ValueError,
        SyntaxError,
        KeyError,
        RecursionError,
        zipfile.BadZipFile,
    ) as error:
        raise RegistryCompatibilityError(
            "rollback wheel has no verifiable registry schema declaration"
        ) from error


def check_registry_compatibility(wheel: Path, registry: Path) -> None:
    """Refuse an unreadable downgrade without migrating or restoring user data."""
    if not registry.exists():
        return
    ceiling = wheel_schema_version(wheel)
    try:
        with closing(
            sqlite3.connect(registry.resolve().as_uri() + "?mode=ro", uri=True)
        ) as connection:
            current = int(connection.execute("PRAGMA user_version").fetchone()[0])
    except (OSError, ValueError, sqlite3.Error) as error:
        raise RegistryCompatibilityError("current registry schema cannot be inspected") from error
    if current > ceiling:
        raise RegistryCompatibilityError(
            f"registry schema {current} is newer than rollback reader {ceiling}"
        )


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
            if job["direction"] == "rollback":
                registry_path = job.get("registry_path")
                if not isinstance(registry_path, str) or not registry_path:
                    raise RegistryCompatibilityError(
                        "rollback continuation has no registry binding"
                    )
                check_registry_compatibility(wheel, Path(registry_path))
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
            if job["direction"] == "rollback":
                check_registry_compatibility(wheel, Path(job["registry_path"]))
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
