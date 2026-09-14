"""Shared install/invoke/remove for catalog `cli` components.

A `cli` component is one executable, not seven copies under harness homes.
The prefix is the CLI data directory, never a provider target.
"""

from __future__ import annotations

import io
import os
import shutil
import signal
import sqlite3
import stat
import subprocess
import tempfile
import threading
import zipfile
from pathlib import Path
from typing import IO, Final

from pydantic import ValidationError

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import content, revisions, versions
from ai_stp_cli.paths import (
    data_dir,
    ensure_directory,
    is_executable_file,
    write_private,
    write_private_bytes,
)
from ai_stp_contracts.machine_help import CliProgram
from ai_stp_foundation.ids import is_valid_id
from ai_stp_foundation.versioning import parse_version
from ai_stp_passports.envelope import verify_revision_id
from ai_stp_passports.versions import ComponentVersionPassport

CURRENT: Final[str] = "current"
MAX_INVOKE_OUTPUT: Final[int] = 65_536
MAX_POINTER_BYTES: Final[int] = 32_768
INVOKE_TIMEOUT_SECONDS: Final[float] = 30.0

#: How long to wait for a reader after the child is gone. A surviving grandchild
#: can hold the write end open with nothing left to send, and this command
#: answers its caller rather than waiting on that.
_DRAIN_GRACE_SECONDS: Final[float] = 2.0

#: How much is read from a child pipe at a time. Small enough that a program
#: writing without stopping is drained rather than buffered, large enough that
#: an ordinary program is read in one or two calls.
_READ_CHUNK: Final[int] = 8_192


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
        prefix=str(prefix()),
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
    passport, recorded, executable = installed
    try:
        code, output = _bounded_run(
            _argv(executable, arguments),
            env=_environment(passport),
            timeout=INVOKE_TIMEOUT_SECONDS,
        )
    except (OSError, UnicodeError, subprocess.SubprocessError) as error:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the cli program could not be invoked",
            details={"id": recorded.stable_id, "error": type(error).__name__},
        ) from error
    return CliProgram(
        stable_id=recorded.stable_id,
        version=recorded.version,
        operation="invoke",
        state="invoked",
        prefix=str(prefix()),
        executable=str(executable),
        exit_code=code,
        output=output,
    )


def _environment(passport: ComponentVersionPassport) -> dict[str, str]:
    """Exactly the environment this program declared, and nothing else.

    Readiness and execution used to describe two different processes:
    `environment inspect` reported a declared variable as satisfied when it was
    present *here*, while the program itself was started with `PATH` and `HOME`
    alone, so a declared variable could never reach it. Whichever of the two a
    caller believed, one of them was wrong.

    The passport is the boundary. A variable the version declares is forwarded
    when this process holds it; everything else stays behind, so an ambient
    secret in the caller's environment is not handed to a catalog program that
    never asked for it. `PATH` is empty because the executable is chosen by
    exact installed path and must never be resolved through a search path, and
    `HOME` is passed because a program without one writes into whatever it
    finds.
    """
    held = {"PATH": "", "HOME": os.environ.get("HOME", "")}
    missing: list[str] = []
    for requirement in passport.required_env:
        value = os.environ.get(requirement.name)
        if value is None:
            missing.append(requirement.name)
            continue
        held[requirement.name] = value
    if missing:
        # Named, never valued: `SPEC-011` REQ-1108 keeps values out of output,
        # and the name is what the caller has to act on anyway.
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this program declares environment variables this process does not hold",
            details={"id": passport.stable_id, "variables": ", ".join(sorted(missing))},
            next_actions=["environment inspect ..."],
        )
    return held


