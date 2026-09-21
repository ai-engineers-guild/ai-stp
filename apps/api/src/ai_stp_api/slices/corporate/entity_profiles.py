"""Shared presentation edits without granting membership or registry governance."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import service
from ai_stp_contracts.corporate_profiles import (
    EntityProfileFields,
    EntityProfileSubject,
    EntityProfileView,
    EntityProfileWriteRequest,
    TechnologyOwnerRequest,
)
from ai_stp_platform.corporate_authorization import has_corporate_permission
from ai_stp_platform.models import Account, AvatarAsset, ComponentMedia
from ai_stp_platform.organization_models import (
    CorporateProject,
    CorporateTeam,
    CorporateTeamMember,
    OrganizationMembership,
    ProjectIdentity,
)
from ai_stp_platform.technology_models import ProjectTeamRelation, Technology

ProfileRow = CorporateTeam | CorporateProject | OrganizationMembership | Technology


async def can_edit_profile(
    db: AsyncSession,
    *,
    ctx: AuthContext | None = None,
    account_id: str | None = None,
    organization_id: str,
    subject_kind: str,
    subject_id: str,
    owner_assignment: bool = False,
) -> bool:
    principal_id = account_id or (ctx.account_id if ctx is not None else "")
    if not principal_id:
        return False
    # Callers first establish active tenant membership; each grant remains tenant-scoped.
    resource = "member" if subject_kind == "employee" else subject_kind
    subject_permission = (
        ("catalog_object.ownership_transfer" if owner_assignment else "catalog_object.edit")
        if subject_kind == "catalog_object"
        else f"{resource}.update"
    )

    async def _org(permission: str) -> bool:
        return await has_corporate_permission(
            db,
            organization_id=organization_id,
            principal_type="user",
            principal_id=principal_id,
            permission=permission,
            scope_kind="organization",
            scope_id=organization_id,
        )

    if await _org(subject_permission) or await _org("member.update"):
        return True
    led_teams = (
        select(CorporateTeamMember.team_id)
        .join(
            CorporateTeam,
            (CorporateTeam.organization_id == CorporateTeamMember.organization_id)
            & (CorporateTeam.id == CorporateTeamMember.team_id),
        )
        .where(
            CorporateTeamMember.organization_id == organization_id,
            CorporateTeamMember.account_id == principal_id,
            CorporateTeamMember.role == "lead",
            CorporateTeam.state == "active",
        )
    )
    if subject_kind == "employee":
        return (
            await db.scalar(
                select(CorporateTeamMember.account_id).where(
                    CorporateTeamMember.organization_id == organization_id,
                    CorporateTeamMember.account_id == subject_id,
                    CorporateTeamMember.team_id.in_(led_teams),
                )
            )
            is not None
        )
    if subject_kind == "team":
        return (
            await db.scalar(
                select(CorporateTeam.id).where(
                    CorporateTeam.organization_id == organization_id,
                    CorporateTeam.id == subject_id,
                    CorporateTeam.id.in_(led_teams),
                )
            )
            is not None
        )
    if subject_kind == "project":
        return (
            await db.scalar(
                select(ProjectTeamRelation.team_id).where(
                    ProjectTeamRelation.organization_id == organization_id,
                    ProjectTeamRelation.project_id == subject_id,
                    ProjectTeamRelation.team_id.in_(led_teams),
                    ProjectTeamRelation.role == "owner",
                    ProjectTeamRelation.state == "current",
                )
            )
            is not None
        )
    if subject_kind == "technology" and not owner_assignment:
        return (
            await db.scalar(
                select(Technology.id).where(
                    Technology.organization_id == organization_id,
                    Technology.id == subject_id,
                    Technology.owner_account_id == principal_id,
                    Technology.redirect_id.is_(None),
                    Technology.lifecycle != "archived",
                )
            )
            is not None
        )
    return False


async def profile_target(
    db: AsyncSession,
    organization_id: str,
    subject: EntityProfileSubject,
    *,
    lock: bool = False,
) -> ProfileRow:
    kind, identity = subject.subject_kind, subject.subject_id
    if kind == "employee":
        statement = select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.account_id == identity,
        )
        row = await db.scalar(statement.with_for_update() if lock else statement)
    elif kind == "technology":
        row = await db.get(Technology, (organization_id, identity), with_for_update=lock)
        if row is not None and row.redirect_id is not None:
            row = None
    else:
        model = CorporateTeam if kind == "team" else CorporateProject
        statement = select(model).where(
            model.organization_id == organization_id,
            model.id == identity,
        )
        row = await db.scalar(statement.with_for_update() if lock else statement)
        if isinstance(row, CorporateProject):
            anchor = await db.get(ProjectIdentity, identity)
            if row.lifecycle == "deleted" or anchor is None or anchor.state == "deleted":
                row = None
    if row is None:
        raise ApiError(ErrorCategory.PERMISSION, "profile is unavailable")
    return row


async def _view(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    subject: EntityProfileSubject,
    row: ProfileRow,
) -> EntityProfileView:
    fields = EntityProfileFields.model_validate(
        row.profile
        or {
            "description": getattr(row, "description", "") or "",
        }
    )
    if isinstance(row, OrganizationMembership):
        account = await db.get(Account, row.account_id)
        name = row.display_name or (account.display_name if account else None) or "Employee"
    else:
        name = row.name
    avatar = await db.get(AvatarAsset, fields.avatar_asset_id) if fields.avatar_asset_id else None
    owner_id = row.owner_account_id if isinstance(row, Technology) else None
    if owner_id is not None:
        owner_active = await db.scalar(
            select(OrganizationMembership.id).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.account_id == owner_id,
                OrganizationMembership.state == "active",
            )
        )
        if owner_active is None or not await has_corporate_permission(
            db,
            organization_id=organization_id,
            principal_type="user",
            principal_id=ctx.account_id,
            permission="member.read",
            scope_kind="organization",
            scope_id=organization_id,
        ):
            owner_id = None
    return EntityProfileView(
        **subject.model_dump(),
        organization_id=organization_id,
        name=name,
        fields=fields,
        revision=row.profile_revision or 0,
        can_edit=await can_edit_profile(
            db, ctx=ctx, organization_id=organization_id, **subject.model_dump()
        ),
        avatar_url=avatar.public_url if avatar and avatar.state == "ready" else None,
        owner_account_id=owner_id,
    )


async def read_profile(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    subject: EntityProfileSubject,
) -> EntityProfileView:
    await service.organization_and_membership(db, ctx=ctx, organization_id=organization_id)
    editable = await can_edit_profile(
        db, ctx=ctx, organization_id=organization_id, **subject.model_dump()
    )
    if not editable:
        kind = "member" if subject.subject_kind == "employee" else subject.subject_kind
        await service.authorize(
            db,
            ctx=ctx,
            organization_id=organization_id,
            permission=f"{kind}.read",
            scope_kind="organization" if kind == "member" else kind,
            scope_id=organization_id if kind == "member" else subject.subject_id,
        )
    row = await profile_target(db, organization_id, subject)
    return await _view(db, ctx=ctx, organization_id=organization_id, subject=subject, row=row)


async def write_profile(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    subject: EntityProfileSubject,
    payload: EntityProfileWriteRequest | TechnologyOwnerRequest,
    request_id: str | None,
) -> EntityProfileView:
    owner_assignment = isinstance(payload, TechnologyOwnerRequest)
    if owner_assignment and subject.subject_kind != "technology":
        raise ApiError(ErrorCategory.VALIDATION, "ownership requires a technology")
    operation = "technology.owner.update" if owner_assignment else "entity.profile.update"
    fingerprint = service.mutation_fingerprint(
        {**subject.model_dump(), **payload.model_dump(mode="json", exclude={"idempotency_key"})}
    )
    _, receipt = await service.authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="entity_profile.owner" if owner_assignment else "entity_profile.update",
        scope_kind=subject.subject_kind,
        scope_id=subject.subject_id,
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation=operation,
        fingerprint=fingerprint,
        request_id=request_id,
    )
    if receipt is not None:
        return EntityProfileView.model_validate(receipt.response_body)
    row = await profile_target(db, organization_id, subject, lock=True)
    if (row.profile_revision or 0) != payload.expected_revision:
        raise ApiError(ErrorCategory.PRECONDITION, "profile revision is stale")
    if isinstance(payload, TechnologyOwnerRequest):
        if not isinstance(row, Technology):
            raise ApiError(ErrorCategory.VALIDATION, "ownership requires a technology")
        if payload.owner_account_id is not None:
            active = await db.scalar(
                select(OrganizationMembership.id).where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.account_id == payload.owner_account_id,
                    OrganizationMembership.state == "active",
                )
            )
            if active is None:
                raise ApiError(ErrorCategory.PERMISSION, "owner is unavailable")
        row.owner_account_id = payload.owner_account_id
    else:
        fields = payload.fields
        if fields.avatar_asset_id:
            asset = await db.get(AvatarAsset, fields.avatar_asset_id)
            previous = EntityProfileFields.model_validate(row.profile or {})
            if (
                asset is None
                or asset.state != "ready"
                or not asset.content_type.startswith("image/")
                or (
                    asset.account_id != ctx.account_id
                    and fields.avatar_asset_id != previous.avatar_asset_id
                )
            ):
                raise ApiError(ErrorCategory.PERMISSION, "avatar is unavailable")
        previous_media = EntityProfileFields.model_validate(row.profile or {}).media
        for media in fields.media:
            if media.url.startswith("/v1/media/avatars/"):
                uploaded = await db.get(AvatarAsset, media.url.rsplit("/", 1)[-1])
                if (
                    uploaded is None
                    or uploaded.state != "ready"
                    or (
                        uploaded.account_id != ctx.account_id
                        and media.url not in {item.url for item in previous_media}
                    )
                    or ("video" if uploaded.content_type.startswith("video/") else "image")
                    != media.kind
                ):
                    raise ApiError(ErrorCategory.PERMISSION, "media is unavailable")
            if media.url.startswith("/v1/media/component/"):
                asset = await db.get(ComponentMedia, media.url.rsplit("/", 1)[-1])
                if (
                    asset is None
                    or asset.state != "ready"
                    or asset.kind != media.kind
                    or (
                        asset.owner_account_id != ctx.account_id
                        and media.url not in {item.url for item in previous_media}
                    )
                ):
                    raise ApiError(ErrorCategory.PERMISSION, "media is unavailable")
        row.profile = fields.model_dump(mode="json")
    row.profile_revision = (row.profile_revision or 0) + 1
    await db.flush()
    response = await _view(db, ctx=ctx, organization_id=organization_id, subject=subject, row=row)
    await service.store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation=operation,
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action=operation,
        target_table=row.__tablename__,
        target_id=subject.subject_id,
        request_id=request_id,
    )
    return response
