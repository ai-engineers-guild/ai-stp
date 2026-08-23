"""Custom PostgreSQL job queue engine (SPEC-018, ADR-0038).

At-least-once delivery via `FOR UPDATE SKIP LOCKED` claiming, transactional
enqueue used as an outbox, bounded exponential backoff and a dead-letter
terminal state. No external broker and no queue library.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, case, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.queue.models import Job
from ai_stp_platform.queue.states import CLAIMABLE_STATES, TERMINAL_STATES, JobState, JobType
from ai_stp_platform.safety.metrics import record_queue_claim, record_queue_requeue

DEFAULT_MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 2.0
BACKOFF_CAP_SECONDS = 300.0
DEFAULT_LEASE_TIMEOUT_SECONDS = 900.0
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30.0
STALE_LEASE_ERROR = "stale worker lease expired"


def _now() -> datetime:
    return datetime.now(UTC)


def backoff_seconds(attempts: int) -> float:
    """Bounded exponential backoff for the given attempt count."""
    return min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS**attempts)


async def enqueue(
    session: AsyncSession,
    *,
    job_type: JobType,
    payload: Mapping[str, object],
    idempotency_key: str,
    priority: int = 0,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    run_after: datetime | None = None,
) -> Job:
    """Insert a job in the caller's transaction (outbox); duplicate keys are a no-op."""
    values = {
        "job_type": str(job_type),
        "payload": dict(payload),
        "state": JobState.QUEUED,
        "priority": priority,
        "max_attempts": max_attempts,
        "run_after": run_after or _now(),
        "idempotency_key": idempotency_key,
    }
    stmt = (
        pg_insert(Job).values(**values).on_conflict_do_nothing(index_elements=["idempotency_key"])
    )
    await session.execute(stmt)
    existing = await session.execute(select(Job).where(Job.idempotency_key == idempotency_key))
    return existing.scalar_one()


async def claim(
    session: AsyncSession,
    *,
    worker_id: str,
    batch: int = 1,
    now: datetime | None = None,
) -> list[Job]:
    """Claim up to `batch` due jobs; concurrent workers never take the same row."""
    moment = now or _now()
    stmt = (
        select(Job)
        .where(Job.state.in_(CLAIMABLE_STATES), Job.run_after <= moment)
        .order_by(Job.priority.desc(), Job.run_after)
        .limit(batch)
        .with_for_update(skip_locked=True)
    )
    jobs = list((await session.execute(stmt)).scalars().all())
    queue_waits: list[int] = []
    for job in jobs:
        job.state = JobState.RUNNING
        job.locked_by = worker_id
        job.locked_at = moment
        queue_waits.append(max(0, int((moment - job.created_at).total_seconds() * 1000)))
    await session.flush()
    record_queue_claim(
        batch_size=batch,
        claimed_count=len(jobs),
        queue_wait_ms_sum=sum(queue_waits),
        queue_wait_ms_max=max(queue_waits, default=0),
    )
    return jobs


async def mark_succeeded(session: AsyncSession, job: Job) -> None:
    """Move a job to its single success state."""
    job.state = JobState.SUCCEEDED
    job.locked_by = None
    job.locked_at = None
    job.last_error = None
    await session.flush()


async def fail(
    session: AsyncSession,
    job: Job,
    *,
    error: str,
    now: datetime | None = None,
) -> None:
    """Record a failure: schedule a bounded retry or move to dead-letter."""
    moment = now or _now()
    job.attempts += 1
    job.last_error = error[:2000]
    job.locked_by = None
    job.locked_at = None
    if job.attempts >= job.max_attempts:
        job.state = JobState.DEAD_LETTER
    else:
        job.state = JobState.RETRY_SCHEDULED
        job.run_after = moment + timedelta(seconds=backoff_seconds(job.attempts))
    await session.flush()


async def cancel(session: AsyncSession, *, idempotency_key: str) -> bool:
    """Cooperatively cancel a not-yet-running job; return whether it was cancelled."""
    found = await session.execute(select(Job).where(Job.idempotency_key == idempotency_key))
    job = found.scalar_one_or_none()
    if job is None or job.state not in CLAIMABLE_STATES:
        return False
    job.state = JobState.CANCELLED
    await session.flush()
    return True


async def requeue_locked(
    session: AsyncSession,
    *,
    worker_id: str,
) -> int:
    """Requeue jobs still held by a stopping worker so none is lost on drain."""
    stmt = (
        update(Job)
        .where(Job.state == JobState.RUNNING, Job.locked_by == worker_id)
        .values(state=JobState.QUEUED, locked_by=None, locked_at=None)
    )
    result = await session.execute(stmt)
    await session.flush()
    count = cast("CursorResult[Any]", result).rowcount
    record_queue_requeue(count=count)
    return count


async def heartbeat(
    session: AsyncSession,
    *,
    worker_id: str,
    job_id: int,
    now: datetime | None = None,
) -> bool:
    """Extend one live lease without touching a handler transaction."""
    moment = now or _now()
    stmt = (
        update(Job)
        .where(
            Job.id == job_id,
            Job.state == JobState.RUNNING,
            Job.locked_by == worker_id,
        )
        .values(locked_at=moment)
    )
    result = cast("CursorResult[Any]", await session.execute(stmt))
    await session.flush()
    return result.rowcount == 1


async def requeue_stale(
    session: AsyncSession,
    *,
    lease_timeout_seconds: float = DEFAULT_LEASE_TIMEOUT_SECONDS,
    now: datetime | None = None,
) -> int:
    """Reclaim jobs whose worker lease expired after a crash or hard stop.

    A reclaimed delivery consumes one attempt. This prevents a repeatedly
    crashing job from remaining retryable forever while preserving the queue's
    at-least-once semantics.
    """
    moment = now or _now()
    cutoff = moment - timedelta(seconds=lease_timeout_seconds)
    next_attempts = Job.attempts + 1
    stmt = (
        update(Job)
        .where(
            Job.state == JobState.RUNNING,
            Job.locked_at.is_not(None),
            Job.locked_at <= cutoff,
        )
        .values(
            state=case(
                (next_attempts >= Job.max_attempts, JobState.DEAD_LETTER),
                else_=JobState.QUEUED,
            ),
            attempts=next_attempts,
            run_after=moment,
            locked_by=None,
            locked_at=None,
            last_error=STALE_LEASE_ERROR,
        )
    )
    result = cast("CursorResult[Any]", await session.execute(stmt))
    await session.flush()
    count = result.rowcount
    record_queue_requeue(count=count)
    return count


__all__ = [
    "TERMINAL_STATES",
    "backoff_seconds",
    "cancel",
    "claim",
    "enqueue",
    "fail",
    "heartbeat",
    "mark_succeeded",
    "requeue_locked",
    "requeue_stale",
]
