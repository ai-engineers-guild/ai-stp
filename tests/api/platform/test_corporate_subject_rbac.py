"""Scoped RBAC coverage: member-scope grants and catalog-object capabilities."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_foundation.ids import new_id
from ai_stp_platform.catalog_ownership_models import CorporateCatalogOwnership
from ai_stp_platform.models import Account, CatalogIdentity, CatalogMetadata
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
        (author_auth, {"delete", "edit", "edit_presentation"}),
        (owner_auth, {"delete", "edit", "edit_presentation"}),
        (stranger_auth, {"edit", "edit_presentation"}),
    ):
        response = await client.get(
            f"/v1/owner/objects/component/{draft_id}/capabilities", headers=headers
        )
        assert response.status_code == 200, response.text
        assert set(response.json()["capabilities"]) == expected

    response = await client.get(
        f"/v1/owner/objects/component/{published_id}/capabilities", headers=author_auth
    )
    assert response.status_code == 200, response.text
    assert set(response.json()["capabilities"]) == {"edit", "edit_presentation"}

    response = await client.delete(
        f"/v1/owner/objects/component/{published_id}", headers=author_auth
    )
    assert response.status_code == 409, response.text

    response = await client.delete(f"/v1/owner/objects/component/{draft_id}", headers=stranger_auth)
    assert response.status_code == 403, response.text

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
