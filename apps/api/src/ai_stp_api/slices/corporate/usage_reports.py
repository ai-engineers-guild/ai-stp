"""Runtime usage aggregate reports and bounded exports (SPEC-088).

Aggregates are the default surface (`telemetry_usage.read`); exports are a
separately permissioned mutation that leaves a digested receipt and an audit
row. Every read resolves the caller's employee scope before touching data.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import service
from ai_stp_api.slices.corporate.usage_events import usage_scope
from ai_stp_contracts.corporate import OrganizationId
from ai_stp_contracts.runtime_usage import (
    RuntimeUsageExportRequest,
    RuntimeUsageExportView,
    RuntimeUsageReport,
    RuntimeUsageReportQuery,
)
from ai_stp_platform import runtime_usage_service

router = APIRouter(tags=["corporate"])


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@router.get(
    "/corporate/organizations/{organization_id}/telemetry/usage-reports",
    response_model=RuntimeUsageReport,
)
async def read_usage_report(
    organization_id: OrganizationId,
    query: Annotated[RuntimeUsageReportQuery, Query()],
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> RuntimeUsageReport:
    scope = await usage_scope(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=runtime_usage_service.PERMISSION_READ,
    )
    return await runtime_usage_service.aggregate_report(
        db,
        organization_id=organization_id,
        query=query,
        scope=scope,
    )


@router.post(
    "/corporate/organizations/{organization_id}/telemetry/usage-exports",
    response_model=RuntimeUsageExportView,
)
async def create_usage_export(
    organization_id: OrganizationId,
    payload: RuntimeUsageExportRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> RuntimeUsageExportView:
    try:
        await service.authorize(
            db,
            ctx=ctx,
            organization_id=organization_id,
            permission=runtime_usage_service.PERMISSION_EXPORT,
            authorization_revision=payload.authorization_revision,
        )
        scope = runtime_usage_service.UsageScope(employees=None)
    except ApiError as denied:
        scope = await runtime_usage_service.resolve_scope(
            db,
            organization_id=organization_id,
            principal_id=ctx.account_id,
            permission=runtime_usage_service.PERMISSION_EXPORT,
        )
        if scope.denied:
            raise denied
    view = await runtime_usage_service.create_export(
        db,
        organization_id=organization_id,
        request=payload,
        scope=scope,
        actor_account_id=ctx.account_id,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="telemetry_usage.export",
        target_table="runtime_usage_export",
        target_id=view.export_id,
        request_id=_request_id(request),
        payload={"row_count": view.row_count, "content_digest": view.content_digest},
    )
    return view


@router.get(
    "/corporate/organizations/{organization_id}/telemetry/usage-exports/{export_id}",
    response_model=RuntimeUsageExportView,
)
async def read_usage_export(
    organization_id: OrganizationId,
    export_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> RuntimeUsageExportView:
    await usage_scope(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=runtime_usage_service.PERMISSION_READ,
    )
    view = await runtime_usage_service.read_export(
        db, organization_id=organization_id, export_id=export_id
    )
    if view is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "usage export not found")
    return view
