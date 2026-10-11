"""One menu registry filtered by live authorization and entity state."""

from datetime import UTC, datetime
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate.subject_access import subject_permission_allowed
from ai_stp_contracts.entity_actions import EntityAction, EntityActionMenu, EntityActionSubject
from ai_stp_platform.organization_models import (
    CorporateInvitation,
    CorporateJobTitle,
    CorporateProject,
    CorporateRole,
    CorporateTeam,
    OrganizationMembership,
)
from ai_stp_platform.technology_models import Technology, TechnologyArea, TechnologyCategory

# Presentation order is independent from the authorization policy.
COMMON_ACTIONS = (
    EntityAction(id="open", group="navigation"),
    EntityAction(id="copy_id", group="sharing"),
    EntityAction(id="copy_url", group="sharing"),
    EntityAction(id="share", group="sharing"),
)
REPORT = EntityAction(id="report", group="support")
RESOURCE_MODELS = {
    "team": CorporateTeam,
    "project": CorporateProject,
    "member": OrganizationMembership,
    "technology": Technology,
    "category": TechnologyCategory,
    "area": TechnologyArea,
    "job_title": CorporateJobTitle,
    "role": CorporateRole,
}
RESOURCE_ROUTES = {
    "team": "teams",
    "project": "projects",
    "member": "employees",
    "technology": "technologies",
    "category": "categories",
    "area": "admin/technology-areas",
    "job_title": "admin/job-titles",
    "role": "admin/roles",
}
RESOURCE_IDENTITIES = {
    "team": CorporateTeam.id,
    "project": CorporateProject.id,
    "member": OrganizationMembership.account_id,
    "technology": Technology.id,
    "category": TechnologyCategory.id,
    "area": TechnologyArea.id,
    "job_title": CorporateJobTitle.id,
    "role": CorporateRole.name,
}


