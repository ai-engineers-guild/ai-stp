"""Delegated-authority bounds, binding provenance, and direct permission grants."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_foundation.ids import new_id
from ai_stp_platform.catalog_ownership_models import CorporateCatalogOwnership
from ai_stp_platform.models import AccessGrant, Account, CatalogIdentity, CatalogMetadata
from ai_stp_platform.organization_models import (
    CorporateRole,
    CorporateRoleBinding,
    CorporateRolePermission,
    Organization,
)
from ai_stp_platform.tenant_scope import set_tenant_scope

pytestmark = pytest.mark.platform


async def test_legacy_role_matrix_requires_missing_permission_repair(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    """A superadmin label does not bypass the persisted delegation bound."""
    client, sessionmaker, _settings = db_api_client
    owner, auth = await _account_with_session(sessionmaker)
    org = await _bootstrap_org(client, owner_id=owner)
    async with sessionmaker() as db:
        await set_tenant_scope(db, org)
        lead = await db.get(CorporateRole, (org, "lead"))
        staff = await db.get(CorporateRole, (org, "staff"))
        assert lead and staff
        lead.parent_role = "superadmin"
        staff.parent_role = "lead"
        await db.execute(
            delete(CorporateRolePermission).where(
                CorporateRolePermission.organization_id == org,
                CorporateRolePermission.role == "superadmin",
                CorporateRolePermission.permission == "team.delete",
            )
        )
        await db.commit()
    body: dict[str, object] = {
        "recipient_email": "recipient@example.com",
        "display_name": "Recipient",
        "role": "staff",
        "team_ids": [],
        "ttl_seconds": 86400,
    }
    denied = await _mutate(client, org, auth, "invitations", body, expected=403)
    assert denied.json()["error"]["message"] == "grant exceeds delegated authority"
    delegation = await client.get(f"/v1/corporate/organizations/{org}/delegation", headers=auth)
    assert "staff" not in {role["name"] for role in delegation.json()["grantable_roles"]}
    async with sessionmaker() as db:
        await set_tenant_scope(db, org)
        db.add(
            CorporateRolePermission(
                organization_id=org, role="superadmin", permission="team.delete"
            )
        )
        role = await db.get(CorporateRole, (org, "superadmin"))
        organization = await db.get(Organization, org)
        assert role and organization
        role.revision += 1
        organization.policy_revision += 1
        await db.commit()
    created = await _mutate(client, org, auth, "invitations", body)
    assert created["role"] == "staff"
    delegation = await client.get(f"/v1/corporate/organizations/{org}/delegation", headers=auth)
    assert "staff" in {role["name"] for role in delegation.json()["grantable_roles"]}


async def _account_with_session(
    sessionmaker: async_sessionmaker[AsyncSession],
    account_id: str | None = None,
) -> tuple[str, dict[str, str]]:
    async with sessionmaker() as db:
        account = await db.get(Account, account_id) if account_id else None
        if account is None:
            account = Account(id=account_id or new_id("account"), status="active")
            db.add(account)
            await db.flush()
        issued = await issue_session(db, account_id=account.id, device_id=None, ttl_seconds=3600)
        await db.commit()
        return account.id, {"Authorization": f"Bearer {issued.raw_token}"}


async def _bootstrap_org(
    client: AsyncClient, *, owner_id: str, name: str = "Delegation Corp"
) -> str:
    response = await client.post(
        "/v1/corporate/bootstrap",
        json={
            "organization_name": name,
            "superadmin_account_id": owner_id,
            "idempotency_key": str(uuid.uuid4()),
        },
        headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
    )
    assert response.status_code == 200, response.text
    return response.json()["organization_id"]


async def _revision(client: AsyncClient, org: str, headers: dict[str, str]) -> int:
    context = await client.get(f"/v1/corporate/organizations/{org}/context", headers=headers)
    assert context.status_code == 200, context.text
    return context.json()["organization"]["authorization_revision"]


async def _mutate(
    client: AsyncClient,
    org: str,
    headers: dict[str, str],
    path: str,
    body: dict[str, object],
    *,
    method: str = "POST",
    expected: int = 200,
) -> Any:
    revision = await _revision(client, org, headers)
    response = await client.request(
        method,
        f"/v1/corporate/organizations/{org}/{path}",
        json={
            **body,
            "authorization_revision": revision,
            "idempotency_key": str(uuid.uuid4()),
        },
        headers=headers,
    )
    assert response.status_code == expected, response.text
    return response.json() if expected == 200 else response


async def _member_revision(
    client: AsyncClient, org: str, headers: dict[str, str], account_id: str
) -> int:
    response = await client.get(
        f"/v1/corporate/organizations/{org}/members/{account_id}", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["revision"]


async def _bindings(client: AsyncClient, org: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    response = await client.get(f"/v1/corporate/organizations/{org}/bindings", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def _setup_operator_org(
    client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> tuple[str, dict[str, str], dict[str, Any], dict[str, str], dict[str, Any]]:
    """Owner + org, an operator member with narrow delegated rights, a staff member."""
    owner_id, owner_auth = await _account_with_session(sessionmaker)
    org = await _bootstrap_org(client, owner_id=owner_id)
    await _mutate(
        client,
        org,
        owner_auth,
        "roles",
        {
            "name": "operator",
            "permissions": [
                "organization.read",
                "member.invite",
                "member.read",
                "member.list",
                "binding.create",
                "binding.list",
            ],
        },
    )
    await _mutate(
        client,
        org,
        owner_auth,
        "roles",
        {"name": "viewer", "permissions": ["organization.read", "member.list"]},
    )
    operator = await _mutate(
        client,
        org,
        owner_auth,
        "members",
        {"display_name": "Operator", "email": "operator@example.com", "role": "staff"},
    )
    member = await _mutate(
        client,
        org,
        owner_auth,
        "members",
        {"display_name": "Plain", "email": "plain@example.com", "role": "staff"},
    )
    await _mutate(
        client,
        org,
        owner_auth,
        "bindings",
        {
            "account_id": operator["account_id"],
            "role": "operator",
            "scope_kind": "organization",
        },
    )
    _, operator_auth = await _account_with_session(sessionmaker, operator["account_id"])
    return org, owner_auth, operator, operator_auth, member


async def test_delegation_bound_limits_role_assignment(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    """A delegate may only grant roles whose closed permissions fit its own."""
    client, sessionmaker, _settings = db_api_client
    org, _owner_auth, _operator, operator_auth, member = await _setup_operator_org(
        client, sessionmaker
    )

    delegation = await client.get(
        f"/v1/corporate/organizations/{org}/delegation", headers=operator_auth
    )
    assert delegation.status_code == 200, delegation.text
    grantable = {item["name"] for item in delegation.json()["grantable_roles"]}
    # The operator's bound covers its own staff membership closure plus the
    # narrow custom roles — anything above that stays out of reach.
    assert {"viewer", "staff", "operator"} <= grantable
    assert grantable.isdisjoint({"superadmin", "lead"})
    assert delegation.json()["descendants_coverage"] is False

    await _mutate(
        client,
        org,
        operator_auth,
        "bindings",
        {
            "account_id": member["account_id"],
            "role": "viewer",
            "scope_kind": "organization",
        },
    )
    await _mutate(
        client,
        org,
        operator_auth,
        "bindings",
        {
            "account_id": member["account_id"],
            "role": "superadmin",
            "scope_kind": "organization",
        },
        expected=403,
    )
    await _mutate(
        client,
        org,
        operator_auth,
        "bindings",
        {
            "account_id": member["account_id"],
            "role": "lead",
            "scope_kind": "organization",
        },
        expected=403,
    )
    # The operator lacks descendant coverage, so it cannot mint it.
    await _mutate(
        client,
        org,
        operator_auth,
        "bindings",
        {
            "account_id": member["account_id"],
            "role": "viewer",
            "scope_kind": "organization",
            "coverage": "descendants",
        },
        expected=403,
    )


async def test_owner_managed_bindings_reject_direct_mutation(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    """Membership- and assignment-owned rows are synchronized by their owners
    only; the direct-binding API refuses to rewrite them."""
    client, sessionmaker, _settings = db_api_client
    owner_id, owner_auth = await _account_with_session(sessionmaker)
    org = await _bootstrap_org(client, owner_id=owner_id)
    member = await _mutate(
        client,
        org,
        owner_auth,
        "members",
        {"display_name": "Managed", "email": "managed@example.com", "role": "staff"},
    )
    team = await _mutate(client, org, owner_auth, "teams", {"name": "Team"})
    await _mutate(
        client,
        org,
        owner_auth,
        "membership-assignments",
        {"account_id": member["account_id"], "team_id": team["team_id"], "team_role": "staff"},
    )

    items = await _bindings(client, org, owner_auth)
    membership_row = next(
        item
        for item in items
        if item["account_id"] == member["account_id"] and item["origin"] == "membership"
    )
    assignment_row = next(
        item
        for item in items
        if item["account_id"] == member["account_id"] and item["origin"] == "assignment"
    )
    assert membership_row["scope_kind"] == "organization"
    assert assignment_row["scope_kind"] == "team"

    for row in (membership_row, assignment_row):
        await _mutate(
            client,
            org,
            owner_auth,
            f"bindings/{row['binding_id']}",
            {
                "role": "lead",
                "scope_kind": row["scope_kind"],
                "scope_id": row["scope_id"],
                "state": "active",
                "expected_revision": row["revision"],
            },
            method="PATCH",
            expected=409,
        )
        await _mutate(
            client,
            org,
            owner_auth,
            f"bindings/{row['binding_id']}",
            {"expected_revision": row["revision"]},
            method="DELETE",
            expected=409,
        )

    # A direct binding survives membership-role synchronization.
    direct = await _mutate(
        client,
        org,
        owner_auth,
        "bindings",
        {
            "account_id": member["account_id"],
            "role": "lead",
            "scope_kind": "team",
            "scope_id": team["team_id"],
        },
    )
    assert direct["origin"] == "direct"
    revision = await _member_revision(client, org, owner_auth, member["account_id"])
    await _mutate(
        client,
        org,
        owner_auth,
        f"members/{member['account_id']}",
        {"role": "lead", "state": "active", "expected_revision": revision},
        method="PATCH",
    )
    items = await _bindings(client, org, owner_auth)
    surviving = next(item for item in items if item["binding_id"] == direct["binding_id"])
    assert surviving["state"] == "active"
    assert surviving["origin"] == "direct"


async def test_permission_grant_lifecycle(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    """Direct scoped allows: effect, delegation bound, duplicate guard, revoke."""
    client, sessionmaker, _settings = db_api_client
    org, owner_auth, _operator, operator_auth, member = await _setup_operator_org(
        client, sessionmaker
    )
    project = await _mutate(client, org, owner_auth, "projects", {"name": "Alpha"})
    _, member_auth = await _account_with_session(sessionmaker, member["account_id"])

    # A plain staff member cannot update the project.
    denied = await client.get(
        f"/v1/corporate/organizations/{org}/permission-grants", headers=member_auth
    )
    assert denied.status_code == 403, denied.text

    grant = await _mutate(
        client,
        org,
        owner_auth,
        "permission-grants",
        {
            "account_id": member["account_id"],
            "permission": "project.read",
            "scope_kind": "project",
            "scope_id": project["project_id"],
        },
    )
    assert grant["state"] == "active"
    assert grant["issuer_account_id"] is not None

    # Unknown permission is rejected before any delegation check.
    await _mutate(
        client,
        org,
        owner_auth,
        "permission-grants",
        {
            "account_id": member["account_id"],
            "permission": "project.fly",
            "scope_kind": "project",
            "scope_id": project["project_id"],
        },
        expected=400,
    )

    # Duplicate active grant conflicts.
    await _mutate(
        client,
        org,
        owner_auth,
        "permission-grants",
        {
            "account_id": member["account_id"],
            "permission": "project.read",
            "scope_kind": "project",
            "scope_id": project["project_id"],
        },
        expected=409,
    )

    # The operator may grant only permissions it holds at organization scope:
    # member.list is inside its closure, member.update is not.
    await _mutate(
        client,
        org,
        operator_auth,
        "permission-grants",
        {
            "account_id": member["account_id"],
            "permission": "member.list",
            "scope_kind": "organization",
        },
    )
    await _mutate(
        client,
        org,
        operator_auth,
        "permission-grants",
        {
            "account_id": member["account_id"],
            "permission": "member.update",
            "scope_kind": "organization",
        },
        expected=403,
    )

    listed = await client.get(
        f"/v1/corporate/organizations/{org}/permission-grants?account_id={member['account_id']}",
        headers=owner_auth,
    )
    assert listed.status_code == 200, listed.text
    grant_ids = {item["grant_id"] for item in listed.json()["items"]}
    assert grant["grant_id"] in grant_ids

    revoked = await _mutate(
        client,
        org,
        owner_auth,
        f"permission-grants/{grant['grant_id']}",
        {"expected_revision": grant["revision"]},
        method="DELETE",
    )
    assert revoked["state"] == "revoked"


async def test_last_effective_superadmin_protection(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    """The guard counts effective admin power, not the superadmin role name."""
    client, sessionmaker, _settings = db_api_client
    owner_id, owner_auth = await _account_with_session(sessionmaker)
    org = await _bootstrap_org(client, owner_id=owner_id)
    member = await _mutate(
        client,
        org,
        owner_auth,
        "members",
        {"display_name": "Deputy", "email": "deputy@example.com", "role": "staff"},
    )
    deputy_binding = await _mutate(
        client,
        org,
        owner_auth,
        "bindings",
        {
            "account_id": member["account_id"],
            "role": "superadmin",
            "scope_kind": "organization",
        },
    )
    _, member_auth = await _account_with_session(sessionmaker, member["account_id"])

    # Demoting the owner is safe while the deputy holds effective admin power.
    revision = await _member_revision(client, org, owner_auth, owner_id)
    demoted = await _mutate(
        client,
        org,
        owner_auth,
        f"members/{owner_id}",
        {"role": "staff", "state": "active", "expected_revision": revision},
        method="PATCH",
    )
    assert demoted["role"] == "staff"

    # Revoking the deputy's org superadmin binding would leave zero admins.
    async with sessionmaker() as db:
        await set_tenant_scope(db, org)
        current = await db.get(CorporateRoleBinding, deputy_binding["binding_id"])
        assert current is not None
        binding_revision = current.revision
    await _mutate(
        client,
        org,
        member_auth,
        f"bindings/{deputy_binding['binding_id']}",
        {"expected_revision": binding_revision},
        method="DELETE",
        expected=409,
    )

    # The deputy restores the owner, then can give up admin power.
    revision = await _member_revision(client, org, member_auth, owner_id)
    await _mutate(
        client,
        org,
        member_auth,
        f"members/{owner_id}",
        {"role": "superadmin", "state": "active", "expected_revision": revision},
        method="PATCH",
    )
    await _mutate(
        client,
        org,
        member_auth,
        f"bindings/{deputy_binding['binding_id']}",
        {"expected_revision": binding_revision},
        method="DELETE",
    )
    async with sessionmaker() as db:
        await set_tenant_scope(db, org)
        assert await db.get(CorporateRoleBinding, deputy_binding["binding_id"]) is None


async def test_invitation_role_is_bounded_by_issuer(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    """An issuer cannot invite into a role outside its delegation bound."""
    client, sessionmaker, _settings = db_api_client
    org, _owner_auth, _operator, operator_auth, _member = await _setup_operator_org(
        client, sessionmaker
    )
    revision = await _revision(client, org, operator_auth)

    # The operator holds the staff closure itself, so staff is inside its
    # bound; lead and superadmin are not.
    for role, expected in (("superadmin", 403), ("lead", 403), ("viewer", 200), ("staff", 200)):
        response = await client.post(
            f"/v1/corporate/organizations/{org}/invitations",
            json={
                "schema_version": 1,
                "recipient_email": f"invitee-{role}@example.com",
                "display_name": "Invitee",
                "role": role,
                "authorization_revision": revision,
                "idempotency_key": str(uuid.uuid4()),
            },
            headers=operator_auth,
        )
        assert response.status_code == expected, (role, response.text)


async def test_member_access_explains_sources(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    """Employee access view: independent sources, per-action attribution, and
    private major-line grants limited to this tenant's objects."""
    client, sessionmaker, _settings = db_api_client
    org, owner_auth, _operator, _operator_auth, member = await _setup_operator_org(
        client, sessionmaker
    )
    team = await _mutate(client, org, owner_auth, "teams", {"name": "Scoped team"})
    await _mutate(
        client,
        org,
        owner_auth,
        "bindings",
        {
            "account_id": member["account_id"],
            "role": "viewer",
            "scope_kind": "organization",
        },
    )
    grant = await _mutate(
        client,
        org,
        owner_auth,
        "permission-grants",
        {
            "account_id": member["account_id"],
            "permission": "member.list",
            "scope_kind": "organization",
        },
    )
    _, member_auth = await _account_with_session(sessionmaker, member["account_id"])

    stable_id = new_id("component")
    foreign_stable = new_id("component")
    foreign_org = new_id("organization")
    async with sessionmaker() as db:
        await set_tenant_scope(db, "*")
        db.add(
            Organization(
                id=foreign_org,
                kind="corporate",
                owner_account_id=None,
                display_name="Foreign org",
            )
        )
        await db.flush()
        await set_tenant_scope(db, org)
        db.add(
            CatalogIdentity(
                stable_id=stable_id,
                owner_account_id=member["account_id"],
                organization_id=org,
                canonical_name=f"test/{stable_id}",
                canonical_name_normalized=f"test/{stable_id}",
            )
        )
        db.add(
            AccessGrant(
                id=new_id("grant"),
                organization_id=org,
                object_kind="component",
                stable_id=stable_id,
                major=1,
                owner_account_id=member["account_id"],
                grantee_account_id=member["account_id"],
                state="active",
            )
        )
        await db.flush()
        await set_tenant_scope(db, foreign_org)
        db.add(
            CatalogIdentity(
                stable_id=foreign_stable,
                owner_account_id=member["account_id"],
                organization_id=foreign_org,
                canonical_name=f"test/{foreign_stable}",
                canonical_name_normalized=f"test/{foreign_stable}",
            )
        )
        db.add(
            AccessGrant(
                id=new_id("grant"),
                organization_id=foreign_org,
                object_kind="component",
                stable_id=foreign_stable,
                major=1,
                owner_account_id=member["account_id"],
                grantee_account_id=member["account_id"],
                state="active",
            )
        )
        await db.commit()

    # A plain staff member cannot read another member's access explanation.
    denied = await client.get(
        f"/v1/corporate/organizations/{org}/members/{member['account_id']}/access",
        headers=member_auth,
    )
    assert denied.status_code == 403, denied.text

    view = await client.get(
        f"/v1/corporate/organizations/{org}/members/{member['account_id']}/access",
        headers=owner_auth,
    )
    assert view.status_code == 200, view.text
    body = view.json()
    assert body["account_id"] == member["account_id"]
    assert body["scope_kind"] == "organization"

    origins = {(row["role"], row["origin"]) for row in body["bindings"]}
    assert ("staff", "membership") in origins
    assert ("viewer", "direct") in origins
    assert grant["grant_id"] in {row["grant_id"] for row in body["grants"]}
    assert [row["stable_id"] for row in body["private_grants"]] == [stable_id]

    by_permission = {row["permission"]: row for row in body["effective"]}
    member_list = by_permission["member.list"]
    source_kinds = {record["kind"] for record in member_list["source_records"]}
    assert source_kinds == {"binding", "grant"}
    assert grant["grant_id"] in {record["source_id"] for record in member_list["source_records"]}
    # The staff membership binding does not contribute member.list — only the
    # viewer binding and the direct grant may be cited.
    cited_roles = {record["role"] for record in member_list["source_records"] if record["role"]}
    assert cited_roles == {"viewer"}
    assert "member.update" not in by_permission

    # A team scope the member cannot reach explains an empty decision.
    team_view = await client.get(
        f"/v1/corporate/organizations/{org}/members/{member['account_id']}/access"
        f"?scope_kind=team&scope_id={team['team_id']}",
        headers=owner_auth,
    )
    assert team_view.status_code == 200, team_view.text
    assert team_view.json()["effective"] == []

    unknown = await client.get(
        f"/v1/corporate/organizations/{org}/members/{new_id('account')}/access",
        headers=owner_auth,
    )
    assert unknown.status_code == 404, unknown.text


