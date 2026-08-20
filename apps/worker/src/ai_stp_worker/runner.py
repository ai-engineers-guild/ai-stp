"""Worker runner: bounded polling, per-job transactions and graceful drain.

Claiming and marking a batch running happens in one transaction; each job is
then processed in its own transaction so a crash leaves at most a running job
that drain or a later run requeues. No job is lost or double-run (SPEC-018).
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_platform.logging import get_logger
from ai_stp_platform.queue.engine import claim, fail, mark_succeeded, requeue_locked
from ai_stp_platform.queue.models import Job
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
    ) -> None:
        self._sessionmaker = sessionmaker
        self._worker_id = worker_id
        self._batch_size = batch_size
        self._poll_interval = poll_interval_seconds
        self._stopping = asyncio.Event()

    def request_stop(self) -> None:
        """Signal the run loop to stop claiming and drain."""
        self._stopping.set()

    async def run(self) -> None:
        """Run until stop is requested, then drain held jobs."""
        _log.info("worker_start", worker_id=self._worker_id)
        try:
            while not self._stopping.is_set():
                processed = await self.run_once()
                if processed == 0:
                    await self._wait_or_stop(self._poll_interval)
        finally:
            drained = await self._drain()
            _log.info("worker_stop", worker_id=self._worker_id, requeued=drained)

    async def run_once(self) -> int:
        """Claim one batch and process each job; return the number processed."""
        async with self._sessionmaker() as session, session.begin():
            claimed = await claim(session, worker_id=self._worker_id, batch=self._batch_size)
            job_ids = [job.id for job in claimed]
        for job_id in job_ids:
            await self._process(job_id)
        return len(job_ids)

    async def _process(self, job_id: int) -> None:
        async with self._sessionmaker() as session, session.begin():
            job = await session.get(Job, job_id)
            if job is None:
                return
            handler = resolve(job.job_type)
            if handler is None:
                await fail(session, job, error="unregistered job type")
                return
            try:
                await handler(session, job.payload)
            except Exception as exc:
                await fail(session, job, error=type(exc).__name__)
            else:
                await mark_succeeded(session, job)

    async def _drain(self) -> int:
        async with self._sessionmaker() as session, session.begin():
            return await requeue_locked(session, worker_id=self._worker_id)

    async def _wait_or_stop(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stopping.wait(), timeout=seconds)
        except TimeoutError:
            return
