"""Current canonical links expand explicit grants, never responsibility labels."""

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate.service import bootstrap, update_project
from ai_stp_api.slices.technology.service import (
    write_project_team,
    write_project_technology,
    write_technology_team,
)
from ai_stp_contracts.corporate import CorporateBootstrapRequest, CorporateProjectUpdateRequest
from ai_stp_contracts.technology import (
    ProjectTeamWriteRequest,
    ProjectTechnologyWriteRequest,
    TechnologyTeamWriteRequest,
)
from ai_stp_foundation.ids import new_id
from ai_stp_platform.corporate_authorization import has_corporate_permission
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import (
    CorporateProject,
    CorporateRole,
    CorporateRoleBinding,
    CorporateRolePermission,
    CorporateTeam,
    OrganizationMembership,
    ProjectIdentity,
)
from ai_stp_platform.technology_models import (
    OrganizationTechnologyDecision,
    ProjectTeamRelation,
    ProjectTechnologyRelation,
    Technology,
    TechnologyTeamResponsibility,
    TechnologyUsageFact,
)


async def test_link_changes_revoke_expanded_scopes_without_snapshots(
    db_session: AsyncSession,
) -> None:
    owner, viewer = new_id("account"), new_id("account")
    db_session.add_all([Account(id=value, status="active") for value in (owner, viewer)])
    await db_session.flush()
    ctx = AuthContext(owner, "scope-test", None, "active", False, False)
    org = (
        await bootstrap(
            db_session,
            payload=CorporateBootstrapRequest(
                organization_name="Current scopes",
                superadmin_account_id=owner,
                idempotency_key="scope-bootstrap-0001",
            ),
            request_id="scope-test",
        )
    ).organization_id
    project, tech, team = new_id("remote_project"), new_id("technology"), new_id("operation")
    db_session.add_all(
        [
            OrganizationMembership(organization_id=org, account_id=viewer, role="viewer"),
            CorporateRole(organization_id=org, name="viewer"),
            ProjectIdentity(
                id=project,
                organization_id=org,
                namespace="remote",
                external_key=f"corporate:{project}",
                display_name="Scoped project",
            ),
            CorporateTeam(id=team, organization_id=org, name="Scoped team"),
            Technology(
                id=tech, organization_id=org, name="Bun", lifecycle="active", provenance="manual"
            ),
        ]
    )
    await db_session.flush()
    db_session.add(CorporateProject(id=project, organization_id=org, name="Scoped project"))
    db_session.add_all(
        [
            CorporateRolePermission(organization_id=org, role="viewer", permission=value)
            for value in ("project.read", "technology.read")
        ]
    )
    await db_session.flush()
    usage = new_id("relation")
    db_session.add_all(
        [
            ProjectTeamRelation(
                organization_id=org,
                id=new_id("relation"),
                project_id=project,
                team_id=team,
                role="owner",
            ),
            ProjectTechnologyRelation(
                organization_id=org, id=usage, project_id=project, technology_id=tech
            ),
            TechnologyTeamResponsibility(
                organization_id=org, id=new_id("relation"), technology_id=tech, team_id=team
            ),
            OrganizationTechnologyDecision(
                organization_id=org, technology_id=tech, lead_account_id=viewer
            ),
        ]
    )
    await db_session.flush()
    db_session.add(
        TechnologyUsageFact(
            organization_id=org,
            relation_id=usage,
            context="production",
            review="confirmed",
            freshness="current",
        )
    )
    await db_session.flush()

    async def allowed(kind: str, target: str) -> bool:
        return await has_corporate_permission(
            db_session,
            organization_id=org,
            principal_type="user",
            principal_id=viewer,
            permission=f"{kind}.read",
            scope_kind=kind,
            scope_id=target,
        )

    assert not await allowed("project", project)
    assert not await allowed("technology", tech)
    db_session.add(
        CorporateRoleBinding(
            id=new_id("operation"),
            organization_id=org,
            account_id=viewer,
            role="viewer",
            scope_kind="team",
            scope_id=team,
        )
    )
    await db_session.flush()
    assert await allowed("project", project)
    assert await allowed("technology", tech)
    await write_project_team(
        db_session,
        ctx=ctx,
        organization_id=org,
        project_id=project,
        payload=ProjectTeamWriteRequest(
            team_id=team,
            role="owner",
            state="retired",
            expected_revision=1,
            authorization_revision=1,
            idempotency_key="scope-retire-team-0001",
        ),
        request_id="scope-test",
    )
    assert not await allowed("project", project)
    assert await allowed("technology", tech)
    await write_technology_team(
        db_session,
        ctx=ctx,
        organization_id=org,
        technology_id=tech,
        payload=TechnologyTeamWriteRequest(
            team_id=team,
            state="retired",
            expected_revision=1,
            authorization_revision=2,
            idempotency_key="scope-retire-responsibility-0001",
        ),
        request_id="scope-test",
    )
    assert not await allowed("technology", tech)
    await write_project_team(
        db_session,
        ctx=ctx,
        organization_id=org,
        project_id=project,
        payload=ProjectTeamWriteRequest(
            team_id=team,
            role="owner",
            expected_revision=2,
            authorization_revision=3,
            idempotency_key="scope-restore-team-0001",
        ),
        request_id="scope-test",
    )
    assert await allowed("technology", tech)
    await write_project_technology(
        db_session,
        ctx=ctx,
        organization_id=org,
        project_id=project,
        payload=ProjectTechnologyWriteRequest.model_validate(
            {
                "technology_id": tech,
                "state": "retired",
                "fact": {"context": "production"},
                "expected_revision": 1,
                "authorization_revision": 4,
                "idempotency_key": "scope-retire-usage-0001",
            }
        ),
        request_id="scope-test",
    )
    assert not await allowed("technology", tech)
    assert await allowed("project", project)
    await update_project(
        db_session,
        ctx=ctx,
        organization_id=org,
        project_id=project,
        payload=CorporateProjectUpdateRequest(
            name="Scoped project",
            state="archived",
            expected_revision=1,
            authorization_revision=5,
            idempotency_key="scope-archive-project-0001",
        ),
        request_id="scope-test",
    )
    assert not await allowed("project", project)
