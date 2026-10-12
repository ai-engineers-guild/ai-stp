"""Scoped RBAC coverage: member-scope grants and catalog-object capabilities."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.support.catalog_seed import seed_corpus, upsert_seed_version

from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_foundation.ids import new_id
from ai_stp_platform.catalog_ownership_models import CorporateCatalogOwnership
from ai_stp_platform.models import AccessGrant, Account, CatalogIdentity, CatalogMetadata
from ai_stp_platform.tenant_scope import set_tenant_scope

pytestmark = pytest.mark.platform


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
    client: AsyncClient, *, owner_id: str, name: str = "Scoped RBAC Corp"
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


async def test_team_lead_manages_own_team_members_only(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    """A lead binding scoped to a team covers members of that team only."""
    client, sessionmaker, _settings = db_api_client
    owner_id, owner_auth = await _account_with_session(sessionmaker)
    org = await _bootstrap_org(client, owner_id=owner_id)

    lead = await _mutate(
        client,
        org,
        owner_auth,
        "members",
        {"display_name": "Team lead", "email": "lead@example.com", "role": "staff"},
    )
    member_a = await _mutate(
        client,
        org,
        owner_auth,
        "members",
        {"display_name": "Member A", "email": "member-a@example.com", "role": "staff"},
    )
    member_b = await _mutate(
        client,
        org,
        owner_auth,
        "members",
        {"display_name": "Member B", "email": "member-b@example.com", "role": "staff"},
    )
    team_a = await _mutate(client, org, owner_auth, "teams", {"name": "Team A"})
    team_b = await _mutate(client, org, owner_auth, "teams", {"name": "Team B"})
    for account_id, team_id, team_role in (
        (lead["account_id"], team_a["team_id"], "lead"),
        (owner_id, team_a["team_id"], "staff"),
        (member_a["account_id"], team_a["team_id"], "staff"),
        (member_b["account_id"], team_b["team_id"], "staff"),
    ):
        await _mutate(
            client,
            org,
            owner_auth,
            "membership-assignments",
            {"account_id": account_id, "team_id": team_id, "team_role": team_role},
        )

    _, lead_auth = await _account_with_session(sessionmaker, lead["account_id"])

    detail_a = await client.get(
        f"/v1/corporate/organizations/{org}/members/{member_a['account_id']}",
        headers=lead_auth,
    )
    assert detail_a.status_code == 200, detail_a.text
    assert set(detail_a.json()["available_actions"]) >= {
        "member.update",
        "member.delete",
        "entity_profile.update",
    }

    subject = {"kind": "member", "id": member_a["account_id"], "organization_id": org}
    menus = await client.post(
        "/v1/entity-actions/query", headers=lead_auth, json={"subjects": [subject, subject]}
    )
    assert menus.status_code == 200, menus.text
    assert menus.headers["cache-control"] == "no-store, private"
    first, related = menus.json()["items"]
    assert first == related
    assert [action["id"] for action in first["actions"]] == [
        "open",
        "copy_id",
        "copy_url",
        "share",
        "edit",
        "edit_presentation",
        "delete",
        "report",
    ]
    assert first["href"].endswith(f"/employees/{member_a['account_id']}")
    foreign = await client.post(
        "/v1/entity-actions/query",
        headers=lead_auth,
        json={"subjects": [{**subject, "id": member_b["account_id"]}]},
    )
    assert foreign.status_code == 403, foreign.text

    administrator = await client.post(
        "/v1/entity-actions/query",
        headers=lead_auth,
        json={"subjects": [{**subject, "id": owner_id}]},
    )
    assert administrator.status_code == 200, administrator.text
    administrator_actions = {action["id"] for action in administrator.json()["items"][0]["actions"]}
    assert "edit_presentation" in administrator_actions
    assert not {"edit", "delete", "manage_access"} & administrator_actions

    revision = await _member_revision(client, org, lead_auth, member_a["account_id"])
    updated = await _mutate(
        client,
        org,
        lead_auth,
        f"members/{member_a['account_id']}",
        {
            "role": "staff",
            "state": "suspended",
            "expected_revision": revision,
        },
        method="PATCH",
    )
    assert updated["state"] == "suspended"

    revision = await _member_revision(client, org, lead_auth, member_a["account_id"])
    await _mutate(
        client,
        org,
        lead_auth,
        f"members/{member_a['account_id']}",
        {
            "role": "lead",
            "state": "suspended",
            "expected_revision": revision,
        },
        method="PATCH",
        expected=403,
    )

    # Members of another team are outside the lead's scope entirely.
    detail_b = await client.get(
        f"/v1/corporate/organizations/{org}/members/{member_b['account_id']}",
        headers=lead_auth,
    )
    assert detail_b.status_code == 403, detail_b.text

    revision_b = await _member_revision(client, org, owner_auth, member_b["account_id"])
    await _mutate(
        client,
        org,
        lead_auth,
        f"members/{member_b['account_id']}",
        {
            "role": "staff",
            "state": "suspended",
            "expected_revision": revision_b,
        },
        method="PATCH",
        expected=403,
    )

    revision = await _member_revision(client, org, lead_auth, member_a["account_id"])
    await _mutate(
        client,
        org,
        lead_auth,
        f"members/{member_a['account_id']}",
        {"expected_revision": revision},
        method="DELETE",
    )

    # The superadmin keeps organization-wide member administration.
    revision_b = await _member_revision(client, org, owner_auth, member_b["account_id"])
    promoted = await _mutate(
        client,
        org,
        owner_auth,
        f"members/{member_b['account_id']}",
        {
            "role": "lead",
            "state": "active",
            "expected_revision": revision_b,
        },
        method="PATCH",
    )
    assert promoted["role"] == "lead"


def _seed_catalog_object(
    *,
    author_id: str,
    organization_id: str | None,
    object_kind: str,
    stable_id: str,
    published: bool,
) -> tuple[CatalogIdentity, CatalogMetadata]:
    identity = CatalogIdentity(
        stable_id=stable_id,
        owner_account_id=author_id,
        organization_id=organization_id,
        canonical_name=f"test/{stable_id}",
        canonical_name_normalized=f"test/{stable_id}",
    )
    metadata = CatalogMetadata(
        owner_account_id=author_id,
        organization_id=organization_id,
        object_kind=object_kind,
        stable_id=stable_id,
        version="1.0",
        current_revision_id="revision_" + "0" * 64,
        visibility="public",
        lifecycle_state="active",
        name="scoped-rbac-object",
        published_at=datetime(2025, 1, 1, tzinfo=UTC) if published else None,
    )
    return identity, metadata


async def test_catalog_object_capabilities_and_draft_delete(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    """Capability probe + delete endpoint follow author/superadmin/owner grants."""
    client, sessionmaker, _settings = db_api_client
    owner_id, owner_auth = await _account_with_session(sessionmaker)
    org = await _bootstrap_org(client, owner_id=owner_id)

    author = await _mutate(
        client,
        org,
        owner_auth,
        "members",
        {"display_name": "Author", "email": "author@example.com", "role": "staff"},
    )
    stranger = await _mutate(
        client,
        org,
        owner_auth,
        "members",
        {"display_name": "Stranger", "email": "stranger@example.com", "role": "staff"},
    )
    _, author_auth = await _account_with_session(sessionmaker, author["account_id"])
    _, stranger_auth = await _account_with_session(sessionmaker, stranger["account_id"])

    draft_id = new_id("component")
    published_id = new_id("component")
    async with sessionmaker() as db:
        await set_tenant_scope(db, org)
        for stable_id, published in ((draft_id, False), (published_id, True)):
            identity, metadata = _seed_catalog_object(
                author_id=author["account_id"],
                organization_id=org,
                object_kind="component",
                stable_id=stable_id,
                published=published,
            )
            db.add(identity)
            db.add(metadata)
        db.add(
            CorporateCatalogOwnership(
                organization_id=org,
                object_kind="component",
                stable_id=draft_id,
                owner_kind="employee",
                owner_id=stranger["account_id"],
                owner_account_id=stranger["account_id"],
                revision=1,
            )
        )
        await db.commit()

    for headers, expected in (
        (author_auth, {"delete", "edit", "edit_presentation", "manage_access"}),
        (owner_auth, {"delete", "edit", "edit_presentation"}),
        (stranger_auth, {"edit", "edit_presentation", "manage_access"}),
    ):
        response = await client.get(
            f"/v1/owner/objects/component/{draft_id}/capabilities", headers=headers
        )
        assert response.status_code == 200, response.text
        assert set(response.json()["capabilities"]) == expected

    for headers, expected in ((author_auth, True), (stranger_auth, False)):
        menus = await client.post(
            "/v1/entity-actions/query",
            headers=headers,
            json={"subjects": [{"kind": "component", "id": draft_id}]},
        )
        assert menus.status_code == 200, menus.text
        actions = [action["id"] for action in menus.json()["items"][0]["actions"]]
        assert actions[:5] == ["open", "copy_id", "copy_url", "copy_cli", "share"]
        assert "manage_access" in actions and "edit_presentation" in actions
        assert ("delete" in actions) is expected
        assert actions[-1] == "report"

    response = await client.get(
        f"/v1/owner/objects/component/{published_id}/capabilities", headers=author_auth
    )
    assert response.status_code == 200, response.text
    assert set(response.json()["capabilities"]) == {"edit", "edit_presentation", "manage_access"}

    response = await client.delete(
        f"/v1/owner/objects/component/{published_id}", headers=author_auth
    )
    assert response.status_code == 409, response.text

    response = await client.delete(f"/v1/owner/objects/component/{draft_id}", headers=stranger_auth)
    assert response.status_code == 403, response.text

    member_revision = await _member_revision(client, org, owner_auth, stranger["account_id"])
    await _mutate(
        client,
        org,
        owner_auth,
        f"members/{stranger['account_id']}",
        {"role": "staff", "state": "suspended", "expected_revision": member_revision},
        method="PATCH",
    )
    capabilities = await client.get(
        f"/v1/owner/objects/component/{draft_id}/capabilities", headers=stranger_auth
    )
    assert capabilities.status_code == 200, capabilities.text
    assert capabilities.json()["capabilities"] == []
    hidden = await client.post(
        "/v1/entity-actions/query",
        headers=stranger_auth,
        json={"subjects": [{"kind": "component", "id": draft_id}]},
    )
    assert hidden.status_code == 404, hidden.text

    response = await client.delete(f"/v1/owner/objects/component/{draft_id}", headers=owner_auth)
    assert response.status_code == 204, response.text

    async with sessionmaker() as db:
        await set_tenant_scope(db, org)
        remaining = await db.scalar(
            select(CatalogMetadata.id).where(CatalogMetadata.stable_id == draft_id)
        )
        assert remaining is None
        ownership = await db.get(CorporateCatalogOwnership, (org, "component", draft_id))
        assert ownership is None


async def test_solo_author_menu_is_independent_of_corporate_and_rejects_anonymous_draft(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    author, headers = await _account_with_session(sessionmaker)
    stable_id = new_id("component")
    async with sessionmaker() as db:
        identity, metadata = _seed_catalog_object(
            author_id=author,
            organization_id=None,
            object_kind="component",
            stable_id=stable_id,
            published=False,
        )
        db.add_all([identity, metadata])
        await db.commit()
    response = await client.post(
        "/v1/entity-actions/query",
        headers=headers,
        json={"subjects": [{"kind": "component", "id": stable_id}]},
    )
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["items"][0]["actions"]] == [
        "open",
        "copy_id",
        "copy_url",
        "copy_cli",
        "share",
        "like",
        "edit",
        "edit_presentation",
        "manage_access",
        "delete",
        "report",
    ]
    denied = await client.post(
        "/v1/entity-actions/query", json={"subjects": [{"kind": "component", "id": stable_id}]}
    )
    assert denied.status_code == 404, denied.text
    oversized = await client.post(
        "/v1/entity-actions/query",
        headers=headers,
        json={"subjects": [{"kind": "component", "id": stable_id}] * 257},
    )
    assert oversized.status_code == 400, oversized.text
    assert oversized.json()["error"]["code"] == "AI_STP_VALIDATION_ERROR"


async def test_solo_private_grant_is_read_only_and_revocation_removes_visibility(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    kind, passport, published_at, digest = seed_corpus()[0]
    author, author_auth = await _account_with_session(sessionmaker, str(passport["owner_id"]))
    recipient, recipient_auth = await _account_with_session(sessionmaker)
    stable_id = str(passport["stable_id"])
    grant_id = new_id("grant")
    async with sessionmaker() as db:
        metadata, _ = await upsert_seed_version(
            db,
            object_kind=kind,
            passport=passport,
            published_at_wire=published_at,
            passport_digest=digest,
        )
        metadata.visibility = "private"
        db.add(
            AccessGrant(
                id=grant_id,
                object_kind=kind,
                stable_id=stable_id,
                major=1,
                owner_account_id=author,
                grantee_account_id=recipient,
                state="active",
            )
        )
        await db.commit()
    query = {
        "subjects": [{"kind": "component", "id": stable_id}, {"kind": "grant", "id": grant_id}]
    }
    response = await client.post("/v1/entity-actions/query", headers=recipient_auth, json=query)
    assert response.status_code == 200, response.text
    catalog_menu, grant_menu = response.json()["items"]
    assert [action["id"] for action in catalog_menu["actions"]] == [
        "open",
        "copy_id",
        "copy_url",
        "copy_cli",
        "share",
        "like",
        "report",
    ]
    assert [action["id"] for action in grant_menu["actions"]] == ["copy_id", "report"]
    owner_menu = await client.post(
        "/v1/entity-actions/query",
        headers=author_auth,
        json={"subjects": [{"kind": "grant", "id": grant_id}]},
    )
    assert owner_menu.status_code == 200, owner_menu.text
    assert [action["id"] for action in owner_menu.json()["items"][0]["actions"]] == [
        "copy_id",
        "revoke",
        "report",
    ]
    revoke = await client.post(
        f"/v1/grants/{grant_id}/revoke",
        headers=recipient_auth,
        json={"idempotency_key": str(uuid.uuid4())},
    )
    assert revoke.status_code == 404, revoke.text
    revoked = await client.post(
        f"/v1/grants/{grant_id}/revoke",
        headers=author_auth,
        json={"idempotency_key": str(uuid.uuid4())},
    )
    assert revoked.status_code == 200, revoked.text
    hidden = await client.post(
        "/v1/entity-actions/query",
        headers=recipient_auth,
        json={"subjects": [{"kind": "component", "id": stable_id}]},
    )
    assert hidden.status_code == 404, hidden.text


async def test_role_menus_respect_delegation_and_job_title_lifecycle(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    owner_id, auth = await _account_with_session(sessionmaker)
    org = await _bootstrap_org(client, owner_id=owner_id)
    await _mutate(
        client,
        org,
        auth,
        "roles",
        {
            "name": "menu_manager",
            "permissions": [
                "role.read",
                "role.create",
                "binding.create",
                "job_title.read",
                "job_title.update",
            ],
        },
    )
    manager = await _mutate(
        client,
        org,
        auth,
        "members",
        {
            "display_name": "Menu manager",
            "email": "menu-manager@example.com",
            "role": "menu_manager",
        },
    )
    _, manager_auth = await _account_with_session(sessionmaker, manager["account_id"])
    title = await _mutate(
        client, org, auth, "job-titles", {"name": "Engineer", "description": "Engineering"}
    )
    await _mutate(
        client,
        org,
        auth,
        f"job-titles/{title['job_title_id']}",
        {
            "name": title["name"],
            "description": title["description"],
            "state": "retired",
            "expected_revision": title["revision"],
        },
        method="PATCH",
    )
    response = await client.post(
        "/v1/entity-actions/query",
        headers=manager_auth,
        json={
            "subjects": [
                {"kind": "role", "id": "superadmin", "organization_id": org},
                {"kind": "role", "id": "menu_manager", "organization_id": org},
                {"kind": "job_title", "id": title["job_title_id"], "organization_id": org},
            ]
        },
    )
    assert response.status_code == 200, response.text
    admin, own_role, retired = response.json()["items"]
    assert [item["id"] for item in admin["actions"]] == [
        "open",
        "copy_id",
        "copy_url",
        "share",
        "report",
    ]
    assert {item["id"] for item in own_role["actions"]} >= {"duplicate", "assign_members"}
    assert {item["id"] for item in retired["actions"]} >= {"edit", "restore"}
    assert not {item["id"] for item in retired["actions"]} & {"retire", "delete", "assign_members"}
    retired_admin = await client.post(
        "/v1/entity-actions/query",
        headers=auth,
        json={
            "subjects": [{"kind": "job_title", "id": title["job_title_id"], "organization_id": org}]
        },
    )
    assert retired_admin.status_code == 200, retired_admin.text
    assert "assign_members" not in {
        action["id"] for action in retired_admin.json()["items"][0]["actions"]
    }
    last_admin = await client.post(
        "/v1/entity-actions/query",
        headers=auth,
        json={
            "subjects": [
                {"kind": "member", "id": owner_id, "organization_id": org},
            ]
        },
    )
    assert last_admin.status_code == 200, last_admin.text
    assert "delete" not in {item["id"] for item in last_admin.json()["items"][0]["actions"]}
