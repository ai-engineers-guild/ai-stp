"""Directory discovery filters every named anchor before facets and pagination."""

from collections.abc import Sequence
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import overview
from ai_stp_contracts.corporate_directory import (
    CorporateDirectoryFacets,
    CorporateDirectoryItem,
    CorporateDirectoryQuery,
    CorporateDirectoryReference,
    CorporateDirectoryView,
)
from ai_stp_platform.corporate_authorization import has_corporate_permission
from ai_stp_platform.organization_models import (
    CorporateJobTitle,
    CorporateProject,
    CorporateRoleBinding,
    CorporateTeam,
    OrganizationMembership,
    ProjectIdentity,
)
from ai_stp_platform.technology_models import (
    EmployeeTechnology,
    ProjectTechnologyRelation,
    Technology,
    TechnologyCategory,
    TechnologyClassification,
    TechnologyTeamResponsibility,
)


def select_directory(
    organization: CorporateDirectoryView,
    query: CorporateDirectoryQuery,
) -> CorporateDirectoryView:
    """OR within each selected facet, AND across facets; paginate last."""

    def matches(item: CorporateDirectoryItem) -> bool:
        teams = item.related_teams if query.resource == "teams" else item.teams
        return (
            (
                not query.query
                or query.query.casefold() in f"{item.name} {item.description}".casefold()
            )
            and (not query.lead_ids or any(ref.id in query.lead_ids for ref in item.leads))
            and (not query.team_ids or any(ref.id in query.team_ids for ref in teams))
            and (
                not query.technology_ids
                or any(ref.id in query.technology_ids for ref in item.technologies)
            )
            and (not query.project_ids or any(ref.id in query.project_ids for ref in item.projects))
            and (
                not query.category_ids
                or any(ref.id in query.category_ids for ref in item.categories)
            )
            and (
                not query.job_title_ids
                or (item.job_title is not None and item.job_title.id in query.job_title_ids)
            )
            and (query.is_lead is None or item.is_lead == query.is_lead)
        )

    items = [item for item in organization.items if matches(item)]
    items.sort(
        key=lambda item: (item.name.casefold(), item.id),
        reverse=query.sort == "name_desc",
    )
    return organization.model_copy(
        update={"items": items[query.offset : query.offset + query.limit], "total": len(items)}
    )


