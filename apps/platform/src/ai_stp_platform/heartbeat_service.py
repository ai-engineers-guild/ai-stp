"""Corporate installation heartbeat service (t-heartbeat, GitHub #215).

Writes coalesce onto one row per (organization, device): an incoming beat is
applied only when its client-declared `checked_at` is strictly newer than the
stored one, so replays are idempotent and delayed writes cannot regress newer
state. Health is never stored - it is a deterministic read-time projection
over the stored row, the injectable clock, and the staleness threshold. No
worker job marks rows stale.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.heartbeat import (
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_HEARTBEAT_RETRY_BASE_SECONDS,
    DEFAULT_HEARTBEAT_RETRY_MAX_SECONDS,
    DEFAULT_HEARTBEAT_STALE_AFTER_SECONDS,
    HeartbeatHealthState,
    HeartbeatReportedState,
    InstallationHeartbeat,
    InstallationHeartbeatPolicy,
    InstallationHeartbeatRequest,
    InstallationHeartbeatStatus,
)
from ai_stp_foundation.timestamps import format_timestamp, parse_timestamp
from ai_stp_platform.heartbeat_models import InstallationHeartbeat as HeartbeatRow
from ai_stp_platform.telemetry_policy_models import TelemetryPolicy
from ai_stp_platform.telemetry_privacy_service import (
    TelemetrySubjectRevokedError,
    require_subject_active,
)
from ai_stp_platform.tenant_scope import set_tenant_scope

# Compatibility default when a tenant has no explicit telemetry policy.
DEFAULT_STALE_AFTER: Final = timedelta(hours=24)
# A checked_at ahead of the server clock beyond this bound is rejected, so a
# skewed client cannot poison the ordering key and block later real beats.
MAX_FUTURE_SKEW: Final = timedelta(minutes=5)

REPORTED_STATES: Final = frozenset({"active", "partial", "failing", "disabled"})
HEALTH_STATES: Final = frozenset({"active", "partial", "stale", "failing", "disabled", "unknown"})


class HeartbeatRejected(ValueError):
    """A heartbeat write that must not land."""


class HeartbeatPolicyDisabled(ValueError):
    """The organization has disabled installation heartbeat writes."""


class HeartbeatSubjectRevoked(ValueError):
    """The installation's account or device revoked telemetry processing."""


def utcnow() -> datetime:
    return datetime.now(UTC)


async def organization_policy(
    db: AsyncSession, *, organization_id: str
) -> InstallationHeartbeatPolicy:
    """Return the tenant's public heartbeat settings or compatibility defaults."""
    await set_tenant_scope(db, organization_id)
    row = await db.get(TelemetryPolicy, organization_id)
    return InstallationHeartbeatPolicy(
        organization_id=organization_id,
        enabled=True if row is None else row.heartbeat_enabled,
        interval_seconds=(
            DEFAULT_HEARTBEAT_INTERVAL_SECONDS if row is None else row.heartbeat_interval_seconds
        ),
        retry_base_seconds=(
            DEFAULT_HEARTBEAT_RETRY_BASE_SECONDS
            if row is None
            else row.heartbeat_retry_base_seconds
        ),
        retry_max_seconds=(
            DEFAULT_HEARTBEAT_RETRY_MAX_SECONDS if row is None else row.heartbeat_retry_max_seconds
        ),
        stale_after_seconds=(
            DEFAULT_HEARTBEAT_STALE_AFTER_SECONDS
            if row is None
            else row.heartbeat_stale_after_seconds
        ),
    )


def evaluate_health(
    reported_state: str,
    received_at: datetime,
    *,
    now: datetime,
    stale_after: timedelta,
) -> HeartbeatHealthState:
    """Project the deterministic health state for one stored row.

    `disabled` is a declaration, not a freshness claim, so it survives a stale
    window. Freshness is measured from the server's `received_at`, which a
    client cannot push into the future.
    """
    if reported_state == "disabled":
        return "disabled"
    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=UTC)
    if now - received_at > stale_after:
        return "stale"
    if reported_state == "failing":
        return "failing"
    if reported_state == "partial":
        return "partial"
    return "active"


def health_state_for(
    row: HeartbeatRow | None, *, now: datetime, stale_after: timedelta
) -> HeartbeatHealthState:
    """Health of one installation; `unknown` when no beat has ever landed."""
    if row is None:
        return "unknown"
    return evaluate_health(row.reported_state, row.received_at, now=now, stale_after=stale_after)


def accepts_update(stored_checked_at: datetime | None, checked_at: datetime) -> bool:
    """A strictly newer client-declared moment wins; equal or older coalesces."""
    if stored_checked_at is None:
        return True
    if stored_checked_at.tzinfo is None:
        stored_checked_at = stored_checked_at.replace(tzinfo=UTC)
    return checked_at > stored_checked_at


