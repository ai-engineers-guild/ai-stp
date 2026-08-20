"""PostgreSQL claim/fail/cancel/requeue paths for the custom job queue."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_platform.queue.engine import (
    cancel,
    claim,
    enqueue,
    fail,
    mark_succeeded,
    requeue_locked,
)
from ai_stp_platform.queue.states import JobState, JobType

pytestmark = pytest.mark.platform


@pytest.mark.asyncio
async def test_claim_succeed_and_retry_dead_letter(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Claim moves work to running; failures retry then dead-letter at max_attempts."""
    now = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
    async with db_sessionmaker() as session, session.begin():
        await enqueue(
            session,
            job_type=JobType.UPLOAD,
            payload={"path": "a"},
            idempotency_key="queue-lifecycle-success",
            max_attempts=2,
            run_after=now,
        )
        await enqueue(
            session,
            job_type=JobType.UPLOAD,
            payload={"path": "b"},
            idempotency_key="queue-lifecycle-fail",
            max_attempts=2,
            run_after=now,
        )

    async with db_sessionmaker() as session, session.begin():
        claimed = await claim(session, worker_id="worker-a", batch=2, now=now)
        assert {job.idempotency_key for job in claimed} == {
            "queue-lifecycle-success",
            "queue-lifecycle-fail",
        }
        assert all(job.state is JobState.RUNNING for job in claimed)
        by_key = {job.idempotency_key: job for job in claimed}
        await mark_succeeded(session, by_key["queue-lifecycle-success"])
        await fail(session, by_key["queue-lifecycle-fail"], error="first", now=now)
        assert by_key["queue-lifecycle-fail"].state is JobState.RETRY_SCHEDULED

    async with db_sessionmaker() as session, session.begin():
        # Retry after backoff window.
        later = now + timedelta(seconds=10)
        retried = await claim(session, worker_id="worker-b", batch=2, now=later)
        assert len(retried) == 1
        assert retried[0].idempotency_key == "queue-lifecycle-fail"
        await fail(session, retried[0], error="second", now=later)
        assert retried[0].state is JobState.DEAD_LETTER


@pytest.mark.asyncio
async def test_cancel_and_requeue_locked(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Cancel only claimable jobs; drain requeues work still held by a worker."""
    now = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
    async with db_sessionmaker() as session, session.begin():
        await enqueue(
            session,
            job_type=JobType.UPLOAD,
            payload={"path": "c"},
            idempotency_key="queue-cancel-me",
            run_after=now,
        )
        await enqueue(
            session,
            job_type=JobType.UPLOAD,
            payload={"path": "d"},
            idempotency_key="queue-requeue-me",
            run_after=now,
        )

    async with db_sessionmaker() as session, session.begin():
        assert await cancel(session, idempotency_key="queue-cancel-me") is True
        assert await cancel(session, idempotency_key="missing") is False
        claimed = await claim(session, worker_id="worker-drain", batch=5, now=now)
        assert len(claimed) == 1
        assert claimed[0].idempotency_key == "queue-requeue-me"
        # Cancel is cooperative: running work is not cancelled.
        assert await cancel(session, idempotency_key="queue-requeue-me") is False

    async with db_sessionmaker() as session, session.begin():
        count = await requeue_locked(session, worker_id="worker-drain")
        assert count == 1
        reclaimed = await claim(session, worker_id="worker-new", batch=5, now=now)
        assert len(reclaimed) == 1
        assert reclaimed[0].idempotency_key == "queue-requeue-me"
        assert reclaimed[0].locked_by == "worker-new"
