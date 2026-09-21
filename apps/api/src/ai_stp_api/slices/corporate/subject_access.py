"""Per-subject management capabilities for corporate entities and catalog objects."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.catalog_ownership_models import CorporateCatalogOwnership
from ai_stp_platform.corporate_authorization import has_corporate_permission
from ai_stp_platform.models import CatalogIdentity
from ai_stp_platform.organization_models import CorporateTeam, CorporateTeamMember
from ai_stp_platform.technology_models import ProjectTeamRelation, Technology

OBJECT_CAPABILITIES = ("edit", "edit_presentation", "delete")


def _led_teams(organization_id: str, account_id: str):
    return (
        select(CorporateTeamMember.team_id)
        .join(
            CorporateTeam,
            (CorporateTeam.organization_id == CorporateTeamMember.organization_id)
            & (CorporateTeam.id == CorporateTeamMember.team_id),
        )
        .where(
            CorporateTeamMember.organization_id == organization_id,
            CorporateTeamMember.account_id == account_id,
            CorporateTeamMember.role == "lead",
            CorporateTeam.state == "active",
        )
    )


async def is_technology_owner(
    db: AsyncSession, *, organization_id: str, technology_id: str, account_id: str
) -> bool:
    return (
        await db.scalar(
            select(Technology.id).where(
                Technology.organization_id == organization_id,
                Technology.id == technology_id,
                Technology.owner_account_id == account_id,
                Technology.redirect_id.is_(None),
                Technology.lifecycle != "archived",
            )
        )
        is not None
    )


async def subject_available_actions(
    db: AsyncSession,
    *,
    account_id: str,
    organization_id: str,
    subject_kind: str,
    subject_id: str,
) -> list[str]:
    """Menu actions the principal may perform on one corporate subject."""
    resource = "member" if subject_kind == "employee" else subject_kind

    async def _scoped(permission: str) -> bool:
        if await has_corporate_permission(
            db,
            organization_id=organization_id,
            principal_type="user",
            principal_id=account_id,
            permission=permission,
            scope_kind=resource,
            scope_id=subject_id,
        ):
            return True
        if resource == "member":
            # Scoped member checks only match team bindings and superadmin;
            # organization-wide member roles grant the same capability.
            return await has_corporate_permission(
                db,
                organization_id=organization_id,
                principal_type="user",
                principal_id=account_id,
                permission=permission,
                scope_kind="organization",
                scope_id=organization_id,
            )
        return False

    actions: list[str] = []
    update_allowed = await _scoped(f"{resource}.update")
    if not update_allowed and subject_kind == "technology":
        update_allowed = await is_technology_owner(
            db,
            organization_id=organization_id,
            technology_id=subject_id,
            account_id=account_id,
        )
    if update_allowed:
        actions.append(f"{resource}.update")
    if await _scoped(f"{resource}.delete"):
        actions.append(f"{resource}.delete")
    from ai_stp_api.slices.corporate.entity_profiles import can_edit_profile

    if await can_edit_profile(
        db,
        account_id=account_id,
        organization_id=organization_id,
        subject_kind=subject_kind,
        subject_id=subject_id,
    ):
        actions.append("entity_profile.update")
    return actions


async def catalog_object_capabilities(
    db: AsyncSession,
    *,
    account_id: str,
    organization_id: str,
    object_kind: str,
    stable_id: str,
) -> list[str]:
    """Management capabilities on a catalog object for the current principal."""
    from ai_stp_platform.models import CatalogMetadata

    identity = await db.get(CatalogIdentity, stable_id)
    author_id: str | None = None
    if identity is not None and identity.organization_id == organization_id:
        author_id = identity.owner_account_id
    else:
        author_id = await db.scalar(
            select(CatalogMetadata.owner_account_id).where(
                CatalogMetadata.organization_id == organization_id,
                CatalogMetadata.object_kind == object_kind,
                CatalogMetadata.stable_id == stable_id,
            )
        )
    if author_id == account_id and author_id is not None:
        capabilities = {"edit", "edit_presentation"}
        if not await _has_published_version(
            db, organization_id=organization_id, stable_id=stable_id
        ):
            capabilities.add("delete")
        return sorted(capabilities)

    capabilities: set[str] = set()

    async def _org(permission: str) -> bool:
        return await has_corporate_permission(
            db,
            organization_id=organization_id,
            principal_type="user",
            principal_id=account_id,
            permission=permission,
            scope_kind="organization",
            scope_id=organization_id,
        )

    if await _org("catalog_object.edit"):
        capabilities |= {"edit", "edit_presentation"}
    if await _org("catalog_object.delete") and not await _has_published_version(
        db, organization_id=organization_id, stable_id=stable_id
    ):
        capabilities.add("delete")

    row = await db.get(CorporateCatalogOwnership, (organization_id, object_kind, stable_id))
    owner_id = (row.owner_id or row.owner_account_id) if row is not None else None
    if row is not None and owner_id is not None:
        grant = False
        if row.owner_kind == "employee":
            grant = owner_id == account_id
        elif row.owner_kind == "team":
            grant = (
                await db.scalar(
                    select(CorporateTeamMember.team_id).where(
                        CorporateTeamMember.organization_id == organization_id,
                        CorporateTeamMember.team_id == owner_id,
                        CorporateTeamMember.account_id == account_id,
                        CorporateTeamMember.role == "lead",
                    )
                )
                is not None
            )
        elif row.owner_kind == "project":
            grant = (
                await db.scalar(
                    select(ProjectTeamRelation.team_id).where(
                        ProjectTeamRelation.organization_id == organization_id,
                        ProjectTeamRelation.project_id == owner_id,
                        ProjectTeamRelation.role == "owner",
                        ProjectTeamRelation.state == "current",
                        ProjectTeamRelation.team_id.in_(_led_teams(organization_id, account_id)),
                    )
                )
                is not None
            )
        elif row.owner_kind == "technology":
            grant = await is_technology_owner(
                db,
                organization_id=organization_id,
                technology_id=owner_id,
                account_id=account_id,
            )
        if grant:
            capabilities |= {"edit", "edit_presentation"}
    return sorted(capabilities)


async def _has_published_version(db: AsyncSession, *, organization_id: str, stable_id: str) -> bool:
    from ai_stp_platform.models import CatalogMetadata

    return (
        await db.scalar(
            select(CatalogMetadata.id).where(
                CatalogMetadata.organization_id == organization_id,
                CatalogMetadata.stable_id == stable_id,
                CatalogMetadata.published_at.is_not(None),
            )
        )
        is not None
    )
