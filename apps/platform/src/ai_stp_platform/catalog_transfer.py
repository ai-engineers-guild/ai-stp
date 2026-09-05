"""Database-bound ownership transfer and author verification (SPEC-016, SPEC-059)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.first_party import OWNER_ID as OFFICIAL_ACCOUNT_ID
from ai_stp_foundation.ids import new_id
from ai_stp_platform.identity import IdentityError
from ai_stp_platform.models import (
    Account,
    AccountAuthorVerification,
    AuditEvent,
    CatalogIdentity,
    CatalogMetadata,
    OfficialSyncOutbox,
    OfficialUpstreamSource,
    OfficialUpstreamSync,
    OwnershipClaim,
    OwnershipRevision,
    ReportCase,
)
from ai_stp_platform.queue.engine import cancel
from ai_stp_platform.queue.models import Job
from ai_stp_platform.queue.states import CLAIMABLE_STATES, JobState, JobType

_TERMINAL_ATTEMPTS = frozenset(
    {"unchanged", "published", "dead_lettered", "failed_permanent", "cancelled_transferred"}
)


def _major_lines(versions: list[str]) -> list[int]:
    majors: set[int] = set()
    for version in versions:
        major, _sep, _minor = version.partition(".")
        if major.isdigit():
            majors.add(int(major))
    return sorted(majors)


async def transfer_catalog_line(
    session: AsyncSession,
    *,
    case_id: str,
    expected_owner_account_id: str,
    expected_ownership_revision_id: str,
    recipient_account_id: str,
    reason: str,
    operator_account_id: str,
    evidence: str = "",
) -> OwnershipRevision:
    """Atomically change catalog-line owner and cut off Official work (REQ-5612)."""
    case = await session.scalar(
        select(ReportCase).where(ReportCase.id == case_id).with_for_update()
    )
    if case is None:
        raise IdentityError("AI_STP_NOT_FOUND", "request case not found")
    if case.topic != "ownership_transfer":
        raise IdentityError("AI_STP_VALIDATION_ERROR", "case is not an ownership transfer request")
    requested_recipient = case.payload.get("recipient_account_id")
    if requested_recipient != recipient_account_id:
        raise IdentityError(
            "AI_STP_VALIDATION_ERROR", "recipient does not match the transfer request"
        )
    if case.state == "resolved":
        existing = await session.scalar(
            select(OwnershipRevision).where(OwnershipRevision.case_id == case_id)
        )
        if existing is not None:
            return existing
    if case.state not in {"submitted", "triaged", "awaiting_author", "resolved"}:
        raise IdentityError("AI_STP_CONFLICT", "case is not eligible for transfer")
    stable_id = case.stable_id
    if not stable_id:
        raise IdentityError("AI_STP_VALIDATION_ERROR", "transfer case is missing a component line")
    recipient = await session.get(Account, recipient_account_id)
    if recipient is None:
        raise IdentityError("AI_STP_NOT_FOUND", "recipient account not found")
    sources = list(
        (
            await session.scalars(
                select(OfficialUpstreamSource)
                .where(OfficialUpstreamSource.stable_id == stable_id)
                .with_for_update()
            )
        ).all()
    )
    identity = await session.scalar(
        select(CatalogIdentity).where(CatalogIdentity.stable_id == stable_id).with_for_update()
    )
    if identity is None:
        raise IdentityError("AI_STP_NOT_FOUND", "catalog line not found")
    if identity.owner_account_id != expected_owner_account_id:
        raise IdentityError(
            "AI_STP_FOREIGN_LINE_OWNERSHIP", "the catalog line is owned by another account"
        )
    if identity.ownership_revision_id != expected_ownership_revision_id:
        raise IdentityError(
            "AI_STP_STALE_OWNERSHIP_REVISION",
            "the expected catalog-line ownership revision is no longer current",
        )
    if identity.owner_account_id == recipient_account_id:
        raise IdentityError("AI_STP_CONFLICT", "recipient already owns the catalog line")
    claim = await session.scalar(
        select(OwnershipClaim)
        .where(
            OwnershipClaim.stable_id == stable_id,
            OwnershipClaim.to_account_id == recipient_account_id,
            OwnershipClaim.idempotency_key == case.idempotency_key,
        )
        .with_for_update()
    )
    if claim is not None and claim.state != "requested":
        raise IdentityError("AI_STP_CONFLICT", "the ownership request is no longer pending")
    catalog_versions = list(
        (
            await session.scalars(
                select(CatalogMetadata)
                .where(
                    CatalogMetadata.object_kind == "component",
                    CatalogMetadata.stable_id == stable_id,
                )
                .with_for_update()
            )
        ).all()
    )
    versions = [row.version for row in catalog_versions]
    now = datetime.now(UTC)
    revision = OwnershipRevision(
        id=new_id("operation"),
        claim_id=claim.id if claim is not None else None,
        case_id=case.id,
        stable_id=stable_id,
        from_account_id=identity.owner_account_id,
        to_account_id=recipient_account_id,
        major_lines=_major_lines([item for item in versions if item]),
        reason=reason,
        evidence=evidence,
        staff_account_id=operator_account_id,
    )
    session.add(revision)
    await session.flush()
    identity.owner_account_id = recipient_account_id
    identity.ownership_revision_id = revision.id
    case.state = "resolved"
    if claim is not None:
        claim.state = "approved"
        claim.decided_at = now
        claim.staff_account_id = operator_account_id
        claim.decision_reason = reason
    for source in sources:
        source.enabled = False
        source.inventory_state = "transferred"
        source.update_policy = "disabled"
        source.ownership_revision_id = revision.id
        attempts = list(
            (
                await session.scalars(
                    select(OfficialUpstreamSync).where(OfficialUpstreamSync.source_id == source.id)
                )
            ).all()
        )
        for attempt in attempts:
            if attempt.state in _TERMINAL_ATTEMPTS:
                continue
            attempt.state = "cancelled_transferred"
            attempt.result = "failed"
            attempt.error_code = "cancelled_transferred"
            attempt.error_class = "stale_ownership_fence"
            attempt.cancelled_at = now
            if attempt.outbox_id:
                outbox = await session.get(OfficialSyncOutbox, attempt.outbox_id)
                if outbox is not None and outbox.state == "pending":
                    outbox.state = "cancelled"
            if attempt.job_id is not None:
                job = await session.get(Job, attempt.job_id)
                if job is not None and job.state in CLAIMABLE_STATES:
                    job.state = JobState.CANCELLED
            elif attempt.trigger_key:
                await cancel(
                    session,
                    idempotency_key=f"official-upstream-sync:{source.id}:{attempt.trigger_key}",
                )
        pending = list(
            (
                await session.scalars(
                    select(OfficialSyncOutbox).where(
                        OfficialSyncOutbox.source_id == source.id,
                        OfficialSyncOutbox.state == "pending",
                    )
                )
            ).all()
        )
        for outbox in pending:
            outbox.state = "cancelled"
        queued = list(
            (
                await session.scalars(
                    select(Job).where(
                        Job.job_type == JobType.OFFICIAL_UPSTREAM_SYNC,
                        Job.state.in_(tuple(CLAIMABLE_STATES)),
                    )
                )
            ).all()
        )
        for job in queued:
            payload = dict(job.payload)
            if payload.get("source_id") == source.id:
                job.state = JobState.CANCELLED
    for metadata in catalog_versions:
        metadata.owner_account_id = recipient_account_id
    session.add(
        AuditEvent(
            actor_account_id=operator_account_id,
            action="catalog.ownership_transferred",
            target_table="catalog_identity",
            target_id=stable_id,
            reason=reason,
            payload={
                "case_id": case_id,
                "from_account_id": revision.from_account_id,
                "to_account_id": recipient_account_id,
                "ownership_revision_id": revision.id,
            },
        )
    )
    if claim is not None:
        session.add(
            AuditEvent(
                actor_account_id=operator_account_id,
                action="ownership.claim_approved",
                target_table="ownership_claim",
                target_id=claim.id,
                reason=reason,
                payload={
                    "case_id": case_id,
                    "stable_id": stable_id,
                    "ownership_revision_id": revision.id,
                },
            )
        )
    await session.flush()
    return revision


async def apply_author_verification(
    session: AsyncSession,
    *,
    subject_account_id: str,
    verified: bool,
    reason: str,
    operator_account_id: str,
    case_id: str | None = None,
) -> AccountAuthorVerification:
    """Grant or revoke author_verified without an HTTP decision route."""
    if case_id:
        case = await session.get(ReportCase, case_id)
        if case is None:
            raise IdentityError("AI_STP_NOT_FOUND", "request case not found")
        if case.topic != "verification_request":
            raise IdentityError("AI_STP_VALIDATION_ERROR", "case is not a verification request")
        case.state = "resolved"
    subject = await session.get(Account, subject_account_id)
    if subject is None:
        raise IdentityError("AI_STP_NOT_FOUND", "account not found")
    row = await session.get(AccountAuthorVerification, subject_account_id)
    if row is None:
        row = AccountAuthorVerification(
            account_id=subject_account_id,
            verified=verified,
            reason=reason,
            issued_by_account_id=operator_account_id,
        )
        session.add(row)
    else:
        row.verified = verified
        row.reason = reason
        row.issued_by_account_id = operator_account_id
    versions = list(
        (
            await session.scalars(
                select(CatalogMetadata).where(
                    CatalogMetadata.owner_account_id == subject_account_id
                )
            )
        ).all()
    )
    for version in versions:
        version.author_verified = verified
        if verified and version.component_verified:
            version.trust_lane = "authoritative"
        elif version.trust_lane == "authoritative" and not verified:
            version.trust_lane = "experimental"
    action = "staff.author_verified_issued" if verified else "staff.author_verified_revoked"
    session.add(
        AuditEvent(
            actor_account_id=operator_account_id,
            action=action,
            target_table="account_author_verification",
            target_id=subject_account_id,
            reason=reason,
            payload={"case_id": case_id, "verified": verified},
        )
    )
    await session.flush()
    from ai_stp_platform.catalog_search import upsert_catalog_search_projection

    for object_kind, stable_id in sorted(
        {(version.object_kind, version.stable_id) for version in versions}
    ):
        await upsert_catalog_search_projection(
            session, object_kind=object_kind, stable_id=stable_id
        )
    return row


def official_account_id() -> str:
    return OFFICIAL_ACCOUNT_ID
