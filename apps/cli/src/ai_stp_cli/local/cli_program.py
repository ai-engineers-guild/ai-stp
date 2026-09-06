"""Shared install/invoke/remove for catalog `cli` components.

A `cli` component is one executable, not seven copies under harness homes.
The prefix is the CLI data directory, never a provider target.
"""

from __future__ import annotations

import io
import os
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Final, cast

from pydantic import ValidationError

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, content, revisions, versions
from ai_stp_cli.paths import (
    data_dir,
    ensure_directory,
    is_executable_file,
    write_private,
    write_private_bytes,
)
from ai_stp_contracts.machine_help import CliProgram
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.ids import is_valid_id
from ai_stp_foundation.versioning import parse_version
from ai_stp_passports.envelope import verify_revision_id
from ai_stp_passports.versions import ComponentVersionPassport

CURRENT: Final[str] = "current"
MAX_INVOKE_OUTPUT: Final[int] = 65_536
MAX_POINTER_BYTES: Final[int] = 32_768
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
    _require_component_id(stable_id)
    _passport, recorded, payload = _load(connection, stable_id, version)
    root = _program_root(recorded.stable_id, create=True)
    target = root / recorded.version
    _directory(target, create=True)
    executable = target / "program"
    _plain_program(executable)
    try:
        # Never truncate an existing inode or follow a pre-existing program link.
        write_private_bytes(executable, payload)
        if os.name != "nt":
            executable.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        pointer = root / CURRENT
        _replace_pointer(pointer, executable)
    except OSError as error:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the cli program could not be installed",
            details={"id": recorded.stable_id, "error": type(error).__name__},
        ) from error
    return CliProgram(
        stable_id=recorded.stable_id,
        version=recorded.version,
        operation="install",
        state="present",
        prefix=str(root.parent),
        executable=str(pointer),
    )


def invoke(
    connection: sqlite3.Connection,
    *,
    stable_id: str,
    version: str | None,
    arguments: tuple[str, ...],
) -> CliProgram:
    """Run the exact installed version, or the validated current pointer."""
    _require_component_id(stable_id)
    installed = _installed(connection, stable_id, version)
    if installed is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "that cli program is not installed",
            details={"id": stable_id},
            next_actions=[f"component program install --id {stable_id} --json"],
        )
    recorded, executable = installed
    try:
        finished = subprocess.run(
            _argv(executable, arguments),
            capture_output=True,
            text=True,
            timeout=INVOKE_TIMEOUT_SECONDS,
            check=False,
            env={"PATH": "", "HOME": os.environ.get("HOME", "")},
        )
    except (OSError, UnicodeError, subprocess.SubprocessError) as error:
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
    """Report the version and bytes actually selected by the installed pointer."""
    _require_component_id(stable_id)
    installed = _installed(connection, stable_id, None)
    return CliProgram(
        stable_id=stable_id,
        version=installed[0].version if installed is not None else "0.0",
        operation="status",
        state="present" if installed is not None else "never_installed",
        prefix=str(prefix()),
        executable=str(prefix() / stable_id / CURRENT) if installed is not None else "",
    )


def remove(*, stable_id: str) -> CliProgram:
    """Remove only what this module installed for this component."""
    _require_component_id(stable_id)
    base = prefix().expanduser().absolute()
    _directory(base)
    root = base.resolve() / stable_id
    existed = root.exists() or root.is_symlink() or root.is_junction()
    try:
        if root.is_symlink() or root.is_file():
            root.unlink()
        elif root.is_junction():
            root.rmdir()
        elif root.is_dir():
            # Use the standard library's descriptor-based POSIX traversal and
            # Windows junction handling rather than following a hand-built walk.
            shutil.rmtree(root)
        elif existed:
            raise CliFailure("AI_STP_CONFLICT", "the cli program root is not a directory")
    except OSError as error:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the cli program could not be removed",
            details={"id": stable_id, "error": type(error).__name__},
        ) from error
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
    try:
        passport = ComponentVersionPassport.model_validate(stored.envelope.model_dump(mode="json"))
    except ValidationError as error:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the recorded cli passport is invalid",
            details={"id": stable_id},
        ) from error
    if (
        passport.stable_id != stable_id
        or passport.version != recorded.version
        or not verify_revision_id(passport)
        or cache.digest_of(cast(JsonValue, passport.model_dump(mode="json")))
        != recorded.passport_digest
    ):
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the recorded cli passport does not match its immutable identity",
            details={"id": stable_id, "version": recorded.version},
        )
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
            members = [member for member in archive.infolist() if not member.is_dir()]
            if len(members) != 1 or stat.S_IFMT(members[0].external_attr >> 16) not in (
                0,
                stat.S_IFREG,
            ):
                raise CliFailure(
                    "AI_STP_CONFLICT",
                    "the cli archive must contain exactly one regular program",
                )
            if members[0].file_size > content.MAX_CONTENT_BYTES:
                raise CliFailure("AI_STP_CONFLICT", "the expanded cli program is too large")
            with archive.open(members[0]) as stream:
                program = stream.read(content.MAX_CONTENT_BYTES + 1)
            if len(program) > content.MAX_CONTENT_BYTES:
                raise CliFailure("AI_STP_CONFLICT", "the expanded cli program is too large")
            return program
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as error:
        raise CliFailure("AI_STP_CONFLICT", "the cli archive cannot be read") from error


