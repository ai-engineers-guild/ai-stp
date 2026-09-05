"""Worker runner: one-job claiming, leased delivery and graceful drain."""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_platform.logging import get_logger
from ai_stp_platform.official_upstream.enqueue import enqueue_daily
from ai_stp_platform.official_upstream.github import worker_github_token
from ai_stp_platform.official_upstream.ledger import record_queue_outcome
from ai_stp_platform.queue.engine import (
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_LEASE_TIMEOUT_SECONDS,
    claim,
    fail,
    heartbeat,
    mark_succeeded,
    requeue_locked,
    requeue_stale,
)
from ai_stp_platform.queue.models import Job
from ai_stp_platform.queue.states import JobState, JobType
from ai_stp_platform.safety.metrics import record_queue_job
from ai_stp_worker.handlers import resolve

_log = get_logger("runner")


class Worker:
    """Polls the queue, runs handlers and drains cleanly on stop."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        worker_id: str,
        batch_size: int,
        poll_interval_seconds: float,
        drain_timeout_seconds: float = 30.0,
        lease_timeout_seconds: float = DEFAULT_LEASE_TIMEOUT_SECONDS,
        heartbeat_interval_seconds: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        schedule_official_upstream: bool = True,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._worker_id = worker_id
        # Keep the setting for backwards-compatible configuration, but never
        # preclaim a batch: one worker owns at most one not-yet-finished job.
        self._batch_size = min(batch_size, 1)
        self._poll_interval = poll_interval_seconds
        self._drain_timeout = drain_timeout_seconds
        self._lease_timeout = lease_timeout_seconds
        self._heartbeat_interval = heartbeat_interval_seconds
        self._stopping = asyncio.Event()
        self._official_enqueue_day: date | None = date.min if schedule_official_upstream else None

    def request_stop(self) -> None:
        """Signal the run loop to stop claiming and drain."""
        self._stopping.set()

    async def run(self) -> None:
        """Run until stop is requested, then drain held jobs."""
        _log.info("worker_start", worker_id=self._worker_id)
        if self._official_enqueue_day is not None and not worker_github_token():
            _log.warning(
                "official_upstream_github_unauthenticated",
                worker_id=self._worker_id,
            )
        active: asyncio.Task[int] | None = None
        safe_to_requeue = True
        try:
            while not self._stopping.is_set():
                active = asyncio.create_task(self.run_once())
                stop_waiter = asyncio.create_task(self._stopping.wait())
                done, _ = await asyncio.wait(
                    (active, stop_waiter),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if active in done:
                    stop_waiter.cancel()
                    with suppress(asyncio.CancelledError):
                        await stop_waiter
                    processed = active.result()
                    active = None
                else:
                    stop_waiter.result()
                    safe_to_requeue = await self._cancel_active(active)
                    active = None
                    break
                if processed == 0:
                    await self._wait_or_stop(self._poll_interval)
        finally:
            if active is not None and not active.done():
                safe_to_requeue = await self._cancel_active(active)
            drained = await self._drain() if safe_to_requeue else 0
            _log.info("worker_stop", worker_id=self._worker_id, requeued=drained)

    async def _cancel_active(self, task: asyncio.Task[int]) -> bool:
        """Cancel a cooperative handler before requeueing its rolled-back job."""
        task.cancel()
        try:
            async with asyncio.timeout(self._drain_timeout):
                await task
        except asyncio.CancelledError:
            return True
        except TimeoutError:
            _log.error("worker_active_job_timeout", worker_id=self._worker_id)
            # Do not requeue a handler that did not finish cancellation: its
            # transaction may still commit a side effect. Lease recovery will
            # reclaim the job after the process has actually stopped.
            return False
        return True

    async def run_once(self) -> int:
        """Reclaim expired leases, claim one job and process it."""
        enqueued_for: date | None = None
        async with self._sessionmaker() as session, session.begin():
            today = datetime.now(UTC).date()
            if self._official_enqueue_day is not None and self._official_enqueue_day != today:
                await enqueue_daily(session)
                enqueued_for = today
            await requeue_stale(session, lease_timeout_seconds=self._lease_timeout)
            queue_events = list(
                (
                    await session.scalars(
                        select(Job).where(
                            Job.job_type == JobType.OFFICIAL_UPSTREAM_SYNC,
                            Job.state.in_((JobState.RETRY_SCHEDULED, JobState.DEAD_LETTER)),
                        )
                    )
                ).all()
            )
            for queue_event in queue_events:
                await record_queue_outcome(session, queue_event)
            claimed = await claim(
                session,
                worker_id=self._worker_id,
                batch=self._batch_size,
            )
            job_id = claimed[0].id if claimed else None
        if enqueued_for is not None:
            self._official_enqueue_day = enqueued_for
        if job_id is None:
            return 0
        await self._process(job_id)
        return 1

    async def _process(self, job_id: int) -> None:
        started = time.perf_counter()
        job_type = "missing"
        result = "missing"
        heartbeat_task: asyncio.Task[None] | None = None
        try:
            async with self._sessionmaker() as session:
                job = await session.get(Job, job_id)
                if job is None:
                    return
                job_type = job.job_type
                payload = dict(job.payload)
                handler = resolve(job.job_type)
            if handler is None:
                async with self._sessionmaker() as session, session.begin():
                    current = await session.get(Job, job_id)
                    if current is not None:
                        await fail(session, current, error="unregistered job type")
                result = "failed"
                return

            heartbeat_task = asyncio.create_task(self._heartbeat(job_id))
            error: str | None = None
            async with self._sessionmaker() as handler_session:
                try:
                    await handler(handler_session, payload)
                    await handler_session.commit()
                except Exception as exc:
                    await handler_session.rollback()
                    detail = str(exc).strip()
                    error = type(exc).__name__ + (f": {detail}" if detail else "")
                    _log.error(
                        "job_handler_failed",
                        job_id=job_id,
                        job_type=job_type,
                        error=error,
                    )

            async with self._sessionmaker() as status_session, status_session.begin():
                current = await status_session.get(Job, job_id)
                if current is None:
                    return
                if error is None:
                    await mark_succeeded(status_session, current)
                    result = "succeeded"
                else:
                    await fail(status_session, current, error=error)
                    await record_queue_outcome(status_session, current)
                    result = "failed"
        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat_task
            record_queue_job(
                job_type=job_type,
                duration_ms=int((time.perf_counter() - started) * 1000),
                result=result,
            )

    async def _heartbeat(self, job_id: int) -> None:
        """Keep a live job lease valid using short independent transactions."""
        while True:
            await asyncio.sleep(self._heartbeat_interval)
            async with self._sessionmaker() as session, session.begin():
                alive = await heartbeat(
                    session,
                    worker_id=self._worker_id,
                    job_id=job_id,
                )
            if not alive:
                _log.warning("worker_lease_lost", worker_id=self._worker_id, job_id=job_id)
                return

    async def _drain(self) -> int:
        async def _requeue() -> int:
            async with self._sessionmaker() as session, session.begin():
                return await requeue_locked(session, worker_id=self._worker_id)

        try:
            async with asyncio.timeout(self._drain_timeout):
                return await _requeue()
        except TimeoutError:
            _log.error("worker_drain_timeout", worker_id=self._worker_id)
            return 0

    async def _wait_or_stop(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stopping.wait(), timeout=seconds)
        except TimeoutError:
            return
