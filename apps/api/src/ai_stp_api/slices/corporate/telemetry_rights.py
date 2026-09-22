"""Corporate telemetry data-rights routes: notice, revocation, erasure."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate.service import (
    authorize_idempotent,
    mutation_fingerprint,
    store_mutation_receipt,
)
from ai_stp_contracts.telemetry_privacy import (
    CorporateTelemetryDeleteRequest,
    CorporateTelemetryDeleteResult,
    CorporateTelemetryRevokeRequest,
    CorporateTelemetryRightRequest,
    CorporateTelemetryRightView,
    TelemetryLegalBasis,
    TelemetryRightState,
    TelemetrySubjectKind,
)
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.telemetry_policy_models import TelemetryRevocation
from ai_stp_platform.telemetry_privacy_service import (
    TelemetryRightStateError,
    delete_subject,
    record_privileged_access,
    record_right,
    revoke_subject,
)

router = APIRouter(tags=["corporate"])


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _ts(value: datetime | None) -> str | None:
    if value is None:
        return None
    return format_timestamp(value if value.tzinfo is not None else value.replace(tzinfo=UTC))


def _right_view(row: TelemetryRevocation) -> CorporateTelemetryRightView:
    return CorporateTelemetryRightView(
        organization_id=row.organization_id,
        subject_kind=cast(TelemetrySubjectKind, row.subject_kind),
        subject_id=row.subject_id,
        state=cast(TelemetryRightState, row.state),
        legal_basis=cast(TelemetryLegalBasis | None, row.legal_basis),
        notice_revision=row.notice_revision,
        notice_acknowledged_at=_ts(row.notice_acknowledged_at),
        revoked_at=_ts(row.revoked_at),
        deletion_requested_at=_ts(row.deletion_requested_at),
        anonymized_at=_ts(row.anonymized_at),
        deleted_at=_ts(row.deleted_at),
        updated_at=_ts(row.updated_at) or "",
    )


@router.post(
    "/corporate/organizations/{organization_id}/telemetry/rights",
    response_model=CorporateTelemetryRightView,
)
async def record_telemetry_right(
    organization_id: str,
    payload: CorporateTelemetryRightRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateTelemetryRightView:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json"))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="telemetry.manage",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="telemetry.rights.write",
        fingerprint=fingerprint,
        request_id=_request_id(request),
    )
    if receipt is not None:
        return CorporateTelemetryRightView.model_validate(receipt.response_body)
    try:
        row = await record_right(
            db,
            organization_id=organization.id,
            subject_kind=payload.subject_kind,
            subject_id=payload.subject_id,
            legal_basis=payload.legal_basis,
            notice_revision=payload.notice_revision,
            now=datetime.now(UTC),
        )
    except TelemetryRightStateError as error:
        raise ApiError(ErrorCategory.CONFLICT, str(error)) from error
    view = _right_view(row)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization.id,
        action="telemetry.rights.write",
        target_table="telemetry_revocation",
        target_id=f"{row.subject_kind}:{row.subject_id}",
        request_id=_request_id(request),
        payload={"legal_basis": payload.legal_basis},
    )
    await record_privileged_access(
        db,
        organization_id=organization.id,
        actor_account_id=ctx.account_id,
        action="telemetry.rights.write",
        target_table="telemetry_revocation",
        target_id=f"{row.subject_kind}:{row.subject_id}",
        request_id=_request_id(request),
        detail={"subject_kind": row.subject_kind, "state": row.state},
    )
    await store_mutation_receipt(
        db,
        organization_id=organization.id,
        key=payload.idempotency_key,
        operation="telemetry.rights.write",
        fingerprint=fingerprint,
        response=view,
    )
    return view


@router.post(
    "/corporate/organizations/{organization_id}/telemetry/rights"
    "/{subject_kind}/{subject_id}/revocation",
    response_model=CorporateTelemetryRightView,
)
async def revoke_telemetry_right(
    organization_id: str,
    subject_kind: TelemetrySubjectKind,
    subject_id: str,
    payload: CorporateTelemetryRevokeRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateTelemetryRightView:
    fingerprint = mutation_fingerprint(
        {
            "subject_kind": subject_kind,
            "subject_id": subject_id,
            **payload.model_dump(mode="json"),
        }
    )
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="telemetry.delete",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="telemetry.rights.revoke",
        fingerprint=fingerprint,
        request_id=_request_id(request),
    )
    if receipt is not None:
        return CorporateTelemetryRightView.model_validate(receipt.response_body)
    try:
        row, anonymized = await revoke_subject(
            db,
            organization_id=organization.id,
            subject_kind=subject_kind,
            subject_id=subject_id,
            anonymize=payload.anonymize,
            now=datetime.now(UTC),
        )
    except TelemetryRightStateError as error:
        raise ApiError(ErrorCategory.CONFLICT, str(error)) from error
    view = _right_view(row)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization.id,
        action="telemetry.rights.revoke",
        target_table="telemetry_revocation",
        target_id=f"{subject_kind}:{subject_id}",
        reason=payload.reason,
        request_id=_request_id(request),
        payload={"anonymized_events": anonymized},
    )
    await record_privileged_access(
        db,
        organization_id=organization.id,
        actor_account_id=ctx.account_id,
        action="telemetry.rights.revoke",
        target_table="telemetry_revocation",
        target_id=f"{subject_kind}:{subject_id}",
        request_id=_request_id(request),
        detail={"anonymized_events": anonymized},
    )
    await store_mutation_receipt(
        db,
        organization_id=organization.id,
        key=payload.idempotency_key,
        operation="telemetry.rights.revoke",
        fingerprint=fingerprint,
        response=view,
    )
    return view


@router.post(
    "/corporate/organizations/{organization_id}/telemetry/deletions",
    response_model=CorporateTelemetryDeleteResult,
)
async def delete_telemetry_subject(
    organization_id: str,
    payload: CorporateTelemetryDeleteRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateTelemetryDeleteResult:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json"))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="telemetry.delete",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="telemetry.delete",
        fingerprint=fingerprint,
        request_id=_request_id(request),
    )
    if receipt is not None:
        return CorporateTelemetryDeleteResult.model_validate(receipt.response_body)
    row, affected = await delete_subject(
        db,
        organization_id=organization.id,
        subject_kind=payload.subject_kind,
        subject_id=payload.subject_id,
        mode=payload.mode,
        now=datetime.now(UTC),
    )
    result = CorporateTelemetryDeleteResult(
        organization_id=organization.id,
        subject_kind=payload.subject_kind,
        subject_id=payload.subject_id,
        mode=payload.mode,
        affected_events=affected,
        state=cast(TelemetryRightState, row.state),
        processed_at=format_timestamp(datetime.now(UTC)),
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization.id,
        action="telemetry.delete",
        target_table="telemetry_revocation",
        target_id=f"{payload.subject_kind}:{payload.subject_id}",
        reason=payload.reason,
        request_id=_request_id(request),
        payload={"mode": payload.mode, "affected_events": affected},
    )
    await record_privileged_access(
        db,
        organization_id=organization.id,
        actor_account_id=ctx.account_id,
        action="telemetry.delete",
        target_table="telemetry_event",
        target_id=f"{payload.subject_kind}:{payload.subject_id}",
        request_id=_request_id(request),
        detail={"mode": payload.mode, "affected_events": affected},
    )
    await store_mutation_receipt(
        db,
        organization_id=organization.id,
        key=payload.idempotency_key,
        operation="telemetry.delete",
        fingerprint=fingerprint,
        response=result,
    )
    return result


__all__ = ["router"]
