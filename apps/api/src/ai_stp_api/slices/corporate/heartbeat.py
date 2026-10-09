"""Corporate installation heartbeat routes (t-heartbeat, GitHub #215).

Authenticated `/v1` routes under the corporate tenant. Writes bind account
and device to the authenticated session - a body that claims another account
or device is rejected, and a session without a device cannot heartbeat at
all. Reads are role-gated: members see their own row, `telemetry.read` opens
member-scoped or organization-scoped visibility. Health is evaluated at read
time; nothing here emits a runtime invocation event.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import and_, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import service
from ai_stp_api.slices.devices.crypto import verify_ed25519
from ai_stp_contracts.corporate import OrganizationId
from ai_stp_contracts.heartbeat import (
    HeartbeatHealthState,
    InstallationHeartbeat,
    InstallationHeartbeatList,
    InstallationHeartbeatPolicy,
    InstallationHeartbeatRequest,
    InstallationHeartbeatStatus,
    heartbeat_signature_message,
)
from ai_stp_foundation.timestamps import format_timestamp, parse_timestamp
from ai_stp_platform import heartbeat_service
from ai_stp_platform.corporate_authorization import (
    bulk_effective_permissions,
    corporate_effective_permissions,
)
from ai_stp_platform.heartbeat_models import InstallationHeartbeat as HeartbeatRow
from ai_stp_platform.models import Device
from ai_stp_platform.telemetry_privacy_service import record_privileged_access
from ai_stp_platform.tenant_scope import set_tenant_scope

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
    device = await db.get(Device, ctx.device_id)
    if device is None or device.account_id != ctx.account_id or device.state != "active":
        raise ApiError(ErrorCategory.PERMISSION, "heartbeat device is unavailable")
    if abs(datetime.now(UTC) - parse_timestamp(payload.checked_at)) > timedelta(minutes=5):
        raise ApiError(
            ErrorCategory.VALIDATION, "heartbeat timestamp is outside the accepted window"
        )
    verify_ed25519(
        public_key=device.public_key,
        message=heartbeat_signature_message(organization_id, payload),
        signature=payload.signature,
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
    request: Request,
    ctx: Annotated[AuthContext, Depends(require_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
    health_state: Annotated[HeartbeatHealthState | None, Query()] = None,
) -> InstallationHeartbeatList:
    """Installation health visible to the caller's role, health-filtered."""
    await service.organization_and_membership(db, ctx=ctx, organization_id=organization_id)
    await set_tenant_scope(db, organization_id)
    now = heartbeat_service.utcnow()
    policy = await heartbeat_service.organization_policy(db, organization_id=organization_id)
    stale_after = timedelta(seconds=policy.stale_after_seconds)
    account_ids = set(
        (
            await db.scalars(
                select(HeartbeatRow.account_id)
                .where(HeartbeatRow.organization_id == organization_id)
                .distinct()
            )
        ).all()
    )
    allowed_ids = await _visible_heartbeat_accounts(
        db,
        ctx=ctx,
        organization_id=organization_id,
        account_ids=account_ids - {ctx.account_id},
    )
    visible = and_(
        HeartbeatRow.organization_id == organization_id,
        or_(
            HeartbeatRow.account_id == ctx.account_id,
            HeartbeatRow.account_id.in_(sorted(allowed_ids)),
        ),
    )
    health = (
        heartbeat_service.health_clause(health_state, now=now, stale_after=stale_after)
        if health_state is not None
        else true()
    )
    # `returned` is the health-filtered visible count; `foreign` deliberately
    # ignores the health filter, as it did when rows were scanned in Python.
    total, foreign = (
        await db.execute(
            select(
                func.count().filter(health),
                func.count().filter(HeartbeatRow.account_id != ctx.account_id),
            ).where(visible)
        )
    ).one()
    views = [
        heartbeat_service.to_view(row, now=now, stale_after=stale_after)
        for row in (
            await db.scalars(
                select(HeartbeatRow)
                .where(visible, health)
                .order_by(HeartbeatRow.account_id, HeartbeatRow.device_id)
                .limit(256)
            )
        ).all()
    ]
    if foreign:
        # Reading other members' telemetry is a privileged operation: it takes
        # the same platform + governance audit pair as the telemetry list.
        request_id = getattr(request.state, "request_id", None)
        await emit_audit(
            db,
            actor_account_id=ctx.account_id,
            organization_id=organization_id,
            action="telemetry.list",
            target_table="installation_heartbeat",
            target_id=organization_id,
            request_id=request_id,
        )
        await record_privileged_access(
            db,
            organization_id=organization_id,
            actor_account_id=ctx.account_id,
            action="telemetry.list",
            target_table="installation_heartbeat",
            target_id=organization_id,
            request_id=request_id,
            detail={"returned": len(views), "foreign": foreign},
        )
    return InstallationHeartbeatList(
        organization_id=organization_id,
        evaluated_at=format_timestamp(now),
        stale_after_seconds=int(stale_after.total_seconds()),
        total=total,
        items=views,
    )


async def _visible_heartbeat_accounts(
    db: AsyncSession, *, ctx: AuthContext, organization_id: str, account_ids: set[str]
) -> set[str]:
    """Member accounts whose heartbeats the caller may read, in one pass.

    `telemetry.read` at organization scope opens every member; otherwise the
    member-scope grants decide per account — the same verdict `_telemetry_read_allowed`
    used to reach one `service.authorize` call per row."""
    if not account_ids:
        return set()
    org_wide = await corporate_effective_permissions(
        db,
        organization_id=organization_id,
        principal_type="user",
        principal_id=ctx.account_id,
        scope_kind="organization",
        scope_id=organization_id,
    )
    if org_wide is not None and _TELEMETRY_READ in org_wide:
        return set(account_ids)
    member_grants = await bulk_effective_permissions(
        db,
        organization_id=organization_id,
        principal_type="user",
        principal_id=ctx.account_id,
        scope_kind="member",
        scope_ids=account_ids,
    )
    if member_grants is None:
        return set()
    return {
        account_id
        for account_id in account_ids
        if _TELEMETRY_READ in member_grants.get(account_id, frozenset())
    }
