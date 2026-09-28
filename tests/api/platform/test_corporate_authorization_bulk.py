"""Equivalence between the single-scope evaluator and the batched one.

The batch path re-implements every scope arm of `has_corporate_permission`'s
binding-match clause in memory; this test builds a fixture touching every arm —
organization, team, project, technology and member scopes, role inheritance,
wildcard bindings, inactive teams, ineligible projects and stale usage facts —
and requires the two implementations to agree on every (scope, permission)
pair, for both principal kinds.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_foundation.ids import new_id
from ai_stp_platform.corporate_authorization import (
    PrincipalType,
    bulk_effective_permissions,
    corporate_effective_permissions,
    has_corporate_permission,
)
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import (
    CorporateProject,
    CorporateRole,
    CorporateRoleBinding,
    CorporateRolePermission,
    CorporateServicePrincipal,
    CorporateTeam,
    CorporateTeamMember,
    Organization,
    OrganizationMembership,
    ProjectIdentity,
)
from ai_stp_platform.technology_models import (
    ProjectTeamRelation,
    ProjectTechnologyRelation,
    Technology,
    TechnologyTeamResponsibility,
    TechnologyUsageFact,
)

pytestmark = pytest.mark.platform

PERMISSIONS = (
    "organization.read",
    "project.read",
    "project.update",
    "team.read",
    "technology.read",
    "technology_decision.read",
    "member.read",
    "never.granted",
)


async def _seed_authorization_fixture(db: AsyncSession) -> dict[str, Any]:
    org = Organization(id=new_id("organization"), kind="corporate", display_name="Bulk Corp")
    account = Account(id=new_id("account"))
    member_account = Account(id=new_id("account"))
    outsider_account = Account(id=new_id("account"))
    db.add_all([org, account, member_account, outsider_account])
    await db.flush()
    service = CorporateServicePrincipal(
        id=new_id("service_principal"), organization_id=org.id, name="Probe"
    )
    memberships = [
        OrganizationMembership(
            organization_id=org.id,
            account_id=row.id,
            role="member",
            state="active",
        )
        for row in (account, member_account)
    ]
    db.add_all([service, *memberships])
    await db.flush()

    team_a = CorporateTeam(id=new_id("operation"), organization_id=org.id, name="Team A")
    team_b = CorporateTeam(id=new_id("operation"), organization_id=org.id, name="Team B")
    team_archived = CorporateTeam(
        id=new_id("operation"),
        organization_id=org.id,
        name="Retired",
        state="archived",
    )
    member_team = CorporateTeam(id=new_id("operation"), organization_id=org.id, name="Members")
    db.add_all([team_a, team_b, team_archived, member_team])
    await db.flush()
    db.add(
        CorporateTeamMember(
            organization_id=org.id,
            team_id=member_team.id,
            account_id=member_account.id,
            role="staff",
        )
    )

    project_eligible = CorporateProject(
        id=new_id("remote_project"), organization_id=org.id, name="Eligible"
    )
    project_ineligible = CorporateProject(
        id=new_id("remote_project"), organization_id=org.id, name="Ineligible"
    )
    db.add_all(
        [
            ProjectIdentity(
                id=project_eligible.id,
                organization_id=org.id,
                namespace="remote",
                external_key="remote-eligible",
                display_name="Eligible",
            ),
            # A remote identity that is not active makes team bindings skip
            # this project while direct project bindings still land.
            ProjectIdentity(
                id=project_ineligible.id,
                organization_id=org.id,
                namespace="remote",
                external_key="remote-ineligible",
                display_name="Ineligible",
                state="archived",
            ),
        ]
    )
    await db.flush()
    db.add_all([project_eligible, project_ineligible])
    await db.flush()
    db.add(
        ProjectTeamRelation(
            id=new_id("operation"),
            organization_id=org.id,
            project_id=project_eligible.id,
            team_id=team_a.id,
            role="contributor",
        )
    )

    technologies = {
        key: Technology(
            id=new_id("technology"),
            organization_id=org.id,
            owner_account_id=None,
            name=name,
            lifecycle=lifecycle,
            provenance="ai_stp:test:bulk",
        )
        for key, name, lifecycle in (
            ("linked", "Linked", "active"),
            ("unlinked", "Unlinked", "active"),
            ("archived", "Archived", "archived"),
        )
    }
    db.add_all(technologies.values())
    await db.flush()
    linked_relation = ProjectTechnologyRelation(
        id=new_id("operation"),
        organization_id=org.id,
        project_id=project_eligible.id,
        technology_id=technologies["linked"].id,
    )
    db.add(linked_relation)
    await db.flush()
    db.add(
        TechnologyUsageFact(
            organization_id=org.id,
            relation_id=linked_relation.id,
            context="production",
            review="confirmed",
            freshness="current",
        )
    )
    db.add(
        TechnologyTeamResponsibility(
            id=new_id("operation"),
            organization_id=org.id,
            technology_id=technologies["linked"].id,
            team_id=team_b.id,
        )
    )

    db.add_all(
        [
            CorporateRole(organization_id=org.id, name="viewer"),
            CorporateRole(organization_id=org.id, name="lead", parent_role="viewer"),
            CorporateRole(organization_id=org.id, name="principal", parent_role="lead"),
        ]
    )
    await db.flush()
    db.add_all(
        [
            CorporateRolePermission(organization_id=org.id, role=role, permission=permission)
            for role, permissions in (
                ("viewer", ("project.read", "team.read", "technology.read", "member.read")),
                ("lead", ("project.update", "technology_decision.read")),
                ("principal", ("organization.read",)),
            )
            for permission in permissions
        ]
    )

    def binding(
        principal_type: PrincipalType,
        role: str,
        scope_kind: str,
        scope_id: str,
        principal: str,
    ) -> CorporateRoleBinding:
        return CorporateRoleBinding(
            id=new_id("operation"),
            organization_id=org.id,
            principal_type=principal_type,
            account_id=principal if principal_type == "user" else None,
            service_principal_id=principal if principal_type == "service_principal" else None,
            role=role,
            scope_kind=scope_kind,
            scope_id=scope_id,
        )

    db.add_all(
        [
            # Non-superadmin organization bindings match only at org scope.
            binding("user", "viewer", "organization", org.id, account.id),
            binding("user", "lead", "team", team_a.id, account.id),
            binding("user", "viewer", "team", team_archived.id, account.id),
            binding("user", "lead", "project", project_eligible.id, account.id),
            binding("user", "viewer", "project", project_ineligible.id, account.id),
            binding("user", "viewer", "technology", "*", account.id),
            # Member scopes are reached through bindings on the member's team.
            binding("user", "viewer", "team", member_team.id, account.id),
            binding("service_principal", "lead", "team", team_b.id, service.id),
        ]
    )
    await db.commit()
    return {
        "org": org,
        "account": account,
        "member_account": member_account,
        "outsider_account": outsider_account,
        "service": service,
        "teams": (team_a, team_b, team_archived, member_team),
        "projects": (project_eligible, project_ineligible),
        "technologies": technologies,
        "scopes": {
            "organization": [org.id],
            "team": [team_a.id, team_b.id, team_archived.id, member_team.id],
            "project": [project_eligible.id, project_ineligible.id],
            "technology": [row.id for row in technologies.values()],
            "member": [member_account.id, outsider_account.id],
        },
    }


@pytest.mark.parametrize("principal_type", ["user", "service_principal"])
async def test_bulk_effective_permissions_matches_single_evaluator(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
    principal_type: PrincipalType,
) -> None:
    _client, sessionmaker, _settings = db_api_client
    async with sessionmaker() as db:
        seeded = await _seed_authorization_fixture(db)
        account: Account = seeded["account"]
        service: CorporateServicePrincipal = seeded["service"]
        org: Organization = seeded["org"]
        principal_id = account.id if principal_type == "user" else service.id
        scopes: dict[str, list[str]] = seeded["scopes"]
        for scope_kind, scope_ids in scopes.items():
            bulk = await bulk_effective_permissions(
                db,
                organization_id=org.id,
                principal_type=principal_type,
                principal_id=principal_id,
                scope_kind=scope_kind,
                scope_ids=scope_ids,
            )
            assert bulk is not None
            for scope_id in scope_ids:
                expected = {
                    permission
                    for permission in PERMISSIONS
                    if await has_corporate_permission(
                        db,
                        organization_id=org.id,
                        principal_type=principal_type,
                        principal_id=principal_id,
                        permission=permission,
                        scope_kind=scope_kind,
                        scope_id=scope_id,
                    )
                }
                assert bulk[scope_id] == expected, (
                    scope_kind,
                    scope_id,
                    bulk[scope_id],
                    expected,
                )
                single = await corporate_effective_permissions(
                    db,
                    organization_id=org.id,
                    principal_type=principal_type,
                    principal_id=principal_id,
                    scope_kind=scope_kind,
                    scope_id=scope_id,
                )
                assert single == bulk[scope_id]


async def test_bulk_effective_permissions_gate_denial(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    _client, sessionmaker, _settings = db_api_client
    async with sessionmaker() as db:
        seeded = await _seed_authorization_fixture(db)
        org: Organization = seeded["org"]
        outsider: Account = seeded["outsider_account"]
        teams: tuple[CorporateTeam, ...] = seeded["teams"]
        # An account with no active membership fails the gate in both shapes.
        assert (
            await bulk_effective_permissions(
                db,
                organization_id=org.id,
                principal_type="user",
                principal_id=outsider.id,
                scope_kind="team",
                scope_ids=[row.id for row in teams],
            )
            is None
        )
        assert not await has_corporate_permission(
            db,
            organization_id=org.id,
            principal_type="user",
            principal_id=outsider.id,
            permission="team.read",
            scope_kind="team",
            scope_id=teams[0].id,
        )
        assert (
            await corporate_effective_permissions(
                db,
                organization_id=org.id,
                principal_type="user",
                principal_id=outsider.id,
                scope_kind="team",
                scope_id=teams[0].id,
            )
            is None
        )
        # So does an organization that stops being active.
        org.state = "suspended"
        await db.flush()
        account: Account = seeded["account"]
        assert (
            await bulk_effective_permissions(
                db,
                organization_id=org.id,
                principal_type="user",
                principal_id=account.id,
                scope_kind="team",
                scope_ids=[teams[0].id],
            )
            is None
        )
        await db.rollback()
