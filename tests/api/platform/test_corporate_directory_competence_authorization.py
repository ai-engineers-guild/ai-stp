"""Directory must not bypass competence authorization for roster-visible employees."""

from __future__ import annotations

import uuid
from typing import cast

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.session import issue_session
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account
from ai_stp_platform.technology_models import (
    EmployeeTechnology,
    Technology,
    TechnologyTeamResponsibility,
)

pytestmark = pytest.mark.platform


async def test_scoped_team_lead_cannot_read_roster_member_competences(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    client, sessionmaker, _settings = db_api_client

    async def token(account_id: str | None = None) -> tuple[str, dict[str, str]]:
        async with sessionmaker() as db:
            account = await db.get(Account, account_id) if account_id else None
            if account is None:
                account = Account(id=account_id or new_id("account"), status="active")
                db.add(account)
                await db.flush()
            issued = await issue_session(
                db, account_id=account.id, device_id=None, ttl_seconds=3600
            )
            await db.commit()
            return account.id, {"Authorization": f"Bearer {issued.raw_token}"}

    owner_id, owner_auth = await token()
    bootstrap = await client.post(
        "/v1/corporate/bootstrap",
        json={
            "organization_name": "Competence isolation",
            "superadmin_account_id": owner_id,
            "idempotency_key": str(uuid.uuid4()),
        },
        headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
    )
    assert bootstrap.status_code == 200, bootstrap.text
    organization_id = bootstrap.json()["organization_id"]
    base = f"/v1/corporate/organizations/{organization_id}"

    async def mutate(path: str, payload: dict[str, object]) -> dict[str, object]:
        context = await client.get(f"{base}/context", headers=owner_auth)
        assert context.status_code == 200, context.text
        response = await client.post(
            f"{base}/{path}",
            json={
                **payload,
                "authorization_revision": context.json()["organization"]["authorization_revision"],
                "idempotency_key": str(uuid.uuid4()),
            },
            headers=owner_auth,
        )
        assert response.status_code == 200, response.text
        return response.json()

    lead = await mutate(
        "members",
        {"display_name": "Scoped lead", "email": "scoped-lead@example.com", "role": "staff"},
    )
    employee = await mutate(
        "members",
        {
            "display_name": "Private competence subject",
            "email": "private-competence@example.com",
            "role": "staff",
        },
    )
    team = await mutate("teams", {"name": "Scoped team"})
    lead_id = cast(str, lead["account_id"])
    employee_id = cast(str, employee["account_id"])
    team_id = cast(str, team["team_id"])
    await mutate(
        "membership-assignments",
        {"account_id": lead_id, "team_id": team_id, "team_role": "lead"},
    )
    await mutate(
        "membership-assignments",
        {"account_id": employee_id, "team_id": team_id},
    )
    await mutate(
        "roles",
        {
            "name": "scoped_technology_reader",
            "parent_role": "lead",
            "permissions": ["technology.read", "technology.list"],
        },
    )
    await mutate(
        "bindings",
        {
            "account_id": lead_id,
            "role": "scoped_technology_reader",
            "scope_kind": "team",
            "scope_id": team_id,
        },
    )

    technology_id = new_id("technology")
    async with sessionmaker() as db:
        db.add(
            Technology(
                id=technology_id,
                organization_id=organization_id,
                name="Private competence",
                lifecycle="active",
                provenance="directory-competence-authorization-test",
            )
        )
        await db.flush()
        db.add(
            TechnologyTeamResponsibility(
                id=new_id("relation"),
                organization_id=organization_id,
                technology_id=technology_id,
                team_id=team_id,
            )
        )
        db.add(
            EmployeeTechnology(
                id=new_id("relation"),
                organization_id=organization_id,
                account_id=employee_id,
                technology_id=technology_id,
                state="current",
                revision=1,
            )
        )
        await db.commit()

    _, lead_auth = await token(lead_id)
    response = await client.get(
        f"{base}/directory", params={"resource": "members"}, headers=lead_auth
    )
    assert response.status_code == 200, response.text
    item = next(row for row in response.json()["items"] if row["id"] == employee_id)
    assert item["name"] == "Private competence subject"
    assert item["technologies"] == []


async def test_profile_omits_suspended_technology_owner(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    client, sessionmaker, _settings = db_api_client

    async def token(account_id: str | None = None) -> tuple[str, dict[str, str]]:
        async with sessionmaker() as db:
            account = await db.get(Account, account_id) if account_id else None
            if account is None:
                account = Account(id=account_id or new_id("account"), status="active")
                db.add(account)
                await db.flush()
            issued = await issue_session(
                db, account_id=account.id, device_id=None, ttl_seconds=3600
            )
            await db.commit()
            return account.id, {"Authorization": f"Bearer {issued.raw_token}"}

    admin_id, admin_auth = await token()
    bootstrap = await client.post(
        "/v1/corporate/bootstrap",
        json={
            "organization_name": "Owner visibility isolation",
            "superadmin_account_id": admin_id,
            "idempotency_key": str(uuid.uuid4()),
        },
        headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
    )
    assert bootstrap.status_code == 200, bootstrap.text
    organization_id = bootstrap.json()["organization_id"]
    base = f"/v1/corporate/organizations/{organization_id}"
    context = await client.get(f"{base}/context", headers=admin_auth)
    member = await client.post(
        f"{base}/members",
        json={
            "display_name": "Soon suspended owner",
            "email": "suspended-owner@example.com",
            "role": "staff",
            "authorization_revision": context.json()["organization"]["authorization_revision"],
            "idempotency_key": str(uuid.uuid4()),
        },
        headers=admin_auth,
    )
    assert member.status_code == 200, member.text
    owner_id = cast(str, member.json()["account_id"])
    technology_id = new_id("technology")
    async with sessionmaker() as db:
        db.add(
            Technology(
                id=technology_id,
                organization_id=organization_id,
                owner_account_id=owner_id,
                name="Owned technology",
                lifecycle="active",
                provenance="owner-visibility-authorization-test",
            )
        )
        await db.commit()

    context = await client.get(f"{base}/context", headers=admin_auth)
    suspend = await client.patch(
        f"{base}/members/{owner_id}",
        json={
            "role": "staff",
            "state": "suspended",
            "expected_revision": 1,
            "authorization_revision": context.json()["organization"]["authorization_revision"],
            "idempotency_key": str(uuid.uuid4()),
        },
        headers=admin_auth,
    )
    assert suspend.status_code == 200, suspend.text

    profile = await client.get(
        f"{base}/entity-profiles/technology/{technology_id}", headers=admin_auth
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["owner_account_id"] is None
