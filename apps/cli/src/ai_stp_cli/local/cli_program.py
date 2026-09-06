"""Shared install/invoke/remove for catalog `cli` components.

A `cli` component is one executable, not seven copies under harness homes.
The prefix is the CLI data directory, never a provider target.
"""

from __future__ import annotations

import io
import os
import sqlite3
import stat
import subprocess
import zipfile
from pathlib import Path
from typing import Final

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import content, revisions, versions
from ai_stp_cli.paths import DIRECTORY_MODE, data_dir, ensure_directory
from ai_stp_contracts.machine_help import CliProgram
from ai_stp_passports.versions import ComponentVersionPassport

CURRENT: Final[str] = "current"
MAX_INVOKE_OUTPUT: Final[int] = 65_536
INVOKE_TIMEOUT_SECONDS: Final[float] = 30.0


def prefix() -> Path:
    """Shared executable root. One tree, not a harness home."""
    return data_dir() / "cli-programs"


def install(
    connection: sqlite3.Connection,
    *,
    stable_id: str,
    version: str | None,
) -> CliProgram:
    """Install one recorded `cli` artifact under the shared prefix."""
    _passport, recorded, payload = _load(connection, stable_id, version)
    root = ensure_directory(prefix())
    target = ensure_directory(root / recorded.stable_id / recorded.version)
    executable = target / "program"
    executable.write_bytes(payload)
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    pointer = root / recorded.stable_id / CURRENT
    _replace_pointer(pointer, executable)
    return CliProgram(
        stable_id=recorded.stable_id,
        version=recorded.version,
        operation="install",
        state="present",
        prefix=str(root),
        executable=str(pointer),
    )


def invoke(
    connection: sqlite3.Connection,
    *,
    stable_id: str,
    version: str | None,
    arguments: tuple[str, ...],
) -> CliProgram:
    """Run the installed pointer. Never resolves through PATH."""
    recorded = _recorded(connection, stable_id, version)
    pointer = prefix() / recorded.stable_id / CURRENT
    executable = _resolved(pointer)
    if executable is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "that cli program is not installed",
            details={"id": recorded.stable_id},
            next_actions=[f"component program install --id {recorded.stable_id} --json"],
        )
    if not executable.is_file():
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the installed cli pointer does not name a file",
            details={"id": recorded.stable_id, "path": str(pointer)},
        )
    try:
        finished = subprocess.run(
            _argv(executable, arguments),
            capture_output=True,
            text=True,
            timeout=INVOKE_TIMEOUT_SECONDS,
            check=False,
            env={"PATH": "", "HOME": os.environ.get("HOME", "")},
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the cli program could not be invoked",
            details={"id": recorded.stable_id, "error": type(error).__name__},
        ) from error
    output = ((finished.stdout or "") + (finished.stderr or ""))[:MAX_INVOKE_OUTPUT]
    return CliProgram(
        stable_id=recorded.stable_id,
        version=recorded.version,
        operation="invoke",
        state="invoked",
        prefix=str(prefix()),
        executable=str(executable),
        exit_code=finished.returncode,
        output=output,
    )


def status(connection: sqlite3.Connection, *, stable_id: str) -> CliProgram:
    """Report whether the shared executable is present."""
    pointer = prefix() / stable_id / CURRENT
    resolved = _resolved(pointer)
    present = resolved is not None and resolved.is_file()
    version = ""
    if present:
        held = versions.line(connection, stable_id)
        version = held[-1].version if held else "0.0"
    return CliProgram(
        stable_id=stable_id,
        version=version or "0.0",
        operation="status",
        state="present" if present else "never_installed",
        prefix=str(prefix()),
        executable=str(pointer) if present else "",
    )


def remove(*, stable_id: str) -> CliProgram:
    """Remove only what this module installed for this component."""
    root = prefix() / stable_id
    pointer = root / CURRENT
    existed = pointer.exists() or root.exists()
    if root.exists():
        for child in sorted(root.rglob("*"), reverse=True):
            if child.is_file() or child.is_symlink():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        root.rmdir()
    return CliProgram(
        stable_id=stable_id,
        version="0.0",
        operation="remove",
        state="removed" if existed else "never_installed",
        prefix=str(prefix()),
    )


def _load(
    connection: sqlite3.Connection, stable_id: str, version: str | None
) -> tuple[ComponentVersionPassport, versions.Recorded, bytes]:
    recorded = _recorded(connection, stable_id, version)
    stored = revisions.get(connection, recorded.revision_id)
    if stored is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the recorded cli revision is missing",
            details={"id": stable_id},
        )
    passport = ComponentVersionPassport.model_validate(stored.envelope.model_dump(mode="json"))
    if passport.component_type != "cli":
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "program lifecycle is for cli components",
            details={"component_type": passport.component_type},
        )
    payload = content.get(connection, passport.artifact.digest)
    program = _program_bytes(payload)
    if not program:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the cli artifact is empty",
            details={"id": recorded.stable_id},
        )
    return passport, recorded, program


def _program_bytes(payload: bytes) -> bytes:
    if not payload.startswith(b"PK"):
        return payload
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = [name for name in archive.namelist() if not name.endswith("/")]
            if not names:
                return b""
            return archive.read(names[0])
    except zipfile.BadZipFile:
        return payload


def _recorded(
    connection: sqlite3.Connection, stable_id: str, version: str | None
) -> versions.Recorded:
    if version:
        recorded = versions.held(connection, stable_id, version)
        if recorded is None:
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "that component version is not in the local registry",
                details={"id": stable_id, "version": version},
            )
        return recorded
    held = versions.line(connection, stable_id)
    if not held:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "that component is not in the local registry",
            details={"id": stable_id},
        )
    return held[-1]


def _argv(executable: Path, arguments: tuple[str, ...]) -> list[str]:
    raw = executable.read_bytes()[:128]
    if raw.startswith(b"#!"):
        line = raw.split(b"\n", 1)[0][2:].decode("utf-8", errors="replace").strip()
        return [*line.split(), str(executable), *arguments]
    return [str(executable), *arguments]


def _resolved(pointer: Path) -> Path | None:
    if not pointer.exists():
        return None
    if pointer.is_symlink() or os.name != "nt":
        return pointer.resolve() if pointer.exists() else None
    text = pointer.read_text(encoding="utf-8")
    if not text.startswith("path:"):
        return None
    return Path(text.removeprefix("path:"))


def _replace_pointer(pointer: Path, target: Path) -> None:
    pointer.parent.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
    staged = pointer.with_name(f".{CURRENT}.staging")
    staged.unlink(missing_ok=True)
    if os.name == "nt":
        staged.write_text(f"path:{target}", encoding="utf-8")
    else:
        staged.symlink_to(target)
    staged.replace(pointer)
