"""PostgreSQL directory/overview isolation (SPEC-083 REQ-8310/8311/8315)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.app import create_app
from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import (
    CorporateProject,
    CorporateTeam,
    Organization,
    ProjectIdentity,
)
from ai_stp_platform.technology_models import (
    ProjectTeamRelation,
    ProjectTechnologyRelation,
    Technology,
    TechnologyTeamResponsibility,
)
from ai_stp_platform.tenant_scope import set_tenant_scope

pytestmark = pytest.mark.platform


async def test_corporate_profile_routes_are_registered(
    api_client: AsyncClient,
    settings_factory: Callable[..., Settings],
) -> None:
    """Registered routes reach auth instead of falling through to 404."""
    organization_id = new_id("organization")
    team_id = new_id("operation")
    technology_id = new_id("technology")
    profile = f"/v1/corporate/organizations/{organization_id}/entity-profiles/team/{team_id}"
    upload = f"/v1/corporate/organizations/{organization_id}/profiles/team/{team_id}/media"
    owner = f"/v1/corporate/organizations/{organization_id}/technologies/{technology_id}/owner"

    responses = [
        await api_client.get(profile),
        await api_client.put(
            profile,
            json={
                "fields": {"description": "Team"},
                "expected_revision": 0,
                "authorization_revision": 1,
                "idempotency_key": str(uuid.uuid4()),
            },
        ),
        await api_client.post(
            upload,
            params={"purpose": "avatar", "expected_revision": 0, "authorization_revision": 1},
            headers={"Idempotency-Key": str(uuid.uuid4()), "Content-Type": "image/png"},
            content=b"png",
        ),
        await api_client.put(
            owner,
            json={
                "owner_account_id": None,
                "expected_revision": 0,
                "authorization_revision": 1,
                "idempotency_key": str(uuid.uuid4()),
            },
        ),
    ]
    assert [response.status_code for response in responses] == [401, 401, 401, 401]

    app = create_app(settings_factory())
    expected = {
        (
            "/v1/corporate/organizations/{organization_id}/entity-profiles/{subject_kind}/{subject_id}",
            "GET",
        ),
        (
            "/v1/corporate/organizations/{organization_id}/entity-profiles/{subject_kind}/{subject_id}",
            "PUT",
        ),
        ("/v1/corporate/organizations/{organization_id}/profiles/{kind}/{id}/media", "POST"),
        (
            "/v1/corporate/organizations/{organization_id}/technologies/{technology_id}/owner",
            "PUT",
        ),
    }
    routes: list[object] = list(app.routes)
    flattened: list[APIRoute] = []
    while routes:
        route = routes.pop()
        if isinstance(route, APIRoute):
            flattened.append(route)
            continue
        nested = getattr(route, "routes", None)
        if nested is None:
            nested = getattr(getattr(route, "original_router", None), "routes", None)
        if nested is not None:
            routes.extend(nested)
    for path, method in expected:
        assert (
            sum(
                f"/v1{route.path}" == path and route.methods is not None and method in route.methods
                for route in flattened
            )
            == 1
        )


async def test_directory_and_overview_hide_unreadable_names_and_preserve_team_lead_roster(
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

    async def bootstrap(name: str) -> str:
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

    org = await bootstrap("Directory Corp")
    foreign_org = new_id("organization")
    base = f"/v1/corporate/organizations/{org}"

    async def mutate(path: str, body: dict[str, object], tenant: str = org) -> Any:
        root = f"/v1/corporate/organizations/{tenant}"
        context = await client.get(f"{root}/context", headers=owner_auth)
        assert context.status_code == 200, context.text
        response = await client.post(
            f"{root}/{path}",
            json={
                **body,
                "authorization_revision": context.json()["organization"]["authorization_revision"],
                "idempotency_key": str(uuid.uuid4()),
            },
            headers=owner_auth,
        )
        assert response.status_code == 200, response.text
        return response.json()

    people = [
        await mutate(
            "members",
            {"display_name": name, "email": f"directory-{index}@example.com", "role": "staff"},
        )
        for index, name in enumerate(("Visible lead", "Visible staff", "Visible colleague"))
    ]
    hidden_employee = await mutate(
        "members",
        {"display_name": "Hidden local employee", "email": "hidden@example.com", "role": "staff"},
    )
    visible_team = await mutate("teams", {"name": "Z visible team"})
    hidden_team = await mutate("teams", {"name": "A hidden local team"})
    visible_project = await mutate("projects", {"name": "Z visible project"})
    hidden_project = await mutate("projects", {"name": "A hidden local project"})
    foreign_team = {"team_id": new_id("operation")}
    foreign_project = {"project_id": new_id("remote_project")}
    for index, person in enumerate(people):
        await mutate(
            "membership-assignments",
            {
                "account_id": person["account_id"],
                "team_id": visible_team["team_id"],
                "team_role": "lead" if index == 0 else "staff",
            },
        )
    await mutate(
        "membership-assignments",
        {"account_id": hidden_employee["account_id"], "team_id": hidden_team["team_id"]},
    )
    # Read-only relation authority follows the existing team-scoped policy.
    await mutate(
        "roles",
        {
            "name": "directory_reader",
            "parent_role": "lead",
            "permissions": [
                "project_team.list",
                "project_team.read",
                "technology.read",
                "technology_team.list",
                "technology_team.read",
            ],
        },
    )
    await mutate(
        "bindings",
        {
            "account_id": people[0]["account_id"],
            "role": "directory_reader",
            "scope_kind": "team",
            "scope_id": visible_team["team_id"],
        },
    )
    technology_ids = [new_id("technology") for _ in range(3)]
    async with sessionmaker() as db:
        await set_tenant_scope(db, "*")
        db.add(
            Organization(
                id=foreign_org,
                kind="corporate",
                owner_account_id=None,
                display_name="Foreign secret organization",
            )
        )
        await db.flush()
        await set_tenant_scope(db, foreign_org)
        db.add(
            ProjectIdentity(
                id=foreign_project["project_id"],
                organization_id=foreign_org,
                namespace="remote",
                external_key="directory-foreign-project",
                display_name="Foreign secret project",
                state="active",
            )
        )
        await db.flush()
        db.add_all(
            [
                CorporateProject(
                    id=foreign_project["project_id"],
                    organization_id=foreign_org,
                    name="Foreign secret project",
                    lifecycle="active",
                    state="active",
                ),
                CorporateTeam(
                    id=foreign_team["team_id"],
                    organization_id=foreign_org,
                    name="Foreign secret team",
                ),
            ]
        )
        await db.flush()
        for tenant, team, project, tech_id, name in (
            (org, visible_team, visible_project, technology_ids[0], "Visible technology"),
            (org, hidden_team, hidden_project, technology_ids[1], "Hidden local technology"),
            (
                foreign_org,
                foreign_team,
                foreign_project,
                technology_ids[2],
                "Foreign secret technology",
            ),
        ):
            await set_tenant_scope(db, tenant)
            db.add(
                Technology(
                    id=tech_id,
                    organization_id=tenant,
                    name=name,
                    lifecycle="active",
                    provenance="directory-authorization-test",
                )
            )
            await db.flush()
            db.add_all(
                [
                    ProjectTeamRelation(
                        id=new_id("operation"),
                        organization_id=tenant,
                        project_id=project["project_id"],
                        team_id=team["team_id"],
                        role="owner",
                    ),
                    TechnologyTeamResponsibility(
                        id=new_id("operation"),
                        organization_id=tenant,
                        technology_id=tech_id,
                        team_id=team["team_id"],
                    ),
                ]
            )
            await db.flush()
        # A visible project also relates to an unreadable team: its name must
        # disappear from both the card and the complete team facet universe.
        await set_tenant_scope(db, org)
        db.add(
            ProjectTechnologyRelation(
                id=new_id("operation"),
                organization_id=org,
                project_id=visible_project["project_id"],
                technology_id=technology_ids[1],
            )
        )
        db.add(
            ProjectTeamRelation(
                id=new_id("operation"),
                organization_id=org,
                project_id=visible_project["project_id"],
                team_id=hidden_team["team_id"],
                role="contributor",
            )
        )
        await db.commit()

    _, lead_auth = await token(people[0]["account_id"])
    _, staff_auth = await token(people[1]["account_id"])
    hidden_values = (
        hidden_team["team_id"],
        hidden_project["project_id"],
        hidden_employee["account_id"],
        foreign_team["team_id"],
        foreign_project["project_id"],
        foreign_org,
        *technology_ids[1:],
        "Hidden local",
        "hidden local",
        "Foreign secret",
    )
    for resource, expected_id in (
        ("teams", visible_team["team_id"]),
        ("projects", visible_project["project_id"]),
    ):
        response = await client.get(
            f"{base}/directory", params={"resource": resource, "limit": 1}, headers=lead_auth
        )
        assert response.status_code == 200, response.text
        assert all(value not in response.text for value in hidden_values)
        page = response.json()
        assert page["total"] == 1
        assert [item["id"] for item in page["items"]] == [expected_id]
        assert [ref["id"] for ref in page["facets"]["leads"]] == [people[0]["account_id"]]
        if resource == "teams":
            assert [ref["id"] for ref in page["facets"]["technologies"]] == [technology_ids[0]]
            relation_filter = {"project_ids": visible_project["project_id"]}
        else:
            assert [ref["id"] for ref in page["facets"]["teams"]] == [visible_team["team_id"]]
            relation_filter = {"team_ids": visible_team["team_id"]}
        nested = await client.get(
            f"{base}/directory",
            params={"resource": resource, **relation_filter},
            headers=lead_auth,
        )
        assert nested.status_code == 200, nested.text
        assert nested.json()["items"] == page["items"]
        assert nested.json()["total"] == page["total"] == 1
        assert nested.json()["facets"] == page["facets"]
        tail = await client.get(
            f"{base}/directory",
            params={"resource": resource, "offset": 1, "limit": 1},
            headers=lead_auth,
        )
        assert tail.status_code == 200, tail.text
        assert tail.json()["items"] == [] and tail.json()["total"] == 1
        assert tail.json()["facets"] == page["facets"]
        filtered = await client.get(
            f"{base}/directory",
            params={"resource": resource, "team_ids": hidden_team["team_id"]},
            headers=lead_auth,
        )
        assert filtered.status_code == 200, filtered.text
        assert filtered.json()["items"] == [] and filtered.json()["total"] == 0
        assert filtered.json()["facets"] == page["facets"]
        rejected = await client.get(
            f"/v1/corporate/organizations/{foreign_org}/directory",
            params={"resource": resource},
            headers=lead_auth,
        )
        assert rejected.status_code == 403, rejected.text
        assert "Foreign secret" not in rejected.text

    for headers, employees in (
        (lead_auth, {person["account_id"] for person in people}),
        (staff_auth, {person["account_id"] for person in people[:2]}),
    ):
        response = await client.get(f"{base}/overview", headers=headers)
        assert response.status_code == 200, response.text
        assert all(value not in response.text for value in hidden_values)
        graph = response.json()
        assert {node["id"] for node in graph["nodes"]} == {
            visible_team["team_id"],
            visible_project["project_id"],
            *employees,
        }
        team = next(node for node in graph["nodes"] if node["id"] == visible_team["team_id"])
        assert team["lead_account_ids"] == [people[0]["account_id"]]
        assert {
            edge["child_id"] for edge in graph["edges"] if edge["kind"] == "team_employee"
        } == employees
        assert all(
            edge["parent_id"] in {node["id"] for node in graph["nodes"]}
            and edge["child_id"] in {node["id"] for node in graph["nodes"]}
            for edge in graph["edges"]
        )
    rejected = await client.get(
        f"/v1/corporate/organizations/{foreign_org}/overview", headers=lead_auth
    )
    assert rejected.status_code == 403, rejected.text
    assert "Foreign secret" not in rejected.text