async def read_menu(
    db: AsyncSession,
    *,
    ctx: AuthContext | None,
    subject: EntityActionSubject,
) -> EntityActionMenu:
    if subject.kind in {"component", "setup"}:
        return await _catalog_menu(db, ctx=ctx, subject=subject)
    if subject.kind == "publisher":
        from ai_stp_platform.models import Account

        account = await db.get(Account, subject.id)
        if account is None or account.status != "active":
            raise ApiError(ErrorCategory.NOT_FOUND, "publisher not found")
        actions = list(COMMON_ACTIONS)
        actions.insert(3, EntityAction(id="copy_cli", group="sharing"))
        if ctx and ctx.account_id == subject.id:
            actions.append(EntityAction(id="edit_profile", group="management"))
        actions.append(REPORT)
        return EntityActionMenu(subject=subject, href=f"/publishers/{subject.id}", actions=actions)
    if ctx is None:
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "authentication required")
    if subject.kind == "grant":
        return await _grant_menu(db, ctx=ctx, subject=subject)
    if subject.kind == "scan":
        from ai_stp_api.slices.technology.detection import read_scan_detail

        if not subject.organization_id:
            raise ApiError(ErrorCategory.NOT_FOUND, "scan not found")
        await read_scan_detail(
            db,
            ctx=ctx,
            organization_id=subject.organization_id,
            scan_id=subject.id,
            request_id=None,
        )
        return EntityActionMenu(
            subject=subject,
            href=f"/corporate/technology-scans/{subject.id}",
            actions=[
                EntityAction(id="open", group="navigation"),
                EntityAction(id="open_project", group="navigation"),
            ],
        )
    if subject.kind == "finding":
        return await _finding_menu(db, ctx=ctx, subject=subject)
    if subject.kind == "invitation":
        return await _invitation_menu(db, ctx=ctx, subject=subject)
    if not subject.organization_id or subject.kind not in RESOURCE_MODELS:
        raise ApiError(ErrorCategory.NOT_FOUND, "entity not found")
    from ai_stp_api.slices.corporate.service import organization_and_membership

    organization, _ = await organization_and_membership(
        db,
        ctx=ctx,
        organization_id=subject.organization_id,
    )
    model = RESOURCE_MODELS[subject.kind]
    identity = RESOURCE_IDENTITIES[subject.kind]
    row = await db.scalar(
        select(model).where(model.organization_id == organization.id, identity == subject.id)
    )
    if row is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "entity not found")
    scoped = subject.kind in {"team", "project", "member", "technology", "category"}

    async def allowed(permission: str) -> bool:
        return await subject_permission_allowed(
            db,
            account_id=ctx.account_id,
            organization_id=organization.id,
            subject_kind=subject.kind if scoped else "organization",
            subject_id=subject.id if scoped else organization.id,
            permission=permission,
        )

    if not await allowed(f"{subject.kind}.read"):
        raise ApiError(ErrorCategory.PERMISSION, "entity access denied")
    actions = list(COMMON_ACTIONS)
    update = f"{subject.kind}.update"
    if await allowed(update):
        actions.append(EntityAction(id="edit", group="management"))
    if subject.kind in {"team", "project", "member", "technology"} and await allowed(
        "entity_profile.update"
    ):
        actions.append(EntityAction(id="edit_presentation", group="management"))
    if (
        subject.kind == "job_title"
        and isinstance(row, CorporateJobTitle)
        and row.state == "current"
        and await allowed("job_title.update")
        and await allowed("member.update")
    ):
        actions.append(EntityAction(id="assign_members", group="management"))
    if (
        subject.kind == "member"
        and await allowed("member.update")
        and await subject_permission_allowed(
            db,
            account_id=ctx.account_id,
            organization_id=organization.id,
            subject_kind="organization",
            subject_id=organization.id,
            permission="member.read",
        )
        and await subject_permission_allowed(
            db,
            account_id=ctx.account_id,
            organization_id=organization.id,
            subject_kind="organization",
            subject_id=organization.id,
            permission="member.list",
        )
    ):
        actions.append(EntityAction(id="manage_access", group="management"))
    delegable_role = True
    if subject.kind == "role":
        from ai_stp_api.slices.corporate.service import assert_delegable_roles

        try:
            await assert_delegable_roles(
                db, organization_id=organization.id, account_id=ctx.account_id, roles={subject.id}
            )
        except ApiError as error:
            if error.category != ErrorCategory.PERMISSION:
                raise
            delegable_role = False
    if subject.kind == "role" and delegable_role and await allowed("role.create"):
        actions.append(EntityAction(id="duplicate", group="management"))
    if subject.kind == "role" and delegable_role and await allowed("binding.create"):
        actions.append(EntityAction(id="assign_members", group="management"))
    if subject.kind == "category" and await allowed("technology.update"):
        actions.append(EntityAction(id="manage_technologies", group="management"))
    deletion = "job_title.update" if subject.kind == "job_title" else f"{subject.kind}.delete"
    from ai_stp_api.slices.corporate.service import BUILT_IN_ROLES

    builtin = subject.kind == "role" and subject.id in BUILT_IN_ROLES
    if builtin:
        actions = [action for action in actions if action.id != "edit"]
    restoring = (isinstance(row, CorporateJobTitle) and row.state == "retired") or (
        isinstance(row, (TechnologyCategory, TechnologyArea)) and row.state == "archived"
    )
    deletable = not builtin and await allowed(update if restoring else deletion)
    if subject.kind == "member":
        from ai_stp_api.slices.corporate.service import organization_admin_state

        admins, _ = await organization_admin_state(db, organization_id=organization.id)
        if subject.id in admins:
            from ai_stp_platform.corporate_authorization import has_corporate_permission

            if not await has_corporate_permission(
                db,
                organization_id=organization.id,
                principal_type="user",
                principal_id=ctx.account_id,
                permission="member.update",
                scope_kind="organization",
                scope_id=organization.id,
            ):
                actions = [action for action in actions if action.id != "edit"]
            deletable = (
                deletable
                and len(admins) > 1
                and await has_corporate_permission(
                    db,
                    organization_id=organization.id,
                    principal_type="user",
                    principal_id=ctx.account_id,
                    permission="member.delete",
                    scope_kind="organization",
                    scope_id=organization.id,
                )
            )
    if isinstance(row, Technology) and row.redirect_id is not None:
        actions = [action for action in actions if action.id not in {"edit", "edit_presentation"}]
        deletable = False
    if deletable:
        action = (
            "restore"
            if (isinstance(row, CorporateJobTitle) and row.state == "retired")
            or (isinstance(row, (TechnologyCategory, TechnologyArea)) and row.state == "archived")
            else "retire"
            if subject.kind == "job_title"
            else "delete"
        )
        actions.append(
            EntityAction(id=action, group="management" if action == "restore" else "danger")
        )
    actions.append(REPORT)
    route = RESOURCE_ROUTES[subject.kind]
    href = f"/corporate/{route}"
    if subject.kind in {"team", "project", "member", "technology", "category"}:
        href += f"/{subject.id}"
    return EntityActionMenu(
        subject=subject,
        href=href,
        revision=getattr(row, "revision", None),
        authorization_revision=organization.policy_revision,
        actions=actions,
    )


