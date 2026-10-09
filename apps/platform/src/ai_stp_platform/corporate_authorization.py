"""Shared tenant-scoped corporate authorization evaluator."""

from __future__ import annotations

from collections.abc import Collection
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from ai_stp_platform.tenant_scope import set_tenant_scope

PrincipalType = Literal["user", "service_principal"]


async def _role_graph(session: AsyncSession, organization_id: str) -> dict[str, str | None]:
    """The tenant's whole role->parent map in one query."""
    rows = (
        await session.execute(
            select(CorporateRole.name, CorporateRole.parent_role).where(
                CorporateRole.organization_id == organization_id
            )
        )
    ).all()
    return {row.name: row.parent_role for row in rows}


def _close_roles(graph: dict[str, str | None], roles: set[str]) -> set[str]:
    """Ancestors of every bound role, with the same per-chain bound the old
    per-hop walk used (32 steps)."""
    closed: set[str] = set()
    for role in roles:
        current: str | None = role
        seen: set[str] = set()
        while current is not None and current not in seen and len(seen) < 32:
            seen.add(current)
            closed.add(current)
            current = graph.get(current)
    return closed


async def _grants_for_roles(
    session: AsyncSession, organization_id: str, roles: set[str]
) -> set[str]:
    """Every permission granted to any of the closed roles, in one query."""
    if not roles:
        return set()
    return set(
        await session.scalars(
            select(CorporateRolePermission.permission)
            .where(
                CorporateRolePermission.organization_id == organization_id,
                CorporateRolePermission.role.in_(roles),
            )
            .distinct()
        )
    )


async def _principal_gate(
    session: AsyncSession,
    *,
    organization_id: str,
    principal_type: PrincipalType,
    principal_id: str,
    authorization_revision: int | None,
) -> bool:
    """The prologue every evaluation shares: active corporate organization,
    matching policy revision, and an active principal record."""
    await set_tenant_scope(session, organization_id)
    organization = await session.get(Organization, organization_id)
    if organization is None or organization.kind != "corporate" or organization.state != "active":
        return False
    if (
        authorization_revision is not None
        and organization.policy_revision != authorization_revision
    ):
        return False
    if principal_type == "user":
        return (
            await session.scalar(
                select(OrganizationMembership.id).where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.account_id == principal_id,
                    OrganizationMembership.state == "active",
                )
            )
        ) is not None
    return (
        await session.scalar(
            select(CorporateServicePrincipal.id).where(
                CorporateServicePrincipal.organization_id == organization_id,
                CorporateServicePrincipal.id == principal_id,
                CorporateServicePrincipal.state == "active",
            )
        )
    ) is not None


async def _principal_bindings(
    session: AsyncSession,
    *,
    organization_id: str,
    principal_type: PrincipalType,
    principal_id: str,
    extra_clause: object | None = None,
) -> list[CorporateRoleBinding]:
    """Active bindings for the principal, with the team-scope aliveness filter
    the evaluator always applies (a binding to an inactive team grants
    nothing). `extra_clause` narrows further where a single scope is being
    evaluated."""
    principal_filter = (
        CorporateRoleBinding.account_id == principal_id
        if principal_type == "user"
        else CorporateRoleBinding.service_principal_id == principal_id
    )
    conditions = [
        CorporateRoleBinding.organization_id == organization_id,
        CorporateRoleBinding.principal_type == principal_type,
        principal_filter,
        CorporateRoleBinding.state == "active",
        (CorporateRoleBinding.scope_kind != "team")
        | CorporateRoleBinding.scope_id.in_(
            select(CorporateTeam.id).where(
                CorporateTeam.organization_id == organization_id,
                CorporateTeam.state == "active",
            )
        ),
    ]
    if extra_clause is not None:
        conditions.append(extra_clause)  # type: ignore[arg-type]
    return list((await session.scalars(select(CorporateRoleBinding).where(*conditions))).all())


