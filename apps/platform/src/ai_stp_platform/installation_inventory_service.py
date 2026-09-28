"""Authenticated, idempotent intake of scoped installation discovery."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.installation_inventory import (
    InstallationInventoryBatch,
    InstallationInventoryReceipt,
    InstallationInventorySnapshot,
)
from ai_stp_foundation.digests import digest_canonical
from ai_stp_platform.installation_inventory_models import (
    InstallationInventorySnapshot as SnapshotRow,
)
from ai_stp_platform.models import Device
from ai_stp_platform.organization_models import CorporateProject
from ai_stp_platform.runtime_usage_service import (  # pyright: ignore[reportPrivateUsage]
    raw_retention_days,
    revoked_subjects,
)
from ai_stp_platform.telemetry_policy_models import TelemetryPolicy
from ai_stp_platform.tenant_scope import set_tenant_scope


async def ingest_snapshots(
    session: AsyncSession,
    *,
    organization_id: str,
    batch: InstallationInventoryBatch,
    caller_account_id: str,
    caller_device_id: str | None,
    now: datetime | None = None,
) -> InstallationInventoryReceipt:
    """Store both full and partial checks; only full checks prove absence."""
    await set_tenant_scope(session, organization_id)
    policy = await session.get(TelemetryPolicy, organization_id)
    if policy is None or not policy.inventory_scan_enabled:
        return InstallationInventoryReceipt(
            rejected_ids=[snapshot.scan_id for snapshot in batch.snapshots]
        )
    moment = now or datetime.now(UTC)
    cutoff = moment - timedelta(
        days=await raw_retention_days(session, organization_id=organization_id)
    )
    revoked = await revoked_subjects(session, organization_id=organization_id)
    device_query = select(Device.id).where(
        Device.account_id == caller_account_id, Device.state == "active"
    )
    if caller_device_id is not None:
        device_query = device_query.where(Device.id == caller_device_id)
    devices = frozenset(await session.scalars(device_query))
    projects = frozenset(
        await session.scalars(
            select(CorporateProject.id).where(
                CorporateProject.organization_id == organization_id,
                CorporateProject.state == "active",
            )
        )
    )
    accepted: list[str] = []
    duplicates: list[str] = []
    rejected: list[str] = []
    seen: set[str] = set()
    for snapshot in batch.snapshots:
        scanned = datetime.fromisoformat(snapshot.scanned_at.replace("Z", "+00:00"))
        if (
            snapshot.organization_id != organization_id
            or snapshot.employee_id != caller_account_id
            or snapshot.device_id not in devices
            or (snapshot.project_id is not None and snapshot.project_id not in projects)
            or ("account", snapshot.employee_id) in revoked
            or ("device", snapshot.device_id) in revoked
            or scanned > moment + timedelta(minutes=5)
            or scanned < cutoff
        ):
            rejected.append(snapshot.scan_id)
            continue
        digest = digest_canonical(
            "ai-stp:installation-inventory:v1", snapshot.model_dump(mode="json")
        )
        existing = await session.get(SnapshotRow, (organization_id, snapshot.scan_id))
        if existing is not None and existing.snapshot_digest != digest:
            rejected.append(snapshot.scan_id)
        elif snapshot.scan_id in seen or existing is not None:
            duplicates.append(snapshot.scan_id)
        else:
            session.add(_row(snapshot, scanned, digest))
            seen.add(snapshot.scan_id)
            accepted.append(snapshot.scan_id)
    await session.flush()
    return InstallationInventoryReceipt(
        accepted_ids=accepted, duplicate_ids=duplicates, rejected_ids=rejected
    )


def _row(snapshot: InstallationInventorySnapshot, scanned: datetime, digest: str) -> SnapshotRow:
    return SnapshotRow(
        organization_id=snapshot.organization_id,
        scan_id=snapshot.scan_id,
        snapshot_digest=digest,
        employee_account_id=snapshot.employee_id,
        device_id=snapshot.device_id,
        project_id=snapshot.project_id,
        scope=snapshot.scope,
        scanned_at=scanned,
        complete=snapshot.complete,
        components=[item.model_dump(mode="json") for item in snapshot.components],
    )
