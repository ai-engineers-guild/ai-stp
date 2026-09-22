"""Corporate telemetry privacy: boundary, isolation, rights, retention, audit.

The telemetry slice routers are mounted onto the test application; production
wiring into the corporate router is the integration point outside this file.
PostgreSQL fixtures mirror `tests/api/platform/conftest.py` so the root
conftest's `pg` marker still applies through the shared fixture names.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.support.api_settings import make_settings
from tests.support.postgres import migrated_database, migrated_template

from ai_stp_api.app import create_app
from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_api.slices.corporate import telemetry_policy, telemetry_rights
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, AuditEvent
from ai_stp_platform.organization_models import Organization, OrganizationMembership
from ai_stp_platform.telemetry_policy_models import TelemetryAudit, TelemetryEvent
from ai_stp_platform.telemetry_retention import apply_retention
from ai_stp_platform.tenant_scope import set_tenant_scope

pytestmark = pytest.mark.platform

TEST_DB_ENV = "AI_STP_TEST_DB_URL"
BOOTSTRAP_SECRET = "corporate-bootstrap-test-secret"


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
    app.include_router(telemetry_policy.router, prefix="/v1")
    app.include_router(telemetry_rights.router, prefix="/v1")
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app.state.sessionmaker, settings


async def _account_token(
    sessionmaker: async_sessionmaker[AsyncSession], *, account_id: str | None = None
) -> tuple[str, str]:
    async with sessionmaker() as db:
        account = await db.get(Account, account_id) if account_id else None
        if account is None:
            account = Account(id=account_id or new_id("account"), status="active")
            db.add(account)
            await db.flush()
        issued = await issue_session(db, account_id=account.id, device_id=None, ttl_seconds=3600)
        await db.commit()
        return account.id, issued.raw_token


async def _tenant(
    client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    key: str,
) -> tuple[str, str, dict[str, str]]:
    """Bootstrap one tenant and grant its superadmin the telemetry matrix."""
    account_id, token = await _account_token(sessionmaker)
    response = await client.post(
        "/v1/corporate/bootstrap",
        json={
            "schema_version": 1,
            "organization_name": key,
            "superadmin_account_id": account_id,
            "idempotency_key": key,
        },
        headers={"X-AI-STP-Bootstrap-Secret": BOOTSTRAP_SECRET},
    )
    assert response.status_code == 200, response.text
    organization_id = response.json()["organization_id"]
    return organization_id, account_id, {"Authorization": f"Bearer {token}"}


def _heartbeat(event_id: str, **overrides: object) -> dict[str, object]:
    event: dict[str, object] = {
        "kind": "heartbeat",
        "event_id": event_id,
        "device_id": "dev-001",
        "harness": "codex",
        "harness_version": "0.140.1",
        "provider_name": "codex-cli",
        "capabilities": ["apply", "status"],
        "health": "active",
        "occurred_at": "2026-09-21T10:00:00.000Z",
    }
    event.update(overrides)
    return event


def _invocation(event_id: str, account_id: str, **overrides: object) -> dict[str, object]:
    event: dict[str, object] = {
        "kind": "invocation",
        "event_id": event_id,
        "account_id": account_id,
        "device_id": "dev-001",
        "harness": "claude",
        "component_kind": "skill",
        "component_stable_id": "component-001",
        "component_version": "1.0",
        "outcome": "succeeded",
        "occurred_at": "2026-09-21T11:00:00.000Z",
    }
    event.update(overrides)
    return event


async def _ingest(
    client: AsyncClient,
    organization_id: str,
    auth: dict[str, str],
    event: dict[str, object],
    key: str,
    revision: int = 1,
):
    return await client.post(
        f"/v1/corporate/organizations/{organization_id}/telemetry/events",
        json={
            "schema_version": 1,
            "event": event,
            "authorization_revision": revision,
            "idempotency_key": key,
        },
        headers=auth,
    )


async def test_ingest_list_export_and_dedup(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    organization_id, account_id, auth = await _tenant(client, sessionmaker, "tp-ingest-0001-x")
    base = f"/v1/corporate/organizations/{organization_id}/telemetry"

    created = await _ingest(
        client, organization_id, auth, _heartbeat("evt-hb-0001"), "tp-ingest-key-1-"
    )
    assert created.status_code == 200, created.text
    replay = await _ingest(
        client, organization_id, auth, _heartbeat("evt-hb-0001"), "tp-ingest-key-1-"
    )
    assert replay.status_code == 200 and replay.json() == created.json()
    duplicate = await _ingest(
        client, organization_id, auth, _heartbeat("evt-hb-0001"), "tp-ingest-key-2-"
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["event_id"] == "evt-hb-0001"

    invoked = await _ingest(
        client,
        organization_id,
        auth,
        _invocation("evt-inv-0001", account_id),
        "tp-ingest-key-3-",
    )
    assert invoked.status_code == 200, invoked.text
    assert invoked.json()["outcome"] == "succeeded"

    listed = await client.get(f"{base}/events", headers=auth)
    assert listed.status_code == 200, listed.text
    assert {item["event_id"] for item in listed.json()["items"]} == {
        "evt-hb-0001",
        "evt-inv-0001",
    }
    heartbeats = await client.get(
        f"{base}/events", params={"event_kind": "heartbeat"}, headers=auth
    )
    assert [item["kind"] for item in heartbeats.json()["items"]] == ["heartbeat"]

    exported = await client.get(f"{base}/export", headers=auth)
    assert exported.status_code == 200, exported.text
    assert len(exported.json()["items"]) == 2

    aggregates = await client.get(f"{base}/aggregates", headers=auth)
    assert aggregates.status_code == 200, aggregates.text
    assert sum(item["event_count"] for item in aggregates.json()["items"]) == 2
    for item in aggregates.json()["items"]:
        assert set(item) <= {"day", "event_kind", "outcome", "event_count"}


async def test_ingest_boundary_rejects_forbidden_fields(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    organization_id, _account_id, auth = await _tenant(client, sessionmaker, "tp-boundary-0001")
    for index, forbidden in enumerate(
        (
            {"prompt": "summarize this file"},
            {"repository_url": "https://example.invalid/private"},
            {"local_path": "C:\\Users\\dev\\project"},
            {"environment": {"API_KEY": "x"}},
            {"capabilities": ["apply", "OPENAI_KEY=sk-1"]},
        )
    ):
        response = await _ingest(
            client,
            organization_id,
            auth,
            _heartbeat(f"evt-bad-{index:04d}", **forbidden),
            f"tp-boundary-key-{index}",
        )
        assert response.status_code in (400, 409, 422), response.text


async def test_tenant_and_role_isolation(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    organization_id, account_id, auth = await _tenant(client, sessionmaker, "tp-iso-0001-xxxx")
    _foreign_id, foreign_token = await _account_token(sessionmaker)
    foreign_auth = {"Authorization": f"Bearer {foreign_token}"}
    base = f"/v1/corporate/organizations/{organization_id}/telemetry"

    assert (
        await _ingest(
            client,
            organization_id,
            auth,
            _invocation("evt-iso-0001", account_id),
            "tp-iso-key-1-xxx",
        )
    ).status_code == 200

    # A stranger: no membership at all.
    for path in ("events", "aggregates", "export", "policy"):
        denied = await client.get(f"{base}/{path}", headers=foreign_auth)
        assert denied.status_code == 403, (path, denied.text)

    # A staff member of the tenant without telemetry permissions.
    staff_id, staff_token = await _account_token(sessionmaker)
    async with sessionmaker() as db:
        await set_tenant_scope(db, organization_id)
        db.add(
            OrganizationMembership(
                organization_id=organization_id,
                account_id=staff_id,
                role="staff",
                display_name="Staff",
            )
        )
        await db.commit()
    staff_auth = {"Authorization": f"Bearer {staff_token}"}
    for path in ("events", "aggregates", "export"):
        denied = await client.get(f"{base}/{path}", headers=staff_auth)
        assert denied.status_code == 403, (path, denied.text)
    denied_delete = await client.post(
        f"{base}/deletions",
        json={
            "schema_version": 1,
            "subject_kind": "account",
            "subject_id": account_id,
            "mode": "delete",
            "reason": "data rights",
            "authorization_revision": 1,
            "idempotency_key": "tp-iso-del-1-xxx",
        },
        headers=staff_auth,
    )
    assert denied_delete.status_code == 403

    # Row-level security: a foreign tenant scope sees none of the raw rows.
    # Bootstrap is one-shot per database, so the second tenant is ORM-seeded.
    other_id = new_id("organization")
    async with sessionmaker() as db:
        await set_tenant_scope(db, other_id)
        db.add(Organization(id=other_id, kind="corporate", display_name="Other"))
        await db.commit()
    async with sessionmaker() as db:
        await set_tenant_scope(db, other_id)
        bypasses_rls = await db.scalar(
            text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        )
        if bypasses_rls:
            await db.execute(text("SET LOCAL ROLE pg_read_all_data"))
        visible = (
            await db.scalars(
                select(TelemetryEvent).where(TelemetryEvent.organization_id == organization_id)
            )
        ).all()
        assert visible == []
        await db.rollback()


async def test_policy_rights_revocation_and_retention(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    organization_id, account_id, auth = await _tenant(client, sessionmaker, "tp-pol-0001-xxxx")
    base = f"/v1/corporate/organizations/{organization_id}/telemetry"

    missing = await client.get(f"{base}/policy", headers=auth)
    assert missing.status_code == 404

    policy = await client.put(
        f"{base}/policy",
        json={
            "schema_version": 1,
            "raw_retention_days": 30,
            "legal_basis": "consent",
            "notice_revision": 2,
            "expected_policy_revision": 0,
            "authorization_revision": 1,
            "reason": "initial policy",
            "idempotency_key": "tp-policy-1-xxxx",
        },
        headers=auth,
    )
    assert policy.status_code == 200, policy.text
    assert policy.json()["policy_version"] == 1
    stale = await client.put(
        f"{base}/policy",
        json={
            "schema_version": 1,
            "raw_retention_days": 60,
            "legal_basis": "consent",
            "notice_revision": 2,
            "expected_policy_revision": 0,
            "authorization_revision": 1,
            "reason": "stale write",
            "idempotency_key": "tp-policy-2-xxxx",
        },
        headers=auth,
    )
    assert stale.status_code == 409

    right = await client.post(
        f"{base}/rights",
        json={
            "schema_version": 1,
            "subject_kind": "account",
            "subject_id": account_id,
            "legal_basis": "consent",
            "notice_revision": 2,
            "authorization_revision": 1,
            "idempotency_key": "tp-right-1-xxxxx",
        },
        headers=auth,
    )
    assert right.status_code == 200, right.text
    assert right.json()["state"] == "active"

    subject = new_id("account")
    assert (
        await _ingest(
            client,
            organization_id,
            auth,
            _invocation("evt-right-0001", subject),
            "tp-right-ingest-1",
        )
    ).status_code == 200
    revoked = await client.post(
        f"{base}/rights/account/{subject}/revocation",
        json={
            "schema_version": 1,
            "anonymize": True,
            "reason": "subject revoked telemetry",
            "authorization_revision": 1,
            "idempotency_key": "tp-revoke-1-xxxx",
        },
        headers=auth,
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["state"] == "revoked"

    blocked = await _ingest(
        client,
        organization_id,
        auth,
        _invocation("evt-right-0002", subject),
        "tp-right-ingest-2",
    )
    assert blocked.status_code == 409

    async with sessionmaker() as db:
        await set_tenant_scope(db, organization_id)
        retained = (
            await db.scalars(
                select(TelemetryEvent).where(
                    TelemetryEvent.organization_id == organization_id,
                    TelemetryEvent.event_id == "evt-right-0001",
                )
            )
        ).one()
        assert retained.account_id is None
        assert retained.device_id is None
        assert retained.subject_state == "anonymized"
        await db.rollback()

    deleted = await client.post(
        f"{base}/deletions",
        json={
            "schema_version": 1,
            "subject_kind": "account",
            "subject_id": subject,
            "mode": "delete",
            "reason": "erasure request",
            "authorization_revision": 1,
            "idempotency_key": "tp-delete-1-xxxx",
        },
        headers=auth,
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["state"] == "deleted"
    replayed = await client.post(
        f"{base}/deletions",
        json={
            "schema_version": 1,
            "subject_kind": "account",
            "subject_id": subject,
            "mode": "delete",
            "reason": "erasure request",
            "authorization_revision": 1,
            "idempotency_key": "tp-delete-1-xxxx",
        },
        headers=auth,
    )
    assert replayed.status_code == 200 and replayed.json() == deleted.json()
    repeated = await client.post(
        f"{base}/deletions",
        json={
            "schema_version": 1,
            "subject_kind": "account",
            "subject_id": subject,
            "mode": "delete",
            "reason": "erasure request",
            "authorization_revision": 1,
            "idempotency_key": "tp-delete-2-xxxx",
        },
        headers=auth,
    )
    assert repeated.status_code == 200
    assert repeated.json()["affected_events"] == 0

    await _ingest(
        client,
        organization_id,
        auth,
        _heartbeat("evt-old-0001", occurred_at="2026-08-01T10:00:00.000Z"),
        "tp-old-key-1-xxx",
    )
    async with sessionmaker() as db:
        await set_tenant_scope(db, organization_id)
        removed = await apply_retention(db, organization_id=organization_id, now=datetime.now(UTC))
        assert removed == 1
        remaining = (
            await db.scalars(
                select(TelemetryEvent).where(TelemetryEvent.organization_id == organization_id)
            )
        ).all()
        assert all(row.event_id != "evt-old-0001" for row in remaining)
        await db.rollback()


async def test_privileged_telemetry_reads_and_writes_are_audited(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    organization_id, _account_id, auth = await _tenant(client, sessionmaker, "tp-audit-0001-xx")
    base = f"/v1/corporate/organizations/{organization_id}/telemetry"
    await _ingest(client, organization_id, auth, _heartbeat("evt-audit-0001"), "tp-audit-key-1-x")
    await client.get(f"{base}/events", headers=auth)
    await client.get(f"{base}/export", headers=auth)

    audit_page = await client.get(f"{base}/audit", headers=auth)
    assert audit_page.status_code == 200, audit_page.text
    audit_actions = {item["action"] for item in audit_page.json()["items"]}
    assert {"telemetry.list", "telemetry.export", "telemetry.audit.list"} <= audit_actions
    for item in audit_page.json()["items"]:
        assert not {"token", "secret", "password"} & set(item["detail"])

    async with sessionmaker() as db:
        await set_tenant_scope(db, organization_id)
        actions = set(
            (
                await db.scalars(
                    select(AuditEvent.action).where(
                        AuditEvent.organization_id == organization_id,
                        AuditEvent.action.like("telemetry.%"),
                    )
                )
            ).all()
        )
        assert {"telemetry.ingest", "telemetry.list", "telemetry.export"} <= actions
        rows = (
            await db.scalars(
                select(AuditEvent).where(
                    AuditEvent.organization_id == organization_id,
                    AuditEvent.action.like("telemetry.%"),
                )
            )
        ).all()
        for row in rows:
            assert not {"token", "secret", "password"} & set(row.payload)
        governed = (
            await db.scalars(
                select(TelemetryAudit).where(TelemetryAudit.organization_id == organization_id)
            )
        ).all()
        assert {"telemetry.list", "telemetry.export"} <= {row.action for row in governed}
        await db.rollback()
