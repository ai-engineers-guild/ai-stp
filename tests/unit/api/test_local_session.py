"""Bounds and reaping for the loopback local-session process table."""

from __future__ import annotations

import asyncio
from asyncio.subprocess import Process
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import Request
from starlette.types import Scope

from ai_stp_api import local_session
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.local_session import (
    _MAX_LOCAL_PROCESSES,  # pyright: ignore[reportPrivateUsage]
    LocalSession,
    _LocalProcess,  # pyright: ignore[reportPrivateUsage]
)


class _FakeProcess:
    def __init__(self, returncode: int | None) -> None:
        self.returncode = returncode
        self.stdin = None
        self.waited = False

    async def wait(self) -> int:
        self.waited = True
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9


def _request(processes: dict[str, _LocalProcess]) -> Request:
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/local/session",
        "raw_path": b"/v1/local/session",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
        "app": SimpleNamespace(state=SimpleNamespace(local_processes=processes)),
    }
    return Request(scope)


def _entry(*, returncode: int | None, expired: bool = False) -> _LocalProcess:
    process = cast(Process, _FakeProcess(returncode))
    expires = datetime.now(UTC) + (timedelta(minutes=-1) if expired else timedelta(hours=1))
    return _LocalProcess(
        process=process,
        session=LocalSession("tok", "csrf", expires, "http://127.0.0.1:1"),
    )


async def test_start_refuses_beyond_the_process_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processes = {f"token-{i}": _entry(returncode=None) for i in range(_MAX_LOCAL_PROCESSES)}
    spawned = False

    async def _fork(*args: object, **kwargs: object) -> object:
        nonlocal spawned
        spawned = True
        raise AssertionError("must not fork past the cap")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fork)

    with pytest.raises(ApiError) as exc:
        await local_session.start(_request(processes))
    assert exc.value.category is ErrorCategory.RATE_LIMITED
    assert spawned is False
    assert len(processes) == _MAX_LOCAL_PROCESSES


async def test_start_reaps_dead_and_expired_entries_before_checking_the_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dead = _entry(returncode=0)
    expired_live = _entry(returncode=None, expired=True)
    processes = {
        "dead": dead,
        "expired-live": expired_live,
        "expired-dead": _entry(returncode=0, expired=True),
        "live": _entry(returncode=None),
    }
    spawned = asyncio.Event()

    async def _fork(*args: object, **kwargs: object) -> object:
        spawned.set()
        raise RuntimeError("sentinel: fork attempted after reaping")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fork)

    with pytest.raises(RuntimeError, match="sentinel"):
        await local_session.start(_request(processes))
    assert spawned.is_set()
    # Reaped: dead pid entry, expired entries (the live one was asked to wait).
    # Survivor: the one unexpired running session.
    assert set(processes) == {"live"}
    assert cast(_FakeProcess, expired_live.process).waited is True


async def test_stop_keeps_the_session_when_csrf_fails() -> None:
    entry = _entry(returncode=None)
    processes = {"tok": entry}
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "DELETE",
        "scheme": "http",
        "path": "/v1/local/session",
        "raw_path": b"/v1/local/session",
        "query_string": b"",
        "headers": [
            (b"x-ai-stp-local-session", b"tok"),
            (b"x-ai-stp-local-csrf", b"wrong"),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
        "app": SimpleNamespace(state=SimpleNamespace(local_processes=processes)),
    }
    with pytest.raises(ApiError) as exc:
        await local_session.stop(Request(scope))
    assert exc.value.category is ErrorCategory.AUTH_REQUIRED
    # A failed CSRF probe must not kill the live session it names.
    assert processes.get("tok") is entry
    assert cast(_FakeProcess, entry.process).returncode is None