def _require_component_id(stable_id: str) -> None:
    if not is_valid_id(stable_id, "component"):
        raise CliFailure("AI_STP_VALIDATION_ERROR", "a valid component id is required")


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
    with executable.open("rb") as stream:
        raw = stream.read(128)
    if raw.startswith(b"#!"):
        line = raw.split(b"\n", 1)[0][2:].decode("utf-8").strip()
        interpreter = line.split()
        if not interpreter or not Path(interpreter[0]).is_absolute():
            raise CliFailure(
                "AI_STP_CONFLICT", "the cli interpreter must be an absolute path"
            )
        return [*interpreter, str(executable), *arguments]
    return [str(executable), *arguments]


def _directory(path: Path, *, create: bool = False) -> None:
    if path.is_symlink() or path.is_junction() or (path.exists() and not path.is_dir()):
        raise CliFailure("AI_STP_CONFLICT", "the cli prefix contains a linked or invalid directory")
    if create:
        ensure_directory(path)


def _program_root(stable_id: str, *, create: bool = False) -> Path:
    base = prefix().expanduser().absolute()
    _directory(base, create=create)
    root = base.resolve() / stable_id
    _directory(root, create=create)
    return root


def _plain_program(path: Path) -> None:
    if path.is_symlink() or path.is_junction() or (path.exists() and not path.is_file()):
        raise CliFailure("AI_STP_CONFLICT", "the installed cli program is not a regular file")


def _installed(
    connection: sqlite3.Connection, stable_id: str, version: str | None
) -> tuple[versions.Recorded, Path] | None:
    root = _program_root(stable_id)
    if version is None:
        selected = _resolved(root / CURRENT)
        if selected is None:
            return None
        try:
            relative = selected.relative_to(root)
            if len(relative.parts) != 2 or relative.name != "program":
                raise ValueError("the pointer is not a version/program coordinate")
            version = relative.parts[0]
            parse_version(version)
        except ValueError as error:
            raise CliFailure(
                "AI_STP_CONFLICT",
                "the installed cli pointer is outside its component version prefix",
                details={"id": stable_id},
            ) from error
    _passport, recorded, payload = _load(connection, stable_id, version)
    directory = root / recorded.version
    _directory(directory)
    executable = directory / "program"
    _plain_program(executable)
    if not executable.exists():
        return None
    with executable.open("rb") as stream:
        installed_bytes = stream.read(len(payload) + 1)
    if installed_bytes != payload or not is_executable_file(executable):
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the installed cli bytes or executable mode differ from the recorded artifact",
            details={"id": stable_id, "version": recorded.version},
        )
    return recorded, executable


def _resolved(pointer: Path) -> Path | None:
    if pointer.is_symlink():
        target = Path(os.readlink(pointer))
        if not target.is_absolute():
            target = pointer.parent / target
        return target.absolute()
    if not pointer.exists():
        return None
    if os.name != "nt" or not pointer.is_file():
        raise CliFailure("AI_STP_CONFLICT", "the installed cli pointer is invalid")
    with pointer.open("rb") as stream:
        payload = stream.read(MAX_POINTER_BYTES + 1)
    try:
        text = payload.decode("utf-8")
    except UnicodeError as error:
        raise CliFailure("AI_STP_CONFLICT", "the installed cli pointer is invalid") from error
    if len(payload) > MAX_POINTER_BYTES or not text.startswith("path:"):
        raise CliFailure("AI_STP_CONFLICT", "the installed cli pointer is invalid")
    target = Path(text.removeprefix("path:"))
    if not target.is_absolute():
        raise CliFailure("AI_STP_CONFLICT", "the installed cli pointer is invalid")
    return target.absolute()


def _replace_pointer(pointer: Path, target: Path) -> None:
    # Concurrent activations must not unlink one another's staging name.
    if os.name == "nt":
        write_private(pointer, f"path:{target}")
    else:
        with tempfile.TemporaryDirectory(prefix=f".{CURRENT}-", dir=pointer.parent) as room:
            staged = Path(room) / CURRENT
            staged.symlink_to(target)
            staged.replace(pointer)
