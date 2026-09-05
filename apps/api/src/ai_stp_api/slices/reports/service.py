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
    StaffAuthorVerificationRequest,
    StaffLifecycleRequest,
    StaffTriageRequest,
)
from ai_stp_foundation.ids import new_id
from ai_stp_platform.external_catalog import COUNTRY_CODES, canonical_external_url
from ai_stp_platform.models import (
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
        topic=row.topic,  # type: ignore[arg-type]
        object_kind=row.object_kind or "",  # type: ignore[arg-type]
        stable_id=row.stable_id or "",
        version=row.version or "",  # type: ignore[arg-type]
        state=row.state,  # type: ignore[arg-type]
        vulnerability=row.vulnerability,
        locale=row.locale,  # type: ignore[arg-type]
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

    if body.service:
        canonical = canonical_external_url(body.service.primary_url)
        if canonical is None:
            raise ApiError(
                ErrorCategory.VALIDATION,
                "primary_url must be a shallow public HTTPS URL",
            )
        invalid_codes = sorted(set(body.service.country_codes) - COUNTRY_CODES)
        if invalid_codes:
            raise ApiError(
                ErrorCategory.VALIDATION,
                "unknown country code",
                details={"country_codes": ",".join(invalid_codes)},
            )
        for value in (
            body.service.name,
            body.service.primary_url,
            body.service.description_ru,
            body.service.description_en,
            body.service.source_url,
        ):
            _scan_forbidden(value)
        group_key = f"service:{canonical[1]}"
        request_payload: dict[str, object] = body.service.model_dump(mode="json")
    elif body.country:
        for value in (body.country.name_ru, body.country.name_en):
            _scan_forbidden(value)
        group_key = f"country:{body.country.code}"
        request_payload = body.country.model_dump(mode="json")
    elif body.topic == "component_complaint":
        group_key = f"component_complaint:{body.stable_id}"
        request_payload = {
            "message": body.message,
            "evidence": body.evidence,
            "author_account_id": body.author_account_id,
        }
    elif body.topic == "author_complaint":
        group_key = f"author_complaint:{body.author_account_id}"
        request_payload = {"message": body.message, "evidence": body.evidence}
    elif body.topic == "ownership_transfer":
        group_key = f"ownership_transfer:{body.stable_id}:{body.recipient_account_id}"
        request_payload = {
            "message": body.message,
            "evidence": body.evidence,
            "recipient_account_id": body.recipient_account_id,
            "author_account_id": body.author_account_id,
        }
    elif body.topic == "verification_request":
        group_key = f"verification_request:{body.author_account_id}"
        request_payload = {"message": body.message, "evidence": body.evidence}
    elif body.topic == "other":
        group_key = f"other:{body.subject.strip().casefold()}"
        request_payload = {
            "subject": body.subject,
            "message": body.message,
            "evidence": body.evidence,
        }
    else:
        group_key = f"{body.object_kind}:{body.stable_id}:{body.version}"
        request_payload = {
            "harness_id": body.harness_id,
            "harness_version": body.harness_version,
            "provider_version": body.provider_version,
            "operation_id": body.operation_id,
            "error_code": body.error_code,
            "validation_snapshot_ids": list(body.validation_snapshot_ids),
            "diagnostics_len": len(body.diagnostics),
        }
    if body.message:
        _scan_forbidden(body.message)
    if body.evidence:
        _scan_forbidden(body.evidence)
    if body.subject:
        _scan_forbidden(body.subject)
    state = "security_escalated" if body.vulnerability else "submitted"
    case = ReportCase(
        id=new_id("report"),
        reporter_account_id=ctx.account_id,
        topic=body.topic,
        object_kind=body.object_kind,
        stable_id=body.stable_id,
        version=body.version,
        content_digest=body.content_digest,
        state=state,
        vulnerability=body.vulnerability,
        payload=request_payload,
        locale=body.locale,
        group_key=group_key,
        idempotency_key=body.idempotency_key,
    )
    db.add(case)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="request.created",
        target_table="report_case",
        target_id=case.id,
        payload={"topic": body.topic, "group_key": group_key, "vulnerability": body.vulnerability},
    )
    await db.flush()
    return case_to_wire(case)


async def read_own_report(
    db: AsyncSession, *, ctx: AuthContext, case_id: str
) -> ReportCaseResponse:
    row = await db.get(ReportCase, case_id)
    if row is None or row.reporter_account_id != ctx.account_id:
        raise ApiError(ErrorCategory.NOT_FOUND, "report case not found")
    return case_to_wire(row)


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
            topic=row.topic,  # type: ignore[arg-type]
            object_kind=row.object_kind or "",  # type: ignore[arg-type]
            stable_id=row.stable_id or "",
            version=row.version or "",  # type: ignore[arg-type]
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
        topic=row.topic,  # type: ignore[arg-type]
        object_kind=row.object_kind or "",  # type: ignore[arg-type]
        stable_id=row.stable_id or "",
        version=row.version or "",  # type: ignore[arg-type]
        state=row.state,
        vulnerability=row.vulnerability,
        created_at=_ts(row.created_at),
        content_digest=row.content_digest,
        error_code=str(error_code) if isinstance(error_code, str) else "",
        harness_id=str(harness_id) if isinstance(harness_id, str) else "",
        request_payload=payload,
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
    from ai_stp_platform.seo.enqueue import enqueue_seo_build, mutation_digest

    await enqueue_seo_build(
        db,
        kind=body.object_kind,  # type: ignore[arg-type]
        subject_id=body.stable_id,
        source_digest=mutation_digest(
            body.object_kind,
            body.stable_id,
            body.version,
            row.lifecycle_state,
            row.passport_digest or row.current_revision_id or "",
        ),
    )
    from ai_stp_platform.catalog_search import upsert_catalog_search_projection

    await upsert_catalog_search_projection(
        db, object_kind=body.object_kind, stable_id=body.stable_id
    )
    await db.flush()
    return StaffActionResponse(schema_version=1, applied=True, action=body.action)


async def staff_author_verification(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    staff_ids: frozenset[str],
    body: StaffAuthorVerificationRequest,
) -> StaffActionResponse:
    await require_staff(ctx, staff_ids)
    from ai_stp_platform.catalog_transfer import apply_author_verification

    await apply_author_verification(
        db,
        subject_account_id=body.subject_account_id,
        verified=body.verified,
        reason=body.reason,
        operator_account_id=ctx.account_id,
    )
    return StaffActionResponse(
        schema_version=1,
        applied=True,
        action="author_verified_issued" if body.verified else "author_verified_revoked",
    )
