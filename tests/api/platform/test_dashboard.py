"""Corporate dashboard reads canonical tenant-scoped health and audits access."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.session import issue_session
from ai_stp_api.slices.corporate import dashboard
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.heartbeat_models import InstallationHeartbeat
from ai_stp_platform.models import Account, Device
from ai_stp_platform.organization_models import (
    CorporateProject,
    CorporateRoleBinding,
    CorporateTeam,
    CorporateTeamMember,
    Organization,
    OrganizationMembership,
    ProjectIdentity,
)
from ai_stp_platform.telemetry_policy_models import TelemetryAudit, TelemetryEvent
from ai_stp_platform.tenant_scope import set_tenant_scope

pytestmark = pytest.mark.platform


async def _actor(sessionmaker: async_sessionmaker[AsyncSession]) -> tuple[str, str, str]:
    async with sessionmaker() as db:
        account_id, device_id = new_id("account"), new_id("device")
        db.add_all(
            [
                Account(id=account_id, status="active"),
                Device(
                    id=device_id,
                    account_id=account_id,
                    public_key="dashboard-" + uuid.uuid4().hex[:24],
                    state="active",
                ),
            ]
        )
        await db.flush()
        token = (
            await issue_session(db, account_id=account_id, device_id=device_id, ttl_seconds=3600)
        ).raw_token
        await db.commit()
        return account_id, device_id, token


async def _bootstrap(client: AsyncClient, account_id: str) -> str:
    response = await client.post(
        "/v1/corporate/bootstrap",
        json={
            "organization_name": "dashboard-" + uuid.uuid4().hex[:20],
            "superadmin_account_id": account_id,
            "idempotency_key": "boot-" + uuid.uuid4().hex,
        },
        headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
    )
    assert response.status_code == 200, response.text
    return response.json()["organization_id"]


async def _revision(sessionmaker: async_sessionmaker[AsyncSession], org: str) -> int:
    async with sessionmaker() as db:
        organization = await db.get(Organization, org)
        member = await db.scalar(
            select(OrganizationMembership).where(OrganizationMembership.organization_id == org)
        )
        assert organization is not None and member is not None
        return organization.policy_revision


async def test_dashboard_ci_provider_heartbeat_and_saved_views(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    client, sessionmaker, _ = db_api_client
    account_id, device_id, token = await _actor(sessionmaker)
    org = await _bootstrap(client, account_id)
    _, _, foreign_token = await _actor(sessionmaker)
    project_id = new_id("remote_project")
    async with sessionmaker() as db:
        db.add(
            ProjectIdentity(
                id=project_id,
                organization_id=org,
                namespace="remote",
                external_key=f"manual:{project_id}",
                display_name="service",
                state="active",
            )
        )
        await db.flush()
        db.add(
            CorporateProject(
                id=project_id,
                organization_id=org,
                name="service",
                lifecycle="active",
                state="active",
                revision=1,
            )
        )
        await db.commit()
    root = f"/v1/corporate/organizations/{org}/dashboard"
    auth = {"Authorization": f"Bearer {token}"}
    now = datetime.now(UTC)
    ci_body = {
        "project_id": project_id,
        "account_id": account_id,
        "device_id": device_id,
        "harness": "codex",
        "status": "fail",
        "reason": "target_drift",
        "checked_at": format_timestamp(now),
    }
    unsafe = await client.put(
        f"{root}/ci-check", json={**ci_body, "prompt": "unsafe"}, headers=auth
    )
    assert unsafe.status_code == 400
    other_device = await client.put(
        f"{root}/ci-check", json={**ci_body, "device_id": new_id("device")}, headers=auth
    )
    assert other_device.status_code == 403
    stored = await client.put(f"{root}/ci-check", json=ci_body, headers=auth)
    assert stored.status_code == 200, stored.text
    assert stored.json()["revision"] == 1
    stale_write = await client.put(
        f"{root}/ci-check", json={**ci_body, "status": "pass"}, headers=auth
    )
    assert stale_write.status_code == 200 and stale_write.json()["status"] == "fail"

    query = {
        "dataset": "ci",
        "dimensions": ["state"],
        "filters": [{"dimension": "state", "values": ["fail"]}],
        "measures": ["count", "devices", "projects"],
        "sort_by": "count",
    }
    result = await client.post(f"{root}/query", json={"query": query}, headers=auth)
    assert result.status_code == 200, result.text
    assert result.json()["items"] == [
        {
            "dimensions": {"state": "fail"},
            "measures": {"count": 1, "devices": 1, "projects": 1},
        }
    ]
    details = await client.post(
        f"{root}/query",
        json={
            "query": {
                "dataset": "ci",
                "dimensions": [
                    "state",
                    "project",
                    "account",
                    "device",
                    "harness",
                    "setup",
                    "checked_at",
                    "reason",
                ],
                "sort_by": "checked_at",
                "view": "table",
            }
        },
        headers=auth,
    )
    assert details.status_code == 200, details.text
    detail = details.json()["items"][0]["dimensions"]
    assert detail["project"] == project_id and detail["device"] == device_id
    assert detail["harness"] == "codex" and detail["reason"] == "target_drift"
    assert detail["checked_at"] == ci_body["checked_at"]
    bad_dimension = await client.post(
        f"{root}/query",
        json={"query": {"dataset": "heartbeat", "dimensions": ["project"]}},
        headers=auth,
    )
    assert bad_dimension.status_code == 400
    empty = await client.post(
        f"{root}/query",
        json={"query": {"dataset": "ci", "filters": [{"dimension": "state", "values": ["pass"]}]}},
        headers=auth,
    )
    assert empty.status_code == 200 and empty.json()["items"] == []
    outsider = await client.post(
        f"{root}/query",
        json={"query": query},
        headers={"Authorization": f"Bearer {foreign_token}"},
    )
    assert outsider.status_code == 403

    async with sessionmaker() as db:
        await set_tenant_scope(db, org)
        db.add_all(
            [
                InstallationHeartbeat(
                    organization_id=org,
                    account_id=account_id,
                    device_id=device_id,
                    cli_version="1.0",
                    capabilities=[],
                    reported_state="active",
                    checked_at=now - timedelta(days=2),
                    received_at=now - timedelta(days=2),
                    revision=1,
                ),
                TelemetryEvent(
                    organization_id=org,
                    event_id="provider-" + uuid.uuid4().hex,
                    kind="heartbeat",
                    account_id=account_id,
                    device_id=device_id,
                    harness="codex",
                    provider_name="opennetwork",
                    provider_version="1.0",
                    capabilities=[],
                    health="failing",
                    subject_state="active",
                    occurred_at=now,
                    received_at=now,
                ),
            ]
        )
        await db.commit()
    heartbeat = await client.post(
        f"{root}/query",
        json={"query": {"dataset": "heartbeat", "dimensions": ["state"]}},
        headers=auth,
    )
    assert heartbeat.status_code == 200, heartbeat.text
    assert heartbeat.json()["items"][0]["dimensions"]["state"] == "stale"
    async with sessionmaker() as db:
        await set_tenant_scope(db, org)
        beat = await db.get(InstallationHeartbeat, (org, device_id))
        assert beat is not None
        beat.reported_state = "partial"
        beat.received_at = now
        await db.commit()
    partial = await client.post(
        f"{root}/query",
        json={"query": {"dataset": "heartbeat", "dimensions": ["state"]}},
        headers=auth,
    )
    assert partial.status_code == 200, partial.text
    assert partial.json()["items"][0]["dimensions"]["state"] == "partial"
    provider = await client.post(
        f"{root}/query",
        json={"query": {"dataset": "provider", "dimensions": ["state"]}},
        headers=auth,
    )
    assert provider.status_code == 200, provider.text
    assert provider.json()["items"][0]["dimensions"]["state"] == "failing"

    view_body = {
        "name": "CI health",
        "scope": "organization",
        "scope_id": org,
        "query": query,
        "authorization_revision": await _revision(sessionmaker, org),
        "expected_revision": 0,
        "idempotency_key": "view-" + uuid.uuid4().hex,
    }
    saved = await client.post(f"{root}/views", json=view_body, headers=auth)
    assert saved.status_code == 200, saved.text
    replay = await client.post(f"{root}/views", json=view_body, headers=auth)
    assert replay.status_code == 200 and replay.json() == saved.json()
    listed = await client.get(f"{root}/views", headers=auth)
    assert listed.status_code == 200 and len(listed.json()["items"]) == 1
    changed_scope = await client.put(
        f"{root}/views/{saved.json()['id']}",
        json={
            **view_body,
            "scope": "user",
            "scope_id": account_id,
            "expected_revision": 1,
            "idempotency_key": "change-" + uuid.uuid4().hex,
        },
        headers=auth,
    )
    assert changed_scope.status_code == 400
    async with sessionmaker() as db:
        await set_tenant_scope(db, org)
        audited = list(
            (
                await db.scalars(
                    select(TelemetryAudit).where(
                        TelemetryAudit.organization_id == org,
                        TelemetryAudit.action == "telemetry.aggregate",
                    )
                )
            ).all()
        )
        assert len(audited) >= 4


async def test_dashboard_lead_scope_reason_redaction_and_team_views(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    client, sessionmaker, _ = db_api_client
    owner, _, owner_token = await _actor(sessionmaker)
    org = await _bootstrap(client, owner)
    lead, _, lead_token = await _actor(sessionmaker)
    visible, visible_device, _ = await _actor(sessionmaker)
    hidden, hidden_device, _ = await _actor(sessionmaker)
    team_id, hidden_team = new_id("operation"), new_id("operation")
    now = datetime.now(UTC)
    async with sessionmaker() as db:
        await set_tenant_scope(db, org)
        db.add_all(
            [
                OrganizationMembership(
                    organization_id=org, account_id=lead, role="lead", state="active"
                ),
                OrganizationMembership(
                    organization_id=org, account_id=visible, role="member", state="active"
                ),
                OrganizationMembership(
                    organization_id=org, account_id=hidden, role="member", state="active"
                ),
                CorporateTeam(id=team_id, organization_id=org, name="Visible"),
                CorporateTeam(id=hidden_team, organization_id=org, name="Hidden"),
            ]
        )
        await db.flush()
        db.add_all(
            [
                CorporateTeamMember(
                    organization_id=org, team_id=team_id, account_id=lead, role="lead"
                ),
                CorporateTeamMember(organization_id=org, team_id=team_id, account_id=visible),
                CorporateTeamMember(organization_id=org, team_id=hidden_team, account_id=hidden),
                CorporateRoleBinding(
                    id=new_id("operation"),
                    organization_id=org,
                    principal_type="user",
                    account_id=lead,
                    role="lead",
                    scope_kind="team",
                    scope_id=team_id,
                    state="active",
                ),
                InstallationHeartbeat(
                    organization_id=org,
                    account_id=visible,
                    device_id=visible_device,
                    cli_version="1.0",
                    capabilities=[],
                    reported_state="active",
                    checked_at=now,
                    received_at=now,
                    revision=1,
                ),
                InstallationHeartbeat(
                    organization_id=org,
                    account_id=hidden,
                    device_id=hidden_device,
                    cli_version="1.0",
                    capabilities=[],
                    reported_state="failing",
                    checked_at=now,
                    received_at=now,
                    revision=1,
                ),
            ]
        )
        await db.commit()
    root = f"/v1/corporate/organizations/{org}/dashboard"
    lead_auth = {"Authorization": f"Bearer {lead_token}"}
    query = {"query": {"dataset": "heartbeat", "dimensions": ["account"]}}
    lead_result = await client.post(f"{root}/query", json=query, headers=lead_auth)
    assert lead_result.status_code == 200, lead_result.text
    assert {item["dimensions"]["account"] for item in lead_result.json()["items"]} == {visible}
    owner_result = await client.post(
        f"{root}/query", json=query, headers={"Authorization": f"Bearer {owner_token}"}
    )
    assert {item["dimensions"]["account"] for item in owner_result.json()["items"]} == {
        visible,
        hidden,
    }
    diagnostic = await client.post(
        f"{root}/query",
        json={"query": {"dataset": "ci", "dimensions": ["reason"]}},
        headers=lead_auth,
    )
    assert diagnostic.status_code == 403
    view = {
        "name": "Team health",
        "scope": "team",
        "scope_id": team_id,
        "query": query["query"],
        "authorization_revision": await _revision(sessionmaker, org),
        "idempotency_key": "team-view-" + uuid.uuid4().hex,
    }
    saved = await client.post(f"{root}/views", json=view, headers=lead_auth)
    assert saved.status_code == 200, saved.text
    denied = await client.post(
        f"{root}/views",
        json={
            **view,
            "scope": "organization",
            "scope_id": org,
            "idempotency_key": "org-view-" + uuid.uuid4().hex,
        },
        headers=lead_auth,
    )
    assert denied.status_code == 403


async def test_dashboard_query_cost_and_result_limit(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, sessionmaker, _ = db_api_client
    account_id, _, token = await _actor(sessionmaker)
    org = await _bootstrap(client, account_id)

    async def accounts(*_args: object, **_kwargs: object) -> tuple[set[str], dict[str, list[str]]]:
        return {account_id}, {account_id: ["team-a", "team-b"]}

    async def expensive(*_args: object, **_kwargs: object) -> list[dict[str, str]]:
        return [
            {
                "state": "pass",
                "project": "project-a",
                "account": account_id,
                "device": f"device-{index}",
                "harness": "codex",
                "setup": "",
                "day": "2026-09-22",
                "reason": "none",
            }
            for index in range(700)
        ]

    monkeypatch.setattr(dashboard, "_visible_accounts", accounts)
    monkeypatch.setattr(dashboard, "_source_rows", expensive)
    root = f"/v1/corporate/organizations/{org}/dashboard/query"
    auth = {"Authorization": f"Bearer {token}"}
    rejected = await client.post(
        root,
        json={
            "query": {
                "dataset": "ci",
                "dimensions": ["state", "account"],
                "group_by": ["device"],
                "pivot_rows": ["team"],
            }
        },
        headers=auth,
    )
    assert rejected.status_code == 400

    async def many_groups(*_args: object, **_kwargs: object) -> list[dict[str, str]]:
        return (await expensive())[:250]

    monkeypatch.setattr(dashboard, "_source_rows", many_groups)
    bounded = await client.post(
        root,
        json={"query": {"dataset": "ci", "dimensions": ["device"], "limit": 200}},
        headers=auth,
    )
    assert bounded.status_code == 200, bounded.text
    assert bounded.json()["total_groups"] == 250
    assert len(bounded.json()["items"]) == 200
