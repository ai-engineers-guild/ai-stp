"""Service-level checks for corporate runtime usage over SQLite (SPEC-088).

The async service is exercised against a real database - the same code path
PostgreSQL takes minus RLS, which `set_tenant_scope` already no-ops off the
postgres dialect. Governance tables (`telemetry_policy`,
`telemetry_revocation`) are the privacy stream's seam: tests create stub tables
where a behavior depends on them and leave them absent where it must not.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import Table, create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, sessionmaker

from ai_stp_contracts.runtime_usage import (
    RuntimeUsageEvent,
    RuntimeUsageEventBatch,
    RuntimeUsageEventQuery,
    RuntimeUsageExportRequest,
    RuntimeUsageReportQuery,
)
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform import runtime_usage_service
from ai_stp_platform.db import Base
from ai_stp_platform.models import Account, CatalogMetadata, Device
from ai_stp_platform.organization_models import (
    CorporateCatalogAssignment,
    CorporateProject,
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
from ai_stp_platform.technology_models import ProjectTechnologyRelation, Technology

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
    ProjectIdentity.__table__,
    CorporateProject.__table__,
    CatalogMetadata.__table__,
    CorporateCatalogAssignment.__table__,
    Technology.__table__,
    ProjectTechnologyRelation.__table__,
    EventRow.__table__,
    ExportRow.__table__,
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

    async def run_sync(self, fn: Callable[..., Any], *args: object) -> Any:
        return fn(self._sync, *args)


@pytest.fixture()
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    engine = create_engine(f"sqlite:///{tmp_path}/service.db")
    Base.metadata.create_all(engine, tables=cast("Sequence[Table]", TABLES))
    maker = sessionmaker(engine, expire_on_commit=False)
    with maker() as sync:
        yield cast(AsyncSession, _SyncFacade(sync))


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
    async def test_accepts_then_deduplicates(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
        event = _event(tenant, "usage_event_0000000000001")
        result = await _ingest(session, tenant, [event])
        assert (result.accepted, result.duplicates, result.rejected) == (1, 0, 0)
        replay = await _ingest(session, tenant, [event])
        assert (replay.accepted, replay.duplicates, replay.rejected) == (0, 1, 0)

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
        installed = {row.stable_id: row for row in report.installed}
        assert installed["skill_review"].state == "invoked"
        assert installed["skill_review"].invocations == 1
        assert installed["skill_unused"].state == "not_invoked"
        assert installed["skill_unused"].invocations == 0


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
        await session.execute(
            text(
                "CREATE TABLE telemetry_policy ("
                "organization_id TEXT PRIMARY KEY, raw_retention_days INTEGER NOT NULL)"
            )
        )
        await session.execute(
            text("INSERT INTO telemetry_policy VALUES (:org, 7)"),
            {"org": tenant.organization_id},
        )
        old = _event(
            tenant,
            "usage_event_0000000000020",
            invoked_at=format_timestamp(NOW - timedelta(days=8)),
        )
        result = await _ingest(session, tenant, [old])
        assert result.rejected == 1
        recent = await _ingest(session, tenant, [_event(tenant, "usage_event_0000000000021")])
        assert recent.accepted == 1

    async def test_default_window_without_policy_table(self, session: AsyncSession) -> None:
        tenant = await _seed(session)
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
