"""The manual HTTP path does not require a detector or repository scan."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.session import issue_session
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account

pytestmark = pytest.mark.platform


async def test_manual_technology_http_path(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    client, sessionmaker, _ = db_api_client
    account = new_id("account")
    async with sessionmaker() as db:
        db.add(Account(id=account, status="active"))
        await db.flush()
        session = await issue_session(db, account_id=account, device_id=None, ttl_seconds=3600)
        await db.commit()
    auth = {"Authorization": f"Bearer {session.raw_token}"}
    bootstrap = await client.post(
        "/v1/corporate/bootstrap",
        json={
            "organization_name": "Manual HTTP acceptance",
            "superadmin_account_id": account,
            "idempotency_key": "technology-http-bootstrap-0001",
        },
        headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
    )
    assert bootstrap.status_code == 200, bootstrap.text
    organization_id = bootstrap.json()["organization_id"]
    base = f"/v1/corporate/organizations/{organization_id}"
    category, technology = new_id("category"), new_id("technology")
    categories = await client.put(
        f"{base}/technology-categories/{category}",
        headers=auth,
        json={
            "metadata": {"name": "Runtime"},
            "expected_revision": 0,
            "authorization_revision": 1,
            "idempotency_key": "technology-http-category-0001",
        },
    )
    assert categories.status_code == 200, categories.text
    create = await client.put(
        f"{base}/technologies/{technology}",
        headers=auth,
        json={
            "metadata": {"name": "Bun", "category_ids": [category], "aliases": ["Bun runtime"]},
            "expected_revision": 0,
            "authorization_revision": 2,
            "idempotency_key": "technology-http-create-0001",
        },
    )
    assert create.status_code == 200, create.text
    assert create.json()["technology_id"] == technology
    approve = await client.patch(
        f"{base}/technologies/{technology}/lifecycle",
        headers=auth,
        json={
            "lifecycle": "active",
            "expected_revision": 1,
            "authorization_revision": 3,
            "idempotency_key": "technology-http-approve-0001",
        },
    )
    assert approve.status_code == 200, approve.text
    project = await client.post(
        f"{base}/projects",
        headers=auth,
        json={
            "name": "Manual HTTP project",
            "authorization_revision": 4,
            "idempotency_key": "technology-http-project-0001",
        },
    )
    assert project.status_code == 200, project.text
    project_id = project.json()["project_id"]
    payload = {
        "technology_id": technology,
        "fact": {"context": "production"},
        "expected_revision": 0,
        "authorization_revision": 5,
        "idempotency_key": "technology-http-usage-0001",
    }
    usage = await client.put(
        f"{base}/projects/{project_id}/technologies", headers=auth, json=payload
    )
    assert usage.status_code == 200, usage.text
    assert usage.json()["facts"][0]["review"] == "confirmed"
    replay = await client.put(
        f"{base}/projects/{project_id}/technologies", headers=auth, json=payload
    )
    assert replay.status_code == 200, replay.text
    assert replay.json() == usage.json()
    listed = await client.get(f"{base}/technologies", headers=auth)
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1
    foreign = await client.get(
        f"/v1/corporate/organizations/{new_id('organization')}/technologies/{technology}",
        headers=auth,
    )
    assert foreign.status_code == 403, foreign.text
    teams: list[str] = []
    for revision, name in ((6, "Owning team"), (7, "Replacement team")):
        team = await client.post(
            f"{base}/teams",
            headers=auth,
            json={
                "name": name,
                "authorization_revision": revision,
                "idempotency_key": f"technology-http-team-{revision}",
            },
        )
        assert team.status_code == 200, team.text
        teams.append(team.json()["team_id"])
    owner_payload = {
        "team_id": teams[0],
        "role": "owner",
        "expected_revision": 0,
        "authorization_revision": 8,
        "idempotency_key": "technology-http-owner-0001",
    }
    owner = await client.put(
        f"{base}/projects/{project_id}/teams", headers=auth, json=owner_payload
    )
    assert owner.status_code == 200, owner.text
    conflicting = await client.put(
        f"{base}/projects/{project_id}/teams",
        headers=auth,
        json={
            **owner_payload,
            "team_id": teams[1],
            "authorization_revision": 9,
            "idempotency_key": "technology-http-owner-conflict-0001",
        },
    )
    assert conflicting.status_code == 409, conflicting.text
    replacement_payload = {
        **owner_payload,
        "team_id": teams[1],
        "authorization_revision": 9,
        "idempotency_key": "technology-http-owner-replace-0001",
        "replace_owner_relation_id": owner.json()["relation_id"],
        "replace_owner_expected_revision": 1,
    }
    replacement = await client.put(
        f"{base}/projects/{project_id}/teams", headers=auth, json=replacement_payload
    )
    assert replacement.status_code == 200, replacement.text
    repeated = await client.put(
        f"{base}/projects/{project_id}/teams", headers=auth, json=replacement_payload
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json() == replacement.json()
    for policy_revision, entity_revision, state in ((10, 1, "retired"), (11, 2, "current")):
        changed = await client.put(
            f"{base}/projects/{project_id}/teams",
            headers=auth,
            json={
                "team_id": teams[1],
                "role": "owner",
                "state": state,
                "authorization_revision": policy_revision,
                "expected_revision": entity_revision,
                "idempotency_key": f"technology-http-owner-{state}",
            },
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["relation_id"] == replacement.json()["relation_id"]
    responsibility = await client.put(
        f"{base}/technologies/{technology}/responsible-teams",
        headers=auth,
        json={
            "team_id": teams[1],
            "expected_revision": 0,
            "authorization_revision": 12,
            "idempotency_key": "technology-http-responsibility-0001",
        },
    )
    assert responsibility.status_code == 200, responsibility.text
    decision = await client.put(
        f"{base}/technologies/{technology}/decision",
        headers=auth,
        json={
            "lead_account_id": account,
            "approved": False,
            "adoption": "trial",
            "expected_revision": 0,
            "authorization_revision": 13,
            "idempotency_key": "technology-http-decision-0001",
        },
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["technology_id"] == technology
    read = await client.get(f"{base}/technologies/{technology}", headers=auth)
    assert read.status_code == 200, read.text
    assert read.json()["lifecycle"] == "active"
    for forward, reverse in (
        (f"{base}/projects/{project_id}/teams", f"{base}/teams/{teams[1]}/projects"),
        (
            f"{base}/technologies/{technology}/responsible-teams",
            f"{base}/teams/{teams[1]}/technologies",
        ),
        (
            f"{base}/projects/{project_id}/technologies",
            f"{base}/technologies/{technology}/projects",
        ),
    ):
        first = await client.get(forward, headers=auth)
        back = await client.get(reverse, headers=auth)
        assert first.status_code == 200, first.text
        assert back.status_code == 200, back.text
        assert first.json() == back.json()
        assert first.json()["total"] == 1
        page = await client.get(forward, headers=auth, params={"offset": 1, "limit": 1})
        assert page.status_code == 200, page.text
        assert page.json()["items"] == []
        assert page.json()["total"] == 1
    previous_owner = await client.get(f"{base}/teams/{teams[0]}/projects", headers=auth)
    assert previous_owner.status_code == 200, previous_owner.text
    assert previous_owner.json()["items"] == []
    history = await client.get(
        f"{base}/teams/{teams[0]}/projects", headers=auth, params={"include_history": "true"}
    )
    assert history.status_code == 200, history.text
    assert history.json()["items"][0]["relation_id"] == owner.json()["relation_id"]
    assert history.json()["items"][0]["state"] == "retired"
    decision_read = await client.get(f"{base}/technologies/{technology}/decision", headers=auth)
    assert decision_read.status_code == 200, decision_read.text
    assert decision_read.json() == decision.json()
