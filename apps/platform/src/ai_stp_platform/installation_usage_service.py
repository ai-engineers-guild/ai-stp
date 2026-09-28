"""Authenticated, idempotent intake of settled installation journal facts."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.installation_usage import (
    InstallationOperationBatch,
    InstallationOperationFact,
    InstallationOperationReceipt,
)
from ai_stp_foundation.digests import digest_canonical
from ai_stp_platform.installation_usage_models import InstallationOperationFact as FactRow
from ai_stp_platform.models import Device
from ai_stp_platform.organization_models import CorporateProject
from ai_stp_platform.runtime_usage_service import (  # pyright: ignore[reportPrivateUsage]
    raw_retention_days,
    revoked_subjects,
)
from ai_stp_platform.tenant_scope import set_tenant_scope


async def ingest_operations(
    session: AsyncSession,
    *,
    organization_id: str,
    batch: InstallationOperationBatch,
    caller_account_id: str,
    caller_device_id: str | None,
    now: datetime | None = None,
) -> InstallationOperationReceipt:
    """Store only facts bound to the authenticated employee and device."""
    await set_tenant_scope(session, organization_id)
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
    for fact in batch.operations:
        occurred = datetime.fromisoformat(fact.occurred_at.replace("Z", "+00:00"))
        if (
            fact.organization_id != organization_id
            or fact.employee_id != caller_account_id
            or fact.device_id not in devices
            or fact.project_id not in projects
            or ("account", fact.employee_id) in revoked
            or ("device", fact.device_id) in revoked
            or occurred > moment + timedelta(minutes=5)
            or occurred < cutoff
        ):
            rejected.append(fact.operation_id)
            continue
        digest = digest_canonical("ai-stp:installation-operation:v1", fact.model_dump(mode="json"))
        existing = await session.get(FactRow, (organization_id, fact.operation_id))
        if existing is not None and existing.fact_digest != digest:
            rejected.append(fact.operation_id)
            continue
        if fact.operation_id in seen or existing is not None:
            duplicates.append(fact.operation_id)
            continue
        session.add(_row(organization_id, fact, occurred, digest))
        try:
            async with session.begin_nested():
                await session.flush()
        except IntegrityError:
            # A concurrent ingest of the same operation_id committed between
            # the existence read and this flush: classify it by the stored
            # row's digest, the same verdict the read path would produce.
            stored = await session.get(FactRow, (organization_id, fact.operation_id))
            if stored is None:
                raise
            if stored.fact_digest != digest:
                rejected.append(fact.operation_id)
            else:
                duplicates.append(fact.operation_id)
            continue
        seen.add(fact.operation_id)
        accepted.append(fact.operation_id)
    await session.flush()
    return InstallationOperationReceipt(
        accepted_ids=accepted, duplicate_ids=duplicates, rejected_ids=rejected
    )


def _row(
    organization_id: str, fact: InstallationOperationFact, occurred: datetime, digest: str
) -> FactRow:
    return FactRow(
        organization_id=organization_id,
        operation_id=fact.operation_id,
        fact_digest=digest,
        employee_account_id=fact.employee_id,
        device_id=fact.device_id,
        project_id=fact.project_id,
        harness=fact.harness,
        scope=fact.scope,
        action=fact.action,
        result=fact.result,
        occurred_at=occurred,
        setup_stable_id=fact.setup_stable_id,
        setup_version=fact.setup_version,
        components=[item.model_dump(mode="json") for item in fact.components],
        components_complete=fact.components_complete,
        schema_version=fact.schema_version,
    )
