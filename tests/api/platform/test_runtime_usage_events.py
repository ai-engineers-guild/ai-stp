"""Runtime usage event ingestion and scoped drill-down (SPEC-088, #218).

Exercises the new platform service and the new routers directly - the global
app registry is integration-owned and untouched here.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_contracts.runtime_usage import (
    RuntimeUsageComponentCoordinate,
    RuntimeUsageEvent,
    RuntimeUsageEventBatch,
    RuntimeUsageEventQuery,
    RuntimeUsageSetupCoordinate,
)
from ai_stp_foundation.ids import new_id
from ai_stp_platform import runtime_usage_service
from ai_stp_platform.models import Account, Device
from ai_stp_platform.organization_models import (
    CorporateProject,
    CorporateRole,
    CorporateRoleBinding,
    CorporateRolePermission,
    CorporateTeam,
    CorporateTeamMember,
    Organization,
    OrganizationMembership,
    ProjectIdentity,
)
from ai_stp_platform.tenant_scope import set_tenant_scope

pytestmark = pytest.mark.platform

DIGEST = "sha256:" + "a" * 64
INVOKED = "2026-09-22T10:00:00.000Z"
NOW = datetime(2026, 9, 22, 12, 0, 0, tzinfo=UTC)


def _event(organization_id: str, employee_id: str, **overrides: object) -> RuntimeUsageEvent:
    fields: dict[str, object] = {
        "event_id": f"usage_event_{new_id('account')[-26:]}",
        "organization_id": organization_id,
        "employee_id": employee_id,
        "device_id": "device-01",
        "project_id": new_id("remote_project"),
        "harness": "claude-code",
        "invoked_at": INVOKED,
        "outcome": "succeeded",
        "setup": RuntimeUsageSetupCoordinate(
            stable_id=new_id("setup"), version="1.0", passport_digest=DIGEST
        ),
        "component": RuntimeUsageComponentCoordinate(
            kind="skill",
            stable_id=new_id("component"),
            version="1.0",
            passport_digest=DIGEST,
        ),
    }
    fields.update(overrides)
    return RuntimeUsageEvent(**fields)  # pyright: ignore[reportArgumentType]


async def _seed_tenant(
    session: AsyncSession,
) -> tuple[str, str, str, str, str]:
    """An org, a superadmin, a lead with one team, one member, one project."""
    organization_id = new_id("organization")
    superadmin = new_id("account")
    lead = new_id("account")
    member = new_id("account")
    team_id = new_id("operation")
    project_id = new_id("remote_project")
    # FORCE RLS makes tenant rows invisible without the scope GUC, so the
    # foreign-key checks on dependents would fail with "not present".
    await set_tenant_scope(session, organization_id)
    session.add(Organization(id=organization_id, kind="corporate", display_name="Acme"))
    # The org row must exist before roles and bindings; the FKs live only in
    # DDL, so the unit of work does not order them.
    await session.flush()
    for account_id in (superadmin, lead, member):
        session.add(Account(id=account_id, status="active"))
        session.add(
            OrganizationMembership(
                organization_id=organization_id,
                account_id=account_id,
                role="member",
                state="active",
            )
        )
    # Memberships must exist before bindings; the tenant-scoped FKs live
    # only in DDL, so the unit of work does not order these inserts.
    await session.flush()
    for name in ("superadmin", "lead", "staff"):
        session.add(CorporateRole(organization_id=organization_id, name=name))
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
    for permission in (
        "telemetry_usage.ingest",
        "telemetry_usage.read",
        "telemetry_usage.events",
    ):
        session.add(
            CorporateRolePermission(
                organization_id=organization_id, role="lead", permission=permission
            )
        )
    session.add(
        CorporateRolePermission(
            organization_id=organization_id, role="staff", permission="telemetry_usage.ingest"
        )
    )
    # Memberships must exist before bindings; the FK lives only in DDL.
    await session.flush()
    session.add(
        CorporateRoleBinding(
            id="binding-superadmin",
            organization_id=organization_id,
            principal_type="user",
            account_id=superadmin,
            role="superadmin",
            scope_kind="organization",
            scope_id="*",
            state="active",
        )
    )
    session.add(CorporateTeam(id=team_id, organization_id=organization_id, name="Platform"))
    await session.flush()
    session.add(
        CorporateTeamMember(organization_id=organization_id, team_id=team_id, account_id=member)
    )
    session.add(
        CorporateRoleBinding(
            id="binding-lead",
            organization_id=organization_id,
            principal_type="user",
            account_id=lead,
            role="lead",
            scope_kind="team",
            scope_id=team_id,
            state="active",
        )
    )
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
    session.add(Device(id="device-01", account_id=member, public_key="key-device-01"))
    await session.commit()
    return organization_id, superadmin, lead, member, project_id


async def test_ingest_deduplicates_on_event_key(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    _, sessionmaker, _ = db_api_client
    async with sessionmaker() as db:
        organization_id, _, _, member, project_id = await _seed_tenant(db)
    async with sessionmaker() as db:
        event = _event(organization_id, member, project_id=project_id)
        batch = RuntimeUsageEventBatch(events=[event])
        first = await runtime_usage_service.ingest_events(
            db,
            organization_id=organization_id,
            batch=batch,
            caller_account_id=member,
            caller_device_id="device-01",
            now=NOW,
        )
        assert (first.accepted, first.duplicates, first.rejected) == (1, 0, 0)
        await db.commit()
    async with sessionmaker() as db:
        # A retry of the same buffered batch must not double-store.
        replay = await runtime_usage_service.ingest_events(
            db,
            organization_id=organization_id,
            batch=batch,
            caller_account_id=member,
            caller_device_id="device-01",
            now=NOW,
        )
        assert (replay.accepted, replay.duplicates, replay.rejected) == (0, 1, 0)


async def test_ingest_rejects_cross_tenant_event(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    _, sessionmaker, _ = db_api_client
    async with sessionmaker() as db:
        organization_id, _, _, member, _ = await _seed_tenant(db)
    async with sessionmaker() as db:
        forged = _event(new_id("organization"), member)
        result = await runtime_usage_service.ingest_events(
            db,
            organization_id=organization_id,
            batch=RuntimeUsageEventBatch(events=[forged]),
            caller_account_id=member,
            caller_device_id="device-01",
            now=NOW,
        )
        assert result.rejected == 1
        assert result.accepted == 0


async def test_resolve_scope_isolates_team_visibility(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    _, sessionmaker, _ = db_api_client
    async with sessionmaker() as db:
        organization_id, superadmin, lead, member, _ = await _seed_tenant(db)
        # _seed_tenant committed; the scope GUC is transaction-local.
        await set_tenant_scope(db, organization_id)
        other = new_id("account")
        db.add(Account(id=other, status="active"))
        db.add(
            OrganizationMembership(
                organization_id=organization_id,
                account_id=other,
                role="member",
                state="active",
            )
        )
        await db.commit()
    async with sessionmaker() as db:
        assert (
            await runtime_usage_service.resolve_scope(
                db,
                organization_id=organization_id,
                principal_id=superadmin,
                permission=runtime_usage_service.PERMISSION_READ,
            )
        ).employees is None
        scope = await runtime_usage_service.resolve_scope(
            db,
            organization_id=organization_id,
            principal_id=lead,
            permission=runtime_usage_service.PERMISSION_READ,
        )
        assert scope.employees == frozenset({lead, member})
        denied = await runtime_usage_service.resolve_scope(
            db,
            organization_id=organization_id,
            principal_id=other,
            permission=runtime_usage_service.PERMISSION_READ,
        )
        assert denied.denied
        # The export permission is separate: a lead with ingest, read, and
        # events gets no export-level scope.
        assert (
            await runtime_usage_service.resolve_scope(
                db,
                organization_id=organization_id,
                principal_id=lead,
                permission=runtime_usage_service.PERMISSION_EXPORT,
            )
        ).denied


async def test_list_events_applies_employee_scope(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    _, sessionmaker, _ = db_api_client
    async with sessionmaker() as db:
        organization_id, _, lead, member, project_id = await _seed_tenant(db)
        # _seed_tenant committed; the scope GUC is transaction-local.
        await set_tenant_scope(db, organization_id)
        outsider = new_id("account")
        db.add(Account(id=outsider, status="active"))
        db.add(
            OrganizationMembership(
                organization_id=organization_id,
                account_id=outsider,
                role="member",
                state="active",
            )
        )
        db.add(Device(id="device-02", account_id=outsider, public_key="key-device-02"))
        await db.commit()
        member_ingest = await runtime_usage_service.ingest_events(
            db,
            organization_id=organization_id,
            batch=RuntimeUsageEventBatch(
                events=[_event(organization_id, member, project_id=project_id)]
            ),
            caller_account_id=member,
            caller_device_id="device-01",
            now=NOW,
        )
        assert (member_ingest.accepted, member_ingest.rejected) == (1, 0)
        outsider_ingest = await runtime_usage_service.ingest_events(
            db,
            organization_id=organization_id,
            batch=RuntimeUsageEventBatch(
                events=[
                    _event(
                        organization_id,
                        outsider,
                        device_id="device-02",
                        project_id=project_id,
                    )
                ]
            ),
            caller_account_id=outsider,
            caller_device_id="device-02",
            now=NOW,
        )
        assert (outsider_ingest.accepted, outsider_ingest.rejected) == (1, 0)
        await db.commit()
    async with sessionmaker() as db:
        scope = await runtime_usage_service.resolve_scope(
            db,
            organization_id=organization_id,
            principal_id=lead,
            permission=runtime_usage_service.PERMISSION_EVENTS,
        )
        assert scope.employees == frozenset({lead, member})
        page = await runtime_usage_service.list_events(
            db,
            organization_id=organization_id,
            query=RuntimeUsageEventQuery(),
            scope=scope,
        )
        assert {event.employee_id for event in page.events} == {member}
        # The redacted view carries no digest-bearing or content field.
        for event in page.events:
            assert set(event.model_dump()) <= {
                "event_id",
                "employee_id",
                "device_id",
                "project_id",
                "harness",
                "setup_stable_id",
                "setup_version",
                "component_kind",
                "component_stable_id",
                "component_version",
                "invoked_at",
                "outcome",
            }
