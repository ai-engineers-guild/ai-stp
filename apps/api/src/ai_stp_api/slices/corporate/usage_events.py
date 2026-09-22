"""Runtime usage event ingestion and redacted drill-down (SPEC-088).

Ingestion rides the existing authenticated corporate channel; the drill-down
read is separately permissioned (`telemetry_usage.events`) and audited. Events
carry identities and exact coordinates only - there is no payload column for
forbidden content to land in.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.errors import ApiError
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import service
from ai_stp_contracts.corporate import OrganizationId
from ai_stp_contracts.runtime_usage import (
    RuntimeUsageEventBatch,
    RuntimeUsageEventList,
    RuntimeUsageEventQuery,
    RuntimeUsageIngestResult,
)
from ai_stp_platform import runtime_usage_service

router = APIRouter(tags=["corporate"])


async def usage_scope(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    permission: str,
) -> runtime_usage_service.UsageScope:
    """Resolve the caller's visibility: employees=None for org-wide.

    An organization-scoped grant answers ``UsageScope(None)``. A team-scoped
    principal falls back to the members of the teams where the permission
    holds, plus itself. Anything else re-raises the original denial.
    """
    try:
        await service.authorize(
            db,
            ctx=ctx,
            organization_id=organization_id,
            permission=permission,
        )
        return runtime_usage_service.UsageScope(employees=None)
    except ApiError as denied:
        scope = await runtime_usage_service.resolve_scope(
            db,
            organization_id=organization_id,
            principal_id=ctx.account_id,
            permission=permission,
        )
        if scope.denied:
            raise denied
        return scope


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@router.post(
    "/corporate/organizations/{organization_id}/telemetry/usage-events",
    response_model=RuntimeUsageIngestResult,
)
async def ingest_usage_events(
    organization_id: OrganizationId,
    payload: RuntimeUsageEventBatch,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> RuntimeUsageIngestResult:
    await service.authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=runtime_usage_service.PERMISSION_INGEST,
        scope_kind="member",
        scope_id=ctx.account_id,
    )
    result = await runtime_usage_service.ingest_events(
        db,
        organization_id=organization_id,
        batch=payload,
        caller_account_id=ctx.account_id,
        caller_device_id=ctx.device_id,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="telemetry_usage.ingest",
        target_table="runtime_usage_event",
        target_id=organization_id,
        request_id=_request_id(request),
        payload={
            "accepted": result.accepted,
            "duplicates": result.duplicates,
            "rejected": result.rejected,
        },
    )
    return result


@router.get(
    "/corporate/organizations/{organization_id}/telemetry/usage-events",
    response_model=RuntimeUsageEventList,
)
async def list_usage_events(
    organization_id: OrganizationId,
    query: Annotated[RuntimeUsageEventQuery, Query()],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> RuntimeUsageEventList:
    scope = await usage_scope(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=runtime_usage_service.PERMISSION_EVENTS,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="telemetry_usage.events.read",
        target_table="runtime_usage_event",
        target_id=organization_id,
        request_id=_request_id(request),
    )
    return await runtime_usage_service.list_events(
        db,
        organization_id=organization_id,
        query=query,
        scope=scope,
    )
