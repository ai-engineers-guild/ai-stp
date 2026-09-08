"""Owner-only updater cache, plans and journal. Separate from the registry."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Final, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.paths import FILE_MODE, POSIX, data_dir, ensure_directory, write_private
from ai_stp_foundation.canonical import JsonValue

LOCK_TIMEOUT_SECONDS: Final[float] = 5.0
CACHE_NAME: Final[str] = "check-cache.json"
JOURNAL_NAME: Final[str] = "journal.json"
_reentry = threading.local()
_thread_lock = threading.RLock()


def root() -> Path:
    identity = hashlib.sha256(str(Path(sys.prefix).resolve()).encode()).hexdigest()
    return data_dir() / "self-update" / "installations" / identity


def cache_path() -> Path:
    return root() / CACHE_NAME


def journal_path() -> Path:
    return root() / JOURNAL_NAME


def plans_dir() -> Path:
    return root() / "plans"


def stage_dir() -> Path:
    return root() / "stage"


def backup_dir() -> Path:
    return root() / "backups"


def lock_path() -> Path:
    return root() / ".lock"


def read_json(path: Path) -> dict[str, JsonValue] | None:
    if not path.is_file() or path.is_symlink():
        return None
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return cast(dict[str, JsonValue], payload)


def write_json(path: Path, payload: Mapping[str, JsonValue]) -> None:
    write_private(path, json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n")


@contextmanager
def exclusive_lock(timeout: float | None = None) -> Generator[None]:
    """One apply/recover/rollback at a time. Advisory; dropped if the holder dies."""
    budget = LOCK_TIMEOUT_SECONDS if timeout is None else timeout
    if not _thread_lock.acquire(timeout=budget):
        raise _busy()
    try:
        depth = getattr(_reentry, "depth", 0)
        if depth:
            _reentry.depth = depth + 1
            try:
                yield
            finally:
                _reentry.depth -= 1
            return
        ensure_directory(root())
        path = lock_path()
        if not POSIX:
            import msvcrt

            with path.open("a+b") as stream:
                stream.seek(0, os.SEEK_END)
                if stream.tell() == 0:
                    stream.write(b"0")
                    stream.flush()
                deadline = time.monotonic() + budget
                while True:
                    try:
                        stream.seek(0)
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise _busy() from None
                        time.sleep(0.05)
                _reentry.depth = 1
                try:
                    yield
                finally:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
                    _reentry.depth = 0
            return
        import fcntl

        handle = os.open(path, os.O_CREAT | os.O_RDWR, FILE_MODE)
        try:
            deadline = time.monotonic() + budget
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise _busy() from None
                    time.sleep(0.05)
            _reentry.depth = 1
            try:
                yield
            finally:
                _reentry.depth = 0
                fcntl.flock(handle, fcntl.LOCK_UN)  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
        finally:
            os.close(handle)
    finally:
        _thread_lock.release()


def _busy() -> CliFailure:
    return CliFailure(
        "AI_STP_CONFLICT",
        "another process is already applying a CLI update",
        retryable=True,
        next_actions=["update status --json"],
    )
