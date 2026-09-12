"""Shared tenant-scoped corporate authorization evaluator."""

from __future__ import annotations

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


async def _role_has_permission(
    session: AsyncSession, *, organization_id: str, role: str, permission: str
) -> bool:
    """Resolve a role's inherited permissions inside one tenant."""
    current: str | None = role
    seen: set[str] = set()
    while current is not None and current not in seen and len(seen) < 32:
        seen.add(current)
        if (
            await session.scalar(
                select(CorporateRolePermission.role).where(
                    CorporateRolePermission.organization_id == organization_id,
                    CorporateRolePermission.role == current,
                    CorporateRolePermission.permission == permission,
                )
            )
            is not None
        ):
            return True
        current = await session.scalar(
            select(CorporateRole.parent_role).where(
                CorporateRole.organization_id == organization_id,
                CorporateRole.name == current,
            )
        )
    return False


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
        principal_active = await session.scalar(
            select(OrganizationMembership.id).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.account_id == principal_id,
                OrganizationMembership.state == "active",
            )
        )
        principal_filter = CorporateRoleBinding.account_id == principal_id
    else:
        principal_active = await session.scalar(
            select(CorporateServicePrincipal.id).where(
                CorporateServicePrincipal.organization_id == organization_id,
                CorporateServicePrincipal.id == principal_id,
                CorporateServicePrincipal.state == "active",
            )
        )
        principal_filter = CorporateRoleBinding.service_principal_id == principal_id
    if principal_active is None:
        return False
    scope = scope_id or organization_id
    scope_clause = (
        (CorporateRoleBinding.scope_kind == "organization")
        & ((CorporateRoleBinding.role == "superadmin") | (scope_kind == "organization"))
    ) | (
        (CorporateRoleBinding.scope_kind == scope_kind)
        & ((CorporateRoleBinding.scope_id == "*") | (CorporateRoleBinding.scope_id == scope))
    )
    project_teams = (
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
        current_projects = (
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
                ProjectTechnologyRelation.technology_id == scope,
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
        responsible_teams = (
            select(TechnologyTeamResponsibility.team_id)
            .join(
                Technology,
                (Technology.organization_id == TechnologyTeamResponsibility.organization_id)
                & (Technology.id == TechnologyTeamResponsibility.technology_id),
            )
            .where(
                TechnologyTeamResponsibility.organization_id == organization_id,
                TechnologyTeamResponsibility.technology_id == scope,
                TechnologyTeamResponsibility.state == "current",
                Technology.lifecycle.in_(("active", "deprecated")),
                Technology.redirect_id.is_(None),
            )
        )
        technology_teams = responsible_teams.union(
            project_teams.where(ProjectTeamRelation.project_id.in_(current_projects))
        )
        scope_clause |= (
            (CorporateRoleBinding.scope_kind == "project")
            & CorporateRoleBinding.scope_id.in_(current_projects)
        ) | (
            (CorporateRoleBinding.scope_kind == "team")
            & CorporateRoleBinding.scope_id.in_(technology_teams)
        )
    bindings = await session.scalars(
        select(CorporateRoleBinding.role)
        .where(
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
            scope_clause,
        )
        .distinct()
    )
    for role in bindings:
        if await _role_has_permission(
            session, organization_id=organization_id, role=role, permission=permission
        ):
            return True
    return False


__all__ = ["PrincipalType", "has_corporate_permission"]