async def _catalog_menu(
    db: AsyncSession,
    *,
    ctx: AuthContext | None,
    subject: EntityActionSubject,
) -> EntityActionMenu:
    from ai_stp_api.slices.owner.service import read_owner_object_capabilities
    from ai_stp_platform.catalog_read import get_visible_metadata
    from ai_stp_platform.models import CatalogMetadata

    kind = cast(Literal["component", "setup"], subject.kind)
    capabilities: list[str] = []
    if ctx is not None:
        try:
            result = await read_owner_object_capabilities(
                db,
                ctx=ctx,
                object_kind=kind,
                stable_id=subject.id,
            )
            capabilities = list(result.capabilities)
        except ApiError as error:
            if error.category != ErrorCategory.NOT_FOUND:
                raise
    metadata = None
    if not capabilities:
        versions = await db.scalars(
            select(CatalogMetadata.version)
            .where(
                CatalogMetadata.object_kind == subject.kind,
                CatalogMetadata.stable_id == subject.id,
            )
            .order_by(CatalogMetadata.updated_at.desc())
            .limit(256)
        )
        metadata = None
        for version in versions:
            if version is None:
                continue
            metadata = await get_visible_metadata(
                db,
                object_kind=kind,
                stable_id=subject.id,
                version=version,
                account_id=ctx.account_id if ctx else None,
            )
            if metadata is not None:
                break
        if metadata is None:
            raise ApiError(ErrorCategory.NOT_FOUND, "object not found")
    latest = (
        await db.scalar(
            select(CatalogMetadata)
            .where(
                CatalogMetadata.object_kind == kind,
                CatalogMetadata.stable_id == subject.id,
            )
            .order_by(CatalogMetadata.updated_at.desc())
            .limit(1)
        )
        if capabilities
        else metadata
    )
    if latest is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "object not found")
    device_id = None
    visibility_allowed = False
    if ctx and ctx.device_id:
        from ai_stp_platform.models import Device

        device = await db.get(Device, ctx.device_id)
        visibility_allowed = (
            latest.owner_account_id == ctx.account_id
            and latest.published_at is not None
            and latest.lifecycle_state in {"active", "deprecated"}
            and bool(latest.passport_digest)
            and device is not None
            and device.account_id == ctx.account_id
            and device.state == "active"
        )
        if visibility_allowed:
            device_id = ctx.device_id
    change_owner = False
    assign = False
    if ctx and subject.organization_id:
        from ai_stp_api.slices.corporate.subject_access import can_edit_subject_profile

        change_owner = (
            latest.organization_id == subject.organization_id
            and await can_edit_subject_profile(
                db,
                account_id=ctx.account_id,
                organization_id=subject.organization_id,
                subject_kind="catalog_object",
                subject_id=subject.id,
                owner_assignment=True,
            )
        )
        from ai_stp_platform.corporate_authorization import bulk_effective_permissions

        for target_kind, model, identity, permission, active in (
            (
                "team",
                CorporateTeam,
                CorporateTeam.id,
                "team.update",
                CorporateTeam.state == "active",
            ),
            (
                "project",
                CorporateProject,
                CorporateProject.id,
                "project.update",
                CorporateProject.state == "active",
            ),
            (
                "technology",
                Technology,
                Technology.id,
                "technology.update",
                Technology.lifecycle.in_(("active", "deprecated")),
            ),
        ):
            ids = list(
                await db.scalars(
                    select(identity).where(model.organization_id == subject.organization_id, active)
                )
            )
            grants = await bulk_effective_permissions(
                db,
                organization_id=subject.organization_id,
                principal_type="user",
                principal_id=ctx.account_id,
                scope_kind=target_kind,
                scope_ids=ids,
            )
            assign = any(permission in permissions for permissions in (grants or {}).values())
            if not assign and target_kind == "technology" and grants is not None:
                assign = (
                    await db.scalar(
                        select(Technology.id)
                        .where(
                            Technology.organization_id == subject.organization_id,
                            Technology.id.in_(ids),
                            Technology.owner_account_id == ctx.account_id,
                            Technology.redirect_id.is_(None),
                        )
                        .limit(1)
                    )
                    is not None
                )
            if assign:
                break
        assign = assign or await subject_permission_allowed(
            db,
            account_id=ctx.account_id,
            organization_id=subject.organization_id,
            subject_kind="organization",
            subject_id=subject.organization_id,
            permission="member.manage",
        )
    actions = list(COMMON_ACTIONS)
    actions.insert(3, EntityAction(id="copy_cli", group="sharing"))
    if ctx is not None:
        actions.append(EntityAction(id="like", group="management"))
    for capability in ("edit_presentation", "manage_access", "delete"):
        if capability in capabilities:
            actions.append(
                EntityAction(
                    id=capability, group="danger" if capability == "delete" else "management"
                )
            )
    for action_id, permitted in (
        ("change_owner", change_owner),
        ("visibility", visibility_allowed),
        ("assign", assign),
    ):
        if permitted:
            actions.insert(
                -1 if actions[-1].group == "danger" else len(actions),
                EntityAction(id=action_id, group="management"),
            )
    actions.append(REPORT)
    return EntityActionMenu(
        subject=subject,
        object_version=latest.version,
        object_name=latest.name,
        visibility=cast(Literal["public", "private"], latest.visibility),
        device_id=device_id,
        href=f"/catalog/{'components' if subject.kind == 'component' else 'setups'}/{subject.id}",
        actions=actions,
    )


