"""Ownership claim request, staff decision, and immutable revision history."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.reports.service import require_staff
from ai_stp_contracts.ownership import (
    OwnershipClaimCreateRequest,
    OwnershipClaimDecisionRequest,
    OwnershipClaimPreview,
    OwnershipClaimResponse,
    OwnershipRevisionListResponse,
    OwnershipRevisionView,
)
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import (
    AccountAuthorVerification,
    CatalogMetadata,
    OwnershipClaim,
    OwnershipRevision,
)
from ai_stp_platform.official_upstream import OFFICIAL_ACCOUNT_ID


def _ts(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _major_lines(versions: list[str]) -> list[int]:
    majors: set[int] = set()
    for version in versions:
        major, _sep, _minor = version.partition(".")
        if major.isdigit():
            majors.add(int(major))
    return sorted(majors)


def _preview_from_rows(stable_id: str, rows: list[CatalogMetadata]) -> OwnershipClaimPreview:
    versions = sorted({str(row.version) for row in rows if row.version})
    owner = rows[0].owner_account_id
    name = next((str(row.name) for row in rows if row.name), "")
    return OwnershipClaimPreview(
        schema_version=1,
        object_kind="component",
        stable_id=stable_id,
        name=name,
        current_owner_account_id=owner,
        versions=versions,  # type: ignore[arg-type]
        major_lines=_major_lines(versions),
    )


def _claim_to_wire(row: OwnershipClaim) -> OwnershipClaimResponse:
    preview = OwnershipClaimPreview.model_validate(row.preview)
    return OwnershipClaimResponse(
        schema_version=1,
        claim_id=row.id,
        stable_id=row.stable_id,
        requester_account_id=row.requester_account_id,
        from_account_id=row.from_account_id,
        to_account_id=row.to_account_id,
        reason=row.reason,
        evidence=row.evidence,
        state=row.state,  # type: ignore[arg-type]
        preview=preview,
        created_at=_ts(row.created_at),
        decided_at=None if row.decided_at is None else _ts(row.decided_at),
        staff_account_id=row.staff_account_id,
        decision_reason=row.decision_reason,
    )


def _revision_to_wire(row: OwnershipRevision) -> OwnershipRevisionView:
    majors = [int(item) for item in row.major_lines]
    return OwnershipRevisionView(
        schema_version=1,
        revision_id=row.id,
        claim_id=row.claim_id,
        stable_id=row.stable_id,
        from_account_id=row.from_account_id,
        to_account_id=row.to_account_id,
        major_lines=majors,
        reason=row.reason,
        staff_account_id=row.staff_account_id,
        created_at=_ts(row.created_at),
    )


async def _component_rows(db: AsyncSession, stable_id: str) -> list[CatalogMetadata]:
    rows = list(
        (
            await db.execute(
                select(CatalogMetadata)
                .where(
                    CatalogMetadata.object_kind == "component",
                    CatalogMetadata.stable_id == stable_id,
                )
                .order_by(CatalogMetadata.version)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise ApiError(ErrorCategory.NOT_FOUND, "catalog component not found")
    return rows


async def create_claim(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    body: OwnershipClaimCreateRequest,
) -> OwnershipClaimResponse:
    existing = await db.scalar(
        select(OwnershipClaim).where(OwnershipClaim.idempotency_key == body.idempotency_key)
    )
    if existing is not None:
        if existing.requester_account_id != ctx.account_id:
            raise ApiError(ErrorCategory.CONFLICT, "idempotency key already used")
        return _claim_to_wire(existing)

    verification = await db.get(AccountAuthorVerification, ctx.account_id)
    if verification is None or not verification.verified:
        raise ApiError(ErrorCategory.PERMISSION, "verified maintainer required")

    rows = await _component_rows(db, body.stable_id)
    owners = {row.owner_account_id for row in rows}
    if owners != {OFFICIAL_ACCOUNT_ID}:
        raise ApiError(
            ErrorCategory.PRECONDITION, "only official catalog components may be claimed"
        )
    if ctx.account_id == OFFICIAL_ACCOUNT_ID:
        raise ApiError(ErrorCategory.CONFLICT, "the official owner cannot claim its own component")

    preview = _preview_from_rows(body.stable_id, rows)
    claim = OwnershipClaim(
        id=new_id("operation"),
        object_kind="component",
        stable_id=body.stable_id,
        requester_account_id=ctx.account_id,
        from_account_id=OFFICIAL_ACCOUNT_ID,
        to_account_id=ctx.account_id,
        reason=body.reason,
        evidence=body.evidence,
        state="requested",
        preview=preview.model_dump(mode="json"),
        idempotency_key=body.idempotency_key,
    )
    db.add(claim)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="ownership.claim_requested",
        target_table="ownership_claim",
        target_id=claim.id,
        reason=body.reason,
        payload={"stable_id": body.stable_id, "major_lines": preview.major_lines},
    )
    await db.flush()
    return _claim_to_wire(claim)


async def read_claim(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    claim_id: str,
    staff_ids: frozenset[str],
) -> OwnershipClaimResponse:
    claim = await db.get(OwnershipClaim, claim_id)
    if claim is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "ownership claim not found")
    if ctx.account_id != claim.requester_account_id and ctx.account_id not in staff_ids:
        raise ApiError(ErrorCategory.PERMISSION, "staff allowlist required")
    return _claim_to_wire(claim)


async def decide_claim(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    staff_ids: frozenset[str],
    claim_id: str,
    body: OwnershipClaimDecisionRequest,
    approved: bool,
) -> OwnershipClaimResponse:
    await require_staff(ctx, staff_ids)
    claim = await db.get(OwnershipClaim, claim_id)
    if claim is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "ownership claim not found")
    wanted = "approved" if approved else "denied"
    if claim.state != "requested":
        if claim.state == wanted:
            return _claim_to_wire(claim)
        raise ApiError(ErrorCategory.CONFLICT, "ownership claim is already decided")

    claim.state = wanted
    claim.decided_at = datetime.now(UTC)
    claim.staff_account_id = ctx.account_id
    claim.decision_reason = body.reason
    action = "ownership.claim_approved" if approved else "ownership.claim_denied"
    if approved:
        rows = await _component_rows(db, claim.stable_id)
        for row in rows:
            row.owner_account_id = claim.to_account_id
        revision = OwnershipRevision(
            id=new_id("operation"),
            claim_id=claim.id,
            stable_id=claim.stable_id,
            from_account_id=claim.from_account_id,
            to_account_id=claim.to_account_id,
            major_lines=list(OwnershipClaimPreview.model_validate(claim.preview).major_lines),
            reason=body.reason,
            evidence=claim.evidence,
            staff_account_id=ctx.account_id,
        )
        db.add(revision)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action=action,
        target_table="ownership_claim",
        target_id=claim.id,
        reason=body.reason,
        payload={"stable_id": claim.stable_id, "state": wanted},
    )
    await db.flush()
    return _claim_to_wire(claim)


async def list_revisions(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    stable_id: str,
    staff_ids: frozenset[str],
) -> OwnershipRevisionListResponse:
    rows = await _component_rows(db, stable_id)
    owners = {row.owner_account_id for row in rows}
    if ctx.account_id not in owners and ctx.account_id not in staff_ids:
        prior = await db.scalar(
            select(OwnershipRevision.id).where(
                OwnershipRevision.stable_id == stable_id,
                OwnershipRevision.from_account_id == ctx.account_id,
            )
        )
        if prior is None:
            raise ApiError(ErrorCategory.PERMISSION, "staff allowlist required")
    items = list(
        (
            await db.execute(
                select(OwnershipRevision)
                .where(OwnershipRevision.stable_id == stable_id)
                .order_by(OwnershipRevision.created_at)
            )
        )
        .scalars()
        .all()
    )
    return OwnershipRevisionListResponse(
        schema_version=1,
        stable_id=stable_id,
        items=[_revision_to_wire(item) for item in items],
    )
