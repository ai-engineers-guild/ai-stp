from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_worker import runner

pytestmark = pytest.mark.platform


class _Session:
    def __init__(self, jobs: dict[int, object]) -> None:
        self.jobs = jobs

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    def begin(self) -> _Session:
        return self

    async def get(self, model: object, job_id: int) -> object | None:
        del model
        return self.jobs.get(job_id)


class _SessionMaker:
    def __init__(self, jobs: dict[int, object]) -> None:
        self.jobs = jobs

    def __call__(self) -> _Session:
        return _Session(self.jobs)


def _worker(jobs: dict[int, object]) -> runner.Worker:
    sessionmaker = cast(async_sessionmaker[AsyncSession], _SessionMaker(jobs))
    return runner.Worker(
        sessionmaker,
        worker_id="worker-test",
        batch_size=2,
        poll_interval_seconds=0.001,
    )


@pytest.mark.asyncio
async def test_worker_processes_success_missing_unknown_and_failed_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jobs: dict[int, object] = {
        1: SimpleNamespace(id=1, job_type="success", payload={"id": 1}),
        2: SimpleNamespace(id=2, job_type="unknown", payload={}),
        3: SimpleNamespace(id=3, job_type="failure", payload={}),
    }
    claimed: list[object] = [jobs[1], jobs[2], jobs[3]]
    events: list[tuple[str, object]] = []

    async def claim(session: object, *, worker_id: str, batch: int) -> list[object]:
        del session
        assert worker_id == "worker-test" and batch == 2
        return claimed

    async def success(session: object, payload: object) -> None:
        del session
        events.append(("handled", payload))

    async def failure(session: object, payload: object) -> None:
        del session, payload
        raise ValueError("expected")

    async def fail(session: object, job: object, *, error: str) -> None:
        del session
        events.append((error, job))

    async def succeeded(session: object, job: object) -> None:
        del session
        events.append(("succeeded", job))

    monkeypatch.setattr(runner, "claim", claim)

    def resolve(kind: str) -> object:
        return success if kind == "success" else failure if kind == "failure" else None

    monkeypatch.setattr(runner, "resolve", resolve)
    monkeypatch.setattr(runner, "fail", fail)
    monkeypatch.setattr(runner, "mark_succeeded", succeeded)

    worker = _worker(jobs)
    assert await worker.run_once() == 3
    await worker._process(999)  # pyright: ignore[reportPrivateUsage]

    assert ("handled", {"id": 1}) in events
    assert any(event[0] == "succeeded" for event in events)
    assert any(event[0] == "unregistered job type" for event in events)
    assert any(event[0] == "ValueError" for event in events)


@pytest.mark.asyncio
async def test_worker_stop_wait_and_drain_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = _worker({})

    async def requeue(session: object, *, worker_id: str) -> int:
        del session
        assert worker_id == "worker-test"
        return 2

    monkeypatch.setattr(runner, "requeue_locked", requeue)
    assert await worker._drain() == 2  # pyright: ignore[reportPrivateUsage]
    await worker._wait_or_stop(0)  # pyright: ignore[reportPrivateUsage]
    worker.request_stop()
    await worker._wait_or_stop(1)  # pyright: ignore[reportPrivateUsage]
    await worker.run()


@pytest.mark.asyncio
async def test_worker_run_polls_once_then_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = _worker({})
    calls = 0

    async def run_once() -> int:
        nonlocal calls
        calls += 1
        worker.request_stop()
        return 0

    async def drain() -> int:
        return 0

    monkeypatch.setattr(worker, "run_once", run_once)
    monkeypatch.setattr(worker, "_drain", drain)

    await worker.run()

    assert calls == 1