async def corporate_effective_permissions(
    session: AsyncSession,
    *,
    organization_id: str,
    principal_type: PrincipalType,
    principal_id: str,
    scope_kind: str = "organization",
    scope_id: str | None = None,
    authorization_revision: int | None = None,
) -> set[str] | None:
    """The full permission set an active principal holds at one scope.

    `None` means the gate itself denied (inactive organization, principal or
    stale policy revision); an empty set means the principal is active but
    holds nothing at this scope. Three queries total — bindings, role graph,
    grants — where `has_corporate_permission` used to walk the role chain one
    hop per query per bound role."""
    if not await _principal_gate(
        session,
        organization_id=organization_id,
        principal_type=principal_type,
        principal_id=principal_id,
        authorization_revision=authorization_revision,
    ):
        return None
    scope = scope_id or organization_id
    scope_clause = (
        (CorporateRoleBinding.scope_kind == "organization")
        & ((CorporateRoleBinding.role == "superadmin") | (scope_kind == "organization"))
    ) | (
        (CorporateRoleBinding.scope_kind == scope_kind)
        & ((CorporateRoleBinding.scope_id == "*") | (CorporateRoleBinding.scope_id == scope))
    )
    project_teams = _active_project_teams(organization_id)
    if scope_kind == "project":
        current_teams = (
            project_teams.join(
                CorporateProject,
                (CorporateProject.organization_id == ProjectTeamRelation.organization_id)
                & (CorporateProject.id == ProjectTeamRelation.project_id),
            )
            .join(
                ProjectIdentity,
                (ProjectIdentity.organization_id == CorporateProject.organization_id)
                & (ProjectIdentity.id == CorporateProject.id),
            )
            .where(
                ProjectTeamRelation.project_id == scope,
                CorporateProject.state == "active",
                ProjectIdentity.state == "active",
                ProjectIdentity.namespace == "remote",
            )
        )
        scope_clause |= (CorporateRoleBinding.scope_kind == "team") & (
            CorporateRoleBinding.scope_id.in_(current_teams)
        )
    elif scope_kind == "technology":
        current_projects = _technology_current_projects(organization_id, scope)
        responsible = _technology_responsible_teams(organization_id, scope)
        technology_teams = responsible.union(
            project_teams.where(ProjectTeamRelation.project_id.in_(current_projects))
        )
        scope_clause |= (
            (CorporateRoleBinding.scope_kind == "project")
            & CorporateRoleBinding.scope_id.in_(current_projects)
        ) | (
            (CorporateRoleBinding.scope_kind == "team")
            & CorporateRoleBinding.scope_id.in_(technology_teams)
        )
    elif scope_kind == "member":
        member_teams = (
            select(CorporateTeamMember.team_id)
            .join(
                CorporateTeam,
                (CorporateTeam.organization_id == CorporateTeamMember.organization_id)
                & (CorporateTeam.id == CorporateTeamMember.team_id),
            )
            .where(
                CorporateTeamMember.organization_id == organization_id,
                CorporateTeamMember.account_id == scope,
                CorporateTeam.state == "active",
            )
        )
        scope_clause |= (CorporateRoleBinding.scope_kind == "team") & (
            CorporateRoleBinding.scope_id.in_(member_teams)
        )
    bindings = await _principal_bindings(
        session,
        organization_id=organization_id,
        principal_type=principal_type,
        principal_id=principal_id,
        extra_clause=scope_clause,
    )
    roles = {binding.role for binding in bindings}
    graph = await _role_graph(session, organization_id)
    return await _grants_for_roles(session, organization_id, _close_roles(graph, roles))


def _active_project_teams(organization_id: str):
    """team_id per current project->team link where the team itself is active."""
    return (
        select(ProjectTeamRelation.team_id)
        .join(
            CorporateTeam,
            (CorporateTeam.organization_id == ProjectTeamRelation.organization_id)
            & (CorporateTeam.id == ProjectTeamRelation.team_id),
        )
        .where(
            ProjectTeamRelation.organization_id == organization_id,
            ProjectTeamRelation.state == "current",
            CorporateTeam.state == "active",
        )
    )