async def test_corporate_access_grant_owner_context(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    """ADR-0221: the resolved operational owner issues and revokes private
    major-line grants; bare corporate status never does."""
    client, sessionmaker, _settings = db_api_client
    owner_id, owner_auth = await _account_with_session(sessionmaker)
    org = await _bootstrap_org(client, owner_id=owner_id)
    member = await _mutate(
        client,
        org,
        owner_auth,
        "members",
        {"display_name": "Owner", "email": "obj-owner@example.com", "role": "staff"},
    )
    recipient_id, _recipient_auth = await _account_with_session(sessionmaker)
    author_id, _author_auth = await _account_with_session(sessionmaker)
    _, member_auth = await _account_with_session(sessionmaker, member["account_id"])
    stranger_id, stranger_auth = await _account_with_session(sessionmaker)

    stable_id = new_id("component")
    async with sessionmaker() as db:
        await set_tenant_scope(db, org)
        identity = CatalogIdentity(
            stable_id=stable_id,
            owner_account_id=author_id,
            organization_id=org,
            canonical_name=f"test/{stable_id}",
            canonical_name_normalized=f"test/{stable_id}",
        )
        metadata = CatalogMetadata(
            owner_account_id=author_id,
            organization_id=org,
            object_kind="component",
            stable_id=stable_id,
            version="1.0",
            current_revision_id="revision_" + "0" * 64,
            visibility="private",
            lifecycle_state="active",
            name="corporate-owned-object",
        )
        db.add(identity)
        db.add(metadata)
        db.add(
            CorporateCatalogOwnership(
                organization_id=org,
                object_kind="component",
                stable_id=stable_id,
                owner_kind="employee",
                owner_id=member["account_id"],
                owner_account_id=member["account_id"],
                revision=1,
            )
        )
        await db.commit()

    body = {
        "schema_version": 1,
        "object_kind": "component",
        "stable_id": stable_id,
        "major": 1,
        "recipient_kind": "user_id",
        "idempotency_key": str(uuid.uuid4()),
    }
    stranger_denied = await client.post(
        "/v1/grants/direct",
        json={**body, "recipient": recipient_id},
        headers=stranger_auth,
    )
    assert stranger_denied.status_code == 403, stranger_denied.text
    # The organization superadmin is not the object's operational owner.
    admin_denied = await client.post(
        "/v1/grants/direct",
        json={**body, "recipient": recipient_id},
        headers=owner_auth,
    )
    assert admin_denied.status_code == 403, admin_denied.text

    issued = await client.post(
        "/v1/grants/direct",
        json={**body, "recipient": recipient_id},
        headers=member_auth,
    )
    assert issued.status_code == 201, issued.text
    grant = issued.json()
    assert grant["owner_account_id"] == member["account_id"]
    assert grant["grantee_account_id"] == recipient_id

    # The grant landed in the object's tenant scope, not the issuer's
    # personal workspace.
    async with sessionmaker() as db:
        await set_tenant_scope(db, org)
        row = await db.get(AccessGrant, grant["grant_id"])
        assert row is not None and row.organization_id == org

    # After operational ownership moves, the new owner can withdraw the grant.
    successor = await _mutate(
        client,
        org,
        owner_auth,
        "members",
        {"display_name": "Successor", "email": "successor@example.com", "role": "staff"},
    )
    _, successor_auth = await _account_with_session(sessionmaker, successor["account_id"])
    async with sessionmaker() as db:
        await set_tenant_scope(db, org)
        ownership = await db.get(CorporateCatalogOwnership, (org, "component", stable_id))
        assert ownership is not None
        ownership.owner_id = successor["account_id"]
        ownership.owner_account_id = successor["account_id"]
        await db.commit()

    revoked = await client.post(
        f"/v1/grants/{grant['grant_id']}/revoke",
        json={"schema_version": 1, "idempotency_key": str(uuid.uuid4())},
        headers=successor_auth,
    )
    assert revoked.status_code == 200, revoked.text
    async with sessionmaker() as db:
        await set_tenant_scope(db, org)
        row = await db.get(AccessGrant, grant["grant_id"])
        assert row is not None and row.state == "revoked"

    # The displaced issuer's authority is gone with the ownership record.
    displaced = await client.post(
        "/v1/grants/direct",
        json={**body, "recipient": stranger_id},
        headers=member_auth,
    )
    assert displaced.status_code == 403, displaced.text


async def test_descendant_coverage_controls_propagation(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    """Organization bindings reach descendant scopes only with explicit coverage."""
    client, sessionmaker, _settings = db_api_client
    owner_id, owner_auth = await _account_with_session(sessionmaker)
    org = await _bootstrap_org(client, owner_id=owner_id)
    member = await _mutate(
        client,
        org,
        owner_auth,
        "members",
        {"display_name": "Scoped", "email": "scoped@example.com", "role": "staff"},
    )
    team = await _mutate(client, org, owner_auth, "teams", {"name": "Team"})
    _, member_auth = await _account_with_session(sessionmaker, member["account_id"])

    # membership coverage=self: the org binding does not reach the team scope.
    denied = await client.get(
        f"/v1/corporate/organizations/{org}/teams/{team['team_id']}",
        headers=member_auth,
    )
    assert denied.status_code == 403, denied.text

    # A coverage=descendants org binding does reach team scope.
    await _mutate(
        client,
        org,
        owner_auth,
        "bindings",
        {
            "account_id": member["account_id"],
            "role": "lead",
            "scope_kind": "organization",
            "coverage": "descendants",
        },
    )
    allowed = await client.get(
        f"/v1/corporate/organizations/{org}/teams/{team['team_id']}",
        headers=member_auth,
    )
    assert allowed.status_code == 200, allowed.text
