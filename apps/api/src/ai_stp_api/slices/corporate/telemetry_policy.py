"""Corporate telemetry governance routes: ingest boundary, reads, policy, audit."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate.service import (
    authorize,
    authorize_idempotent,
    mutation_fingerprint,
    store_mutation_receipt,
)
from ai_stp_contracts.telemetry_privacy import (
    CorporateTelemetryAggregate,
    CorporateTelemetryAggregateList,
    CorporateTelemetryAggregateQuery,
    CorporateTelemetryAuditList,
    CorporateTelemetryAuditQuery,
    CorporateTelemetryAuditView,
    CorporateTelemetryEventBatchRequest,
    CorporateTelemetryEventBatchResult,
    CorporateTelemetryEventList,
    CorporateTelemetryEventQuery,
    CorporateTelemetryEventRequest,
    CorporateTelemetryEventView,
    CorporateTelemetryExport,
    CorporateTelemetryExportQuery,
    CorporateTelemetryPolicyRequest,
    CorporateTelemetryPolicyView,
    TelemetryEventKind,
    TelemetryEventOutcome,
    TelemetryHealth,
    TelemetryLegalBasis,
    TelemetrySubjectState,
)
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.telemetry_policy_models import (
    TelemetryAudit,
    TelemetryEvent,
    TelemetryPolicy,
)
from ai_stp_platform.telemetry_privacy_service import (
    TelemetryBoundaryError,
    TelemetryPolicyConflictError,
    TelemetrySubjectRevokedError,
    aggregate_events,
    export_events,
    ingest_event,
    list_events,
    list_privileged_access,
    read_policy,
    record_privileged_access,
    write_policy,
)

router = APIRouter(tags=["corporate"])


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _ts(value: datetime | None) -> str | None:
    if value is None:
        return None
    return format_timestamp(value if value.tzinfo is not None else value.replace(tzinfo=UTC))


def _parse_ts(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _event_view(row: TelemetryEvent) -> CorporateTelemetryEventView:
    return CorporateTelemetryEventView(
        organization_id=row.organization_id,
        kind=cast(TelemetryEventKind, row.kind),
        event_id=row.event_id,
        account_id=row.account_id,
        device_id=row.device_id,
        project_id=row.project_id,
        harness=row.harness,
        harness_version=row.harness_version,
        provider_name=row.provider_name,
        provider_version=row.provider_version,
        capabilities=list(row.capabilities or []),
        last_sync_at=_ts(row.last_sync_at),
        health=cast(TelemetryHealth | None, row.health),
        setup_id=row.setup_id,
        component_kind=row.component_kind,
        component_stable_id=row.component_stable_id,
        component_version=row.component_version,
        outcome=cast(TelemetryEventOutcome | None, row.outcome),
        subject_state=cast(TelemetrySubjectState, row.subject_state),
        occurred_at=_ts(row.occurred_at) or "",
        received_at=_ts(row.received_at) or "",
    )


def _policy_view(row: TelemetryPolicy) -> CorporateTelemetryPolicyView:
    return CorporateTelemetryPolicyView(
        organization_id=row.organization_id,
        raw_retention_days=row.raw_retention_days,
        aggregate_retention_days=row.aggregate_retention_days,
        legal_basis=cast(TelemetryLegalBasis, row.legal_basis),
        notice_text=row.notice_text,
        notice_revision=row.notice_revision,
        policy_version=row.policy_version,
        updated_at=_ts(row.updated_at) or "",
    )


def _audit_view(row: TelemetryAudit) -> CorporateTelemetryAuditView:
    return CorporateTelemetryAuditView(
        audit_id=row.id,
        organization_id=row.organization_id,
        actor_account_id=row.actor_account_id,
        action=row.action,
        target_table=row.target_table,
        target_id=row.target_id,
        detail=dict(row.detail or {}),
        request_id=row.request_id,
        created_at=_ts(row.created_at) or "",
    )


def _event_fields(event: Any) -> dict[str, Any]:
    return {key: value for key, value in event.model_dump(mode="json").items() if value is not None}


async def _ingest(
    db: AsyncSession,
    *,
    organization_id: str,
    event: Any,
) -> tuple[TelemetryEvent, bool]:
    try:
        return await ingest_event(
            db,
            organization_id=organization_id,
            kind=event.kind,
            fields=_event_fields(event),
        )
    except TelemetryBoundaryError as error:
        raise ApiError(ErrorCategory.VALIDATION, str(error)) from error
    except TelemetrySubjectRevokedError as error:
        raise ApiError(ErrorCategory.CONFLICT, "telemetry subject revoked or erased") from error


@router.post(
    "/corporate/organizations/{organization_id}/telemetry/events",
    response_model=CorporateTelemetryEventView,
)
async def ingest_telemetry_event(
    organization_id: str,
    payload: CorporateTelemetryEventRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateTelemetryEventView:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json"))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="telemetry.write",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="telemetry.ingest",
        fingerprint=fingerprint,
        request_id=_request_id(request),
    )
    if receipt is not None:
        return CorporateTelemetryEventView.model_validate(receipt.response_body)
    row, _created = await _ingest(db, organization_id=organization.id, event=payload.event)
    view = _event_view(row)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization.id,
        action="telemetry.ingest",
        target_table="telemetry_event",
        target_id=row.event_id,
        request_id=_request_id(request),
        payload={"event_kind": row.kind},
    )
    await store_mutation_receipt(
        db,
        organization_id=organization.id,
        key=payload.idempotency_key,
        operation="telemetry.ingest",
        fingerprint=fingerprint,
        response=view,
    )
    return view


@router.post(
    "/corporate/organizations/{organization_id}/telemetry/events/batch",
    response_model=CorporateTelemetryEventBatchResult,
)
async def ingest_telemetry_event_batch(
    organization_id: str,
    payload: CorporateTelemetryEventBatchRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateTelemetryEventBatchResult:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json"))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="telemetry.write",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="telemetry.ingest.batch",
        fingerprint=fingerprint,
        request_id=_request_id(request),
    )
    if receipt is not None:
        return CorporateTelemetryEventBatchResult.model_validate(receipt.response_body)
    items: list[CorporateTelemetryEventView] = []
    deduplicated = 0
    for event in payload.events:
        row, created = await _ingest(db, organization_id=organization.id, event=event)
        items.append(_event_view(row))
        if not created:
            deduplicated += 1
    result = CorporateTelemetryEventBatchResult(
        organization_id=organization.id,
        accepted=len(items) - deduplicated,
        deduplicated=deduplicated,
        items=items,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization.id,
        action="telemetry.ingest.batch",
        target_table="telemetry_event",
        target_id=organization.id,
        request_id=_request_id(request),
        payload={"accepted": result.accepted, "deduplicated": deduplicated},
    )
    await store_mutation_receipt(
        db,
        organization_id=organization.id,
        key=payload.idempotency_key,
        operation="telemetry.ingest.batch",
        fingerprint=fingerprint,
        response=result,
    )
    return result


@router.get(
    "/corporate/organizations/{organization_id}/telemetry/events",
    response_model=CorporateTelemetryEventList,
)
async def list_telemetry_events(
    organization_id: str,
    query: Annotated[CorporateTelemetryEventQuery, Query()],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateTelemetryEventList:
    organization, _membership = await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="telemetry.list",
    )
    rows = await list_events(
        db,
        organization_id=organization.id,
        event_kind=query.event_kind,
        account_id=query.account_id,
        before_occurred_at=_parse_ts(query.before_occurred_at),
        before_id=query.before_id,
        limit=query.limit,
    )
    page = rows[: query.limit]
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization.id,
        action="telemetry.list",
        target_table="telemetry_event",
        target_id=organization.id,
        request_id=_request_id(request),
    )
    await record_privileged_access(
        db,
        organization_id=organization.id,
        actor_account_id=ctx.account_id,
        action="telemetry.list",
        target_table="telemetry_event",
        target_id=organization.id,
        request_id=_request_id(request),
        detail={"returned": len(page), "event_kind": query.event_kind},
    )
    has_next = len(rows) > query.limit
    return CorporateTelemetryEventList(
        organization_id=organization.id,
        items=[_event_view(row) for row in page],
        next_before_occurred_at=_ts(page[-1].occurred_at) if has_next else None,
        next_before_id=page[-1].event_id if has_next else None,
    )


@router.get(
    "/corporate/organizations/{organization_id}/telemetry/aggregates",
    response_model=CorporateTelemetryAggregateList,
)
async def read_telemetry_aggregates(
    organization_id: str,
    query: Annotated[CorporateTelemetryAggregateQuery, Query()],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateTelemetryAggregateList:
    organization, _membership = await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="telemetry.read",
    )
    rows = await aggregate_events(
        db,
        organization_id=organization.id,
        occurred_from=_parse_ts(query.occurred_from),
        occurred_to=_parse_ts(query.occurred_to),
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization.id,
        action="telemetry.aggregate",
        target_table="telemetry_event",
        target_id=organization.id,
        request_id=_request_id(request),
    )
    await record_privileged_access(
        db,
        organization_id=organization.id,
        actor_account_id=ctx.account_id,
        action="telemetry.aggregate",
        target_table="telemetry_event",
        target_id=organization.id,
        request_id=_request_id(request),
        detail={"buckets": len(rows)},
    )
    return CorporateTelemetryAggregateList(
        organization_id=organization.id,
        items=[
            CorporateTelemetryAggregate(
                day=day,
                event_kind=cast(TelemetryEventKind, kind),
                outcome=outcome,
                event_count=count,
            )
            for day, kind, outcome, count in rows
        ],
    )


@router.get(
    "/corporate/organizations/{organization_id}/telemetry/export",
    response_model=CorporateTelemetryExport,
)
async def export_telemetry_events(
    organization_id: str,
    query: Annotated[CorporateTelemetryExportQuery, Query()],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateTelemetryExport:
    organization, _membership = await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="telemetry.export",
    )
    rows = await export_events(
        db,
        organization_id=organization.id,
        occurred_from=_parse_ts(query.occurred_from),
        occurred_to=_parse_ts(query.occurred_to),
        limit=query.limit,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization.id,
        action="telemetry.export",
        target_table="telemetry_event",
        target_id=organization.id,
        request_id=_request_id(request),
        payload={"count": len(rows)},
    )
    await record_privileged_access(
        db,
        organization_id=organization.id,
        actor_account_id=ctx.account_id,
        action="telemetry.export",
        target_table="telemetry_event",
        target_id=organization.id,
        request_id=_request_id(request),
        detail={"count": len(rows)},
    )
    return CorporateTelemetryExport(
        organization_id=organization.id,
        exported_at=format_timestamp(datetime.now(UTC)),
        items=[_event_view(row) for row in rows],
    )


@router.get(
    "/corporate/organizations/{organization_id}/telemetry/audit",
    response_model=CorporateTelemetryAuditList,
)
async def list_telemetry_audit(
    organization_id: str,
    query: Annotated[CorporateTelemetryAuditQuery, Query()],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateTelemetryAuditList:
    organization, _membership = await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="telemetry.list",
    )
    await record_privileged_access(
        db,
        organization_id=organization.id,
        actor_account_id=ctx.account_id,
        action="telemetry.audit.list",
        target_table="telemetry_audit",
        target_id=organization.id,
        request_id=_request_id(request),
        detail={"limit": query.limit},
    )
    rows = await list_privileged_access(
        db,
        organization_id=organization.id,
        before_id=query.before_id,
        limit=query.limit,
    )
    page = rows[: query.limit]
    return CorporateTelemetryAuditList(
        organization_id=organization.id,
        items=[_audit_view(row) for row in page],
        next_before_id=page[-1].id if len(rows) > query.limit else None,
    )


@router.get(
    "/corporate/organizations/{organization_id}/telemetry/policy",
    response_model=CorporateTelemetryPolicyView,
)
async def read_telemetry_policy(
    organization_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateTelemetryPolicyView:
    organization, _membership = await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="telemetry.read",
    )
    row = await read_policy(db, organization_id=organization.id)
    if row is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "telemetry policy is not configured")
    return _policy_view(row)


@router.put(
    "/corporate/organizations/{organization_id}/telemetry/policy",
    response_model=CorporateTelemetryPolicyView,
)
async def write_telemetry_policy(
    organization_id: str,
    payload: CorporateTelemetryPolicyRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateTelemetryPolicyView:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json"))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="telemetry.manage",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="telemetry.policy.write",
        fingerprint=fingerprint,
        request_id=_request_id(request),
    )
    if receipt is not None:
        return CorporateTelemetryPolicyView.model_validate(receipt.response_body)
    try:
        row = await write_policy(
            db,
            organization_id=organization.id,
            raw_retention_days=payload.raw_retention_days,
            aggregate_retention_days=payload.aggregate_retention_days,
            legal_basis=payload.legal_basis,
            notice_text=payload.notice_text,
            notice_revision=payload.notice_revision,
            expected_policy_revision=payload.expected_policy_revision,
            updated_by=ctx.account_id,
        )
    except TelemetryPolicyConflictError as error:
        raise ApiError(ErrorCategory.CONFLICT, str(error)) from error
    view = _policy_view(row)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization.id,
        action="telemetry.policy.write",
        target_table="telemetry_policy",
        target_id=organization.id,
        reason=payload.reason,
        request_id=_request_id(request),
        payload={"policy_version": row.policy_version},
    )
    await record_privileged_access(
        db,
        organization_id=organization.id,
        actor_account_id=ctx.account_id,
        action="telemetry.policy.write",
        target_table="telemetry_policy",
        target_id=organization.id,
        request_id=_request_id(request),
        detail={"policy_version": row.policy_version},
    )
    await store_mutation_receipt(
        db,
        organization_id=organization.id,
        key=payload.idempotency_key,
        operation="telemetry.policy.write",
        fingerprint=fingerprint,
        response=view,
    )
    return view


__all__ = ["router"]