def _technology_current_projects(organization_id: str, technology_id: str):
    """Projects whose current technology link to `technology_id` is confirmed
    and fresh, through an active project with an active remote identity — the
    same eligibility shape the per-scope clause always used."""
    return (
        select(ProjectTechnologyRelation.project_id)
        .join(
            TechnologyUsageFact,
            (TechnologyUsageFact.organization_id == ProjectTechnologyRelation.organization_id)
            & (TechnologyUsageFact.relation_id == ProjectTechnologyRelation.id),
        )
        .join(
            CorporateProject,
            (CorporateProject.organization_id == ProjectTechnologyRelation.organization_id)
            & (CorporateProject.id == ProjectTechnologyRelation.project_id),
        )
        .join(
            ProjectIdentity,
            (ProjectIdentity.organization_id == CorporateProject.organization_id)
            & (ProjectIdentity.id == CorporateProject.id),
        )
        .join(
            Technology,
            (Technology.organization_id == ProjectTechnologyRelation.organization_id)
            & (Technology.id == ProjectTechnologyRelation.technology_id),
        )
        .where(
            ProjectTechnologyRelation.organization_id == organization_id,
            ProjectTechnologyRelation.technology_id == technology_id,
            ProjectTechnologyRelation.state == "current",
            TechnologyUsageFact.review.in_(("confirmed", "overridden")),
            TechnologyUsageFact.freshness != "absent",
            CorporateProject.state == "active",
            ProjectIdentity.state == "active",
            ProjectIdentity.namespace == "remote",
            Technology.lifecycle.in_(("active", "deprecated")),
            Technology.redirect_id.is_(None),
        )
    )


def _technology_responsible_teams(organization_id: str, technology_id: str):
    return (
        select(TechnologyTeamResponsibility.team_id)
        .join(
            Technology,
            (Technology.organization_id == TechnologyTeamResponsibility.organization_id)
            & (Technology.id == TechnologyTeamResponsibility.technology_id),
        )
        .where(
            TechnologyTeamResponsibility.organization_id == organization_id,
            TechnologyTeamResponsibility.technology_id == technology_id,
            TechnologyTeamResponsibility.state == "current",
            Technology.lifecycle.in_(("active", "deprecated")),
            Technology.redirect_id.is_(None),
        )
    )


