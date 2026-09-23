"""Runtime usage aggregate reports and bounded exports (SPEC-088, #218)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_contracts.runtime_usage import (
    RuntimeUsageComponentCoordinate,
    RuntimeUsageEvent,
    RuntimeUsageEventBatch,
    RuntimeUsageExportRequest,
    RuntimeUsageReportQuery,
    RuntimeUsageSetupCoordinate,
)
from ai_stp_foundation.ids import new_id
from ai_stp_platform import runtime_usage_service
from ai_stp_platform.models import Account, CatalogMetadata, Device
from ai_stp_platform.organization_models import (
    CorporateCatalogAssignment,
    CorporateProject,
    CorporateRole,
    CorporateRoleBinding,
    CorporateRolePermission,
    Organization,
    OrganizationMembership,
    ProjectIdentity,
)
from ai_stp_platform.tenant_scope import set_tenant_scope

pytestmark = pytest.mark.platform

DIGEST = "sha256:" + "b" * 64
NOW = datetime(2026, 9, 22, 12, 0, 0, tzinfo=UTC)


def _event(
    organization_id: str,
    employee_id: str,
    *,
    invoked_at: str = "2026-09-20T10:00:00.000Z",
    outcome: str = "succeeded",
    component: RuntimeUsageComponentCoordinate | None = None,
    setup: RuntimeUsageSetupCoordinate | None = None,
    device_id: str = "device-01",
    project_id: str | None = None,
) -> RuntimeUsageEvent:
    return RuntimeUsageEvent(
        event_id=f"usage_event_{new_id('account')[-26:]}",
        organization_id=organization_id,
        employee_id=employee_id,
        device_id=device_id,
        project_id=project_id or new_id("remote_project"),
        harness="claude-code",
        invoked_at=invoked_at,
        outcome=outcome,  # pyright: ignore[reportArgumentType]
        setup=setup
        or RuntimeUsageSetupCoordinate(
            stable_id=new_id("setup"), version="1.0", passport_digest=DIGEST
        ),
        component=component
        or RuntimeUsageComponentCoordinate(
            kind="skill",
            stable_id=new_id("component"),
            version="1.0",
            passport_digest=DIGEST,
        ),
    )


async def _seed_admin(
    session: AsyncSession,
) -> tuple[str, str, str]:
    organization_id = new_id("organization")
    admin = new_id("account")
    project_id = new_id("remote_project")
    # FORCE RLS makes tenant rows invisible without the scope GUC, so the
    # foreign-key checks on dependents would fail with "not present".
    await set_tenant_scope(session, organization_id)
    session.add(Organization(id=organization_id, kind="corporate", display_name="Acme"))
    # Dependents reference the org row through DDL-only FKs; flush first.
    await session.flush()
    session.add(Account(id=admin, status="active"))
    session.add(Device(id="device-01", account_id=admin, public_key="key-device-01"))
    session.add(
        ProjectIdentity(
            id=project_id,
            organization_id=organization_id,
            namespace="remote",
            external_key=f"acme/{project_id[-6:]}",
            display_name="API",
            state="active",
        )
    )
    # Identity and membership rows must exist before their dependents; the
    # FKs live only in DDL, so the unit of work does not order them.
    await session.flush()
    session.add(
        CorporateProject(
            id=project_id,
            organization_id=organization_id,
            name="API",
            lifecycle="active",
            state="active",
        )
    )
    session.add(
        OrganizationMembership(
            organization_id=organization_id,
            account_id=admin,
            role="member",
            state="active",
        )
    )
    await session.flush()
    session.add(CorporateRole(organization_id=organization_id, name="superadmin"))
    await session.flush()
    for permission in (
        "telemetry_usage.ingest",
        "telemetry_usage.read",
        "telemetry_usage.events",
        "telemetry_usage.export",
    ):
        session.add(
            CorporateRolePermission(
                organization_id=organization_id, role="superadmin", permission=permission
            )
        )
    session.add(
        CorporateRoleBinding(
            id="binding-admin",
            organization_id=organization_id,
            principal_type="user",
            account_id=admin,
            role="superadmin",
            scope_kind="organization",
            scope_id="*",
            state="active",
        )
    )
    await session.commit()
    return organization_id, admin, project_id


async def test_report_groups_and_counts_deterministically(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    _, sessionmaker, _ = db_api_client
    async with sessionmaker() as db:
        organization_id, admin, project_id = await _seed_admin(db)
        component = RuntimeUsageComponentCoordinate(
            kind="skill",
            stable_id=new_id("component"),
            version="1.0",
            passport_digest=DIGEST,
        )
        await runtime_usage_service.ingest_events(
            db,
            organization_id=organization_id,
            batch=RuntimeUsageEventBatch(
                events=[
                    _event(organization_id, admin, component=component, project_id=project_id),
                    _event(
                        organization_id,
                        admin,
                        component=component,
                        outcome="failed",
                        invoked_at="2026-09-20T11:00:00.000Z",
                        project_id=project_id,
                    ),
                    _event(
                        organization_id,
                        admin,
                        invoked_at="2026-09-21T10:00:00.000Z",
                        outcome="cancelled",
                        project_id=project_id,
                    ),
                ]
            ),
            caller_account_id=admin,
            caller_device_id="device-01",
            now=NOW,
        )
        await db.commit()
    async with sessionmaker() as db:
        report = await runtime_usage_service.aggregate_report(
            db,
            organization_id=organization_id,
            query=RuntimeUsageReportQuery(group_by="component"),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        assert report.total_events == 3
        assert len(report.rows) == 2
        top = report.rows[0]
        assert top.component_stable_id == component.stable_id
        assert top.invocations == 2
        assert (top.succeeded, top.failed, top.cancelled) == (1, 1, 0)
        assert top.first_invoked_at < top.last_invoked_at


async def test_report_filters_and_empty_window(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    _, sessionmaker, _ = db_api_client
    async with sessionmaker() as db:
        organization_id, admin, project_id = await _seed_admin(db)
        await runtime_usage_service.ingest_events(
            db,
            organization_id=organization_id,
            batch=RuntimeUsageEventBatch(
                events=[_event(organization_id, admin, project_id=project_id)]
            ),
            caller_account_id=admin,
            caller_device_id="device-01",
            now=NOW,
        )
        await db.commit()
    async with sessionmaker() as db:
        empty = await runtime_usage_service.aggregate_report(
            db,
            organization_id=organization_id,
            query=RuntimeUsageReportQuery(invoked_from="2026-09-23T00:00:00.000Z"),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        assert empty.total_events == 0 and empty.rows == []
        failed_only = await runtime_usage_service.aggregate_report(
            db,
            organization_id=organization_id,
            query=RuntimeUsageReportQuery(outcome="failed"),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        assert failed_only.total_events == 0


async def test_installed_vs_invoked(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    _, sessionmaker, _ = db_api_client
    async with sessionmaker() as db:
        organization_id, admin, project_id = await _seed_admin(db)
        # _seed_admin committed; the scope GUC is transaction-local.
        await set_tenant_scope(db, organization_id)
        invoked_component = new_id("component")
        silent_component = new_id("component")
        for stable_id in (invoked_component, silent_component):
            db.add(
                CatalogMetadata(
                    owner_account_id=admin,
                    organization_id=organization_id,
                    object_kind="component",
                    stable_id=stable_id,
                    version="1.0",
                    current_revision_id=f"revision-{stable_id[-8:]}",
                    visibility="private",
                    lifecycle_state="active",
                    name=stable_id[-8:],
                    published_at=datetime.now(UTC),
                    passport_document={"fixture": True},
                    passport_digest=DIGEST,
                    trust_lane="experimental",
                )
            )
            await db.flush()
            db.add(
                CorporateCatalogAssignment(
                    id=f"assignment-{stable_id[-8:]}",
                    organization_id=organization_id,
                    account_id=admin,
                    object_kind="component",
                    stable_id=stable_id,
                    selector="exact",
                    version="1.0",
                    passport_digest=DIGEST,
                    state="current",
                )
            )
        await db.commit()
        await runtime_usage_service.ingest_events(
            db,
            organization_id=organization_id,
            batch=RuntimeUsageEventBatch(
                events=[
                    _event(
                        organization_id,
                        admin,
                        component=RuntimeUsageComponentCoordinate(
                            kind="skill",
                            stable_id=invoked_component,
                            version="1.0",
                            passport_digest=DIGEST,
                        ),
                        project_id=project_id,
                    )
                ]
            ),
            caller_account_id=admin,
            caller_device_id="device-01",
            now=NOW,
        )
        await db.commit()
    async with sessionmaker() as db:
        report = await runtime_usage_service.aggregate_report(
            db,
            organization_id=organization_id,
            query=RuntimeUsageReportQuery(),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        states = {row.stable_id: row.state for row in report.installed}
        assert states[invoked_component] == "invoked"
        assert states[silent_component] == "not_invoked"


async def test_export_is_bounded_digested_and_idempotent(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    _, sessionmaker, _ = db_api_client
    async with sessionmaker() as db:
        organization_id, admin, project_id = await _seed_admin(db)
        await runtime_usage_service.ingest_events(
            db,
            organization_id=organization_id,
            batch=RuntimeUsageEventBatch(
                events=[_event(organization_id, admin, project_id=project_id)]
            ),
            caller_account_id=admin,
            caller_device_id="device-01",
            now=NOW,
        )
        await db.commit()
    async with sessionmaker() as db:
        request = RuntimeUsageExportRequest(
            query=RuntimeUsageReportQuery(),
            authorization_revision=1,
            idempotency_key="export-idem-key-0001",
        )
        first = await runtime_usage_service.create_export(
            db,
            organization_id=organization_id,
            request=request,
            scope=runtime_usage_service.UsageScope(employees=None),
            actor_account_id=admin,
            now=NOW,
        )
        assert first.row_count == 1
        assert first.content_digest.startswith("sha256:")
        replay = await runtime_usage_service.create_export(
            db,
            organization_id=organization_id,
            request=request,
            scope=runtime_usage_service.UsageScope(employees=None),
            actor_account_id=admin,
            now=NOW,
        )
        assert replay.export_id == first.export_id
        held = await runtime_usage_service.read_export(
            db, organization_id=organization_id, export_id=first.export_id
        )
        assert held is not None and held.content_digest == first.content_digest
        # The receipt is a receipt: it carries counts and a digest, not rows.
        assert not hasattr(first, "rows")
