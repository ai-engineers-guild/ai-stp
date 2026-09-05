from __future__ import annotations

import asyncio
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

    async def scalars(self, statement: object) -> _ScalarResult:
        del statement
        return _ScalarResult()

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class _ScalarResult:
    def all(self) -> list[object]:
        return []


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
        drain_timeout_seconds=1.0,
        schedule_official_upstream=False,
    )


@pytest.mark.asyncio
async def test_worker_enqueues_official_sources_once_per_process_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessionmaker = cast(async_sessionmaker[AsyncSession], _SessionMaker({}))
    worker = runner.Worker(
        sessionmaker,
        worker_id="worker-test",
        batch_size=1,
        poll_interval_seconds=0.001,
    )
    calls = 0
    reconciles = 0

    async def enqueue(session: object) -> list[object]:
        nonlocal calls
        del session
        calls += 1
        return []

    async def reconcile(session: object) -> list[str]:
        nonlocal reconciles
        del session
        reconciles += 1
        return []

    async def reclaim(session: object, *, lease_timeout_seconds: float) -> int:
        del session, lease_timeout_seconds
        return 0

    async def claim(session: object, *, worker_id: str, batch: int) -> list[object]:
        del session, worker_id, batch
        return []

    monkeypatch.setattr(runner, "enqueue_daily", enqueue)
    monkeypatch.setattr(runner, "reconcile_delivery", reconcile)
    monkeypatch.setattr(runner, "requeue_stale", reclaim)
    monkeypatch.setattr(runner, "claim", claim)
    assert await worker.run_once() == 0
    assert await worker.run_once() == 0
    assert calls == 1
    assert reconciles == 1


@pytest.mark.asyncio
async def test_worker_processes_success_missing_unknown_and_failed_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jobs: dict[int, object] = {
        1: SimpleNamespace(id=1, job_type="success", payload={"id": 1}),
        2: SimpleNamespace(id=2, job_type="unknown", payload={}),
        3: SimpleNamespace(id=3, job_type="failure", payload={}),
    }
    claimed: list[object] = [jobs[1]]
    events: list[tuple[str, object]] = []

    async def claim(session: object, *, worker_id: str, batch: int) -> list[object]:
        del session
        assert worker_id == "worker-test" and batch == 1
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

    async def reclaim(session: object, *, lease_timeout_seconds: float) -> int:
        del session
        assert lease_timeout_seconds > 0
        return 0

    monkeypatch.setattr(runner, "requeue_stale", reclaim)

    def resolve(kind: str) -> object:
        return success if kind == "success" else failure if kind == "failure" else None

    monkeypatch.setattr(runner, "resolve", resolve)
    monkeypatch.setattr(runner, "fail", fail)
    monkeypatch.setattr(runner, "mark_succeeded", succeeded)

    worker = _worker(jobs)
    assert await worker.run_once() == 1
    await worker._process(2)  # pyright: ignore[reportPrivateUsage]
    await worker._process(3)  # pyright: ignore[reportPrivateUsage]
    await worker._process(999)  # pyright: ignore[reportPrivateUsage]

    assert ("handled", {"id": 1}) in events
    assert any(event[0] == "succeeded" for event in events)
    assert any(event[0] == "unregistered job type" for event in events)
    assert any(event[0] == "ValueError: expected" for event in events)


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


@pytest.mark.asyncio
async def test_worker_stop_cancels_handler_before_requeue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drain requeues only after the handler transaction has rolled back."""
    jobs: dict[int, object] = {1: SimpleNamespace(id=1, job_type="blocking", payload={})}
    worker = _worker(jobs)
    started = asyncio.Event()
    release = asyncio.Event()
    events: list[str] = []

    async def reclaim(session: object, *, lease_timeout_seconds: float) -> int:
        del session, lease_timeout_seconds
        return 0

    async def claim_one(session: object, *, worker_id: str, batch: int) -> list[object]:
        del session, worker_id
        assert batch == 1
        return [jobs[1]]

    async def blocking_handler(session: object, payload: object) -> None:
        del session, payload
        started.set()
        await release.wait()

    async def requeue(session: object, *, worker_id: str) -> int:
        del session
        assert worker_id == "worker-test"
        events.append("requeued")
        return 1

    monkeypatch.setattr(runner, "requeue_stale", reclaim)
    monkeypatch.setattr(runner, "claim", claim_one)
    monkeypatch.setattr(runner, "requeue_locked", requeue)

    def resolve(kind: str) -> object | None:
        return blocking_handler if kind == "blocking" else None

    monkeypatch.setattr(runner, "resolve", resolve)

    run_task = asyncio.create_task(worker.run())
    await started.wait()
    worker.request_stop()
    await run_task

    assert events == ["requeued"]