async def _grant_menu(
    db: AsyncSession, *, ctx: AuthContext, subject: EntityActionSubject
) -> EntityActionMenu:
    from ai_stp_api.slices.grants.service import may_withdraw
    from ai_stp_platform.models import AccessGrant

    row = await db.get(AccessGrant, subject.id)
    if row is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "grant not found")
    withdraw = await may_withdraw(
        db,
        account_id=ctx.account_id,
        issuer_account_id=row.owner_account_id,
        object_kind=row.object_kind,
        stable_id=row.stable_id,
    )
    if ctx.account_id != row.grantee_account_id and not withdraw:
        raise ApiError(ErrorCategory.NOT_FOUND, "grant not found")
    actions = [EntityAction(id="copy_id", group="sharing")]
    if withdraw and row.state == "active":
        actions.append(EntityAction(id="revoke", group="danger"))
    actions.append(REPORT)
    return EntityActionMenu(subject=subject, actions=actions)


async def _invitation_menu(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    subject: EntityActionSubject,
) -> EntityActionMenu:
    from ai_stp_api.slices.corporate.service import authorize

    if subject.organization_id is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "invitation not found")
    organization, _ = await authorize(
        db,
        ctx=ctx,
        organization_id=subject.organization_id,
        permission="member.invite",
    )
    row = await db.scalar(
        select(CorporateInvitation).where(
            CorporateInvitation.organization_id == organization.id,
            CorporateInvitation.id == subject.id,
        )
    )
    if row is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "invitation not found")
    actions = [EntityAction(id="copy_id", group="sharing")]
    if row.state in {"pending", "email_confirm_pending"} and row.expires_at > datetime.now(UTC):
        actions.append(EntityAction(id="revoke", group="danger"))
    return EntityActionMenu(
        subject=subject, authorization_revision=organization.policy_revision, actions=actions
    )


async def _finding_menu(
    db: AsyncSession, *, ctx: AuthContext, subject: EntityActionSubject
) -> EntityActionMenu:
    from ai_stp_api.slices.technology.detection import read_scan_detail

    if not subject.organization_id or not subject.finding_kind or not subject.coordinate:
        raise ApiError(ErrorCategory.VALIDATION, "finding selector required")
    scan = await read_scan_detail(
        db, ctx=ctx, organization_id=subject.organization_id, scan_id=subject.id, request_id=None
    )
    finding = next(
        (
            item
            for item in scan.findings
            if item.kind == subject.finding_kind
            and item.coordinate == subject.coordinate
            and item.context == subject.usage_context
        ),
        None,
    )
    if finding is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "finding not found")

    async def allowed(
        permission: str, kind: str = "organization", identity: str | None = None
    ) -> bool:
        return await subject_permission_allowed(
            db,
            account_id=ctx.account_id,
            organization_id=subject.organization_id or "",
            subject_kind=kind,
            subject_id=identity or subject.organization_id or "",
            permission=permission,
        )

    actions = [EntityAction(id="evidence", group="navigation")]
    technology_id = finding.technology_id or finding.candidate_technology_id
    if technology_id and await allowed("technology.update", "technology", technology_id):
        actions.append(EntityAction(id="edit_technology", group="management"))
    create = await allowed("technology.create")
    review = await allowed("technology.update") and await allowed(
        "project_technology.update", "project", scan.project_id
    )
    if finding.tier == "dependency":
        if (
            technology_id
            and review
            and await allowed("technology.update", "technology", technology_id)
        ) or (not technology_id and create and review):
            actions.append(EntityAction(id="make_technology", group="management"))
    else:
        if create:
            actions.append(EntityAction(id="create_technology", group="management"))
        if review:
            actions.append(EntityAction(id="move_to_dependencies", group="management"))
    return EntityActionMenu(subject=subject, actions=actions)
