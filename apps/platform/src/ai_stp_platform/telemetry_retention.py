"""Telemetry retention executor (SPEC-089, ADR-0203).

Raw events are deleted once they pass the tenant's ``raw_retention_days``.
Aggregates are computed from raw rows and inherit the same storage boundary;
``aggregate_retention_days`` governs how long derived aggregates may be
retained by downstream reports. Both operations are idempotent: rows already
removed are simply absent from the next run.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import select, tuple_, union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from ai_stp_platform.heartbeat_models import InstallationHeartbeat, InstallationHeartbeatEvent
from ai_stp_platform.installation_inventory_models import InstallationInventorySnapshot
from ai_stp_platform.installation_usage_models import InstallationOperationFact
from ai_stp_platform.runtime_usage_models import RuntimeUsageEvent
from ai_stp_platform.telemetry_policy_models import TelemetryEvent, TelemetryPolicy
from ai_stp_platform.tenant_scope import set_tenant_scope

DEFAULT_RAW_RETENTION_DAYS = 90
RETENTION_BATCH_LIMIT = 5000

# (model, time column, primary-key columns) for every governed raw-event table.
_SWEEP_SPECS: tuple[
    tuple[
        type[Any],
        InstrumentedAttribute[Any],
        tuple[InstrumentedAttribute[Any], ...],
    ],
    ...,
] = (
    (
        TelemetryEvent,
        TelemetryEvent.occurred_at,
        (TelemetryEvent.organization_id, TelemetryEvent.event_id),
    ),
    (
        RuntimeUsageEvent,
        RuntimeUsageEvent.invoked_at,
        (RuntimeUsageEvent.organization_id, RuntimeUsageEvent.event_id),
    ),
    (
        InstallationOperationFact,
        InstallationOperationFact.occurred_at,
        (InstallationOperationFact.organization_id, InstallationOperationFact.operation_id),
    ),
    (
        InstallationInventorySnapshot,
        InstallationInventorySnapshot.scanned_at,
        (InstallationInventorySnapshot.organization_id, InstallationInventorySnapshot.scan_id),
    ),
    (
        InstallationHeartbeat,
        InstallationHeartbeat.received_at,
        (InstallationHeartbeat.organization_id, InstallationHeartbeat.device_id),
    ),
    (
        InstallationHeartbeatEvent,
        InstallationHeartbeatEvent.received_at,
        (
            InstallationHeartbeatEvent.organization_id,
            InstallationHeartbeatEvent.device_id,
            InstallationHeartbeatEvent.checked_at,
        ),
    ),
)


async def _delete_expired_batch(
    session: AsyncSession,
    *,
    model: type[Any],
    time_column: InstrumentedAttribute[Any],
    pk_columns: tuple[InstrumentedAttribute[Any], ...],
    organization_id: str,
    cutoff: datetime,
    limit: int,
) -> int:
    keys = (
        await session.execute(
            select(*pk_columns)
            .where(model.organization_id == organization_id, time_column < cutoff)
            .order_by(time_column)
            .limit(limit)
        )
    ).all()
    if not keys:
        return 0
    result = await session.execute(
        sql_delete(model).where(tuple_(*pk_columns).in_(keys), time_column < cutoff)
    )
    rowcount = getattr(result, "rowcount", 0)
    return rowcount if isinstance(rowcount, int) else 0


async def apply_retention(
    session: AsyncSession,
    *,
    organization_id: str,
    now: datetime,
    limit: int = RETENTION_BATCH_LIMIT,
) -> int:
    """Delete raw events past the tenant retention period; idempotent.

    The sweep covers every governed raw-event table: the generic
    `telemetry_event` boundary store and the usage stream's
    `runtime_usage_event`, `installation_operation_fact`, and
    `installation_heartbeat`. Old coalesced rows
    disappear and project as `unknown`; retention never writes `stale`.

    Each table is deleted in primary-key batches of at most ``limit`` rows,
    the same bound every other sweep in the platform applies, so a large
    tenant's first pass drains incrementally instead of holding one
    transaction's worth of locks.
    """
    await set_tenant_scope(session, organization_id)
    policy = await session.get(TelemetryPolicy, organization_id)
    days = policy.raw_retention_days if policy is not None else DEFAULT_RAW_RETENTION_DAYS
    cutoff = now - timedelta(days=days)
    removed = 0
    for model, time_column, pk_columns in _SWEEP_SPECS:
        removed += await _delete_expired_batch(
            session,
            model=model,
            time_column=time_column,
            pk_columns=pk_columns,
            organization_id=organization_id,
            cutoff=cutoff,
            limit=limit,
        )
    return removed


async def retention_tenants(session: AsyncSession) -> list[str]:
    """Return every tenant with policy or governed data, including defaults."""
    # The sweep is a platform job, not a tenant call: governed tables are under
    # FORCE row-level security, so without "*" this list silently comes back
    # empty on Postgres and the retention job retains everything.
    await set_tenant_scope(session, "*")
    rows = await session.scalars(
        union(
            select(TelemetryPolicy.organization_id),
            select(TelemetryEvent.organization_id),
            select(RuntimeUsageEvent.organization_id),
            select(InstallationOperationFact.organization_id),
            select(InstallationInventorySnapshot.organization_id),
            select(InstallationHeartbeat.organization_id),
            select(InstallationHeartbeatEvent.organization_id),
        )
    )
    return list(rows.all())


async def apply_retention_all(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Run the retention pass for every governed tenant; returns rows removed."""
    moment = now or datetime.now(UTC)
    removed = 0
    for organization_id in await retention_tenants(session):
        removed += await apply_retention(session, organization_id=organization_id, now=moment)
    return removed


__all__ = [
    "DEFAULT_RAW_RETENTION_DAYS",
    "apply_retention",
    "apply_retention_all",
    "retention_tenants",
]