def to_view(row: HeartbeatRow, *, now: datetime, stale_after: timedelta) -> InstallationHeartbeat:
    """Project one stored row onto the wire. The row holds no secrets."""
    return InstallationHeartbeat(
        organization_id=row.organization_id,
        account_id=row.account_id,
        device_id=row.device_id,
        cli_version=row.cli_version,
        capabilities=list(row.capabilities or []),
        last_sync_at=(
            format_timestamp(row.last_sync_at.replace(tzinfo=UTC))
            if row.last_sync_at is not None
            else None
        ),
        reported_state=cast(HeartbeatReportedState, row.reported_state),
        health_state=evaluate_health(
            row.reported_state, row.received_at, now=now, stale_after=stale_after
        ),
        checked_at=format_timestamp(row.checked_at.replace(tzinfo=UTC)),
        received_at=format_timestamp(row.received_at.replace(tzinfo=UTC)),
        revision=row.revision,
        stale_after_seconds=int(stale_after.total_seconds()),
    )


def status_view(
    *,
    organization_id: str,
    device_id: str,
    row: HeartbeatRow | None,
    now: datetime,
    stale_after: timedelta,
) -> InstallationHeartbeatStatus:
    return InstallationHeartbeatStatus(
        organization_id=organization_id,
        device_id=device_id,
        health_state=health_state_for(row, now=now, stale_after=stale_after),
        evaluated_at=format_timestamp(now),
        stale_after_seconds=int(stale_after.total_seconds()),
        heartbeat=None if row is None else to_view(row, now=now, stale_after=stale_after),
    )


async def record_heartbeat(
    db: AsyncSession,
    *,
    organization_id: str,
    report: InstallationHeartbeatRequest,
    now: datetime | None = None,
    stale_after: timedelta | None = None,
) -> InstallationHeartbeat:
    """Coalesce one heartbeat onto the (organization, device) row.

    The caller has already bound account/device to the authenticated session;
    this layer owns ordering, coalescing, and the skew guard. The returned
    view carries the evaluated health for `now`.
    """
    now = now or utcnow()
    policy = await organization_policy(db, organization_id=organization_id)
    if not policy.enabled:
        raise HeartbeatPolicyDisabled("heartbeat reporting is disabled for this organization")
    try:
        await require_subject_active(
            db,
            organization_id=organization_id,
            account_id=report.account_id,
            device_id=report.device_id,
        )
    except TelemetrySubjectRevokedError as error:
        raise HeartbeatSubjectRevoked(
            "telemetry processing was revoked for this installation"
        ) from error
    stale_after = stale_after or timedelta(seconds=policy.stale_after_seconds)
    checked_at = parse_timestamp(report.checked_at)
    if checked_at > now + MAX_FUTURE_SKEW:
        raise HeartbeatRejected("checked_at is beyond the accepted clock skew")
    last_sync_at = parse_timestamp(report.last_sync_at) if report.last_sync_at is not None else None
    await set_tenant_scope(db, organization_id)
    result = await db.execute(
        select(HeartbeatRow)
        .where(
            HeartbeatRow.organization_id == organization_id,
            HeartbeatRow.device_id == report.device_id,
        )
        .with_for_update()
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = HeartbeatRow(
            organization_id=organization_id,
            device_id=report.device_id,
            account_id=report.account_id,
            cli_version=report.cli_version,
            capabilities=list(report.capabilities),
            last_sync_at=last_sync_at,
            reported_state=report.health_state,
            checked_at=checked_at,
            received_at=now,
            revision=1,
        )
        db.add(row)
    else:
        if row.account_id != report.account_id:
            raise HeartbeatRejected("device heartbeat is bound to a different account")
        if accepts_update(row.checked_at, checked_at):
            row.cli_version = report.cli_version
            row.capabilities = list(report.capabilities)
            row.last_sync_at = last_sync_at
            row.reported_state = report.health_state
            row.checked_at = checked_at
            row.received_at = now
            row.revision += 1
    await db.flush()
    return to_view(row, now=now, stale_after=stale_after)


async def get_heartbeat(
    db: AsyncSession, *, organization_id: str, device_id: str
) -> HeartbeatRow | None:
    await set_tenant_scope(db, organization_id)
    result = await db.execute(
        select(HeartbeatRow).where(
            HeartbeatRow.organization_id == organization_id,
            HeartbeatRow.device_id == device_id,
        )
    )
    return result.scalar_one_or_none()


async def list_heartbeats(db: AsyncSession, *, organization_id: str) -> list[HeartbeatRow]:
    await set_tenant_scope(db, organization_id)
    result = await db.execute(
        select(HeartbeatRow)
        .where(HeartbeatRow.organization_id == organization_id)
        .order_by(HeartbeatRow.account_id, HeartbeatRow.device_id)
    )
    return list(result.scalars().all())