def _bounded_run(argv: list[str], *, env: dict[str, str], timeout: float) -> tuple[int, str]:
    """Run a child program, keeping at most `MAX_INVOKE_OUTPUT` of its output.

    `subprocess.run(capture_output=True)` keeps everything the child writes and
    the slice happens after it exits, so a program that prints a gigabyte puts a
    gigabyte in this process first. The limit has to bind while reading. The
    pipes are still drained to the end — a reader that stops reading blocks the
    child on a full pipe, which turns a noisy program into a hang — but the
    bytes past the limit are dropped rather than accumulated.

    A child that outlives the timeout is killed with whatever it started, not
    only in its own process: a program that forked leaves its children holding
    the pipe, and waiting on that is the same hang by another route.
    """
    kept: list[list[bytes]] = [[], []]
    sizes = [0, 0]

    def drain(stream: IO[bytes], index: int) -> None:
        while True:
            chunk = stream.read(_READ_CHUNK)
            if not chunk:
                return
            room = MAX_INVOKE_OUTPUT - sizes[index]
            if room > 0:
                kept[index].append(chunk[:room])
                sizes[index] += min(room, len(chunk))

    # A new session on POSIX so the timeout can end the whole group; Windows has
    # no equivalent here and `kill()` ends the process it started.
    child = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        start_new_session=os.name != "nt",
    )
    readers = [
        threading.Thread(target=drain, args=(stream, index), daemon=True)
        for index, stream in enumerate((child.stdout, child.stderr))
        if stream is not None
    ]
    for reader in readers:
        reader.start()
    try:
        code = child.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _end(child)
        code = child.wait()
        raise
    finally:
        # Bounded, and only closed once nobody is reading it. A grandchild that
        # survived still holds the write end, so a reader can be blocked with no
        # more bytes coming; that thread is a daemon and must not be waited on,
        # and closing a pipe underneath it would raise there instead.
        for index, reader in enumerate(readers):
            reader.join(timeout=_DRAIN_GRACE_SECONDS)
            if reader.is_alive():
                continue
            stream = (child.stdout, child.stderr)[index]
            if stream is not None:
                stream.close()
    combined = b"".join(kept[0]) + b"".join(kept[1])
    return code, combined.decode("utf-8", errors="replace")[:MAX_INVOKE_OUTPUT]


def _end(child: subprocess.Popen[bytes]) -> None:
    """Kill the child and anything it started, as far as this platform allows."""
    if os.name != "nt":
        try:
            os.killpg(os.getpgid(child.pid), signal.SIGKILL)
            return
        except (OSError, AttributeError):
            pass
    child.kill()


def status(
    connection: sqlite3.Connection, *, stable_id: str, version: str | None = None
) -> CliProgram:
    """Report the version and bytes actually selected by the installed pointer."""
    _require_component_id(stable_id)
    installed = _installed(connection, stable_id, version)
    return CliProgram(
        stable_id=stable_id,
        version=installed[1].version if installed is not None else "0.0",
        operation="status",
        state="present" if installed is not None else "never_installed",
        prefix=str(prefix()),
        executable=str(installed[2]) if installed is not None else "",
    )


def remove(*, stable_id: str) -> CliProgram:
    """Remove only what this module installed for this component."""
    _require_component_id(stable_id)
    base = prefix().expanduser().absolute()
    if base.exists():
        _directory(base)
    root = (base.resolve() if base.exists() else base) / stable_id
    existed = root.exists() or root.is_symlink() or _is_junction(root)
    try:
        if root.is_symlink() or root.is_file():
            root.unlink()
        elif _is_junction(root):
            root.rmdir()
        elif root.is_dir():
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
    if passport.stable_id != recorded.stable_id or passport.version != recorded.version:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the recorded cli passport does not match its immutable identity",
            details={"id": stable_id, "version": recorded.version},
        )
    if not verify_revision_id(stored.envelope):
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
    extracted = _unzip_first_file(payload) if payload.startswith(b"PK") else payload
    if extracted.startswith(b"PK"):
        return _unzip_only_regular_file(extracted)
    return extracted


def _unzip_first_file(payload: bytes) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = [name for name in archive.namelist() if not name.endswith("/")]
            if not names:
                return b""
            return _read_zip_member(archive, archive.getinfo(names[0]))
    except CliFailure:
        raise
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError, KeyError) as error:
        raise CliFailure("AI_STP_CONFLICT", "the cli archive cannot be read") from error


