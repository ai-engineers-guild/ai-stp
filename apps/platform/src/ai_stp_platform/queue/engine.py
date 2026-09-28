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
from sqlalchemy import delete as sql_delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.corporate_authorization import PrincipalType, has_corporate_permission
from ai_stp_platform.queue.models import Job
from ai_stp_platform.queue.states import CLAIMABLE_STATES, TERMINAL_STATES, JobState, JobType
from ai_stp_platform.safety.metrics import record_queue_claim, record_queue_requeue
from ai_stp_platform.tenant_scope import set_tenant_scope

DEFAULT_MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 2.0
BACKOFF_CAP_SECONDS = 300.0
DEFAULT_LEASE_TIMEOUT_SECONDS = 900.0
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30.0
STALE_LEASE_ERROR = "stale worker lease expired"
TENANT_ENVELOPE_KEY = "_tenant"


class TenantJobInvalid(ValueError):
    """A queued tenant envelope is missing, inconsistent, or stale."""


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
    organization_id: str | None = None,
    authorization_revision: int | None = None,
    principal_type: PrincipalType | None = None,
    principal_id: str | None = None,
    required_permission: str | None = None,
    scope_kind: str = "organization",
    scope_id: str | None = None,
) -> Job:
    """Insert a job in the caller's transaction (outbox); duplicate keys are a no-op."""
    safe_payload = dict(payload)
    if organization_id is None:
        if TENANT_ENVELOPE_KEY in safe_payload:
            raise TenantJobInvalid("global job cannot supply a tenant envelope")
    else:
        if (
            authorization_revision is None
            or authorization_revision < 1
            or principal_type is None
            or principal_id is None
            or required_permission is None
        ):
            raise TenantJobInvalid("tenant job requires an authorization decision")
        supplied = safe_payload.get(TENANT_ENVELOPE_KEY)
        envelope = {
            "organization_id": organization_id,
            "authorization_revision": authorization_revision,
            "principal_type": principal_type,
            "principal_id": principal_id,
            "required_permission": required_permission,
            "scope_kind": scope_kind,
            "scope_id": scope_id,
        }
        if supplied is not None and supplied != envelope:
            raise TenantJobInvalid("tenant job envelope does not match queue scope")
        safe_payload[TENANT_ENVELOPE_KEY] = envelope
        await set_tenant_scope(session, organization_id)
    values = {
        "job_type": str(job_type),
        "payload": safe_payload,
        "organization_id": organization_id,
        "state": JobState.QUEUED,
        "priority": priority,
        "max_attempts": max_attempts,
        "run_after": run_after or _now(),
        "idempotency_key": idempotency_key,
    }
    stmt = pg_insert(Job).values(**values).on_conflict_do_nothing()
    await session.execute(stmt)
    tenant_filter = (
        Job.organization_id.is_(None)
        if organization_id is None
        else Job.organization_id == organization_id
    )
    existing = await session.execute(
        select(Job).where(Job.idempotency_key == idempotency_key, tenant_filter)
    )
    return existing.scalar_one()


async def validate_tenant_job(session: AsyncSession, job: Job) -> dict[str, object]:
    """Validate the persisted tenant envelope immediately before handler execution."""
    payload = dict(job.payload)
    organization_id = getattr(job, "organization_id", None)
    if organization_id is None:
        if TENANT_ENVELOPE_KEY in payload:
            raise TenantJobInvalid("global job carries a tenant envelope")
        return payload
    raw = payload.get(TENANT_ENVELOPE_KEY)
    if not isinstance(raw, dict):
        raise TenantJobInvalid("job tenant envelope does not match persisted scope")
    envelope = cast("dict[str, object]", raw)
    if envelope.get("organization_id") != organization_id:
        raise TenantJobInvalid("job tenant envelope does not match persisted scope")
    revision = envelope.get("authorization_revision")
    if not isinstance(revision, int) or revision < 1:
        raise TenantJobInvalid("job tenant envelope has no authorization revision")
    principal_type = envelope.get("principal_type")
    principal_id = envelope.get("principal_id")
    permission = envelope.get("required_permission")
    scope_kind = envelope.get("scope_kind")
    scope_id = envelope.get("scope_id")
    if (
        principal_type not in ("user", "service_principal")
        or not isinstance(principal_id, str)
        or not isinstance(permission, str)
        or not isinstance(scope_kind, str)
        or (scope_id is not None and not isinstance(scope_id, str))
    ):
        raise TenantJobInvalid("job tenant envelope has no authorization decision")

    from ai_stp_platform.organization_models import Organization

    current = await session.get(Organization, organization_id)
    if current is None or current.state != "active":
        raise TenantJobInvalid("job organization is unavailable")
    if current.policy_revision != revision:
        raise TenantJobInvalid("job authorization revision is stale")
    allowed = await has_corporate_permission(
        session,
        organization_id=organization_id,
        principal_type=principal_type,
        principal_id=principal_id,
        permission=permission,
        scope_kind=scope_kind,
        scope_id=scope_id,
        authorization_revision=revision,
    )
    if not allowed:
        raise TenantJobInvalid("job authorization is no longer effective")
    await set_tenant_scope(session, organization_id)
    return payload


async def claim(
    session: AsyncSession,
    *,
    worker_id: str,
    batch: int = 1,
    now: datetime | None = None,
) -> list[Job]:
    """Claim up to `batch` due jobs; concurrent workers never take the same row."""
    await set_tenant_scope(session, "*")
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


