"""Where local state lives, and how a file holding a secret is written.

Layout follows the XDG base directories, which `cli-config.md` already fixes for
the configuration file and the local registry. Nothing here needs `sudo`
(`SPEC-011` REQ-1101).

The write primitive exists because getting this wrong is the normal outcome. A
real CLI shipped `0600` applied **only at file creation**, so rewriting a file
whose mode had been relaxed put a secret into a world-readable file
(`openai/codex#14704`, cited by `ADR-0058`). The fix is not to remember to
`chmod`: it is to never open an existing file for writing. Every write creates a
fresh file that is `0600` from its first byte and then replaces the target
atomically, so the target is never in a partially written or wrongly readable
state.
"""

import os
import stat
import tempfile
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Final

from ai_stp_cli.errors import CliFailure

#: Owner-only. Directories additionally need execute to be traversable.
FILE_MODE: Final[int] = 0o600
DIRECTORY_MODE: Final[int] = 0o700

#: POSIX modes are not a meaningful access control on Windows, where the ACL is.
#: Asserting them there would fail on a correctly protected file, so the checks
#: are skipped rather than faked.
POSIX: Final[bool] = os.name != "nt"

APPLICATION_DIRECTORY: Final[str] = "ai-stp"


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def data_dir() -> Path:
    """The one directory this installation keeps local state in."""
    return data_home() / APPLICATION_DIRECTORY


def secrets_dir() -> Path:
    """Where the file tier keeps material the OS store would otherwise hold."""
    return data_dir() / "secrets"


def device_file() -> Path:
    """Public device metadata: identifier, public key, state. No secret here."""
    return data_dir() / "device.json"


def ensure_directory(path: Path) -> Path:
    """Create a directory owned by this user and no one else.

    The mode is applied after creation as well as during it: `mkdir` subtracts
    the process umask, so a directory created under a permissive umask would
    otherwise keep group and world bits.
    """
    path.mkdir(parents=True, exist_ok=True, mode=DIRECTORY_MODE)
    if POSIX:
        path.chmod(DIRECTORY_MODE)
    return path


def write_private(path: Path, content: str) -> None:
    """Write `content` so that only the owner can ever have read it.

    Never opens `path` itself. `mkstemp` creates the temporary file with `0600`
    before a byte is written, and `Path.replace` installs it atomically inside
    the same directory, so no reader observes a partial file and no window
    exists in which the bytes sit under a wider mode.
    """
    write_private_bytes(path, content.encode("utf-8"))


def write_private_bytes(path: Path, content: bytes) -> None:
    """Atomically install owner-only bytes without exposing a partial target."""
    ensure_directory(path.parent)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    scratch = Path(temporary)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if POSIX:
            scratch.chmod(FILE_MODE)
        scratch.replace(path)
    except BaseException:
        scratch.unlink(missing_ok=True)
        raise


def read_private(path: Path) -> str:
    """Read a file that must not be readable by anyone but its owner.

    A file whose mode has widened is refused rather than used. Reading it would
    mean continuing to treat material as private after the operating system
    stopped agreeing, and the caller cannot tell from the value alone.
    """
    if POSIX:
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "a private file is readable by more than its owner",
                details={
                    "path": redact_home(path),
                    "mode": f"{mode:04o}",
                    "expected": f"{FILE_MODE:04o}",
                },
                next_actions=["doctor --json"],
            )
    return path.read_text(encoding="utf-8")


def _forward_slashes(text: str) -> str:
    """Render separators as ``/`` only where the separator is a backslash.

    On Windows this keeps machine JSON and tests stable. On POSIX a backslash is
    a legal character in a file name, so rewriting it would report a path that
    is not the one that exists.
    """
    return text.replace("\\", "/") if os.sep == "\\" else text


def redact_home(path: Path | str) -> str:
    """Render a path with the home directory as `~`.

    `#72` and `#73` both require that output carry no home-path material. The
    useful part of `/home/someone/.local/share/ai-stp/registry.sqlite` is
    everything after the account name, and the account name is what a passport,
    a log or an agent transcript should not be carrying. A path outside the home
    directory is shown unchanged: shortening it would hide, not redact.

    Separators are rendered as ``/`` so machine JSON and tests stay stable on
    Windows, where ``str(Path)`` uses backslashes. Only where the separator
    actually is a backslash: on POSIX a backslash is a legal character in a file
    name, and rewriting it would report a different path than the one that
    exists.
    """
    text = str(path)
    try:
        home = str(Path.home())
    except (OSError, RuntimeError):  # pragma: no cover - home is always resolvable here
        return _forward_slashes(text)
    if text == home or text.rstrip("\\/") == home.rstrip("\\/"):
        return "~"
    if text.startswith(home + os.sep) or text.startswith(home + "/"):
        rest = text[len(home) :].lstrip("\\/")
        return "~/" + _forward_slashes(rest)
    return _forward_slashes(text)


