"""Executable acceptance evidence for product-mode resolution (#225)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.session import issue_session
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import Organization, OrganizationMembership

pytestmark = pytest.mark.platform


async def test_product_mode_is_independent_from_auth_and_fails_closed(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Any],
) -> None:
    client, sessionmaker, _settings = db_api_client
    async with sessionmaker() as db:
        account = Account(id=new_id("account"))
        personal = Organization(
            id=new_id("organization"),
            kind="personal",
            owner_account_id=account.id,
            display_name="Personal",
        )
        corporate = Organization(
            id=new_id("organization"),
            kind="corporate",
            owner_account_id=None,
            display_name="Corporate",
        )
        db.add_all(
            [
                account,
                personal,
                corporate,
                OrganizationMembership(
                    organization_id=personal.id,
                    account_id=account.id,
                    role="owner",
                    state="active",
                ),
                OrganizationMembership(
                    organization_id=corporate.id,
                    account_id=account.id,
                    role="owner",
                    state="active",
                ),
            ]
        )
        issued = await issue_session(db, account_id=account.id, device_id=None, ttl_seconds=3600)
        await db.commit()

    authenticated = {"Authorization": f"Bearer {issued.raw_token}"}
    anonymous = await client.get("/v1/context")
    assert anonymous.status_code == 200
    assert anonymous.json()["mode"] == "local"
    assert anonymous.json()["organization_id"] is None

    personal_context = await client.get("/v1/context", headers=authenticated)
    assert personal_context.status_code == 200
    assert personal_context.json()["mode"] == "personal"
    assert personal_context.json()["organization_id"] == personal.id
    personal_projection = personal_context.json()["capabilities"]
    assert "organization.manage" not in personal_projection["capabilities"]
    assert all(
        personal_projection["unavailable"][capability] == "unsupported"
        for capability in (
            "assignment.assign",
            "audit.read",
            "deployment.operate",
            "invitation.manage",
            "member.manage",
            "organization.manage",
            "saml.manage",
            "team.manage",
            "telemetry.read",
        )
    )

    corporate_context = await client.get(
        "/v1/context",
        headers={**authenticated, "X-AI-STP-Organization-Id": corporate.id},
    )
    assert corporate_context.status_code == 200
    assert corporate_context.json()["mode"] == "corporate"
    assert corporate_context.json()["organization_id"] == corporate.id

    forged_remote = await client.get(
        "/v1/context",
        headers={"X-AI-STP-Organization-Id": corporate.id},
    )
    assert forged_remote.status_code == 401
    assert forged_remote.json()["error"]["code"] == "AI_STP_AUTH_REQUIRED"

    unknown_mode = await client.get("/v1/context", headers={"X-AI-STP-Product-Mode": "staging"})
    assert unknown_mode.status_code == 400
    assert unknown_mode.json()["error"]["code"] == "AI_STP_VALIDATION_ERROR"

    local_with_org = await client.get(
        "/v1/context",
        headers={
            **authenticated,
            "X-AI-STP-Product-Mode": "local",
            "X-AI-STP-Organization-Id": corporate.id,
        },
    )
    assert local_with_org.status_code == 401


async def test_organization_list_returns_only_selectable_memberships(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Any],
) -> None:
    """The corporate switcher's data source (#328): `GET /v1/organizations`.

    The list must name exactly the organizations the account may select —
    every active membership, no foreign or suspended rows — in the
    deterministic display order the UI renders, and it must not be cached.
    """
    client, sessionmaker, _settings = db_api_client
    async with sessionmaker() as db:
        account = Account(id=new_id("account"))
        personal = Organization(
            id=new_id("organization"),
            kind="personal",
            owner_account_id=account.id,
            display_name="Personal",
        )
        corporate_b = Organization(
            id=new_id("organization"),
            kind="corporate",
            owner_account_id=None,
            display_name="Beta",
        )
        corporate_a = Organization(
            id=new_id("organization"),
            kind="corporate",
            owner_account_id=None,
            display_name="Alpha",
        )
        foreign = Organization(
            id=new_id("organization"),
            kind="corporate",
            owner_account_id=None,
            display_name="Foreign",
        )
        suspended_org = Organization(
            id=new_id("organization"),
            kind="corporate",
            owner_account_id=None,
            display_name="Suspended",
            state="suspended",
        )
        suspended_membership_org = Organization(
            id=new_id("organization"),
            kind="corporate",
            owner_account_id=None,
            display_name="Retired Membership",
        )
        db.add_all(
            [
                account,
                personal,
                corporate_a,
                corporate_b,
                foreign,
                suspended_org,
                suspended_membership_org,
                OrganizationMembership(
                    organization_id=personal.id,
                    account_id=account.id,
                    role="owner",
                    state="active",
                ),
                OrganizationMembership(
                    organization_id=corporate_b.id,
                    account_id=account.id,
                    role="member",
                    state="active",
                ),
                OrganizationMembership(
                    organization_id=corporate_a.id,
                    account_id=account.id,
                    role="owner",
                    state="active",
                ),
                OrganizationMembership(
                    organization_id=suspended_org.id,
                    account_id=account.id,
                    role="owner",
                    state="active",
                ),
                OrganizationMembership(
                    organization_id=suspended_membership_org.id,
                    account_id=account.id,
                    role="member",
                    state="suspended",
                ),
            ]
        )
        issued = await issue_session(db, account_id=account.id, device_id=None, ttl_seconds=3600)
        await db.commit()

    authenticated = {"Authorization": f"Bearer {issued.raw_token}"}

    anonymous = await client.get("/v1/organizations")
    assert anonymous.status_code == 401

    response = await client.get("/v1/organizations", headers=authenticated)
    assert response.status_code == 200
    assert "no-store" in response.headers.get("cache-control", "")
    items = response.json()["items"]
    returned_ids = [item["organization_id"] for item in items]
    assert set(returned_ids) == {personal.id, corporate_a.id, corporate_b.id}
    assert foreign.id not in returned_ids
    assert suspended_org.id not in returned_ids
    assert suspended_membership_org.id not in returned_ids
    # Deterministic display order: kind, then display name, then id.
    assert returned_ids == sorted(
        returned_ids,
        key=lambda oid: (
            next(i["kind"] for i in items if i["organization_id"] == oid),
            next(i["display_name"] for i in items if i["organization_id"] == oid),
            oid,
        ),
    )
    assert [item["kind"] for item in items].count("corporate") == 2
    assert all(item["membership_revision"] >= 1 for item in items)


async def test_authenticated_account_gets_one_personal_organization_by_default(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Any],
) -> None:
    client, sessionmaker, _settings = db_api_client
    async with sessionmaker() as db:
        account = Account(id=new_id("account"))
        db.add(account)
        await db.flush()
        issued = await issue_session(db, account_id=account.id, device_id=None, ttl_seconds=3600)
        await db.commit()

    responses = await asyncio.gather(
        client.get("/v1/context", headers={"Authorization": f"Bearer {issued.raw_token}"}),
        client.get("/v1/context", headers={"Authorization": f"Bearer {issued.raw_token}"}),
    )

    assert all(response.status_code == 200 for response in responses)
    assert {response.json()["mode"] for response in responses} == {"personal"}
    organization_ids = {response.json()["organization_id"] for response in responses}
    assert len(organization_ids) == 1
    assert next(iter(organization_ids)).startswith("organization_")
    async with sessionmaker() as db:
        organizations = list(
            (
                await db.scalars(
                    select(Organization).where(
                        Organization.owner_account_id == account.id,
                        Organization.kind == "personal",
                    )
                )
            ).all()
        )
        assert len(organizations) == 1
        memberships = list(
            (
                await db.scalars(
                    select(OrganizationMembership).where(
                        OrganizationMembership.organization_id == organizations[0].id,
                    )
                )
            ).all()
        )
    assert len(memberships) == 1
    assert memberships[0].account_id == account.id
    assert memberships[0].role == "owner"
    assert memberships[0].state == "active"
