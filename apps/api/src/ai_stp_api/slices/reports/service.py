"""Report cases and staff moderation (SPEC-026 / SPEC-016)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_contracts.http import PageInfo
from ai_stp_contracts.owner import StaffReportDetail, StaffReportListResponse, StaffReportSummary
from ai_stp_contracts.reports import (
    ReportCaseCreateRequest,
    ReportCaseListResponse,
    ReportCaseResponse,
    StaffActionResponse,
    StaffAuthorVerifiedRequest,
    StaffLifecycleRequest,
    StaffTriageRequest,
)
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import (
    Account,
    AccountAuthorVerification,
    CatalogMetadata,
    ReportCase,
)

# Forbidden automatic payload keys (report-case.md).
_FORBIDDEN_PAYLOAD_MARKERS = (
    "password",
    "secret",
    "token",
    "private_key",
    ".env",
    "home/",
    "c:\\users\\",
)

_RATE_LIMIT = 20
_RATE_WINDOW = timedelta(hours=1)


def _ts(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def case_to_wire(row: ReportCase) -> ReportCaseResponse:
    return ReportCaseResponse(
        schema_version=1,
        case_id=row.id,
        object_kind=row.object_kind,  # type: ignore[arg-type]
        stable_id=row.stable_id,
        version=row.version,
        state=row.state,  # type: ignore[arg-type]
        vulnerability=row.vulnerability,
        created_at=_ts(row.created_at),
    )


def _scan_forbidden(text: str) -> None:
    lowered = text.lower()
    for marker in _FORBIDDEN_PAYLOAD_MARKERS:
        if marker in lowered:
            raise ApiError(ErrorCategory.VALIDATION, "report payload contains forbidden content")


async def require_staff(ctx: AuthContext, staff_ids: frozenset[str]) -> None:
    if ctx.account_id not in staff_ids:
        raise ApiError(ErrorCategory.PERMISSION, "staff allowlist required")


async def create_report(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    body: ReportCaseCreateRequest,
) -> ReportCaseResponse:
    if body.diagnostics and not body.diagnostics_previewed:
        raise ApiError(ErrorCategory.VALIDATION, "diagnostics require preview acknowledgment")
    _scan_forbidden(body.diagnostics)
    _scan_forbidden(body.error_code)

    existing = await db.scalar(
        select(ReportCase).where(
            ReportCase.reporter_account_id == ctx.account_id,
            ReportCase.idempotency_key == body.idempotency_key,
        )
    )
    if existing is not None:
        return case_to_wire(existing)

    since = datetime.now(UTC) - _RATE_WINDOW
    count = await db.scalar(
        select(func.count())
        .select_from(ReportCase)
        .where(
            ReportCase.reporter_account_id == ctx.account_id,
            ReportCase.created_at >= since,
        )
    )
    if count is not None and int(count) >= _RATE_LIMIT:
        raise ApiError(ErrorCategory.RATE_LIMITED, "report rate limit exceeded")

    group_key = f"{body.object_kind}:{body.stable_id}:{body.version}"
    state = "security_escalated" if body.vulnerability else "submitted"
    case = ReportCase(
        id=new_id("report"),
        reporter_account_id=ctx.account_id,
        object_kind=body.object_kind,
        stable_id=body.stable_id,
        version=body.version,
        content_digest=body.content_digest,
        state=state,
        vulnerability=body.vulnerability,
        payload={
            "harness_id": body.harness_id,
            "harness_version": body.harness_version,
            "provider_version": body.provider_version,
            "operation_id": body.operation_id,
            "error_code": body.error_code,
            "validation_snapshot_ids": list(body.validation_snapshot_ids),
            "diagnostics_len": len(body.diagnostics),
        },
        group_key=group_key,
        idempotency_key=body.idempotency_key,
    )
    db.add(case)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="report.created",
        target_table="report_case",
        target_id=case.id,
        payload={"group_key": group_key, "vulnerability": body.vulnerability},
    )
    await db.flush()
    return case_to_wire(case)


async def list_reports(db: AsyncSession, *, ctx: AuthContext) -> ReportCaseListResponse:
    rows = list(
        (
            await db.execute(
                select(ReportCase).where(ReportCase.reporter_account_id == ctx.account_id)
            )
        )
        .scalars()
        .all()
    )
    return ReportCaseListResponse(schema_version=1, items=[case_to_wire(r) for r in rows])


async def list_staff_reports(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    staff_ids: frozenset[str],
    page_size: int = 20,
) -> StaffReportListResponse:
    await require_staff(ctx, staff_ids)
    rows = list(
        (
            await db.execute(
                select(ReportCase)
                .where(ReportCase.state != "security_escalated")
                .order_by(ReportCase.created_at.desc())
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    items = [
        StaffReportSummary(
            schema_version=1,
            case_id=row.id,
            object_kind=row.object_kind,  # type: ignore[arg-type]
            stable_id=row.stable_id,
            version=row.version,
            state=row.state,
            vulnerability=row.vulnerability,
            created_at=_ts(row.created_at),
            content_digest=row.content_digest,
        )
        for row in rows
    ]
    return StaffReportListResponse(
        schema_version=1,
        items=items,
        page=PageInfo(schema_version=1, next_cursor=None, page_size=max(page_size, 1)),
    )


async def read_staff_report(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    staff_ids: frozenset[str],
    case_id: str,
) -> StaffReportDetail:
    await require_staff(ctx, staff_ids)
    row = await db.get(ReportCase, case_id)
    if row is None or row.state == "security_escalated":
        raise ApiError(ErrorCategory.NOT_FOUND, "report case not found")
    payload = row.payload
    error_code = payload.get("error_code")
    harness_id = payload.get("harness_id")
    return StaffReportDetail(
        schema_version=1,
        case_id=row.id,
        object_kind=row.object_kind,  # type: ignore[arg-type]
        stable_id=row.stable_id,
        version=row.version,
        state=row.state,
        vulnerability=row.vulnerability,
        created_at=_ts(row.created_at),
        content_digest=row.content_digest,
        error_code=str(error_code) if isinstance(error_code, str) else "",
        harness_id=str(harness_id) if isinstance(harness_id, str) else "",
    )


async def staff_triage(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    staff_ids: frozenset[str],
    case_id: str,
    body: StaffTriageRequest,
) -> ReportCaseResponse:
    await require_staff(ctx, staff_ids)
    case = await db.get(ReportCase, case_id)
    if case is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "report case not found")
    case.state = body.state
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="report.triaged",
        target_table="report_case",
        target_id=case.id,
        reason=body.reason,
        payload={"state": body.state},
    )
    await db.flush()
    return case_to_wire(case)


async def staff_lifecycle(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    staff_ids: frozenset[str],
    body: StaffLifecycleRequest,
) -> StaffActionResponse:
    await require_staff(ctx, staff_ids)
    row = await db.scalar(
        select(CatalogMetadata).where(
            CatalogMetadata.object_kind == body.object_kind,
            CatalogMetadata.stable_id == body.stable_id,
            CatalogMetadata.version == body.version,
        )
    )
    if row is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "version not found")
    if body.action == "block":
        row.lifecycle_state = "blocked"
    elif body.action == "hide":
        row.lifecycle_state = "hidden"
    elif body.action == "restore":
        row.lifecycle_state = "active"
    else:
        raise ApiError(ErrorCategory.VALIDATION, "unknown lifecycle action")
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action=f"staff.version_{body.action}",
        target_table="catalog_metadata",
        target_id=str(row.id),
        reason=body.reason,
        payload={
            "stable_id": body.stable_id,
            "version": body.version,
            "lifecycle_state": row.lifecycle_state,
        },
    )
    await db.flush()
    return StaffActionResponse(schema_version=1, applied=True, action=body.action)


async def staff_author_verified(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    staff_ids: frozenset[str],
    body: StaffAuthorVerifiedRequest,
) -> StaffActionResponse:
    await require_staff(ctx, staff_ids)
    subject = await db.get(Account, body.subject_account_id)
    if subject is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "account not found")
    row = await db.get(AccountAuthorVerification, body.subject_account_id)
    if row is None:
        row = AccountAuthorVerification(
            account_id=body.subject_account_id,
            verified=body.verified,
            reason=body.reason,
            issued_by_account_id=ctx.account_id,
        )
        db.add(row)
    else:
        row.verified = body.verified
        row.reason = body.reason
        row.issued_by_account_id = ctx.account_id
    # Forward-only projection: update catalog author_verified for owned versions.
    versions = list(
        (
            await db.execute(
                select(CatalogMetadata).where(
                    CatalogMetadata.owner_account_id == body.subject_account_id
                )
            )
        )
        .scalars()
        .all()
    )
    for version in versions:
        version.author_verified = body.verified
        if body.verified and version.component_verified:
            version.trust_lane = "authoritative"
        elif version.trust_lane == "authoritative" and not body.verified:
            version.trust_lane = "experimental"
    action = "staff.author_verified_issued" if body.verified else "staff.author_verified_revoked"
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action=action,
        target_table="account_author_verification",
        target_id=body.subject_account_id,
        reason=body.reason,
    )
    await db.flush()
    return StaffActionResponse(
        schema_version=1,
        applied=True,
        action="author_verified_issue" if body.verified else "author_verified_revoke",
    )
