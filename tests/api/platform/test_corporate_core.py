"""B2B-01 acceptance path for bootstrap, RBAC, isolation, and audit."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.session import issue_session
from ai_stp_api.slices.auth.domain import ProviderProfile
from ai_stp_api.slices.auth.service import resolve_login_identity
from ai_stp_foundation.ids import new_id
from ai_stp_platform.corporate_authorization import has_corporate_permission
from ai_stp_platform.models import Account, AuditEvent
from ai_stp_platform.organization_models import (
    CorporateProject,
    CorporateProjectMember,
    Organization,
)
from ai_stp_platform.tenant_scope import set_tenant_scope

pytestmark = pytest.mark.platform


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


async def test_concurrent_bootstrap_creates_one_initial_owner(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    client, sessionmaker, _settings = db_api_client
    first_id, _ = await _account_token(sessionmaker)
    second_id, _ = await _account_token(sessionmaker)

    async def request(account_id: str, key: str):
        return await client.post(
            "/v1/corporate/bootstrap",
            json={
                "schema_version": 1,
                "organization_name": key,
                "superadmin_account_id": account_id,
                "idempotency_key": key,
            },
            headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
        )

    responses = await asyncio.gather(
        request(first_id, "concurrent-bootstrap-one"),
        request(second_id, "concurrent-bootstrap-two"),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]


async def test_corporate_core_lifecycle_and_tenant_boundary(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    client, sessionmaker, _settings = db_api_client
    owner_id, owner_token = await _account_token(sessionmaker)
    auth = {"Authorization": f"Bearer {owner_token}"}

    bootstrap_payload = {
        "schema_version": 1,
        "organization_name": "Example Corp",
        "superadmin_account_id": owner_id,
        "idempotency_key": "corporate-bootstrap-0001",
    }
    bootstrap = await client.post(
        "/v1/corporate/bootstrap",
        json=bootstrap_payload,
        headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
    )
    assert bootstrap.status_code == 200, bootstrap.text
    organization = bootstrap.json()
    organization_id = organization["organization_id"]
    assert organization["authorization_revision"] == 1

    invalid_role_member = await client.post(
        f"/v1/corporate/organizations/{organization_id}/members",
        json={
            "schema_version": 1,
            "display_name": "Invalid Role",
            "email": "invalid.role@example.com",
            "role": "missing_role",
            "authorization_revision": 1,
            "idempotency_key": "create-invalid-role-0001",
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert invalid_role_member.status_code == 400

    replay = await client.post(
        "/v1/corporate/bootstrap",
        json=bootstrap_payload,
        headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
    )
    assert replay.status_code == 200
    second = await client.post(
        "/v1/corporate/bootstrap",
        json={**bootstrap_payload, "idempotency_key": "corporate-bootstrap-0002"},
        headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
    )
    assert second.status_code == 409

    member = await client.post(
        f"/v1/corporate/organizations/{organization_id}/members",
        json={
            "schema_version": 1,
            "display_name": "Staff One",
            "email": "staff.one@example.com",
            "role": "staff",
            "authorization_revision": 1,
            "idempotency_key": "create-staff-0001",
        },
        headers=auth,
    )
    assert member.status_code == 200, member.text
    member_id = member.json()["account_id"]
    async with sessionmaker() as db:
        linked = await resolve_login_identity(
            db,
            ProviderProfile(
                provider="google",
                subject="provisioned-staff-one",
                email="STAFF.ONE@example.com",
                email_verified=True,
            ),
        )
        await db.commit()
    assert linked.account_id == member_id
    assert linked.created_account is False
    lead = await client.post(
        f"/v1/corporate/organizations/{organization_id}/members",
        json={
            "schema_version": 1,
            "email": "lead@example.com",
            "display_name": "Lead One",
            "role": "lead",
            "authorization_revision": 2,
            "idempotency_key": "create-lead-0001",
        },
        headers=auth,
    )
    assert lead.status_code == 200, lead.text
    lead_id = lead.json()["account_id"]

    stale_project = await client.post(
        f"/v1/corporate/organizations/{organization_id}/projects",
        json={
            "schema_version": 1,
            "name": "Stale",
            "authorization_revision": 1,
            "idempotency_key": "create-project-stale",
        },
        headers=auth,
    )
    assert stale_project.status_code == 412

    context = await client.get(
        f"/v1/corporate/organizations/{organization_id}/context", headers=auth
    )
    assert context.status_code == 200, context.text
    revision = context.json()["organization"]["authorization_revision"]
    bindings = await client.get(
        f"/v1/corporate/organizations/{organization_id}/bindings", headers=auth
    )
    assert bindings.status_code == 200, bindings.text
    assert len(bindings.json()["items"]) == 3
    binding_id = bindings.json()["items"][0]["binding_id"]
    binding = await client.get(
        f"/v1/corporate/organizations/{organization_id}/bindings/{binding_id}", headers=auth
    )
    assert binding.status_code == 200, binding.text
    owner_binding = next(
        item
        for item in bindings.json()["items"]
        if item["account_id"] == owner_id and item["role"] == "superadmin"
    )
    demote_binding = await client.patch(
        f"/v1/corporate/organizations/{organization_id}/bindings/{owner_binding['binding_id']}",
        json={
            "schema_version": 1,
            "role": "lead",
            "scope_kind": "organization",
            "scope_id": organization_id,
            "state": "active",
            "expected_revision": owner_binding["revision"],
            "authorization_revision": revision,
            "idempotency_key": "demote-last-superadmin-binding-0001",
        },
        headers=auth,
    )
    assert demote_binding.status_code == 409, demote_binding.text
    project = await client.post(
        f"/v1/corporate/organizations/{organization_id}/projects",
        json={
            "schema_version": 1,
            "name": "Core",
            "authorization_revision": revision,
            "idempotency_key": "create-project-0001",
        },
        headers=auth,
    )
    assert project.status_code == 200, project.text
    project_id = project.json()["project_id"]
    revision = (
        await client.get(f"/v1/corporate/organizations/{organization_id}/context", headers=auth)
    ).json()["organization"]["authorization_revision"]
    team = await client.post(
        f"/v1/corporate/organizations/{organization_id}/teams",
        json={
            "schema_version": 1,
            "name": "Platform",
            "authorization_revision": revision,
            "idempotency_key": "create-team-0001",
        },
        headers=auth,
    )
    assert team.status_code == 200, team.text
    revision = (
        await client.get(f"/v1/corporate/organizations/{organization_id}/context", headers=auth)
    ).json()["organization"]["authorization_revision"]
    assignment = await client.post(
        f"/v1/corporate/organizations/{organization_id}/membership-assignments",
        json={
            "schema_version": 1,
            "account_id": member_id,
            "team_id": team.json()["team_id"],
            "project_id": project_id,
            "team_role": "lead",
            "authorization_revision": revision,
            "idempotency_key": "assign-staff-0001",
        },
        headers=auth,
    )
    assert assignment.status_code == 200, assignment.text
    revision = (
        await client.get(f"/v1/corporate/organizations/{organization_id}/context", headers=auth)
    ).json()["organization"]["authorization_revision"]
    hidden_project = await client.post(
        f"/v1/corporate/organizations/{organization_id}/projects",
        json={
            "schema_version": 1,
            "name": "Restricted",
            "authorization_revision": revision,
            "idempotency_key": "create-project-0002",
        },
        headers=auth,
    )
    assert hidden_project.status_code == 200, hidden_project.text
    revision = (
        await client.get(f"/v1/corporate/organizations/{organization_id}/context", headers=auth)
    ).json()["organization"]["authorization_revision"]
    lead_assignment = await client.post(
        f"/v1/corporate/organizations/{organization_id}/membership-assignments",
        json={
            "schema_version": 1,
            "account_id": lead_id,
            "project_id": project_id,
            "authorization_revision": revision,
            "idempotency_key": "assign-lead-0001",
        },
        headers=auth,
    )
    assert lead_assignment.status_code == 200, lead_assignment.text
    revision = (
        await client.get(f"/v1/corporate/organizations/{organization_id}/context", headers=auth)
    ).json()["organization"]["authorization_revision"]

    privileged_team_binding = await client.post(
        f"/v1/corporate/organizations/{organization_id}/bindings",
        json={
            "schema_version": 1,
            "account_id": member_id,
            "role": "superadmin",
            "scope_kind": "team",
            "scope_id": team.json()["team_id"],
            "authorization_revision": revision,
            "idempotency_key": "create-team-superadmin-binding-0001",
        },
        headers=auth,
    )
    assert privileged_team_binding.status_code == 200, privileged_team_binding.text
    revision = (
        await client.get(f"/v1/corporate/organizations/{organization_id}/context", headers=auth)
    ).json()["organization"]["authorization_revision"]
    promoted_member = await client.patch(
        f"/v1/corporate/organizations/{organization_id}/members/{member_id}",
        json={
            "schema_version": 1,
            "role": "lead",
            "state": "active",
            "expected_revision": 1,
            "idempotency_key": "promote-member-0001",
            "authorization_revision": revision,
        },
        headers=auth,
    )
    assert promoted_member.status_code == 200, promoted_member.text
    member_bindings = (
        await client.get(f"/v1/corporate/organizations/{organization_id}/bindings", headers=auth)
    ).json()["items"]
    assert not any(
        item["account_id"] == member_id
        and item["scope_kind"] == "team"
        and item["role"] == "superadmin"
        and item["state"] == "active"
        for item in member_bindings
    )
    assert any(
        item["account_id"] == member_id
        and item["scope_kind"] == "team"
        and item["role"] == "lead"
        and item["state"] == "active"
        for item in member_bindings
    )

    _lead_id, lead_token = await _account_token(sessionmaker, account_id=lead_id)
    lead_auth = {"Authorization": f"Bearer {lead_token}"}
    lead_update = await client.patch(
        f"/v1/corporate/organizations/{organization_id}/projects/{project_id}",
        json={
            "schema_version": 1,
            "name": "Core updated",
            "state": "active",
            "expected_revision": 1,
            "idempotency_key": "update-lead-project-0001",
            "authorization_revision": revision + 1,
        },
        headers=lead_auth,
    )
    assert lead_update.status_code == 200, lead_update.text
    lead_foreign_scope = await client.patch(
        f"/v1/corporate/organizations/{organization_id}/projects/{hidden_project.json()['project_id']}",
        json={
            "schema_version": 1,
            "name": "Restricted changed",
            "state": "active",
            "expected_revision": 1,
            "idempotency_key": "update-foreign-project-0001",
            "authorization_revision": revision + 2,
        },
        headers=lead_auth,
    )
    assert lead_foreign_scope.status_code == 403

    _staff_id, staff_token = await _account_token(sessionmaker, account_id=member_id)
    staff_auth = {"Authorization": f"Bearer {staff_token}"}
    visible = await client.get(
        f"/v1/corporate/organizations/{organization_id}/projects", headers=staff_auth
    )
    assert visible.status_code == 200
    assert [item["name"] for item in visible.json()["items"]] == ["Core updated"]
    forbidden = await client.get(
        f"/v1/corporate/organizations/{organization_id}/members", headers=staff_auth
    )
    assert forbidden.status_code == 403
    staff_context = await client.get(
        f"/v1/corporate/organizations/{organization_id}/context", headers=staff_auth
    )
    assert staff_context.status_code == 200
    assert [item["name"] for item in staff_context.json()["teams"]] == ["Platform"]

    membership_revision = staff_context.json()["organization"]["authorization_revision"]
    reassignment_payload = {
        "schema_version": 1,
        "account_id": member_id,
        "team_id": team.json()["team_id"],
        "project_id": project_id,
        "team_role": "staff",
        "operation": "assign",
        "authorization_revision": membership_revision,
        "idempotency_key": "change-staff-membership-0001",
    }
    reassignment = await client.post(
        f"/v1/corporate/organizations/{organization_id}/membership-assignments",
        json=reassignment_payload,
        headers=auth,
    )
    assert reassignment.status_code == 200, reassignment.text
    assert reassignment.json()["operation"] == "assign"
    assert reassignment.json()["team_role"] == "staff"
    replayed_reassignment = await client.post(
        f"/v1/corporate/organizations/{organization_id}/membership-assignments",
        json=reassignment_payload,
        headers=auth,
    )
    assert replayed_reassignment.status_code == 200, replayed_reassignment.text
    assert replayed_reassignment.json() == reassignment.json()

    removal_payload = {
        **reassignment_payload,
        "operation": "remove",
        "authorization_revision": (
            await client.get(f"/v1/corporate/organizations/{organization_id}/context", headers=auth)
        ).json()["organization"]["authorization_revision"],
        "idempotency_key": "remove-staff-membership-0001",
    }
    removal = await client.post(
        f"/v1/corporate/organizations/{organization_id}/membership-assignments",
        json=removal_payload,
        headers=auth,
    )
    assert removal.status_code == 200, removal.text
    assert removal.json()["operation"] == "remove"
    replayed_removal = await client.post(
        f"/v1/corporate/organizations/{organization_id}/membership-assignments",
        json=removal_payload,
        headers=auth,
    )
    assert replayed_removal.status_code == 200, replayed_removal.text
    removed_context = await client.get(
        f"/v1/corporate/organizations/{organization_id}/context", headers=staff_auth
    )
    assert removed_context.status_code == 200
    assert removed_context.json()["teams"] == []
    assert removed_context.json()["projects"] == []

    foreign_id = new_id("organization")
    async with sessionmaker() as db:
        await set_tenant_scope(db, foreign_id)
        db.add(
            Organization(
                id=foreign_id,
                kind="corporate",
                owner_account_id=None,
                display_name="Foreign",
            )
        )
        await db.flush()
        foreign_project_id = new_id("remote_project")
        db.add(CorporateProject(id=foreign_project_id, organization_id=foreign_id, name="Hidden"))
        await db.commit()
    async with sessionmaker() as db:
        await set_tenant_scope(db, "*")
        db.add(
            CorporateProjectMember(
                organization_id=foreign_id,
                project_id=foreign_project_id,
                account_id=owner_id,
            )
        )
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()
    foreign = await client.get(f"/v1/corporate/organizations/{foreign_id}/projects", headers=auth)
    assert foreign.status_code == 403
    assert "Hidden" not in foreign.text
    async with sessionmaker() as db:
        probe_role = f"tenant_probe_{uuid.uuid4().hex}"
        await db.execute(text(f'CREATE ROLE "{probe_role}" NOLOGIN'))
        await db.execute(text(f'GRANT SELECT, UPDATE ON corporate_project TO "{probe_role}"'))
        await set_tenant_scope(db, organization_id)
        await db.execute(text(f'SET LOCAL ROLE "{probe_role}"'))
        assert (
            await db.scalar(
                select(CorporateProject.id).where(CorporateProject.organization_id == foreign_id)
            )
            is None
        )
        hidden_update = await db.execute(
            text(
                "UPDATE corporate_project SET name = 'leaked' WHERE organization_id = :foreign_id"
            ),
            {"foreign_id": foreign_id},
        )
        assert getattr(hidden_update, "rowcount", None) == 0
        await db.execute(text("RESET ROLE"))
        await set_tenant_scope(db, "*")
        await db.execute(text(f'SET LOCAL ROLE "{probe_role}"'))
        with pytest.raises(DBAPIError, match="organization_id is immutable"):
            await db.execute(
                text(
                    "UPDATE corporate_project SET organization_id = :foreign_id "
                    "WHERE id = :project_id"
                ),
                {"foreign_id": foreign_id, "project_id": project_id},
            )
        await db.rollback()

    audit = await client.get(f"/v1/corporate/organizations/{organization_id}/audit", headers=auth)
    assert audit.status_code == 200, audit.text
    actions = {item["action"] for item in audit.json()["items"]}
    assert {
        "corporate.bootstrap",
        "corporate.bootstrap.replay",
        "member.create",
        "project.create",
        "team.create",
        "member.assign",
        "member.remove",
    } <= actions
    assert any(item.startswith("member.") and item.endswith(".replay") for item in actions)
    async with sessionmaker() as db:
        await set_tenant_scope(db, organization_id)
        membership_audit = await db.scalar(
            select(AuditEvent).where(
                AuditEvent.organization_id == organization_id,
                AuditEvent.action == "member.remove",
            )
        )
        assert membership_audit is not None
        assert membership_audit.actor_type == "user"
        assert membership_audit.actor_id == owner_id
        assert membership_audit.effective_role_bindings == [
            {
                "role": "superadmin",
                "scope_kind": "organization",
                "scope_id": organization_id,
            }
        ]
        assert membership_audit.payload["before"] == {
            "team_role": "staff",
            "project_assigned": True,
        }
        assert membership_audit.payload["after"] == {
            "team_role": None,
            "project_assigned": False,
        }

    current = (
        await client.get(f"/v1/corporate/organizations/{organization_id}/context", headers=auth)
    ).json()["organization"]["authorization_revision"]
    same_role = await client.patch(
        f"/v1/corporate/organizations/{organization_id}/members/{member_id}",
        json={
            "schema_version": 1,
            "role": "staff",
            "state": "active",
            "expected_revision": 2,
            "idempotency_key": "update-member-0001",
            "authorization_revision": current,
        },
        headers=auth,
    )
    assert same_role.status_code == 200, same_role.text
    current = (
        await client.get(f"/v1/corporate/organizations/{organization_id}/context", headers=auth)
    ).json()["organization"]["authorization_revision"]
    service_principal = await client.post(
        f"/v1/corporate/organizations/{organization_id}/service-principals",
        json={
            "schema_version": 1,
            "name": "deployment-worker",
            "role": "staff",
            "scope_kind": "project",
            "scope_id": project_id,
            "authorization_revision": current,
            "idempotency_key": "create-service-principal-0001",
        },
        headers=auth,
    )
    assert service_principal.status_code == 200, service_principal.text
    principal_id = service_principal.json()["service_principal_id"]
    async with sessionmaker() as db:
        assert await has_corporate_permission(
            db,
            organization_id=organization_id,
            principal_type="service_principal",
            principal_id=principal_id,
            permission="project.read",
            scope_kind="project",
            scope_id=project_id,
        )
    suspended = await client.patch(
        f"/v1/corporate/organizations/{organization_id}/service-principals/{principal_id}",
        json={
            "schema_version": 1,
            "state": "suspended",
            "expected_revision": 1,
            "idempotency_key": "update-service-principal-0001",
            "authorization_revision": current + 1,
        },
        headers=auth,
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["binding"]["state"] == "revoked"
    suspended_list = await client.get(
        f"/v1/corporate/organizations/{organization_id}/service-principals", headers=auth
    )
    assert suspended_list.status_code == 200, suspended_list.text
    assert suspended_list.json()["items"][0]["state"] == "suspended"
    suspended_read = await client.get(
        f"/v1/corporate/organizations/{organization_id}/service-principals/{principal_id}",
        headers=auth,
    )
    assert suspended_read.status_code == 200, suspended_read.text
    reactivated = await client.patch(
        f"/v1/corporate/organizations/{organization_id}/service-principals/{principal_id}",
        json={
            "schema_version": 1,
            "state": "active",
            "expected_revision": 2,
            "idempotency_key": "reactivate-service-principal-0001",
            "authorization_revision": current + 2,
        },
        headers=auth,
    )
    assert reactivated.status_code == 200, reactivated.text
    assert reactivated.json()["binding"]["state"] == "active"
    current = (
        await client.get(f"/v1/corporate/organizations/{organization_id}/context", headers=auth)
    ).json()["organization"]["authorization_revision"]
    last_admin = await client.patch(
        f"/v1/corporate/organizations/{organization_id}/members/{owner_id}",
        json={
            "schema_version": 1,
            "role": "staff",
            "state": "active",
            "expected_revision": 1,
            "idempotency_key": "demote-last-superadmin-0001",
            "authorization_revision": current,
        },
        headers=auth,
    )
    assert last_admin.status_code == 409

    role_revision = (
        await client.get(f"/v1/corporate/organizations/{organization_id}/context", headers=auth)
    ).json()["organization"]["authorization_revision"]
    created_role = await client.post(
        f"/v1/corporate/organizations/{organization_id}/roles",
        json={
            "schema_version": 1,
            "name": "project_reviewer",
            "parent_role": "lead",
            "permissions": [],
            "authorization_revision": role_revision,
            "idempotency_key": "create-role-0001",
        },
        headers=auth,
    )
    assert created_role.status_code == 200, created_role.text
    assert created_role.json()["parent_role"] == "lead"
    missing_parent_role = await client.post(
        f"/v1/corporate/organizations/{organization_id}/roles",
        json={
            "schema_version": 1,
            "name": "orphan_role",
            "parent_role": "missing_role",
            "permissions": [],
            "authorization_revision": role_revision + 1,
            "idempotency_key": "create-orphan-role-0001",
        },
        headers=auth,
    )
    assert missing_parent_role.status_code == 400
    roles = await client.get(f"/v1/corporate/organizations/{organization_id}/roles", headers=auth)
    assert roles.status_code == 200, roles.text
    assert "project_reviewer" in {item["name"] for item in roles.json()["items"]}
    role_revision = (
        await client.get(f"/v1/corporate/organizations/{organization_id}/context", headers=auth)
    ).json()["organization"]["authorization_revision"]
    role_binding = await client.post(
        f"/v1/corporate/organizations/{organization_id}/bindings",
        json={
            "schema_version": 1,
            "account_id": member_id,
            "role": "project_reviewer",
            "scope_kind": "project",
            "scope_id": project_id,
            "authorization_revision": role_revision,
            "idempotency_key": "create-role-binding-0001",
        },
        headers=auth,
    )
    assert role_binding.status_code == 200, role_binding.text
    async with sessionmaker() as db:
        assert await has_corporate_permission(
            db,
            organization_id=organization_id,
            principal_type="user",
            principal_id=member_id,
            permission="project.update",
            scope_kind="project",
            scope_id=project_id,
        )
    unsupported_scope = await client.post(
        f"/v1/corporate/organizations/{organization_id}/bindings",
        json={
            "schema_version": 1,
            "account_id": member_id,
            "role": "project_reviewer",
            "scope_kind": "telemetry",
            "scope_id": "foreign-telemetry-id",
            "authorization_revision": role_revision + 1,
            "idempotency_key": "create-unsupported-scope-0001",
        },
        headers=auth,
    )
    assert unsupported_scope.status_code == 403
    exported = await client.get(
        f"/v1/corporate/organizations/{organization_id}/audit/export", headers=auth
    )
    assert exported.status_code == 200, exported.text
    assert exported.json()["organization_id"] == organization_id
    assert any(item["action"] == "role.create" for item in exported.json()["items"])
    assert all("token" not in item["payload"] for item in exported.json()["items"])
