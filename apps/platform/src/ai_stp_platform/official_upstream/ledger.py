"""Official sync attempt ledger, outbox dispatch, and delivery reconciliation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.first_party import OWNER_ID as OFFICIAL_ACCOUNT_ID
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import (
    AuditEvent,
    CatalogIdentity,
    OfficialSyncOutbox,
    OfficialUpstreamSource,
    OfficialUpstreamSync,
)
from ai_stp_platform.queue.engine import enqueue
from ai_stp_platform.queue.models import Job
from ai_stp_platform.queue.states import JobState, JobType

SYNC_STATES: Final[frozenset[str]] = frozenset(
    {
        "desired",
        "queued",
        "resolving",
        "unchanged",
        "publishing",
        "published",
        "retry_wait",
        "dead_lettered",
        "failed_permanent",
        "cancelled_transferred",
    }
)
_ACTIVE_INVENTORY: Final[frozenset[str]] = frozenset({"enabled"})
_COMPAT_RESULT: Final[dict[str, str]] = {
    "unchanged": "unchanged",
    "publishing": "publication_started",
    "published": "publication_started",
    "desired": "publication_started",
    "queued": "publication_started",
    "resolving": "publication_started",
    "retry_wait": "failed",
    "dead_lettered": "failed",
    "failed_permanent": "failed",
    "cancelled_transferred": "failed",
}


def compat_result(state: str) -> str:
    return _COMPAT_RESULT.get(state, "failed")


def source_is_schedulable(source: OfficialUpstreamSource) -> bool:
    inventory = source.inventory_state or ("enabled" if source.enabled else "paused")
    return (
        bool(source.enabled)
        and inventory in _ACTIVE_INVENTORY
        and source.update_policy != "disabled"
    )


async def create_attempt_and_outbox(
    session: AsyncSession,
    source: OfficialUpstreamSource,
    *,
    trigger_key: str,
    utc_day: datetime,
    provenance: str,
) -> tuple[OfficialUpstreamSync, OfficialSyncOutbox]:
    """Create one desired attempt and its outbox event in the caller transaction."""
    source = await session.scalar(
        select(OfficialUpstreamSource)
        .where(OfficialUpstreamSource.id == source.id)
        .with_for_update()
    )
    if source is None:
        from ai_stp_platform.official_upstream.errors import INVALID_SOURCE, OfficialUpstreamError

        raise OfficialUpstreamError(INVALID_SOURCE, "source is missing")
    if not source_is_schedulable(source):
        from ai_stp_platform.official_upstream.errors import INVALID_SOURCE, OfficialUpstreamError

        raise OfficialUpstreamError(INVALID_SOURCE, "source is not schedulable")
    existing = await session.scalar(
        select(OfficialUpstreamSync).where(
            OfficialUpstreamSync.source_id == source.id,
            OfficialUpstreamSync.trigger_key == trigger_key,
        )
    )
    identity = await session.get(CatalogIdentity, source.stable_id)
    if existing is not None:
        outbox = None
        if existing.outbox_id:
            outbox = await session.get(OfficialSyncOutbox, existing.outbox_id)
        if outbox is None:
            outbox = await _new_outbox(session, source, existing, trigger_key)
            existing.outbox_id = outbox.id
        return existing, outbox
    attempt = OfficialUpstreamSync(
        source_id=source.id,
        utc_day=utc_day.date(),
        trigger_key=trigger_key,
        result="publication_started",
        state="desired",
        attempt_count=0,
        expected_owner_account_id=source.owner_account_id,
        expected_ownership_revision_id=(
            identity.ownership_revision_id if identity is not None else source.ownership_revision_id
        ),
        manifest_digest=source.manifest_digest,
        provenance=provenance,
    )
    session.add(attempt)
    await session.flush()
    outbox = await _new_outbox(session, source, attempt, trigger_key)
    attempt.outbox_id = outbox.id
    await session.flush()
    return attempt, outbox


async def _new_outbox(
    session: AsyncSession,
    source: OfficialUpstreamSource,
    attempt: OfficialUpstreamSync,
    trigger_key: str,
) -> OfficialSyncOutbox:
    outbox = OfficialSyncOutbox(
        id=new_id("outbox"),
        source_id=source.id,
        attempt_id=attempt.id,
        idempotency_key=f"official-upstream-sync:{source.id}:{trigger_key}",
        state="pending",
    )
    session.add(outbox)
    await session.flush()
    return outbox


async def dispatch_outbox(session: AsyncSession, outbox: OfficialSyncOutbox) -> Job:
    """Insert one idempotent worker job and mark the outbox dispatched."""
    source = await session.scalar(
        select(OfficialUpstreamSource)
        .where(OfficialUpstreamSource.id == outbox.source_id)
        .with_for_update()
    )
    if source is None or outbox.state == "cancelled" or not source_is_schedulable(source):
        from ai_stp_platform.official_upstream.errors import INVALID_SOURCE, OfficialUpstreamError

        raise OfficialUpstreamError(INVALID_SOURCE, "source is no longer schedulable")
    locked_outbox = await session.scalar(
        select(OfficialSyncOutbox).where(OfficialSyncOutbox.id == outbox.id).with_for_update()
    )
    if locked_outbox is None or locked_outbox.state == "cancelled":
        from ai_stp_platform.official_upstream.errors import INVALID_SOURCE, OfficialUpstreamError

        raise OfficialUpstreamError(INVALID_SOURCE, "outbox is cancelled")
    outbox = locked_outbox
    attempt = await session.get(OfficialUpstreamSync, outbox.attempt_id)
    job = await enqueue(
        session,
        job_type=JobType.OFFICIAL_UPSTREAM_SYNC,
        payload={"source_id": outbox.source_id, "attempt_id": outbox.attempt_id},
        idempotency_key=outbox.idempotency_key,
    )
    outbox.job_id = job.id
    if outbox.state != "cancelled":
        outbox.state = "dispatched"
        outbox.dispatched_at = datetime.now(UTC)
    if attempt is not None and attempt.state in {"desired", "retry_wait"}:
        attempt.state = "queued"
        attempt.result = compat_result("queued")
        attempt.job_id = job.id
    await session.flush()
    return job


async def record_queue_outcome(session: AsyncSession, job: Job) -> None:
    """Map generic queue retry/DLQ onto the Official attempt ledger."""
    if job.job_type != JobType.OFFICIAL_UPSTREAM_SYNC:
        return
    payload = dict(job.payload)
    attempt_id = payload.get("attempt_id")
    attempt: OfficialUpstreamSync | None = None
    if isinstance(attempt_id, int):
        attempt = await session.get(OfficialUpstreamSync, attempt_id)
    if attempt is None:
        source_id = payload.get("source_id")
        if isinstance(source_id, str):
            attempt = await session.scalar(
                select(OfficialUpstreamSync)
                .where(OfficialUpstreamSync.source_id == source_id)
                .order_by(OfficialUpstreamSync.id.desc())
            )
    if attempt is None or attempt.state in {
        "unchanged",
        "published",
        "cancelled_transferred",
        "failed_permanent",
    }:
        return
    if job.state == JobState.DEAD_LETTER:
        attempt.state = "dead_lettered"
        attempt.result = "failed"
        attempt.error_class = "exhausted_retry"
        attempt.error_code = attempt.error_code or "dead_lettered"
        attempt.completed_at = datetime.now(UTC)
    elif job.state == JobState.RETRY_SCHEDULED:
        attempt.state = "retry_wait"
        attempt.result = "failed"
        attempt.retry_at = job.run_after
        attempt.attempt_count = max(attempt.attempt_count, job.attempts)
        attempt.error_class = "retryable"
    await session.flush()


async def fence_attempt(
    session: AsyncSession, source: OfficialUpstreamSource, attempt: OfficialUpstreamSync | None
) -> str | None:
    """Return a cancellation code when the attempt may not mutate the catalog."""
    source = await session.scalar(
        select(OfficialUpstreamSource)
        .where(OfficialUpstreamSource.id == source.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if source is None:
        return await _cancel_transferred(attempt)
    if not source.enabled or (source.inventory_state or "enabled") != "enabled":
        if attempt is not None:
            attempt.state = "cancelled_transferred"
            attempt.result = "failed"
            attempt.error_code = "cancelled_transferred"
            attempt.error_class = "stale_ownership_fence"
            attempt.cancelled_at = datetime.now(UTC)
            await session.flush()
        return "cancelled_transferred"
    identity = await session.scalar(
        select(CatalogIdentity)
        .where(CatalogIdentity.stable_id == source.stable_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    expected_owner = attempt.expected_owner_account_id if attempt else source.owner_account_id
    if expected_owner != OFFICIAL_ACCOUNT_ID or source.owner_account_id != OFFICIAL_ACCOUNT_ID:
        return await _cancel_transferred(attempt)
    if identity is not None and identity.owner_account_id != OFFICIAL_ACCOUNT_ID:
        return await _cancel_transferred(attempt)
    expected_revision = (
        attempt.expected_ownership_revision_id
        if attempt is not None
        else source.ownership_revision_id
    )
    current_revision = (
        identity.ownership_revision_id if identity is not None else source.ownership_revision_id
    )
    if (
        expected_revision is not None
        and current_revision is not None
        and expected_revision != current_revision
    ):
        return await _cancel_transferred(attempt)
    return None


async def _cancel_transferred(attempt: OfficialUpstreamSync | None) -> str:
    if attempt is not None:
        attempt.state = "cancelled_transferred"
        attempt.result = "failed"
        attempt.error_code = "cancelled_transferred"
        attempt.error_class = "stale_ownership_fence"
        attempt.cancelled_at = datetime.now(UTC)
    return "cancelled_transferred"


async def mark_attempt(
    session: AsyncSession,
    attempt: OfficialUpstreamSync | None,
    state: str,
    *,
    error_code: str | None = None,
    error_class: str | None = None,
    plan_id: str | None = None,
) -> None:
    if attempt is None:
        return
    attempt.state = state
    attempt.result = compat_result(state)
    if error_code is not None:
        attempt.error_code = error_code
    if error_class is not None:
        attempt.error_class = error_class
    if plan_id is not None:
        attempt.plan_id = plan_id
    if state in {"resolving", "queued", "desired"}:
        attempt.started_at = attempt.started_at or datetime.now(UTC)
    if state in {
        "unchanged",
        "published",
        "dead_lettered",
        "failed_permanent",
        "cancelled_transferred",
    }:
        attempt.completed_at = datetime.now(UTC)
    await session.flush()


async def reconcile_delivery(session: AsyncSession, *, now: datetime | None = None) -> list[str]:
    """Repair missing handoffs through ordinary idempotent paths (REQ-5610)."""
    moment = now or datetime.now(UTC)
    utc_day = moment.date().isoformat()
    repairs: list[str] = []
    sources = list(
        (
            await session.scalars(
                select(OfficialUpstreamSource).where(OfficialUpstreamSource.enabled.is_(True))
            )
        ).all()
    )
    for source in sources:
        if not source_is_schedulable(source):
            continue
        attempt = await session.scalar(
            select(OfficialUpstreamSync).where(
                OfficialUpstreamSync.source_id == source.id,
                OfficialUpstreamSync.trigger_key == utc_day,
            )
        )
        if attempt is None:
            attempt, outbox = await create_attempt_and_outbox(
                session, source, trigger_key=utc_day, utc_day=moment, provenance="reconcile"
            )
            await dispatch_outbox(session, outbox)
            repairs.append(f"due_without_attempt:{source.id}")
            session.add(
                AuditEvent(
                    actor_account_id=OFFICIAL_ACCOUNT_ID,
                    action="official_upstream.reconcile_repair",
                    target_table="official_upstream_sync",
                    target_id=str(attempt.id),
                    payload={"repair": "due_without_attempt", "source_id": source.id},
                )
            )
            continue
        if attempt.outbox_id is None:
            outbox = await _new_outbox(session, source, attempt, utc_day)
            attempt.outbox_id = outbox.id
            await dispatch_outbox(session, outbox)
            repairs.append(f"attempt_without_outbox:{source.id}")
            continue
        outbox = await session.get(OfficialSyncOutbox, attempt.outbox_id)
        if outbox is None:
            outbox = await _new_outbox(session, source, attempt, utc_day)
            attempt.outbox_id = outbox.id
            await dispatch_outbox(session, outbox)
            repairs.append(f"attempt_without_outbox:{source.id}")
            continue
        if outbox.state == "pending":
            await dispatch_outbox(session, outbox)
            repairs.append(f"outbox_without_job:{source.id}")
            continue
        if outbox.job_id is not None:
            job = await session.get(Job, outbox.job_id)
            if job is None or job.state in {JobState.CANCELLED}:
                outbox.state = "pending"
                outbox.job_id = None
                await dispatch_outbox(session, outbox)
                repairs.append(f"missing_job:{source.id}")
                continue
            if job.state == JobState.DEAD_LETTER and attempt.state not in {
                "dead_lettered",
                "cancelled_transferred",
            }:
                await record_queue_outcome(session, job)
                repairs.append(f"unrecorded_dlq:{source.id}")
            if job.state == JobState.SUCCEEDED and attempt.state in {
                "queued",
                "resolving",
                "publishing",
            }:
                # Completion is recorded by the sync/publish path; leave running.
                pass
    await session.flush()
    return repairs
