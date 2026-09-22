"""Worker handler for the telemetry retention executor (SPEC-089).

Payload: ``{"organization_id": "org_..."}`` for a single tenant sweep, or an
empty mapping to sweep every tenant that has a telemetry policy. The handler
is idempotent: rows already removed are absent on the next run. JobType
registration is applied by the orchestrator at integration (worker receipt).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.telemetry_privacy_service import record_privileged_access
from ai_stp_platform.telemetry_retention import apply_retention, apply_retention_all


async def handle_telemetry_retention(session: AsyncSession, payload: Mapping[str, object]) -> None:
    """Apply telemetry retention for one tenant or all governed tenants."""
    organization_id = payload.get("organization_id")
    if isinstance(organization_id, str) and organization_id:
        removed = await apply_retention(
            session, organization_id=organization_id, now=datetime.now(UTC)
        )
        await record_privileged_access(
            session,
            organization_id=organization_id,
            actor_account_id=None,
            action="telemetry.retention",
            target_table="telemetry_event",
            target_id=organization_id,
            detail={"removed": removed},
        )
        return
    await apply_retention_all(session, now=datetime.now(UTC))


__all__ = ["handle_telemetry_retention"]
