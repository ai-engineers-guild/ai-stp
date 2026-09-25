"""One live drain per task: an OS-held lock file is the liveness proof.

Revision CAS alone cannot tell a live executor from a dead one, so a caller
that observes the running revision could claim a fresh revision and drain
beside the first executor. The lease is a file lock held for the drain's
whole lifetime: the OS releases it when the owning process dies, so a free
lock on a running row means recovery is safe, and a held lock means a live
executor — never a second drain.

The file itself is never deleted: unlinking while another opener holds it
would let a later open lock a different inode and take two locks on one
name. One small file per task is the cost of a lock that survives crashes.
"""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Final

from ai_stp_cli.local.database import configured_path
from ai_stp_cli.paths import FILE_MODE, POSIX, ensure_directory

#: A liveness probe must not queue: a busy lease means an executor is draining.
_PROBE_RETRY_SECONDS: Final[float] = 0.0


def _path(task_id: str) -> Path:
    return configured_path().parent / "task-executors" / f"{task_id}.lock"


@dataclass
class ExecutorLease:
    """The open lock-file handle held by the task's single live executor."""

    _stream: IO[bytes] | None = None

    def release(self) -> None:
        stream, self._stream = self._stream, None
        if stream is None:
            return
        if not POSIX:
            import msvcrt

            with contextlib.suppress(OSError):
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
        else:
            import fcntl

            with contextlib.suppress(OSError):
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
        stream.close()

    def __enter__(self) -> ExecutorLease:
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


def try_acquire(task_id: str) -> ExecutorLease | None:
    """Acquire the task's executor lease without blocking.

    `None` means a live executor holds it — in this process or another. A
    crashed executor's lease is already released by the OS, so acquiring is
    also the recovery admission check.
    """
    path = _path(task_id)
    ensure_directory(path.parent)
    deadline = time.monotonic() + _PROBE_RETRY_SECONDS
    stream = path.open("a+b")
    try:
        if not POSIX:
            import msvcrt

            if path.stat().st_size == 0:
                stream.write(b"0")
                stream.flush()
            while True:
                try:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
                    return ExecutorLease(stream)
                except OSError:
                    if time.monotonic() >= deadline:
                        stream.close()
                        return None
                    time.sleep(0.05)
        import fcntl

        if path.exists():
            path.chmod(FILE_MODE)
        while True:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
                return ExecutorLease(stream)
            except OSError:
                if time.monotonic() >= deadline:
                    stream.close()
                    return None
                time.sleep(0.05)
    except BaseException:
        stream.close()
        raise


def held(task_id: str) -> bool:
    """True while a live executor holds the task's lease."""
    probe = try_acquire(task_id)
    if probe is None:
        return True
    probe.release()
    return False
