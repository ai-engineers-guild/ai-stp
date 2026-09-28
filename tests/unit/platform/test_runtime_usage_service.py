"""Service-level checks for corporate runtime usage over SQLite (SPEC-088).

The async service is exercised against a real database - the same code path
PostgreSQL takes minus RLS, which `set_tenant_scope` already no-ops off the
postgres dialect. Governance tables (`telemetry_policy`,
`telemetry_revocation`) are the privacy stream's seam: tests create stub tables
where a behavior depends on them and leave them absent where it must not.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import Table, create_engine, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, sessionmaker

from ai_stp_contracts.installation_inventory import (
    InstallationInventoryBatch,
    InstallationInventorySnapshot,
    InventoryObservedComponent,
)
from ai_stp_contracts.installation_usage import (
    InstallationOperationBatch,
    InstallationOperationFact,
)
from ai_stp_contracts.runtime_usage import (
    RuntimeUsageEvent,
    RuntimeUsageEventBatch,
    RuntimeUsageEventQuery,
    RuntimeUsageExportRequest,
    RuntimeUsageReportQuery,
)
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform import (
    installation_inventory_service,
    installation_usage_service,
    runtime_usage_service,
    telemetry_privacy_service,
)
from ai_stp_platform.db import Base
from ai_stp_platform.installation_inventory_models import (
    InstallationInventorySnapshot as InventoryRow,
)
from ai_stp_platform.installation_usage_models import InstallationOperationFact as InstallationRow
from ai_stp_platform.models import Account, CatalogMetadata, Device
from ai_stp_platform.organization_models import (
    CorporateCatalogAssignment,
    CorporateProject,
    CorporateProjectMember,
    CorporateRole,
    CorporateRoleBinding,
    CorporateRolePermission,
    CorporateServicePrincipal,
    CorporateTeam,
    CorporateTeamMember,
    Organization,
    OrganizationMembership,
    ProjectIdentity,
)
from ai_stp_platform.runtime_usage_models import (
    RuntimeUsageEvent as EventRow,
)
from ai_stp_platform.runtime_usage_models import (
    RuntimeUsageExport as ExportRow,
)
from ai_stp_platform.technology_models import (
    EmployeeTechnology,
    ProjectTechnologyRelation,
    Technology,
)
from ai_stp_platform.telemetry_policy_models import TelemetryPolicy

DIGEST = "sha256:" + "cd" * 32
NOW = datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC)
RECENT = NOW - timedelta(hours=1)

TABLES = [
    Account.__table__,
    Organization.__table__,
    Device.__table__,
    OrganizationMembership.__table__,
    CorporateRole.__table__,
    CorporateRolePermission.__table__,
    CorporateServicePrincipal.__table__,
    CorporateRoleBinding.__table__,
    CorporateTeam.__table__,
    CorporateTeamMember.__table__,
    CorporateProjectMember.__table__,
    ProjectIdentity.__table__,
    CorporateProject.__table__,
    CatalogMetadata.__table__,
    CorporateCatalogAssignment.__table__,
    Technology.__table__,
    ProjectTechnologyRelation.__table__,
    EmployeeTechnology.__table__,
    EventRow.__table__,
    ExportRow.__table__,
    InstallationRow.__table__,
    InventoryRow.__table__,
    TelemetryPolicy.__table__,
]


class _SyncFacade:
    """The AsyncSession surface over a synchronous SQLite session.

    No async SQLite driver is a test dependency, so the same SQLAlchemy
    statements the service issues run against a real synchronous session
    instead. `run_sync` receives the underlying session exactly as the async
    API would hand it over.
    """

    def __init__(self, sync: Session) -> None:
        self._sync = sync

    def get_bind(self) -> object:
        return self._sync.get_bind()

    def add(self, row: object) -> None:
        self._sync.add(row)

    async def execute(self, statement: object, parameters: object = None) -> Any:
        return self._sync.execute(statement, parameters)  # type: ignore[arg-type]

    async def scalar(self, statement: object, parameters: object = None) -> Any:
        return self._sync.scalar(statement, parameters)  # type: ignore[arg-type]

    async def scalars(self, statement: object, parameters: object = None) -> Any:
        return self._sync.scalars(statement, parameters)  # type: ignore[arg-type]

    async def get(self, entity: object, ident: object) -> Any:
        return self._sync.get(entity, ident)  # type: ignore[arg-type]

    async def flush(self) -> None:
        self._sync.flush()

    async def commit(self) -> None:
        self._sync.commit()

    def begin_nested(self) -> Any:
        transaction = self._sync.begin_nested()

        class _AsyncNested:
            async def __aenter__(self) -> Any:
                return transaction.__enter__()

            async def __aexit__(self, *exc_info: object) -> Any:
                return transaction.__exit__(*exc_info)

        return _AsyncNested()

    async def run_sync(self, fn: Callable[..., Any], *args: object) -> Any:
        return fn(self._sync, *args)


@pytest.fixture()
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    engine = create_engine(f"sqlite:///{tmp_path}/service.db")
    Base.metadata.create_all(engine, tables=cast("Sequence[Table]", TABLES))
    maker = sessionmaker(engine, expire_on_commit=False)
    try:
        with maker() as sync:
            yield cast(AsyncSession, _SyncFacade(sync))
    finally:
        engine.dispose()


class Tenant:
    """A seeded tenant: org, two employees with devices, one team, one project."""

    def __init__(self) -> None:
        self.organization_id = new_id("organization")
        self.alice = new_id("account")
        self.bob = new_id("account")
        self.device_a = new_id("device")
        self.device_b = new_id("device")
        self.team_id = new_id("operation")
        self.project_id = new_id("remote_project")
        self.technology_id = new_id("technology")


async def _seed(session: AsyncSession) -> Tenant:
    tenant = Tenant()
    org = Organization(
        id=tenant.organization_id,
        kind="corporate",
        display_name="Acme",
        policy_revision=1,
    )
    session.add(org)
    session.add(
        TelemetryPolicy(
            organization_id=tenant.organization_id,
            raw_retention_days=90,
            aggregate_retention_days=365,
            legal_basis="contract",
            usage_collection_enabled=True,
            policy_version=1,
        )
    )
    for account_id, device_id in (
        (tenant.alice, tenant.device_a),
        (tenant.bob, tenant.device_b),
    ):
        session.add(Account(id=account_id))
        session.add(
            OrganizationMembership(
                organization_id=tenant.organization_id,
                account_id=account_id,
                role="staff",
                state="active",
            )
        )
        session.add(Device(id=device_id, account_id=account_id, public_key=f"key-{device_id}"))
    for role, permissions in (
        ("staff", {runtime_usage_service.PERMISSION_INGEST}),
        (
            "lead",
            {
                runtime_usage_service.PERMISSION_INGEST,
                runtime_usage_service.PERMISSION_READ,
            },
        ),
        (
            "superadmin",
            {
                runtime_usage_service.PERMISSION_INGEST,
                runtime_usage_service.PERMISSION_READ,
                runtime_usage_service.PERMISSION_EVENTS,
                runtime_usage_service.PERMISSION_EXPORT,
            },
        ),
    ):
        session.add(CorporateRole(organization_id=tenant.organization_id, name=role))
        for permission in permissions:
            session.add(
                CorporateRolePermission(
                    organization_id=tenant.organization_id,
                    role=role,
                    permission=permission,
                )
            )
    session.add(
        CorporateRoleBinding(
            id=new_id("operation"),
            organization_id=tenant.organization_id,
            principal_type="user",
            account_id=tenant.alice,
            role="superadmin",
            scope_kind="organization",
            scope_id="*",
        )
    )
    session.add(
        CorporateTeam(id=tenant.team_id, organization_id=tenant.organization_id, name="Platform")
    )
    session.add(
        CorporateTeamMember(
            organization_id=tenant.organization_id,
            team_id=tenant.team_id,
            account_id=tenant.bob,
            role="staff",
        )
    )
    session.add(
        ProjectIdentity(
            id=tenant.project_id,
            organization_id=tenant.organization_id,
            namespace="remote",
            external_key="acme/api",
            display_name="API",
        )
    )
    session.add(
        CorporateProject(
            id=tenant.project_id,
            organization_id=tenant.organization_id,
            name="API",
            lifecycle="active",
            state="active",
        )
    )
    await session.commit()
    return tenant


def _event(tenant: Tenant, event_id: str, **overrides: object) -> RuntimeUsageEvent:
    values: dict[str, object] = {
        "event_id": event_id,
        "organization_id": tenant.organization_id,
        "employee_id": tenant.alice,
        "device_id": tenant.device_a,
        "project_id": tenant.project_id,
        "harness": "claude-code",
        "setup": {
            "stable_id": "setup_main",
            "version": "1.0",
            "passport_digest": DIGEST,
        },
        "component": {
            "kind": "skill",
            "stable_id": "skill_review",
            "version": "2.0",
            "passport_digest": DIGEST,
        },
        "invoked_at": format_timestamp(RECENT),
        "outcome": "succeeded",
        "source": "native_hook",
    }
    values.update(overrides)
    return RuntimeUsageEvent.model_validate(values)


async def _ingest(
    session: AsyncSession,
    tenant: Tenant,
    events: list[RuntimeUsageEvent],
    **overrides: object,
):
    return await runtime_usage_service.ingest_events(
        session,
        organization_id=tenant.organization_id,
        batch=RuntimeUsageEventBatch(events=events),
        caller_account_id=str(overrides.get("caller", tenant.alice)),
        caller_device_id=cast("str | None", overrides.get("caller_device", tenant.device_a)),
        now=NOW,
    )


class TestIngest:
    async def test_collection_policy_is_independent_of_inventory(
        self, session: AsyncSession
    ) -> None:
        tenant = await _seed(session)
        policy = await session.get(TelemetryPolicy, tenant.organization_id)
        assert policy is not None
        policy.inventory_scan_enabled = True
        policy.usage_collection_enabled = False
        await session.flush()
        result = await _ingest(session, tenant, [_event(tenant, "usage_event_0000000000105")])
        assert result.rejected == 1
        assert result.accepted == 0

    async def test_required_registration_needs_collection(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        with pytest.raises(
            telemetry_privacy_service.TelemetryPolicyValidationError,
            match="required usage registration",
        ):
            await telemetry_privacy_service.write_policy(
                session,
                organization_id=tenant.organization_id,
                raw_retention_days=90,
                aggregate_retention_days=365,
                legal_basis="contract",
                notice_text=None,
                notice_revision=0,
                usage_collection_enabled=False,
                usage_registration_required=True,
                expected_policy_revision=1,
                updated_by=tenant.alice,
            )

    async def test_accepts_then_deduplicates(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        event = _event(tenant, "usage_event_0000000000001")
        result = await _ingest(session, tenant, [event])
        assert (result.accepted, result.duplicates, result.rejected) == (1, 0, 0)
        assert result.accepted_ids == [event.event_id]
        replay = await _ingest(session, tenant, [event])
        assert (replay.accepted, replay.duplicates, replay.rejected) == (0, 1, 0)
        assert replay.duplicate_ids == [event.event_id]

    @pytest.mark.parametrize("same_batch", [False, True])
    async def test_native_confirmation_promotes_one_fallback_event(
        self, session: AsyncSession, same_batch: bool
    ) -> None:
        tenant = await _seed(session)
        fallback = _event(tenant, "usage_event_promoted", source="agent_reported")
        native = fallback.model_copy(update={"source": "native_hook", "outcome": "failed"})
        if same_batch:
            await _ingest(session, tenant, [fallback, native])
        else:
            await _ingest(session, tenant, [fallback])
            result = await _ingest(session, tenant, [native])
            assert result.duplicate_ids == [native.event_id]
        await _ingest(session, tenant, [fallback])
        rows = list(await session.scalars(select(EventRow)))
        assert len(rows) == 1
        assert (rows[0].source, rows[0].outcome) == ("native_hook", "failed")
        report = await runtime_usage_service.aggregate_report(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageReportQuery(),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        assert report.total_events == 1

    async def test_duplicate_id_with_changed_component_is_rejected(
        self, session: AsyncSession
    ) -> None:
        tenant = await _seed(session)
        event = _event(tenant, "usage_event_collision")
        await _ingest(session, tenant, [event])
        changed = event.model_copy(
            update={"component": event.component.model_copy(update={"stable_id": "skill_other"})}
        )
        result = await _ingest(session, tenant, [changed])
        assert result.rejected_ids == [event.event_id]
        assert result.duplicates == 0

    async def test_installation_fact_is_bound_and_idempotent(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        fact = InstallationOperationFact(
            operation_id=new_id("operation"),
            organization_id=tenant.organization_id,
            employee_id=tenant.alice,
            device_id=tenant.device_a,
            project_id=tenant.project_id,
            harness="codex",
            scope="global",
            action="install",
            result="verified",
            occurred_at=format_timestamp(RECENT),
            setup_stable_id="setup_demo",
            setup_version="1.0",
        )

        async def ingest(item: InstallationOperationFact):
            return await installation_usage_service.ingest_operations(
                session,
                organization_id=tenant.organization_id,
                batch=InstallationOperationBatch(operations=[item]),
                caller_account_id=tenant.alice,
                caller_device_id=tenant.device_a,
                now=NOW,
            )

        first = await ingest(fact)
        assert first.accepted_ids == [fact.operation_id]
        replay = await ingest(fact)
        assert replay.duplicate_ids == [fact.operation_id]
        forged = await ingest(fact.model_copy(update={"result": "partial"}))
        assert forged.rejected_ids == [fact.operation_id]
        other = fact.model_copy(
            update={"operation_id": new_id("operation"), "employee_id": tenant.bob}
        )
        foreign = await ingest(other)
        assert foreign.rejected_ids == [other.operation_id]

    async def test_inventory_snapshot_is_bound_and_idempotent(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        policy = await session.get(TelemetryPolicy, tenant.organization_id)
        assert policy is not None
        snapshot = InstallationInventorySnapshot(
            scan_id="inventory:000000000000000000000001",
            organization_id=tenant.organization_id,
            employee_id=tenant.alice,
            device_id=tenant.device_a,
            project_id=tenant.project_id,
            scope="project",
            scanned_at=format_timestamp(RECENT),
            complete=False,
            components=[
                InventoryObservedComponent(
                    location_digest=DIGEST,
                    kind="skill",
                    harness="codex",
                    source="managed",
                    state="present",
                    stable_id=new_id("component"),
                    version="2.0",
                    setup_stable_id=new_id("setup"),
                    setup_version="1.0",
                )
            ],
        )

        async def ingest(item: InstallationInventorySnapshot):
            return await installation_inventory_service.ingest_snapshots(
                session,
                organization_id=tenant.organization_id,
                batch=InstallationInventoryBatch(snapshots=[item]),
                caller_account_id=tenant.alice,
                caller_device_id=tenant.device_a,
                now=NOW,
            )

        assert (await ingest(snapshot)).rejected_ids == [snapshot.scan_id]
        policy.inventory_scan_enabled = True
        first = await ingest(snapshot)
        assert first.accepted_ids == [snapshot.scan_id]
        stored = await session.get(InventoryRow, (tenant.organization_id, snapshot.scan_id))
        assert stored is not None and stored.complete is False
        assert stored.components[0]["version"] == "2.0"
        assert (await ingest(snapshot)).duplicate_ids == [snapshot.scan_id]
        changed = snapshot.model_copy(update={"complete": True})
        assert (await ingest(changed)).rejected_ids == [snapshot.scan_id]
        foreign = snapshot.model_copy(
            update={"scan_id": "inventory:000000000000000000000002", "employee_id": tenant.bob}
        )
        assert (await ingest(foreign)).rejected_ids == [foreign.scan_id]

    async def test_duplicate_within_one_batch_is_counted_once(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        event = _event(tenant, "usage_event_0000000000008")
        result = await _ingest(session, tenant, [event, event])
        assert (result.accepted, result.duplicates, result.rejected) == (1, 1, 0)

    async def test_payload_cannot_speak_for_another_employee(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        result = await _ingest(
            session,
            tenant,
            [_event(tenant, "usage_event_0000000000002", employee_id=tenant.bob)],
        )
        assert result.accepted == 0 and result.rejected == 1

    async def test_device_must_match_the_session(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        result = await _ingest(
            session,
            tenant,
            [_event(tenant, "usage_event_0000000000003", device_id=tenant.device_b)],
        )
        assert result.rejected == 1

    async def test_revoked_session_device_cannot_emit(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        device = await session.get(Device, tenant.device_a)
        assert device is not None
        device.state = "revoked"
        await session.commit()
        result = await _ingest(session, tenant, [_event(tenant, "usage_event_0000000000103")])
        assert result.rejected == 1

    async def test_deviceless_session_may_name_own_active_device(
        self, session: AsyncSession
    ) -> None:
        tenant = await _seed(session)
        ok = await _ingest(
            session,
            tenant,
            [_event(tenant, "usage_event_0000000000004")],
            caller_device=None,
        )
        assert ok.accepted == 1
        foreign = await _ingest(
            session,
            tenant,
            [_event(tenant, "usage_event_0000000000005", device_id=tenant.device_b)],
            caller_device=None,
        )
        assert foreign.rejected == 1

    async def test_unknown_project_and_foreign_org_are_rejected(
        self, session: AsyncSession
    ) -> None:
        tenant = await _seed(session)
        result = await _ingest(
            session,
            tenant,
            [
                _event(
                    tenant,
                    "usage_event_0000000000006",
                    project_id=new_id("remote_project"),
                ),
                _event(
                    tenant,
                    "usage_event_0000000000007",
                    organization_id=new_id("organization"),
                ),
            ],
        )
        assert result.rejected == 2

    async def test_future_and_expired_events_are_rejected(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        result = await _ingest(
            session,
            tenant,
            [
                _event(
                    tenant,
                    "usage_event_0000000000008",
                    invoked_at=format_timestamp(NOW + timedelta(days=1)),
                ),
                _event(
                    tenant,
                    "usage_event_0000000000009",
                    invoked_at=format_timestamp(NOW - timedelta(days=365)),
                ),
            ],
        )
        assert result.rejected == 2


class TestReport:
    def test_setup_installation_requires_one_actual_parent_and_environment(self) -> None:
        required = {("a", "1.0"), ("b", "1.0")}
        observations: set[runtime_usage_service.InventoryCoordinate] = {
            ("a", "1.0", "setup", "1.0", "device-a", "project", "project-a"),
            ("b", "1.0", "setup", "1.0", "device-b", "project", "project-a"),
            ("b", "1.0", None, None, "device-a", "project", "project-a"),
            ("b", "1.0", "setup", "1.0", "device-a", "project", "project-b"),
        }
        installed = runtime_usage_service._setup_installed  # pyright: ignore[reportPrivateUsage]
        assert not installed(observations, "setup", "1.0", required)
        observations.add(("b", "1.0", "setup", "1.0", "device-a", "project", "project-a"))
        assert installed(observations, "setup", "1.0", required)
        assert not installed(observations, "setup", "2.0", required)

    async def test_employee_metrics_expand_setup_and_dedupe_direct_component(
        self, session: AsyncSession
    ) -> None:
        tenant = await _seed(session)
        policy = await session.get(TelemetryPolicy, tenant.organization_id)
        assert policy is not None
        policy.inventory_scan_enabled = True
        for object_kind, stable_id, version, document in (
            (
                "setup",
                "setup_main",
                "1.0",
                {
                    "name": "Main setup",
                    "components": [
                        {"stable_id": "skill_review", "version": "2.0"},
                        {"stable_id": "skill_extra", "version": "1.0"},
                    ],
                },
            ),
            ("component", "skill_review", "2.0", {"component_type": "skill"}),
        ):
            session.add(
                CatalogMetadata(
                    owner_account_id=tenant.alice,
                    object_kind=object_kind,
                    stable_id=stable_id,
                    version=version,
                    current_revision_id="revision-1",
                    visibility="public",
                    lifecycle_state="active",
                    passport_document=document,
                    published_at=NOW,
                )
            )
        await session.flush()
        for object_kind, stable_id, version in (
            ("setup", "setup_main", "1.0"),
            ("component", "skill_review", "2.0"),
        ):
            session.add(
                CorporateCatalogAssignment(
                    id=new_id("operation"),
                    organization_id=tenant.organization_id,
                    object_kind=object_kind,
                    stable_id=stable_id,
                    selector="exact",
                    version=version,
                    state="current",
                    revision=1,
                )
            )
        session.add(
            InventoryRow(
                organization_id=tenant.organization_id,
                scan_id="scan-assigned",
                snapshot_digest=DIGEST,
                employee_account_id=tenant.alice,
                device_id=tenant.device_a,
                project_id=tenant.project_id,
                scope="project",
                scanned_at=RECENT,
                complete=True,
                components=[
                    {
                        "kind": "skill",
                        "harness": "claude-code",
                        "source": "managed",
                        "state": "present",
                        "stable_id": "skill_review",
                        "version": "2.0",
                    }
                ],
            )
        )
        await session.flush()
        await _ingest(
            session,
            tenant,
            [_event(tenant, "usage_event_0000000000300", outcome="failed")],
        )
        report = await runtime_usage_service.aggregate_report(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageReportQuery(group_by="employee"),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        alice = next(row for row in report.employees if row.employee_id == tenant.alice)
        assert (
            alice.assigned_components,
            alice.installed_components,
            alice.used_components,
            alice.uses,
            alice.active_days,
        ) == (2, 1, 1, 1, 1)
        selected = await runtime_usage_service.aggregate_report(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageReportQuery(employee_id=tenant.alice),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        states = {
            (row.object_kind, row.stable_id, row.parent_setup_stable_id): row.installation_state
            for row in selected.objects
        }
        assert states[("component", "skill_review", None)] == "present"
        assert states[("component", "skill_review", "setup_main")] == "missing"
        assert states[("component", "skill_extra", "setup_main")] == "missing"
        assert states[("setup", "setup_main", None)] == "missing"
        assert (
            next(row for row in selected.objects if row.object_kind == "setup").name == "Main setup"
        )
        assert all(row.last_checked_at == format_timestamp(RECENT) for row in selected.objects)
        session.add(
            InventoryRow(
                organization_id=tenant.organization_id,
                scan_id="scan-old-version",
                snapshot_digest=DIGEST,
                employee_account_id=tenant.alice,
                device_id=tenant.device_a,
                project_id=tenant.project_id,
                scope="project",
                scanned_at=NOW,
                complete=True,
                components=[
                    {
                        "kind": "skill",
                        "harness": "claude-code",
                        "source": "managed",
                        "state": "present",
                        "stable_id": "skill_review",
                        "version": "1.0",
                    }
                ],
            )
        )
        await session.flush()
        outdated = await runtime_usage_service.aggregate_report(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageReportQuery(group_by="employee"),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        alice = next(row for row in outdated.employees if row.employee_id == tenant.alice)
        assert (alice.assigned_components, alice.installed_components, alice.used_components) == (
            2,
            0,
            1,
        )

    async def test_latest_partial_inventory_never_claims_a_removal(
        self, session: AsyncSession
    ) -> None:
        tenant = await _seed(session)
        policy = await session.get(TelemetryPolicy, tenant.organization_id)
        assert policy is not None
        policy.inventory_scan_enabled = True

        def snapshot(scan_id: str, minute: int, complete: bool, state: str) -> InventoryRow:
            return InventoryRow(
                organization_id=tenant.organization_id,
                scan_id=scan_id,
                snapshot_digest=DIGEST,
                employee_account_id=tenant.alice,
                device_id=tenant.device_a,
                project_id=tenant.project_id,
                scope="project",
                scanned_at=NOW - timedelta(minutes=minute),
                complete=complete,
                components=[
                    {
                        "location_digest": DIGEST,
                        "kind": "skill",
                        "harness": "codex",
                        "source": "managed",
                        "state": state,
                        "stable_id": "skill_review",
                        "version": "2.0",
                        "setup_stable_id": "setup_main",
                        "setup_version": "1.0",
                    }
                ],
            )

        session.add(snapshot("scan_complete", 60, True, "present"))
        session.add(snapshot("scan_partial", 30, False, "missing"))
        await session.flush()
        await _ingest(session, tenant, [_event(tenant, "usage_event_partial_inventory")])
        report = await runtime_usage_service.aggregate_report(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageReportQuery(employee_id=tenant.alice),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        assert report.inventory_scan_enabled
        assert len(report.inventory_employees) == 1
        observed = report.inventory_employees[0]
        assert observed.coverage == "partial"
        for collection_state, expected_ids, expected_events in (
            ("partial", {tenant.alice}, 1),
            ("unknown", {tenant.bob}, 0),
            ("complete", set[str](), 0),
            ("disabled", set[str](), 0),
        ):
            filtered = await runtime_usage_service.aggregate_report(
                session,
                organization_id=tenant.organization_id,
                query=RuntimeUsageReportQuery.model_validate(
                    {"collection_state": collection_state}
                ),
                scope=runtime_usage_service.UsageScope(employees=None),
                now=NOW,
            )
            assert {row.employee_id for row in filtered.employees} == expected_ids
            assert filtered.total_events == expected_events
            assert sum(row.uses for row in filtered.by_day) == expected_events
            assert all(row.employee_id in expected_ids for row in filtered.inventory_employees)
        assert observed.observed_present == 0
        assert observed.last_complete_at == format_timestamp(NOW - timedelta(minutes=60))
        assert (
            next(row for row in report.objects if row.object_kind == "component").installation_state
            == "unknown"
        )
        session.add(snapshot("scan_recovered", 15, True, "present"))
        await session.flush()
        recovered = await runtime_usage_service.aggregate_report(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageReportQuery(employee_id=tenant.alice),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        assert recovered.inventory_employees[0].coverage == "complete"
        assert recovered.inventory_employees[0].observed_present == 1
        assert (
            next(
                row for row in recovered.objects if row.object_kind == "component"
            ).installation_state
            == "present"
        )
        session.add(snapshot("scan_modified", 5, True, "modified"))
        await session.flush()
        modified = await runtime_usage_service.aggregate_report(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageReportQuery(employee_id=tenant.alice),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        assert (
            next(
                row for row in modified.objects if row.object_kind == "component"
            ).installation_state
            == "modified"
        )
        stale = await runtime_usage_service.aggregate_report(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageReportQuery(employee_id=tenant.alice),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW + timedelta(days=2),
        )
        assert stale.inventory_employees[0].coverage == "stale"
        assert stale.inventory_employees[0].observed_present == 0
        assert (
            next(row for row in stale.objects if row.object_kind == "component").installation_state
            == "unknown"
        )
        denied = await runtime_usage_service.aggregate_report(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageReportQuery(employee_id=tenant.alice),
            scope=runtime_usage_service.UsageScope(employees=frozenset()),
            now=NOW,
        )
        assert denied.inventory_employees == []

    async def test_chart_uses_organization_timezone_and_confirmed_filter(
        self, session: AsyncSession
    ) -> None:
        tenant = await _seed(session)
        policy = await session.get(TelemetryPolicy, tenant.organization_id)
        assert policy is not None
        policy.report_timezone = "Pacific/Auckland"
        await _ingest(
            session,
            tenant,
            [
                _event(
                    tenant,
                    "usage_event_0000000000200",
                    invoked_at="2026-02-01T10:30:00.000Z",
                ),
                _event(
                    tenant,
                    "usage_event_0000000000201",
                    invoked_at="2026-02-01T11:30:00.000Z",
                    outcome="failed",
                ),
                _event(
                    tenant,
                    "usage_event_0000000000202",
                    invoked_at="2026-02-01T11:30:00.000Z",
                    source="agent_reported",
                ),
            ],
        )
        report = await runtime_usage_service.aggregate_report(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageReportQuery(),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        assert report.total_events == sum(bucket.uses for bucket in report.by_day) == 2
        assert report.rows[0].active_days == 2
        assert [(bucket.day, bucket.uses) for bucket in report.by_day] == [
            ("2026-02-01", 1),
            ("2026-02-02", 1),
        ]
        assert [(bucket.weekday, bucket.hour, bucket.uses) for bucket in report.by_hour] == [
            (0, 0, 1),
            (6, 23, 1),
        ]

    async def test_only_native_invocations_count_as_uses(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        await _ingest(
            session,
            tenant,
            [
                _event(tenant, "usage_event_0000000000100"),
                _event(tenant, "usage_event_0000000000101", source="agent_reported"),
                _event(tenant, "usage_event_0000000000102", activity_kind="load"),
            ],
        )
        report = await runtime_usage_service.aggregate_report(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageReportQuery(),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        assert report.total_events == 1
        assert report.rows[0].invocations == 1
        listing = await runtime_usage_service.list_events(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageEventQuery(),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        assert {(event.source, event.activity_kind) for event in listing.events} == {
            ("native_hook", "invocation"),
            ("agent_reported", "invocation"),
            ("native_hook", "load"),
        }

    async def test_direct_component_does_not_gain_a_setup(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        await _ingest(
            session,
            tenant,
            [_event(tenant, "usage_event_0000000000104", setup=None)],
        )
        report = await runtime_usage_service.aggregate_report(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageReportQuery(group_by="setup"),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        assert report.total_events == 0
        assert report.rows == []
        detail = await runtime_usage_service.list_events(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageEventQuery(direct_only=True),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        assert [event.event_id for event in detail.events] == ["usage_event_0000000000104"]

    async def test_object_rows_preserve_actual_setup_relation(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        await _ingest(
            session,
            tenant,
            [
                _event(tenant, "usage_event_0000000000201"),
                _event(tenant, "usage_event_0000000000202", setup=None),
            ],
        )
        report = await runtime_usage_service.aggregate_report(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageReportQuery(),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        observed = {
            (row.object_kind, row.stable_id, row.parent_setup_stable_id): row.uses
            for row in report.objects
            if row.uses
        }
        assert observed == {
            ("setup", "setup_main", None): 1,
            ("component", "skill_review", "setup_main"): 1,
            ("component", "skill_review", None): 1,
        }
        assert report.total_events == 2
        assert report.usage_collection_enabled is True

    async def test_usage_state_filters_employee_chart_and_objects(
        self, session: AsyncSession
    ) -> None:
        tenant = await _seed(session)
        await _ingest(session, tenant, [_event(tenant, "usage_event_0000000000205")])
        report = await runtime_usage_service.aggregate_report(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageReportQuery(usage_state="no_recorded"),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        assert {row.employee_id for row in report.employees} == {tenant.bob}
        assert report.total_events == 0
        assert report.by_day == []
        assert all(row.uses == 0 for row in report.objects)

    async def test_detail_local_day_uses_organization_timezone(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        policy = await session.get(TelemetryPolicy, tenant.organization_id)
        assert policy is not None
        policy.report_timezone = "America/Los_Angeles"
        await _ingest(
            session,
            tenant,
            [
                _event(
                    tenant,
                    "usage_event_0000000000203",
                    invoked_at=format_timestamp(NOW.replace(hour=1)),
                ),
                _event(
                    tenant,
                    "usage_event_0000000000204",
                    invoked_at=format_timestamp(NOW.replace(hour=11)),
                ),
            ],
        )
        listing = await runtime_usage_service.list_events(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageEventQuery(local_day=date(2026, 2, 1)),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        assert [event.event_id for event in listing.events] == ["usage_event_0000000000204"]
        hourly = await runtime_usage_service.list_events(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageEventQuery(local_weekday=6, local_hour=3),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        assert [event.event_id for event in hourly.events] == ["usage_event_0000000000204"]

    async def test_aggregates_with_first_and_last(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        events = [
            _event(tenant, "usage_event_0000000000010", outcome="succeeded"),
            _event(
                tenant,
                "usage_event_0000000000011",
                outcome="failed",
                invoked_at=format_timestamp(RECENT + timedelta(minutes=30)),
            ),
        ]
        await _ingest(session, tenant, events)
        report = await runtime_usage_service.aggregate_report(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageReportQuery(group_by="component"),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        assert report.total_events == 2
        row = report.rows[0]
        assert row.component_stable_id == "skill_review"
        assert (row.invocations, row.succeeded, row.failed, row.cancelled) == (2, 1, 1, 0)
        assert row.first_invoked_at == format_timestamp(RECENT)
        assert row.last_invoked_at == format_timestamp(RECENT + timedelta(minutes=30))

    async def test_empty_window_returns_no_rows(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        await _ingest(session, tenant, [_event(tenant, "usage_event_0000000000012")])
        report = await runtime_usage_service.aggregate_report(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageReportQuery(
                invoked_from=format_timestamp(NOW - timedelta(minutes=10)),
                invoked_to=format_timestamp(NOW),
            ),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        assert report.total_events == 0 and report.rows == []

    async def test_team_scope_hides_other_employees(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        await _ingest(session, tenant, [_event(tenant, "usage_event_0000000000013")])
        await _ingest(
            session,
            tenant,
            [
                _event(
                    tenant,
                    "usage_event_0000000000014",
                    employee_id=tenant.bob,
                    device_id=tenant.device_b,
                )
            ],
            caller=tenant.bob,
            caller_device=tenant.device_b,
        )
        report = await runtime_usage_service.aggregate_report(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageReportQuery(group_by="employee"),
            scope=runtime_usage_service.UsageScope(employees=frozenset({tenant.bob})),
            now=NOW,
        )
        assert report.total_events == 1
        assert report.rows[0].group_value == tenant.bob

    async def test_resolve_scope_team_lead_sees_own_team(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        session.add(
            CorporateRoleBinding(
                id=new_id("operation"),
                organization_id=tenant.organization_id,
                principal_type="user",
                account_id=tenant.bob,
                role="lead",
                scope_kind="team",
                scope_id=tenant.team_id,
            )
        )
        await session.commit()
        scope = await runtime_usage_service.resolve_scope(
            session,
            organization_id=tenant.organization_id,
            principal_id=tenant.bob,
            permission=runtime_usage_service.PERMISSION_READ,
        )
        assert scope.employees == frozenset({tenant.bob})
        assert scope.team_ids == frozenset({tenant.team_id})
        denied = await runtime_usage_service.resolve_scope(
            session,
            organization_id=tenant.organization_id,
            principal_id=tenant.bob,
            permission=runtime_usage_service.PERMISSION_EXPORT,
        )
        assert denied.denied

    async def test_installed_vs_invoked(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        session.add(
            CatalogMetadata(
                owner_account_id=tenant.alice,
                object_kind="component",
                stable_id="skill_review",
                version="2.0",
                current_revision_id="rev1",
            )
        )
        session.add(
            CatalogMetadata(
                owner_account_id=tenant.alice,
                object_kind="component",
                stable_id="skill_unused",
                version="1.0",
                current_revision_id="rev2",
            )
        )
        session.add(
            CorporateCatalogAssignment(
                id=new_id("operation"),
                organization_id=tenant.organization_id,
                account_id=tenant.alice,
                object_kind="component",
                stable_id="skill_review",
                selector="exact",
                version="2.0",
            )
        )
        session.add(
            CorporateCatalogAssignment(
                id=new_id("operation"),
                organization_id=tenant.organization_id,
                object_kind="component",
                stable_id="skill_unused",
                selector="exact",
                version="1.0",
            )
        )
        await _ingest(session, tenant, [_event(tenant, "usage_event_0000000000015")])
        report = await runtime_usage_service.aggregate_report(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageReportQuery(),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        assigned = {row.stable_id: row for row in report.assigned}
        assert assigned["skill_review"].state == "recorded_use"
        assert assigned["skill_review"].invocations == 1
        assert assigned["skill_unused"].state == "no_recorded_use"
        assert assigned["skill_unused"].invocations == 0


class TestDrillDown:
    async def test_redacted_rows_and_filters(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        await _ingest(
            session,
            tenant,
            [
                _event(tenant, "usage_event_0000000000016", outcome="failed"),
                _event(tenant, "usage_event_0000000000017"),
            ],
        )
        listing = await runtime_usage_service.list_events(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageEventQuery(outcome="failed"),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        assert [row.event_id for row in listing.events] == ["usage_event_0000000000016"]
        view = listing.events[0].model_dump()
        # The drill-down view is identities and coordinates only.
        assert runtime_usage_service is not None
        assert "prompt" not in view and "payload" not in view

    async def test_revoked_subject_is_redacted_from_drilldown(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        await session.execute(
            text(
                "CREATE TABLE telemetry_revocation ("
                "organization_id TEXT NOT NULL, subject_kind TEXT NOT NULL, "
                "subject_id TEXT NOT NULL, state TEXT NOT NULL)"
            )
        )
        await _ingest(session, tenant, [_event(tenant, "usage_event_0000000000018")])
        await session.execute(
            text("INSERT INTO telemetry_revocation VALUES (:org, 'account', :account, 'revoked')"),
            {"org": tenant.organization_id, "account": tenant.alice},
        )
        listing = await runtime_usage_service.list_events(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageEventQuery(),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        assert listing.events == []
        # Aggregates still count - anonymization preserves the numbers.
        report = await runtime_usage_service.aggregate_report(
            session,
            organization_id=tenant.organization_id,
            query=RuntimeUsageReportQuery(),
            scope=runtime_usage_service.UsageScope(employees=None),
            now=NOW,
        )
        assert report.total_events == 1

    async def test_revoked_subject_cannot_ingest(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        await session.execute(
            text(
                "CREATE TABLE telemetry_revocation ("
                "organization_id TEXT NOT NULL, subject_kind TEXT NOT NULL, "
                "subject_id TEXT NOT NULL, state TEXT NOT NULL)"
            )
        )
        await session.execute(
            text("INSERT INTO telemetry_revocation VALUES (:org, 'device', :device, 'revoked')"),
            {"org": tenant.organization_id, "device": tenant.device_a},
        )
        result = await _ingest(session, tenant, [_event(tenant, "usage_event_0000000000019")])
        assert result.rejected == 1


class TestRetention:
    async def test_policy_table_governs_the_raw_window(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        policy = await session.get(TelemetryPolicy, tenant.organization_id)
        assert policy is not None
        policy.raw_retention_days = 7
        await session.flush()
        old = _event(
            tenant,
            "usage_event_0000000000020",
            invoked_at=format_timestamp(NOW - timedelta(days=8)),
        )
        result = await _ingest(session, tenant, [old])
        assert result.rejected == 1
        recent = await _ingest(session, tenant, [_event(tenant, "usage_event_0000000000021")])
        assert recent.accepted == 1

    async def test_default_window_without_policy_row(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        policy = await session.get(TelemetryPolicy, tenant.organization_id)
        assert policy is not None
        await session.execute(
            text("DELETE FROM telemetry_policy WHERE organization_id = :organization_id"),
            {"organization_id": tenant.organization_id},
        )
        await session.flush()
        assert (
            await runtime_usage_service.raw_retention_days(
                session, organization_id=tenant.organization_id
            )
            == runtime_usage_service.DEFAULT_RAW_RETENTION_DAYS
        )


class TestExport:
    async def test_export_is_bounded_digested_and_idempotent(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        await _ingest(session, tenant, [_event(tenant, "usage_event_0000000000022")])
        request = RuntimeUsageExportRequest(
            query=RuntimeUsageReportQuery(group_by="employee"),
            authorization_revision=1,
            idempotency_key="export-key-00000001",
        )
        scope = runtime_usage_service.UsageScope(employees=None)
        first = await runtime_usage_service.create_export(
            session,
            organization_id=tenant.organization_id,
            request=request,
            scope=scope,
            actor_account_id=tenant.alice,
            now=NOW,
        )
        assert first.row_count == 1
        assert first.content_digest.startswith("sha256:")
        replay = await runtime_usage_service.create_export(
            session,
            organization_id=tenant.organization_id,
            request=request,
            scope=scope,
            actor_account_id=tenant.alice,
            now=NOW,
        )
        assert replay.export_id == first.export_id
        count = await session.scalar(text("SELECT count(*) FROM runtime_usage_export"))
        assert count == 1