def _unzip_only_regular_file(payload: bytes) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            kind = stat.S_IFMT(members[0].external_attr >> 16) if members else 0
            if len(members) != 1 or kind not in (0, stat.S_IFREG):
                raise CliFailure(
                    "AI_STP_CONFLICT",
                    "the cli archive must contain exactly one regular program",
                )
            return _read_zip_member(archive, members[0])
    except CliFailure:
        raise
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError) as error:
        raise CliFailure("AI_STP_CONFLICT", "the cli archive cannot be read") from error


def _read_zip_member(archive: zipfile.ZipFile, member: zipfile.ZipInfo) -> bytes:
    if member.file_size > content.MAX_CONTENT_BYTES:
        raise CliFailure("AI_STP_CONFLICT", "the expanded cli program is too large")
    with archive.open(member) as stream:
        program = stream.read(content.MAX_CONTENT_BYTES + 1)
    if len(program) > content.MAX_CONTENT_BYTES:
        raise CliFailure("AI_STP_CONFLICT", "the expanded cli program is too large")
    return program


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
            raise CliFailure("AI_STP_CONFLICT", "the cli interpreter must be an absolute path")
        if Path(interpreter[0]).name == "env":
            # `#!/usr/bin/env python3` is an absolute path to a resolver, and
            # what it resolves is a `PATH` lookup this program deliberately does
            # not get. It would start, fail to find its runtime, and report
            # whatever that failure looked like; saying so here is the precise
            # answer.
            raise CliFailure(
                "AI_STP_CONFLICT",
                "the cli interpreter must name a runtime, not a PATH resolver",
                details={"interpreter": " ".join(interpreter)},
            )
        return [*interpreter, str(executable), *arguments]
    return [str(executable), *arguments]


def _is_junction(path: Path) -> bool:
    checker = getattr(path, "is_junction", None)
    return bool(checker()) if callable(checker) else False


def _directory(path: Path, *, create: bool = False) -> None:
    if path.is_symlink() or _is_junction(path) or (path.exists() and not path.is_dir()):
        raise CliFailure("AI_STP_CONFLICT", "the cli prefix contains a linked or invalid directory")
    if create:
        ensure_directory(path)


def _program_root(stable_id: str, *, create: bool = False) -> Path:
    base = prefix().expanduser().absolute()
    _directory(base, create=create)
    root = (base.resolve() if base.exists() else base) / stable_id
    _directory(root, create=create)
    return root


def _plain_program(path: Path) -> None:
    if path.is_symlink() or _is_junction(path) or (path.exists() and not path.is_file()):
        raise CliFailure("AI_STP_CONFLICT", "the installed cli program is not a regular file")


def _installed(
    connection: sqlite3.Connection, stable_id: str, version: str | None
) -> tuple[ComponentVersionPassport, versions.Recorded, Path] | None:
    root = _program_root(stable_id)
    selected_version = version
    if selected_version is None:
        selected = _resolved(root / CURRENT)
        if selected is None:
            return None
        try:
            relative = selected.relative_to(root)
            if len(relative.parts) != 2 or relative.name != "program":
                raise ValueError("the pointer is not a version/program coordinate")
            selected_version = relative.parts[0]
            parse_version(selected_version)
        except ValueError as error:
            raise CliFailure(
                "AI_STP_CONFLICT",
                "the installed cli pointer is outside its component version prefix",
                details={"id": stable_id},
            ) from error
    passport, recorded, payload = _load(connection, stable_id, selected_version)
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
    return passport, recorded, executable


def _resolved(pointer: Path) -> Path | None:
    if pointer.is_symlink():
        target = pointer.readlink()
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
    if os.name == "nt":
        write_private(pointer, f"path:{target}")
        return
    with tempfile.TemporaryDirectory(prefix=f".{CURRENT}-", dir=pointer.parent) as room:
        staged = Path(room) / CURRENT
        staged.symlink_to(target)
        staged.replace(pointer)
