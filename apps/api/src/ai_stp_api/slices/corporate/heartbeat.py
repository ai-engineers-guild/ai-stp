"""Corporate installation heartbeat routes (t-heartbeat, GitHub #215).

Authenticated `/v1` routes under the corporate tenant. Writes bind account
and device to the authenticated session - a body that claims another account
or device is rejected, and a session without a device cannot heartbeat at
all. Reads are role-gated: members see their own row, `telemetry.read` opens
member-scoped or organization-scoped visibility. Health is evaluated at read
time; nothing here emits a runtime invocation event.
"""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import service
from ai_stp_contracts.corporate import OrganizationId
from ai_stp_contracts.heartbeat import (
    HeartbeatHealthState,
    InstallationHeartbeat,
    InstallationHeartbeatList,
    InstallationHeartbeatPolicy,
    InstallationHeartbeatRequest,
    InstallationHeartbeatStatus,
)
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform import heartbeat_service

router = APIRouter(tags=["corporate"])

_TELEMETRY_READ = "telemetry.read"


@router.put(
    "/corporate/organizations/{organization_id}/telemetry/heartbeat",
    response_model=InstallationHeartbeat,
)
async def write_heartbeat(
    organization_id: OrganizationId,
    payload: InstallationHeartbeatRequest,
    ctx: Annotated[AuthContext, Depends(require_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InstallationHeartbeat:
    """Coalesce one heartbeat for the session's own device installation."""
    await service.organization_and_membership(db, ctx=ctx, organization_id=organization_id)
    if ctx.device_id is None:
        raise ApiError(ErrorCategory.VALIDATION, "heartbeat requires a device-bound session")
    if payload.account_id != ctx.account_id or payload.device_id != ctx.device_id:
        raise ApiError(
            ErrorCategory.PERMISSION,
            "a heartbeat can only be written for the session's own account and device",
        )
    try:
        view = await heartbeat_service.record_heartbeat(
            db, organization_id=organization_id, report=payload
        )
    except heartbeat_service.HeartbeatPolicyDisabled as error:
        raise ApiError(ErrorCategory.PERMISSION, str(error)) from error
    except heartbeat_service.HeartbeatSubjectRevoked as error:
        raise ApiError(ErrorCategory.PERMISSION, str(error)) from error
    except heartbeat_service.HeartbeatRejected as error:
        raise ApiError(ErrorCategory.VALIDATION, str(error)) from error
    await db.commit()
    return view


@router.get(
    "/corporate/organizations/{organization_id}/telemetry/heartbeat/policy",
    response_model=InstallationHeartbeatPolicy,
)
async def read_heartbeat_policy(
    organization_id: OrganizationId,
    ctx: Annotated[AuthContext, Depends(require_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InstallationHeartbeatPolicy:
    """Read heartbeat cadence visible to a member deciding whether to opt in."""
    await service.organization_and_membership(db, ctx=ctx, organization_id=organization_id)
    return await heartbeat_service.organization_policy(db, organization_id=organization_id)


@router.get(
    "/corporate/organizations/{organization_id}/telemetry/heartbeat",
    response_model=InstallationHeartbeatStatus,
)
async def read_own_heartbeat(
    organization_id: OrganizationId,
    ctx: Annotated[AuthContext, Depends(require_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InstallationHeartbeatStatus:
    """The session device's evaluated health; `unknown` before the first beat."""
    await service.organization_and_membership(db, ctx=ctx, organization_id=organization_id)
    if ctx.device_id is None:
        raise ApiError(ErrorCategory.VALIDATION, "heartbeat status requires a device-bound session")
    row = await heartbeat_service.get_heartbeat(
        db, organization_id=organization_id, device_id=ctx.device_id
    )
    policy = await heartbeat_service.organization_policy(db, organization_id=organization_id)
    return heartbeat_service.status_view(
        organization_id=organization_id,
        device_id=ctx.device_id,
        row=row,
        now=heartbeat_service.utcnow(),
        stale_after=timedelta(seconds=policy.stale_after_seconds),
    )


@router.get(
    "/corporate/organizations/{organization_id}/telemetry/heartbeats",
    response_model=InstallationHeartbeatList,
)
async def list_heartbeats(
    organization_id: OrganizationId,
    ctx: Annotated[AuthContext, Depends(require_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
    health_state: Annotated[HeartbeatHealthState | None, Query()] = None,
) -> InstallationHeartbeatList:
    """Installation health visible to the caller's role, health-filtered."""
    await service.organization_and_membership(db, ctx=ctx, organization_id=organization_id)
    rows = await heartbeat_service.list_heartbeats(db, organization_id=organization_id)
    now = heartbeat_service.utcnow()
    policy = await heartbeat_service.organization_policy(db, organization_id=organization_id)
    stale_after = timedelta(seconds=policy.stale_after_seconds)
    views: list[InstallationHeartbeat] = []
    for row in rows:
        if row.account_id == ctx.account_id or await _telemetry_read_allowed(
            db, ctx=ctx, organization_id=organization_id, member_account_id=row.account_id
        ):
            views.append(heartbeat_service.to_view(row, now=now, stale_after=stale_after))
    if health_state is not None:
        views = [view for view in views if view.health_state == health_state]
    return InstallationHeartbeatList(
        organization_id=organization_id,
        evaluated_at=format_timestamp(now),
        stale_after_seconds=int(stale_after.total_seconds()),
        total=len(views),
        items=views[:256],
    )


async def _telemetry_read_allowed(
    db: AsyncSession, *, ctx: AuthContext, organization_id: str, member_account_id: str
) -> bool:
    """`telemetry.read` at member scope; org-scoped roles fall back inside."""
    try:
        await service.authorize(
            db,
            ctx=ctx,
            organization_id=organization_id,
            permission=_TELEMETRY_READ,
            scope_kind="member",
            scope_id=member_account_id,
        )
    except ApiError:
        return False
    return True
