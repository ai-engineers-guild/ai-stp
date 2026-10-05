"""The worker ends with the signal that stopped it, after it has drained."""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from ai_stp_worker import __main__ as worker_main

pytestmark = pytest.mark.platform

type Registered = tuple[int, Callable[..., object], tuple[object, ...]]


class _Worker:
    def __init__(self) -> None:
        self.stopped = False

    def request_stop(self) -> None:
        self.stopped = True


def test_a_stop_signal_is_recorded_and_re_raised_after_the_drain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2026-10-05: as PID 1 the worker logged `worker_stop` within two seconds
    and then sat in uninterruptible sleep, tearing the interpreter down over
    swapped-out pages, until dockerd killed it. Re-raising the stop signal with
    the default action ends the process at once, as uvicorn does for the API.
    """
    monkeypatch.setattr(worker_main, "_received", [])
    worker = _Worker()

    async def install() -> list[Registered]:
        registered: list[Registered] = []
        loop = asyncio.get_running_loop()

        def capture(sig: int, callback: Callable[..., object], *args: object) -> None:
            registered.append((sig, callback, args))

        monkeypatch.setattr(loop, "add_signal_handler", capture)
        worker_main._install_signals(worker)  # pyright: ignore[reportArgumentType, reportPrivateUsage]
        return registered

    registered = asyncio.run(install())
    assert [sig for sig, _callback, _args in registered] == [signal.SIGTERM, signal.SIGINT]
    _sig, callback, args = registered[0]
    callback(*args)
    assert worker.stopped

    raised: list[int] = []
    restored: list[tuple[int, object]] = []

    def restore(sig: int, handler: object) -> None:
        restored.append((sig, handler))

    monkeypatch.setattr(signal, "raise_signal", raised.append)
    monkeypatch.setattr(signal, "signal", restore)
    worker_main._end_with_received_signal()  # pyright: ignore[reportPrivateUsage]
    assert raised == [signal.SIGTERM]
    assert restored == [(signal.SIGTERM, signal.SIG_DFL)]


def test_a_worker_that_was_not_signalled_exits_normally(monkeypatch: pytest.MonkeyPatch) -> None:
    raised: list[int] = []
    monkeypatch.setattr(worker_main, "_received", [])
    monkeypatch.setattr(signal, "raise_signal", raised.append)
    worker_main._end_with_received_signal()  # pyright: ignore[reportPrivateUsage]
    assert raised == []


def test_the_python_services_do_not_run_as_pid_1() -> None:
    """The re-raised signal only ends the process when it is not PID 1."""
    compose = yaml.safe_load(Path("deploy/compose.prod.yml").read_text(encoding="utf-8"))
    for name in ("api", "worker"):
        assert compose["services"][name].get("init") is True, name