async def _owned_running_job(
    session: AsyncSession, *, job_id: int, locked_by: str | None
) -> Job | None:
    """The row under `job_id`, write-locked, iff it still runs under `locked_by`.

    The settle paths used to stamp whatever object they were handed: a worker
    whose lease expired mid-flight could reclaim-settle over a row `requeue_stale`
    had already handed to somebody else — the stale verdict overwrote the live
    one. Locking and re-reading the ownership facts in one `SELECT … FOR UPDATE`
    is the same condition `heartbeat` writes under.

    `locked_by` is the *expected* owner — the caller's claim-time lease, never
    the value re-read from the row itself (which would always match itself).
    """
    if locked_by is None:
        return None
    row = (
        await session.execute(select(Job).where(Job.id == job_id).with_for_update())
    ).scalar_one_or_none()
    if row is None or row.state != JobState.RUNNING or row.locked_by != locked_by:
        return None
    return row


# Payload keys that are credentials in transit: they exist only so the handler
# can do its work and must not rest in a settled row for the retention window.
_SENSITIVE_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "accept_token",
        "invitation_token",
        "refresh_token",
        "access_token",
        "secret",
        "password",
    }
)


def _scrub_settled_payload(payload: dict[str, object]) -> dict[str, object]:
    """Return payload with credential-bearing keys replaced by a marker."""
    return {
        key: "[delivered]" if key in _SENSITIVE_PAYLOAD_KEYS else value
        for key, value in payload.items()
    }


async def mark_succeeded(session: AsyncSession, job: Job, *, locked_by: str | None = None) -> bool:
    """Move a job to its single success state.

    Returns False when the row no longer belongs to this worker — reclaimed
    after an expired lease or settled by a new owner. The caller then records
    no outcome: writing over the winner's verdict is the stale settle this
    guards, and the new owner reports its own.

    `locked_by` overrides the lease checked against the row; defaults to the
    passed job's own — correct for callers settling the object they claimed.
    """
    expected = locked_by if locked_by is not None else job.locked_by
    row = await _owned_running_job(session, job_id=job.id, locked_by=expected)
    if row is None:
        return False
    row.state = JobState.SUCCEEDED
    row.locked_by = None
    row.locked_at = None
    row.last_error = None
    # A delivered token is spent: the succeeded row is an audit trail, not a
    # credential store — nothing may read the token back out of it.
    row.payload = _scrub_settled_payload(row.payload)
    await session.flush()
    return True


async def fail(
    session: AsyncSession,
    job: Job,
    *,
    error: str,
    permanent: bool = False,
    now: datetime | None = None,
    locked_by: str | None = None,
) -> bool:
    """Record a failure: schedule a bounded retry or move to dead-letter.

    Returns False when the row no longer belongs to this worker — the same
    ownership condition `mark_succeeded` guards. A failure observed by a stale
    worker is not evidence about the job that owns the row now.

    `locked_by` overrides the lease checked against the row; defaults to the
    passed job's own.
    """
    expected = locked_by if locked_by is not None else job.locked_by
    row = await _owned_running_job(session, job_id=job.id, locked_by=expected)
    if row is None:
        return False
    moment = now or _now()
    row.attempts += 1
    row.last_error = error[:2000]
    row.locked_by = None
    row.locked_at = None
    if permanent or row.attempts >= row.max_attempts:
        row.state = JobState.DEAD_LETTER
        # A dead-lettered row is terminal: no retry will read its payload, so
        # carried credentials are scrubbed like on success.
        row.payload = _scrub_settled_payload(row.payload)
    else:
        row.state = JobState.RETRY_SCHEDULED
        row.run_after = moment + timedelta(seconds=backoff_seconds(row.attempts))
    await session.flush()
    return True


async def cancel(
    session: AsyncSession, *, idempotency_key: str, organization_id: str | None = None
) -> bool:
    """Cooperatively cancel one global or tenant-partitioned queued job."""
    await set_tenant_scope(session, organization_id or "*")
    tenant_filter = (
        Job.organization_id.is_(None)
        if organization_id is None
        else Job.organization_id == organization_id
    )
    found = await session.execute(
        select(Job).where(Job.idempotency_key == idempotency_key, tenant_filter)
    )
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
    await set_tenant_scope(session, "*")
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
    await set_tenant_scope(session, "*")
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
    await set_tenant_scope(session, "*")
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


QUEUE_GC_RETENTION_DAYS = 30
QUEUE_GC_BATCH_LIMIT = 5000


async def gc_terminal_jobs(
    session: AsyncSession,
    *,
    retention_days: int = QUEUE_GC_RETENTION_DAYS,
    limit: int = QUEUE_GC_BATCH_LIMIT,
    now: datetime | None = None,
) -> int:
    """Delete terminal job rows older than the retention window.

    Terminal rows otherwise accumulate forever — succeeded SEO builds, daily
    upstream syncs, dead letters — and payloads can carry personal data, so
    growth is also a retention problem. Deletion is bounded per pass; the
    daily sweep drains a backlog over successive days. A re-enqueue under a
    GC'd idempotency key inserts a fresh row, which is the desired replay.
    """
    await set_tenant_scope(session, "*")
    cutoff = (now or _now()) - timedelta(days=retention_days)
    ids = (
        await session.scalars(
            select(Job.id)
            .where(Job.state.in_(TERMINAL_STATES), Job.updated_at < cutoff)
            .order_by(Job.updated_at)
            .limit(limit)
        )
    ).all()
    if not ids:
        return 0
    result = cast(
        "CursorResult[Any]",
        await session.execute(sql_delete(Job).where(Job.id.in_(ids))),
    )
    await session.flush()
    return result.rowcount


__all__ = [
    "TERMINAL_STATES",
    "TenantJobInvalid",
    "backoff_seconds",
    "cancel",
    "claim",
    "enqueue",
    "fail",
    "gc_terminal_jobs",
    "heartbeat",
    "mark_succeeded",
    "requeue_locked",
    "requeue_stale",
    "validate_tenant_job",
]
