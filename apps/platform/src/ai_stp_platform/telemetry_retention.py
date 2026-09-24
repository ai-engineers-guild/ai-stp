"""Telemetry retention executor (SPEC-089, ADR-0203).

Raw events are deleted once they pass the tenant's ``raw_retention_days``.
Aggregates are computed from raw rows and inherit the same storage boundary;
``aggregate_retention_days`` governs how long derived aggregates may be
retained by downstream reports. Both operations are idempotent: rows already
removed are simply absent from the next run.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete as sql_delete
from sqlalchemy import select, union
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.heartbeat_models import InstallationHeartbeat
from ai_stp_platform.runtime_usage_models import RuntimeUsageEvent
from ai_stp_platform.telemetry_policy_models import TelemetryEvent, TelemetryPolicy
from ai_stp_platform.tenant_scope import set_tenant_scope

DEFAULT_RAW_RETENTION_DAYS = 90


async def apply_retention(session: AsyncSession, *, organization_id: str, now: datetime) -> int:
    """Delete raw events past the tenant retention period; idempotent.

    The sweep covers every governed raw-event table: the generic
    `telemetry_event` boundary store and the usage stream's
    `runtime_usage_event`, and `installation_heartbeat`. Old coalesced rows
    disappear and project as `unknown`; retention never writes `stale`.
    """
    await set_tenant_scope(session, organization_id)
    policy = await session.get(TelemetryPolicy, organization_id)
    days = policy.raw_retention_days if policy is not None else DEFAULT_RAW_RETENTION_DAYS
    cutoff = now - timedelta(days=days)
    removed = 0
    for statement in (
        sql_delete(TelemetryEvent).where(
            TelemetryEvent.organization_id == organization_id,
            TelemetryEvent.occurred_at < cutoff,
        ),
        sql_delete(RuntimeUsageEvent).where(
            RuntimeUsageEvent.organization_id == organization_id,
            RuntimeUsageEvent.invoked_at < cutoff,
        ),
        sql_delete(InstallationHeartbeat).where(
            InstallationHeartbeat.organization_id == organization_id,
            InstallationHeartbeat.received_at < cutoff,
        ),
    ):
        result = await session.execute(statement)
        rowcount = getattr(result, "rowcount", 0)
        if isinstance(rowcount, int):
            removed += rowcount
    return removed


async def retention_tenants(session: AsyncSession) -> list[str]:
    """Return every tenant with policy or governed data, including defaults."""
    rows = await session.scalars(
        union(
            select(TelemetryPolicy.organization_id),
            select(TelemetryEvent.organization_id),
            select(RuntimeUsageEvent.organization_id),
            select(InstallationHeartbeat.organization_id),
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