async def bulk_effective_permissions(
    session: AsyncSession,
    *,
    organization_id: str,
    principal_type: PrincipalType,
    principal_id: str,
    scope_kind: str,
    scope_ids: Collection[str],
) -> dict[str, frozenset[str]] | None:
    """Permission sets for many same-kind scopes in bounded queries.

    One gate check, one binding read, one grouped map per relation kind the
    scope arm joins, the role graph, and one grants read for the union of
    every matching role — the count does not grow with `scope_ids`. `None`
    mirrors the single evaluator's gate denial: callers should treat it as
    "denied for every id", not "no data"."""
    if not await _principal_gate(
        session,
        organization_id=organization_id,
        principal_type=principal_type,
        principal_id=principal_id,
        authorization_revision=None,
    ):
        return None
    ids = sorted(set(scope_ids))
    bindings = await _principal_bindings(
        session,
        organization_id=organization_id,
        principal_type=principal_type,
        principal_id=principal_id,
    )
    # Grouped relation maps, built only for the arms this scope kind joins.
    # Each mirrors the subquery the single-scope clause embeds.
    projects_map: dict[str, set[str]] = {tech_id: set() for tech_id in ids}
    responsible_map: dict[str, set[str]] = {tech_id: set() for tech_id in ids}
    project_teams_map: dict[str, set[str]] = {}
    member_teams_map: dict[str, set[str]] = {member_id: set() for member_id in ids}
    if ids and scope_kind == "technology":
        rows = (
            await session.execute(
                select(
                    ProjectTechnologyRelation.technology_id,
                    ProjectTechnologyRelation.project_id,
                )
                .join(
                    TechnologyUsageFact,
                    (
                        TechnologyUsageFact.organization_id
                        == ProjectTechnologyRelation.organization_id
                    )
                    & (TechnologyUsageFact.relation_id == ProjectTechnologyRelation.id),
                )
                .join(
                    CorporateProject,
                    (CorporateProject.organization_id == ProjectTechnologyRelation.organization_id)
                    & (CorporateProject.id == ProjectTechnologyRelation.project_id),
                )
                .join(
                    ProjectIdentity,
                    (ProjectIdentity.organization_id == CorporateProject.organization_id)
                    & (ProjectIdentity.id == CorporateProject.id),
                )
                .join(
                    Technology,
                    (Technology.organization_id == ProjectTechnologyRelation.organization_id)
                    & (Technology.id == ProjectTechnologyRelation.technology_id),
                )
                .where(
                    ProjectTechnologyRelation.organization_id == organization_id,
                    ProjectTechnologyRelation.technology_id.in_(ids),
                    ProjectTechnologyRelation.state == "current",
                    TechnologyUsageFact.review.in_(("confirmed", "overridden")),
                    TechnologyUsageFact.freshness != "absent",
                    CorporateProject.state == "active",
                    ProjectIdentity.state == "active",
                    ProjectIdentity.namespace == "remote",
                    Technology.lifecycle.in_(("active", "deprecated")),
                    Technology.redirect_id.is_(None),
                )
            )
        ).all()
        for technology_id, project_id in rows:
            projects_map.setdefault(technology_id, set()).add(project_id)
        rows = (
            await session.execute(
                select(
                    TechnologyTeamResponsibility.technology_id,
                    TechnologyTeamResponsibility.team_id,
                )
                .join(
                    Technology,
                    (Technology.organization_id == TechnologyTeamResponsibility.organization_id)
                    & (Technology.id == TechnologyTeamResponsibility.technology_id),
                )
                .where(
                    TechnologyTeamResponsibility.organization_id == organization_id,
                    TechnologyTeamResponsibility.technology_id.in_(ids),
                    TechnologyTeamResponsibility.state == "current",
                    Technology.lifecycle.in_(("active", "deprecated")),
                    Technology.redirect_id.is_(None),
                )
            )
        ).all()
        for technology_id, team_id in rows:
            responsible_map.setdefault(technology_id, set()).add(team_id)
    if ids and scope_kind == "project":
        # Team bindings reach a project scope only while the project itself is
        # eligible (active, active remote identity) — the same gate the
        # single-scope clause embeds in `current_teams`.
        eligible = set(
            await session.scalars(
                select(CorporateProject.id)
                .join(
                    ProjectIdentity,
                    (ProjectIdentity.organization_id == CorporateProject.organization_id)
                    & (ProjectIdentity.id == CorporateProject.id),
                )
                .where(
                    CorporateProject.organization_id == organization_id,
                    CorporateProject.id.in_(ids),
                    CorporateProject.state == "active",
                    ProjectIdentity.state == "active",
                    ProjectIdentity.namespace == "remote",
                )
            )
        )
        if eligible:
            rows = (
                await session.execute(
                    select(ProjectTeamRelation.project_id, ProjectTeamRelation.team_id)
                    .join(
                        CorporateTeam,
                        (CorporateTeam.organization_id == ProjectTeamRelation.organization_id)
                        & (CorporateTeam.id == ProjectTeamRelation.team_id),
                    )
                    .where(
                        ProjectTeamRelation.organization_id == organization_id,
                        ProjectTeamRelation.project_id.in_(eligible),
                        ProjectTeamRelation.state == "current",
                        CorporateTeam.state == "active",
                    )
                )
            ).all()
            for project_id, team_id in rows:
                project_teams_map.setdefault(project_id, set()).add(team_id)
    if ids and scope_kind == "member":
        rows = (
            await session.execute(
                select(CorporateTeamMember.account_id, CorporateTeamMember.team_id)
                .join(
                    CorporateTeam,
                    (CorporateTeam.organization_id == CorporateTeamMember.organization_id)
                    & (CorporateTeam.id == CorporateTeamMember.team_id),
                )
                .where(
                    CorporateTeamMember.organization_id == organization_id,
                    CorporateTeamMember.account_id.in_(ids),
                    CorporateTeam.state == "active",
                )
            )
        ).all()
        for account_id, team_id in rows:
            member_teams_map.setdefault(account_id, set()).add(team_id)
    if scope_kind == "technology":
        all_projects = {project for projects in projects_map.values() for project in projects}
        if all_projects:
            rows = (
                await session.execute(
                    select(ProjectTeamRelation.project_id, ProjectTeamRelation.team_id)
                    .join(
                        CorporateTeam,
                        (CorporateTeam.organization_id == ProjectTeamRelation.organization_id)
                        & (CorporateTeam.id == ProjectTeamRelation.team_id),
                    )
                    .where(
                        ProjectTeamRelation.organization_id == organization_id,
                        ProjectTeamRelation.project_id.in_(all_projects),
                        ProjectTeamRelation.state == "current",
                        CorporateTeam.state == "active",
                    )
                )
            ).all()
            for project_id, team_id in rows:
                project_teams_map.setdefault(project_id, set()).add(team_id)
    # Roles each scope's matching bindings grant, evaluated in memory with
    # exactly the arms the single-scope clause has.
    roles_per_scope: dict[str, set[str]] = {scope_id: set() for scope_id in ids}
    all_roles: set[str] = set()
    for binding in bindings:
        for scope_id in ids:
            direct = (
                binding.scope_kind == "organization"
                and (binding.role == "superadmin" or scope_kind == "organization")
            ) or (
                binding.scope_kind == scope_kind
                and (binding.scope_id == "*" or binding.scope_id == scope_id)
            )
            via_project = (
                scope_kind == "technology"
                and binding.scope_kind == "project"
                and binding.scope_id in projects_map[scope_id]
            )
            via_team = False
            if binding.scope_kind == "team":
                if scope_kind == "project":
                    via_team = binding.scope_id in project_teams_map.get(scope_id, set())
                elif scope_kind == "technology":
                    teams = set(responsible_map[scope_id])
                    for project_id in projects_map[scope_id]:
                        teams |= project_teams_map.get(project_id, set())
                    via_team = binding.scope_id in teams
                elif scope_kind == "member":
                    via_team = binding.scope_id in member_teams_map[scope_id]
            if direct or via_project or via_team:
                roles_per_scope[scope_id].add(binding.role)
                all_roles.add(binding.role)
    graph = await _role_graph(session, organization_id)
    closed = _close_roles(graph, all_roles)
    grants_rows = (
        await session.execute(
            select(CorporateRolePermission.role, CorporateRolePermission.permission).where(
                CorporateRolePermission.organization_id == organization_id,
                CorporateRolePermission.role.in_(closed or {""}),
            )
        )
    ).all()
    grants: dict[str, set[str]] = {}
    for role, permission in grants_rows:
        grants.setdefault(role, set()).add(permission)
    result: dict[str, frozenset[str]] = {}
    for scope_id in ids:
        scope_closed = _close_roles(graph, roles_per_scope[scope_id])
        permissions: set[str] = set()
        for role in scope_closed:
            permissions |= grants.get(role, set())
        result[scope_id] = frozenset(permissions)
    return result


async def has_corporate_permission(
    session: AsyncSession,
    *,
    organization_id: str,
    principal_type: PrincipalType,
    principal_id: str,
    permission: str,
    scope_kind: str = "organization",
    scope_id: str | None = None,
    authorization_revision: int | None = None,
) -> bool:
    """Return whether an active principal has the permission at the requested scope."""
    effective = await corporate_effective_permissions(
        session,
        organization_id=organization_id,
        principal_type=principal_type,
        principal_id=principal_id,
        scope_kind=scope_kind,
        scope_id=scope_id,
        authorization_revision=authorization_revision,
    )
    return effective is not None and permission in effective


__all__ = [
    "PrincipalType",
    "bulk_effective_permissions",
    "corporate_effective_permissions",
    "has_corporate_permission",
]
