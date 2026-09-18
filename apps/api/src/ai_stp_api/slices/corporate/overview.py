"""Authorized normalized workspace graph; repeated display nodes create no data."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import assignments, service
from ai_stp_contracts.corporate import (
    CorporateCatalogAssignmentQuery,
    CorporateOverview,
    CorporateOverviewEdge,
    CorporateOverviewNode,
)
from ai_stp_platform.corporate_authorization import has_corporate_permission
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import (
    CorporateProject,
    CorporateTeam,
    CorporateTeamMember,
    OrganizationMembership,
    ProjectIdentity,
)
from ai_stp_platform.technology_models import ProjectTeamRelation


async def read_overview(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    request_id: str | None,
    include_assignments: bool = True,
) -> CorporateOverview:
    organization, _ = await service.authorize(
        db, ctx=ctx, organization_id=organization_id, permission="organization.read"
    )

    async def permitted(
        permission: str, kind: str = "organization", identity: str | None = None
    ) -> bool:
        return await has_corporate_permission(
            db,
            organization_id=organization_id,
            principal_type="user",
            principal_id=ctx.account_id,
            permission=permission,
            scope_kind=kind,
            scope_id=identity,
        )

    nodes: dict[str, CorporateOverviewNode] = {}
    edges: list[CorporateOverviewEdge] = []
    projects = (
        await db.scalars(
            select(CorporateProject)
            .join(
                ProjectIdentity,
                (ProjectIdentity.organization_id == CorporateProject.organization_id)
                & (ProjectIdentity.id == CorporateProject.id),
            )
            .where(
                CorporateProject.organization_id == organization_id,
                CorporateProject.state == "active",
                ProjectIdentity.state == "active",
            )
            .order_by(CorporateProject.name, CorporateProject.id)
        )
    ).all()
    # ponytail: per-anchor queries; batch authorization if graph latency becomes material.
    for project in projects:
        if await permitted("project.read", "project", project.id):
            nodes[project.id] = CorporateOverviewNode(
                kind="project", id=project.id, name=project.name
            )
    teams = (
        await db.scalars(
            select(CorporateTeam)
            .where(
                CorporateTeam.organization_id == organization_id, CorporateTeam.state == "active"
            )
            .order_by(CorporateTeam.name, CorporateTeam.id)
        )
    ).all()
    member_read = await permitted("member.read")
    for team in teams:
        if not await permitted("team.read", "team", team.id):
            continue
        leads = await service.team_lead_ids(db, team)
        node = CorporateOverviewNode(kind="team", id=team.id, name=team.name)
        nodes[team.id] = node
        can_list = (
            member_read
            or ctx.account_id in leads
            or await permitted("member.list", "team", team.id)
        )
        display_leads = set(leads)
        if member_read:
            display_leads.update(
                (
                    await db.scalars(
                        select(CorporateTeamMember.account_id).where(
                            CorporateTeamMember.organization_id == organization_id,
                            CorporateTeamMember.team_id == team.id,
                            CorporateTeamMember.role == "lead",
                        )
                    )
                ).all()
            )
        pairs = (
            await db.execute(
                select(OrganizationMembership, Account)
                .join(Account, Account.id == OrganizationMembership.account_id)
                .where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.state == "active",
                    OrganizationMembership.account_id.in_(
                        select(CorporateTeamMember.account_id).where(
                            CorporateTeamMember.organization_id == organization_id,
                            CorporateTeamMember.team_id == team.id,
                        )
                    )
                    | OrganizationMembership.account_id.in_(leads),
                )
                .order_by(Account.id)
            )
        ).all()
        for member, account in pairs:
            if not can_list and member.account_id not in {ctx.account_id, *leads}:
                continue
            employee = service.member_view(member, account)
            nodes[member.account_id] = CorporateOverviewNode(
                kind="employee", id=member.account_id, name=employee.display_name or ""
            )
            is_lead = member.account_id in display_leads
            if is_lead:
                node.lead_account_ids.append(member.account_id)
            edges.append(
                CorporateOverviewEdge(
                    parent_id=team.id,
                    child_id=member.account_id,
                    kind="team_employee",
                    role="lead" if is_lead else "staff",
                )
            )
    if member_read:
        pairs = (
            await db.execute(
                select(OrganizationMembership, Account)
                .join(Account, Account.id == OrganizationMembership.account_id)
                .where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.state == "active",
                )
                .order_by(Account.id)
            )
        ).all()
        for member, account in pairs:
            if member.account_id not in nodes:
                view = service.member_view(member, account)
                nodes[member.account_id] = CorporateOverviewNode(
                    kind="employee", id=member.account_id, name=view.display_name or ""
                )
    relations = (
        await db.scalars(
            select(ProjectTeamRelation)
            .where(
                ProjectTeamRelation.organization_id == organization_id,
                ProjectTeamRelation.state == "current",
            )
            .order_by(ProjectTeamRelation.project_id, ProjectTeamRelation.team_id)
        )
    ).all()
    for relation in relations:
        if (
            relation.project_id in nodes
            and relation.team_id in nodes
            and await permitted("project_team.list", "project", relation.project_id)
            and await permitted("project_team.read", "project", relation.project_id)
        ):
            edges.append(
                CorporateOverviewEdge.model_validate(
                    {
                        "parent_id": relation.project_id,
                        "child_id": relation.team_id,
                        "kind": "project_team",
                        "role": relation.role,
                    }
                )
            )
    for node in nodes.values() if include_assignments else ():
        if node.kind == "employee" and not member_read:
            continue
        offset = 0
        while True:
            page = await assignments.list_assignments(
                db,
                ctx=ctx,
                organization_id=organization_id,
                query=CorporateCatalogAssignmentQuery(
                    subject_kind=node.kind, subject_id=node.id, offset=offset, limit=256
                ),
                request_id=request_id,
            )
            node.assignments.extend(page.items)
            offset += len(page.items)
            if offset >= page.total or not page.items:
                break
        nodes[node.id] = node.model_copy(update={"assignments_readable": True})
    return CorporateOverview(
        organization=service.organization_view(organization),
        nodes=list(nodes.values()),
        edges=edges,
    )
