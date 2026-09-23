"""Corporate runtime usage: ingest binding, scoped reports, drill-down, export.

The usage routers are mounted onto the test application; production wiring
into the corporate router is the integration point outside this file.
PostgreSQL fixtures mirror `tests/api/platform/conftest.py` so the root
conftest's `pg` marker still applies through the shared fixture names.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.support.api_settings import make_settings
from tests.support.postgres import migrated_database, migrated_template

from ai_stp_api.app import create_app
from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_api.slices.corporate import usage_events, usage_reports
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.models import Account, AuditEvent, Device
from ai_stp_platform.organization_models import (
    CorporateProject,
    CorporateRoleBinding,
    CorporateTeam,
    CorporateTeamMember,
    OrganizationMembership,
    ProjectIdentity,
)
from ai_stp_platform.tenant_scope import set_tenant_scope

pytestmark = pytest.mark.platform

TEST_DB_ENV = "AI_STP_TEST_DB_URL"
BOOTSTRAP_SECRET = "corporate-bootstrap-test-secret"

DIGEST = "sha256:" + "ef" * 32
# Server-side ingest rejects events outside the tenant's raw retention
# window (default 90 days) and beyond the future-skew allowance, so the
# timestamp must be near real now, not a pinned fixture date.
INVOKED_AT = format_timestamp(datetime.now(UTC) - timedelta(hours=1))


@pytest.fixture(scope="session")
def pg_migrated_template() -> Iterator[str | None]:
    with migrated_template() as database:
        yield database


@pytest.fixture()
def migrated_database_url(
    pg_migrated_template: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[str]:
    with migrated_database(
        pg_migrated_template,
        monkeypatch,
        skip_reason=f"{TEST_DB_ENV} is required for PostgreSQL API tests",
    ) as url:
        yield url


@pytest_asyncio.fixture
async def db_api_client(
    tmp_path: Path,
    migrated_database_url: str,
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings]]:
    settings = make_settings(tmp_path, database_url=migrated_database_url)
    app = create_app(settings)
    app.include_router(usage_events.router, prefix="/v1")
    app.include_router(usage_reports.router, prefix="/v1")
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app.state.sessionmaker, settings


async def _device_session(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    account_id: str | None = None,
) -> tuple[str, str, str]:
    """One account, one registered device, one device-bound session token."""
    async with sessionmaker() as db:
        account = await db.get(Account, account_id) if account_id else None
        if account is None:
            account = Account(id=account_id or new_id("account"), status="active")
            db.add(account)
            await db.flush()
        device = Device(id=new_id("device"), account_id=account.id, public_key=f"key-{account.id}")
        db.add(device)
        await db.flush()
        issued = await issue_session(
            db, account_id=account.id, device_id=device.id, ttl_seconds=3600
        )
        await db.commit()
        return account.id, device.id, issued.raw_token


async def _tenant(
    client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    key: str,
) -> tuple[str, str, str, dict[str, str]]:
    """Bootstrap one tenant; return org, account, device, auth headers."""
    account_id, device_id, token = await _device_session(sessionmaker)
    response = await client.post(
        "/v1/corporate/bootstrap",
        json={
            "schema_version": 1,
            "organization_name": key,
            "superadmin_account_id": account_id,
            "idempotency_key": key + "-bootstrap-key",
        },
        headers={"X-AI-STP-Bootstrap-Secret": BOOTSTRAP_SECRET},
    )
    assert response.status_code == 200, response.text
    organization_id = response.json()["organization_id"]
    return organization_id, account_id, device_id, {"Authorization": f"Bearer {token}"}


async def _project(
    sessionmaker: async_sessionmaker[AsyncSession],
    organization_id: str,
) -> str:
    """Register one active corporate project events can name."""
    project_id = new_id("remote_project")
    async with sessionmaker() as db:
        await set_tenant_scope(db, organization_id)
        db.add(
            ProjectIdentity(
                id=project_id,
                organization_id=organization_id,
                namespace="remote",
                external_key=f"acme/{project_id[-6:]}",
                display_name="Project",
            )
        )
        # The identity row must exist before the project row: the UOW does
        # not order these inserts because the FK lives only in DDL.
        await db.flush()
        db.add(
            CorporateProject(
                id=project_id,
                organization_id=organization_id,
                name=f"Project {project_id[-6:]}",
                lifecycle="active",
                state="active",
            )
        )
        await db.commit()
    return project_id


def _usage_event(
    event_id: str,
    organization_id: str,
    account_id: str,
    device_id: str,
    project_id: str,
    **overrides: object,
) -> dict[str, object]:
    event: dict[str, object] = {
        "schema_version": 1,
        "event_id": event_id,
        "organization_id": organization_id,
        "employee_id": account_id,
        "device_id": device_id,
        "project_id": project_id,
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
        "invoked_at": INVOKED_AT,
        "outcome": "succeeded",
    }
    event.update(overrides)
    return event


def _base(organization_id: str) -> str:
    return f"/v1/corporate/organizations/{organization_id}/telemetry"


async def _ingest(
    client: AsyncClient,
    organization_id: str,
    auth: dict[str, str],
    events: list[dict[str, object]],
):
    return await client.post(
        f"{_base(organization_id)}/usage-events",
        json={"schema_version": 1, "events": events},
        headers=auth,
    )


async def test_ingest_dedup_and_identity_binding(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    organization_id, account_id, device_id, auth = await _tenant(
        client, sessionmaker, "tu-ingest-0001"
    )
    project_id = await _project(sessionmaker, organization_id)

    first = await _ingest(
        client,
        organization_id,
        auth,
        [_usage_event("usage_event_ing0001", organization_id, account_id, device_id, project_id)],
    )
    assert first.status_code == 200, first.text
    assert first.json() == {
        "schema_version": 1,
        "accepted": 1,
        "duplicates": 0,
        "rejected": 0,
    }
    replay = await _ingest(
        client,
        organization_id,
        auth,
        [_usage_event("usage_event_ing0001", organization_id, account_id, device_id, project_id)],
    )
    assert replay.status_code == 200 and replay.json()["duplicates"] == 1

    # The payload cannot speak for another employee or another device.
    forged = await _ingest(
        client,
        organization_id,
        auth,
        [
            _usage_event(
                "usage_event_ing0002",
                organization_id,
                new_id("account"),
                device_id,
                project_id,
            ),
            _usage_event(
                "usage_event_ing0003",
                organization_id,
                account_id,
                new_id("device"),
                project_id,
            ),
        ],
    )
    assert forged.status_code == 200
    assert forged.json()["rejected"] == 2


async def test_ingest_rejects_forbidden_fields(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    organization_id, account_id, device_id, auth = await _tenant(
        client, sessionmaker, "tu-forbid-0001"
    )
    project_id = await _project(sessionmaker, organization_id)
    event = _usage_event("usage_event_forbid01", organization_id, account_id, device_id, project_id)
    event["prompt"] = "contents of a user prompt"
    response = await _ingest(client, organization_id, auth, [event])
    # extra="forbid" rejects the body at wire validation.
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "AI_STP_VALIDATION_ERROR"


async def test_report_aggregates_and_export_audit(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    organization_id, account_id, device_id, auth = await _tenant(
        client, sessionmaker, "tu-report-0001"
    )
    project_id = await _project(sessionmaker, organization_id)
    await _ingest(
        client,
        organization_id,
        auth,
        [
            _usage_event("usage_event_rep0001", organization_id, account_id, device_id, project_id),
            _usage_event(
                "usage_event_rep0002",
                organization_id,
                account_id,
                device_id,
                project_id,
                outcome="failed",
            ),
        ],
    )
    base = _base(organization_id)
    report = await client.get(
        f"{base}/usage-reports", params={"group_by": "component"}, headers=auth
    )
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["total_events"] == 2
    row = body["rows"][0]
    assert row["component_stable_id"] == "skill_review"
    assert (row["succeeded"], row["failed"]) == (1, 1)

    export = await client.post(
        f"{base}/usage-exports",
        json={
            "schema_version": 1,
            "authorization_revision": 1,
            "idempotency_key": "export-idem-00000001",
        },
        headers=auth,
    )
    assert export.status_code == 200, export.text
    assert export.json()["row_count"] == 1
    assert export.json()["content_digest"].startswith("sha256:")
    replay = await client.post(
        f"{base}/usage-exports",
        json={
            "schema_version": 1,
            "authorization_revision": 1,
            "idempotency_key": "export-idem-00000001",
        },
        headers=auth,
    )
    assert replay.json()["export_id"] == export.json()["export_id"]
    async with sessionmaker() as db:
        await set_tenant_scope(db, organization_id)
        audit = await db.scalar(
            select(AuditEvent).where(AuditEvent.action == "telemetry_usage.export")
        )
        assert audit is not None


async def test_drilldown_is_separately_permissioned(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    organization_id, account_id, device_id, auth = await _tenant(
        client, sessionmaker, "tu-events-0001"
    )
    project_id = await _project(sessionmaker, organization_id)
    await _ingest(
        client,
        organization_id,
        auth,
        [_usage_event("usage_event_evt0001", organization_id, account_id, device_id, project_id)],
    )
    base = _base(organization_id)

    # A staff member can ingest but must not reach event-level detail.
    staff_id, staff_device, staff_token = await _device_session(sessionmaker)
    async with sessionmaker() as db:
        await set_tenant_scope(db, organization_id)
        db.add(
            OrganizationMembership(
                organization_id=organization_id,
                account_id=staff_id,
                role="staff",
                state="active",
            )
        )
        # Membership must exist before the binding: the FK lives only in DDL.
        await db.flush()
        db.add(
            CorporateRoleBinding(
                id=new_id("operation"),
                organization_id=organization_id,
                principal_type="user",
                account_id=staff_id,
                role="staff",
                scope_kind="organization",
                scope_id=organization_id,
            )
        )
        await db.commit()
    staff_auth = {"Authorization": f"Bearer {staff_token}"}
    staff_ingest = await _ingest(
        client,
        organization_id,
        staff_auth,
        [
            _usage_event(
                "usage_event_evt0002",
                organization_id,
                staff_id,
                staff_device,
                project_id,
            )
        ],
    )
    assert staff_ingest.status_code == 200, staff_ingest.text
    denied = await client.get(f"{base}/usage-events", headers=staff_auth)
    assert denied.status_code == 403

    allowed = await client.get(f"{base}/usage-events", headers=auth)
    assert allowed.status_code == 200, allowed.text
    assert {row["event_id"] for row in allowed.json()["events"]} == {
        "usage_event_evt0001",
        "usage_event_evt0002",
    }


async def test_team_scoped_reader_sees_only_own_team(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    organization_id, account_id, device_id, auth = await _tenant(
        client, sessionmaker, "tu-scope-0001"
    )
    project_id = await _project(sessionmaker, organization_id)

    member_id, member_device, member_token = await _device_session(sessionmaker)
    team_id = new_id("operation")
    async with sessionmaker() as db:
        await set_tenant_scope(db, organization_id)
        db.add(
            OrganizationMembership(
                organization_id=organization_id,
                account_id=member_id,
                role="staff",
                state="active",
            )
        )
        # Membership must exist before team membership and bindings; the
        # tenant-account FKs live only in DDL.
        await db.flush()
        db.add(CorporateTeam(id=team_id, organization_id=organization_id, name="Team A"))
        db.add(
            CorporateTeamMember(
                organization_id=organization_id,
                team_id=team_id,
                account_id=member_id,
                role="lead",
            )
        )
        db.add(
            CorporateRoleBinding(
                id=new_id("operation"),
                organization_id=organization_id,
                principal_type="user",
                account_id=member_id,
                role="lead",
                scope_kind="team",
                scope_id=team_id,
            )
        )
        await db.commit()
    member_auth = {"Authorization": f"Bearer {member_token}"}
    await _ingest(
        client,
        organization_id,
        member_auth,
        [
            _usage_event(
                "usage_event_scope001",
                organization_id,
                member_id,
                member_device,
                project_id,
            )
        ],
    )
    await _ingest(
        client,
        organization_id,
        auth,
        [
            _usage_event(
                "usage_event_scope002",
                organization_id,
                account_id,
                device_id,
                project_id,
            )
        ],
    )
    base = _base(organization_id)
    member_report = await client.get(
        f"{base}/usage-reports", params={"group_by": "employee"}, headers=member_auth
    )
    assert member_report.status_code == 200, member_report.text
    assert member_report.json()["total_events"] == 1
    assert member_report.json()["rows"][0]["group_value"] == member_id
    org_report = await client.get(
        f"{base}/usage-reports", params={"group_by": "employee"}, headers=auth
    )
    assert org_report.json()["total_events"] == 2