async def read_directory(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    query: CorporateDirectoryQuery,
    request_id: str | None,
) -> CorporateDirectoryView:
    requested_resource = query.resource
    if query.resource == "employees":
        query = query.model_copy(update={"resource": "members"})
    graph = await overview.read_overview(
        db,
        ctx=ctx,
        organization_id=organization_id,
        request_id=request_id,
        include_assignments=False,
    )
    nodes = {
        node.id: CorporateDirectoryReference(kind=node.kind, id=node.id, name=node.name)
        for node in graph.nodes
    }
    permission_cache: dict[tuple[str, str, str], bool] = {}

    async def permitted(permission: str, kind: str, identity: str) -> bool:
        key = (permission, kind, identity)
        if key not in permission_cache:
            permission_cache[key] = await has_corporate_permission(
                db,
                organization_id=organization_id,
                principal_type="user",
                principal_id=ctx.account_id,
                permission=permission,
                scope_kind=kind,
                scope_id=identity,
            )
        return permission_cache[key]

    async def available_actions(
        kind: str, identity: str, *, scope_kind: str | None = None
    ) -> list[str]:
        scope = scope_kind or kind
        scope_id = organization_id if scope == "organization" else identity
        return [
            action
            for action, permission in (
                (f"{kind}.update", f"{kind}.update"),
                (f"{kind}.delete", f"{kind}.delete"),
            )
            if await permitted(permission, scope, scope_id)
        ]

    technologies = (
        await db.scalars(
            select(Technology).where(
                Technology.organization_id == organization_id,
                *([] if query.resource == "technologies" else [Technology.lifecycle != "archived"]),
                Technology.redirect_id.is_(None),
            )
        )
    ).all()
    for technology in technologies:
        if await permitted("technology.read", "technology", technology.id):
            nodes[technology.id] = CorporateDirectoryReference(
                kind="technology", id=technology.id, name=technology.name
            )
    usages = (
        await db.scalars(
            select(ProjectTechnologyRelation).where(
                ProjectTechnologyRelation.organization_id == organization_id,
                ProjectTechnologyRelation.state == "current",
            )
        )
    ).all()
    project_technologies: dict[str, set[str]] = {}
    for usage in usages:
        if (
            usage.project_id in nodes
            and usage.technology_id in nodes
            and await permitted("project_technology.list", "project", usage.project_id)
            and await permitted("project_technology.read", "project", usage.project_id)
        ):
            project_technologies.setdefault(usage.project_id, set()).add(usage.technology_id)
    responsibilities = (
        await db.scalars(
            select(TechnologyTeamResponsibility).where(
                TechnologyTeamResponsibility.organization_id == organization_id,
                TechnologyTeamResponsibility.state == "current",
            )
        )
    ).all()
    team_technologies: dict[str, set[str]] = {}
    for relation in responsibilities:
        if (
            relation.team_id in nodes
            and relation.technology_id in nodes
            and await permitted("technology_team.list", "technology", relation.technology_id)
            and await permitted("technology_team.read", "technology", relation.technology_id)
        ):
            team_technologies.setdefault(relation.team_id, set()).add(relation.technology_id)
    project_teams: dict[str, set[str]] = {}
    team_projects: dict[str, set[str]] = {}
    owners: dict[str, str] = {}
    for edge in graph.edges:
        if edge.kind != "project_team":
            continue
        project_teams.setdefault(edge.parent_id, set()).add(edge.child_id)
        team_projects.setdefault(edge.child_id, set()).add(edge.parent_id)
        if edge.role == "owner":
            owners[edge.parent_id] = edge.child_id
        team_technologies.setdefault(edge.child_id, set()).update(
            project_technologies.get(edge.parent_id, set())
        )
    leads = {node.id: set(node.lead_account_ids) for node in graph.nodes if node.kind == "team"}

    def references(identities: set[str]) -> list[CorporateDirectoryReference]:
        return sorted(
            (nodes[identity] for identity in identities if identity in nodes),
            key=lambda ref: (ref.name.casefold(), ref.id),
        )

    if query.resource in {"members", "technologies"}:
        employee_teams: dict[str, set[str]] = {}
        for edge in graph.edges:
            if edge.kind == "team_employee":
                employee_teams.setdefault(edge.child_id, set()).add(edge.parent_id)
        extended: list[CorporateDirectoryItem] = []
        job_title_refs: dict[str, CorporateDirectoryReference] = {}
        if query.resource == "members":
            member_read = await permitted("member.read", "organization", organization_id)
            competences: Sequence[EmployeeTechnology] = []
            if member_read:
                competences = (
                    await db.scalars(
                        select(EmployeeTechnology).where(
                            EmployeeTechnology.organization_id == organization_id,
                            EmployeeTechnology.state == "current",
                        )
                    )
                ).all()
            members = (
                await db.scalars(
                    select(OrganizationMembership).where(
                        OrganizationMembership.organization_id == organization_id,
                    )
                )
            ).all()
            job_title_ids = {
                getattr(member, "job_title_id", None)
                for member in members
                if getattr(member, "job_title_id", None)
            }
            if job_title_ids:
                job_titles = (
                    await db.scalars(
                        select(CorporateJobTitle).where(
                            CorporateJobTitle.organization_id == organization_id,
                            CorporateJobTitle.id.in_(job_title_ids),
                        )
                    )
                ).all()
                job_title_refs = {
                    row.id: CorporateDirectoryReference(kind="job_title", id=row.id, name=row.name)
                    for row in job_titles
                }
            for member in members:
                # The overview applies incumbent member/roster visibility, including team leads.
                if member.account_id not in nodes:
                    continue
                member_teams = employee_teams.get(member.account_id, set())
                extended.append(
                    CorporateDirectoryItem(
                        kind="employee",
                        id=member.account_id,
                        name=nodes[member.account_id].name,
                        revision=member.revision,
                        role=member.role,
                        description=str(
                            cast(dict[str, object], getattr(member, "profile", None) or {}).get(
                                "description", ""
                            )
                        ),
                        teams=references(member_teams),
                        projects=references(
                            {
                                project
                                for team in member_teams
                                for project in team_projects.get(team, set())
                            }
                        ),
                        technologies=references(
                            {
                                relation.technology_id
                                for relation in competences
                                if relation.account_id == member.account_id
                                and relation.technology_id in nodes
                            }
                        ),
                        job_title=job_title_refs.get(getattr(member, "job_title_id", None) or ""),
                        available_actions=await available_actions(
                            "member", member.account_id, scope_kind="organization"
                        ),
                        is_lead=any(member.account_id in ids for ids in leads.values()),
                    )
                )
        else:
            categories = (
                await db.scalars(
                    select(TechnologyCategory).where(
                        TechnologyCategory.organization_id == organization_id,
                        TechnologyCategory.state == "active",
                    )
                )
            ).all()
            for category in categories:
                if await permitted("category.read", "organization", organization_id):
                    nodes[category.id] = CorporateDirectoryReference(
                        kind="category", id=category.id, name=category.name
                    )
            classifications = (
                await db.scalars(
                    select(TechnologyClassification).where(
                        TechnologyClassification.organization_id == organization_id,
                    )
                )
            ).all()
            for technology in technologies:
                if not query.include_archived and technology.lifecycle == "archived":
                    continue
                if technology.id not in nodes or not await permitted(
                    "technology.list", "technology", technology.id
                ):
                    continue
                tech_projects = {
                    project for project, ids in project_technologies.items() if technology.id in ids
                }
                tech_teams = {
                    team for team, ids in team_technologies.items() if technology.id in ids
                }
                extended.append(
                    CorporateDirectoryItem(
                        kind="technology",
                        id=technology.id,
                        name=technology.name,
                        revision=technology.revision,
                        description=technology.description or "",
                        owner=nodes.get(technology.owner_account_id or ""),
                        projects=references(tech_projects),
                        teams=references(tech_teams),
                        categories=references(
                            {
                                relation.category_id
                                for relation in classifications
                                if relation.technology_id == technology.id
                            }
                        ),
                        available_actions=await available_actions("technology", technology.id),
                    )
                )
        extended.sort(key=lambda item: (item.name.casefold(), item.id))

        def extended_facet(field: str) -> list[CorporateDirectoryReference]:
            refs = {ref.id: ref for item in extended for ref in getattr(item, field)}
            return sorted(refs.values(), key=lambda ref: (ref.name.casefold(), ref.id))

        return select_directory(
            CorporateDirectoryView(
                organization=graph.organization,
                resource=query.resource,
                items=extended,
                total=len(extended),
                facets=CorporateDirectoryFacets(
                    leads=[],
                    teams=extended_facet("teams"),
                    technologies=extended_facet("technologies"),
                    projects=extended_facet("projects"),
                    categories=extended_facet("categories"),
                    job_titles=sorted(
                        job_title_refs.values(), key=lambda ref: (ref.name.casefold(), ref.id)
                    ),
                ),
            ),
            query,
        ).model_copy(update={"resource": requested_resource})

    project_leads: dict[str, set[str]] = {}
    if query.resource == "projects":
        bindings = (
            await db.scalars(
                select(CorporateRoleBinding)
                .join(
                    OrganizationMembership,
                    (OrganizationMembership.organization_id == CorporateRoleBinding.organization_id)
                    & (OrganizationMembership.account_id == CorporateRoleBinding.account_id),
                )
                .where(
                    CorporateRoleBinding.organization_id == organization_id,
                    CorporateRoleBinding.scope_kind == "project",
                    CorporateRoleBinding.role == "lead",
                    CorporateRoleBinding.state == "active",
                    OrganizationMembership.state == "active",
                )
            )
        ).all()
        for binding in bindings:
            if binding.scope_id in nodes and binding.account_id in nodes:
                project_leads.setdefault(binding.scope_id, set()).add(str(binding.account_id))
        rows = (
            await db.scalars(
                select(CorporateProject)
                .join(
                    ProjectIdentity,
                    (ProjectIdentity.organization_id == CorporateProject.organization_id)
                    & (ProjectIdentity.id == CorporateProject.id),
                )
                .where(
                    CorporateProject.organization_id == organization_id,
                    ProjectIdentity.state != "deleted",
                    CorporateProject.lifecycle != "deleted",
                )
            )
        ).all()
    else:
        rows = (
            await db.scalars(
                select(CorporateTeam).where(CorporateTeam.organization_id == organization_id)
            )
        ).all()
    items: list[CorporateDirectoryItem] = []
    kind = "project" if query.resource == "projects" else "team"
    # ponytail: request-local permission cache; batch evaluation if directory latency warrants it.
    for row in rows:
        if not query.include_archived and row.state == "archived":
            continue
        if not await permitted(f"{kind}.list", kind, row.id) or not await permitted(
            f"{kind}.read", kind, row.id
        ):
            continue
        teams: set[str] = project_teams.get(row.id, set()) if kind == "project" else set()
        projects: set[str] = team_projects.get(row.id, set()) if kind == "team" else set()
        related: set[str] = {
            team
            for project in projects
            for team in project_teams.get(project, set())
            if team != row.id
        }
        item_leads = (
            project_leads.get(row.id) or {lead for team in teams for lead in leads.get(team, set())}
            if kind == "project"
            else leads.get(row.id, set())
        )
        item = CorporateDirectoryItem.model_validate(
            {
                "kind": kind,
                "id": row.id,
                "name": row.name,
                "description": str((row.profile or {}).get("description", ""))
                or (row.description if isinstance(row, CorporateTeam) else ""),
                "revision": row.revision,
                "teams": references(teams),
                "projects": references(projects),
                "related_teams": references(related),
                "leads": references(item_leads),
                "technologies": references(
                    (project_technologies if kind == "project" else team_technologies).get(
                        row.id, set()
                    )
                ),
                "owner_team": nodes.get(owners.get(row.id, "")),
                "available_actions": await available_actions(kind, row.id),
            }
        )
        items.append(item)
    items.sort(key=lambda item: (item.name.casefold(), item.id))

    def facet(field: str) -> list[CorporateDirectoryReference]:
        refs = {ref.id: ref for item in items for ref in getattr(item, field)}
        return sorted(refs.values(), key=lambda ref: (ref.name.casefold(), ref.id))

    return select_directory(
        CorporateDirectoryView(
            organization=graph.organization,
            resource=query.resource,
            items=items,
            total=len(items),
            facets=CorporateDirectoryFacets(
                leads=facet("leads"),
                teams=facet("teams" if kind == "project" else "related_teams"),
                technologies=facet("technologies"),
                job_titles=[],
            ),
        ),
        query,
    ).model_copy(update={"resource": requested_resource})
