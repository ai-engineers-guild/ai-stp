"""PostgreSQL claim/fail/cancel/requeue paths for the custom job queue."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_platform.queue.engine import (
    DEFAULT_LEASE_TIMEOUT_SECONDS,
    cancel,
    claim,
    enqueue,
    fail,
    heartbeat,
    mark_succeeded,
    requeue_locked,
    requeue_stale,
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


@pytest.mark.asyncio
async def test_stale_lease_is_reclaimed_and_counts_as_a_delivery(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """A crashed worker cannot leave a running job permanently invisible."""
    now = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
    async with db_sessionmaker() as session, session.begin():
        await enqueue(
            session,
            job_type=JobType.UPLOAD,
            payload={"path": "stale"},
            idempotency_key="queue-stale-lease",
            max_attempts=2,
            run_after=now,
        )

    async with db_sessionmaker() as session, session.begin():
        claimed = await claim(session, worker_id="worker-crashed", batch=1, now=now)
        assert len(claimed) == 1

    expired = now + timedelta(seconds=DEFAULT_LEASE_TIMEOUT_SECONDS + 1)
    async with db_sessionmaker() as session, session.begin():
        assert (
            await requeue_stale(
                session,
                lease_timeout_seconds=DEFAULT_LEASE_TIMEOUT_SECONDS,
                now=expired,
            )
            == 1
        )

    async with db_sessionmaker() as session, session.begin():
        reclaimed = await claim(session, worker_id="worker-recovered", batch=1, now=expired)
        assert len(reclaimed) == 1
        assert reclaimed[0].attempts == 1
        assert reclaimed[0].locked_by == "worker-recovered"


@pytest.mark.asyncio
async def test_heartbeat_keeps_a_live_lease_claimed(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """A live worker heartbeat prevents another worker from reclaiming work."""
    now = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
    async with db_sessionmaker() as session, session.begin():
        await enqueue(
            session,
            job_type=JobType.UPLOAD,
            payload={"path": "live"},
            idempotency_key="queue-live-lease",
            run_after=now,
        )
        claimed = await claim(session, worker_id="worker-live", batch=1, now=now)
        assert len(claimed) == 1

    extended = now + timedelta(seconds=DEFAULT_LEASE_TIMEOUT_SECONDS - 1)
    async with db_sessionmaker() as session, session.begin():
        assert (
            await heartbeat(
                session,
                worker_id="worker-live",
                job_id=claimed[0].id,
                now=extended,
            )
            is True
        )
        assert (
            await requeue_stale(
                session,
                lease_timeout_seconds=DEFAULT_LEASE_TIMEOUT_SECONDS,
                now=extended,
            )
            == 0
        )