def is_private(path: Path) -> bool:
    """Whether `path` exists with owner-only permissions."""
    if not path.exists():
        return False
    if not POSIX:  # pragma: no cover - asserted on the POSIX legs of the matrix
        return True
    return not stat.S_IMODE(path.stat().st_mode) & 0o077


#: What Windows treats as directly runnable, lowercased, when `PATHEXT` is unset.
#: The provider artifacts this CLI fetches are `.exe` on both Windows targets
#: (`attested_bind.PLATFORM_TARGETS`), so `.exe` is the member that matters; the
#: rest are here because the shell would run them and refusing them would be a
#: statement about this program rather than about the platform.
DEFAULT_PATHEXT: Final[str] = ".com;.exe;.bat;.cmd"


def is_executable_file(path: Path) -> bool:
    """Whether `path` is a file this user could run, on this operating system.

    `os.access(path, os.X_OK)` is the POSIX answer and **not** a portable one:
    Windows has no execute permission bit, so the call degrades to an existence
    test and returns `True` for `notes.txt`, a `.dll`, or anything else that is
    merely there. Every caller here is choosing or validating a provider binary,
    where "returns True for every file" is not a weaker check but the wrong
    question — discovery would adopt the first file in the directory.

    What makes a file runnable on Windows is its extension being in `PATHEXT`,
    which is what the shell itself consults, so that is what is asked.
    """
    if not path.is_file():
        return False
    if POSIX:
        return os.access(path, os.X_OK)
    suffixes = os.environ.get("PATHEXT") or DEFAULT_PATHEXT
    runnable = {item.strip().lower() for item in suffixes.split(";") if item.strip()}
    return path.suffix.lower() in runnable


#: How long a process waits for another one's first-run work before giving up.
#: Bootstrap writes a few small files, so a wait this long means something is
#: wrong rather than merely busy.
LOCK_TIMEOUT_SECONDS: Final[float] = 10.0

#: Nesting depth of `bootstrap_lock` on the current thread. See its docstring:
#: without this the bootstrap path waits for a lock it is already holding.
_reentry = threading.local()


@contextmanager
def bootstrap_lock(timeout: float = LOCK_TIMEOUT_SECONDS) -> Generator[None]:
    """Serialise first-run creation across processes.

    An agent runs several `ai-stp` calls, and nothing stops two of them from
    reaching a clean home at once. Creating the owner record, the device record
    and the device key is a read-then-write across three files, so two processes
    could each see nothing, each create, and leave halves of two identities
    mixed together — a public record from one and a private key from the other,
    which cannot sign.

    An advisory `flock` rather than a lock file guarded by `O_EXCL`: the kernel
    drops it when the holder dies, so a process killed mid-bootstrap leaves
    nothing to clean up and no staleness heuristic to get wrong.

    The lock file is never read and carries no state; it exists only to be
    locked. On a platform without `fcntl` this yields without locking, which is
    the behaviour that already applied everywhere.

    Re-entrant, because the bootstrap paths nest: creating the device passport
    takes the lock and then mints the owner, which takes it again. `flock` is
    held per open file description, so a second `open` in the same process is a
    different holder and waits for the first — the process deadlocks against
    itself and, having no one to wait for, times out. Re-entering is tracked per
    thread rather than per process so a threaded caller cannot borrow another
    thread's lock.
    """
    depth = getattr(_reentry, "depth", 0)
    if depth:
        _reentry.depth = depth + 1
        try:
            yield
        finally:
            _reentry.depth -= 1
        return

    if not POSIX:  # pragma: no cover - exercised on Windows only
        import msvcrt

        ensure_directory(data_dir())
        path = data_dir() / ".bootstrap.lock"
        with path.open("a+b") as stream:
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            deadline = time.monotonic() + timeout
            while True:
                try:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise CliFailure(
                            "AI_STP_PRECONDITION_FAILED",
                            "another ai-stp process is still setting this installation up",
                            retryable=True,
                            next_actions=["doctor --json"],
                        ) from None
                    time.sleep(0.05)
            _reentry.depth = 1
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                _reentry.depth = 0
        return
    import fcntl

    ensure_directory(data_dir())
    path = data_dir() / ".bootstrap.lock"
    handle = os.open(path, os.O_CREAT | os.O_RDWR, FILE_MODE)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise CliFailure(
                        "AI_STP_PRECONDITION_FAILED",
                        "another ai-stp process is still setting this installation up",
                        retryable=True,
                        next_actions=["doctor --json"],
                    ) from None
                time.sleep(0.05)
        _reentry.depth = 1
        try:
            yield
        finally:
            _reentry.depth = 0
            fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        os.close(handle)
