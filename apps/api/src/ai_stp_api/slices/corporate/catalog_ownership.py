"""Independent operational ownership, with a separately registered router."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import entity_profiles, service
from ai_stp_contracts.corporate import OrganizationId
from ai_stp_contracts.corporate_catalog_ownership import (
    CorporateCatalogOwnership,
    CorporateCatalogOwnershipQuery,
    CorporateCatalogOwnershipRequest,
)
from ai_stp_platform.catalog_ownership_models import CorporateCatalogOwnership as OwnershipRow
from ai_stp_platform.catalog_read import get_visible_metadata
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import OrganizationMembership

router = APIRouter(tags=["corporate"])
PATH = "/corporate/organizations/{organization_id}/catalog-ownership"


async def _catalog(
    db: AsyncSession, subject: CorporateCatalogOwnershipQuery, account_id: str
) -> None:
    catalog = await get_visible_metadata(
        db,
        object_kind=subject.object_kind,
        stable_id=subject.stable_id,
        version=subject.version,
        account_id=account_id,
    )
    if (
        catalog is None
        or catalog.published_at is None
        or catalog.lifecycle_state
        not in {
            "active",
            "deprecated",
        }
    ):
        raise ApiError(ErrorCategory.PERMISSION, "catalog version is unavailable")


async def _owner(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    subject: CorporateCatalogOwnershipQuery,
    account_id: str,
    request_id: str | None,
    can_edit: bool = False,
) -> str | None:
    employee = None
    if not can_edit:
        employee = await service.read_member(
            db,
            ctx=ctx,
            organization_id=organization_id,
            account_id=account_id,
            request_id=request_id,
        )
    member = await db.scalar(
        select(OrganizationMembership)
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.account_id == account_id,
            OrganizationMembership.state == "active",
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if member is None:
        raise ApiError(ErrorCategory.PERMISSION, "owner employee is unavailable")
    await _catalog(db, subject, account_id)
    if employee is not None:
        return employee.display_name
    account = await db.get(Account, account_id)
    if account is None:
        raise ApiError(ErrorCategory.PERMISSION, "owner employee is unavailable")
    return service.member_view(member, account).display_name


def _view(
    organization_id: str,
    subject: CorporateCatalogOwnershipQuery,
    row: OwnershipRow | None,
    *,
    owner_display_name: str | None,
    can_edit: bool,
) -> CorporateCatalogOwnership:
    return CorporateCatalogOwnership(
        organization_id=organization_id,
        object_kind=subject.object_kind,
        stable_id=subject.stable_id,
        owner_account_id=row.owner_account_id if row else None,
        revision=row.revision if row else 0,
        owner_display_name=owner_display_name,
        can_edit=can_edit,
    )


async def read_ownership(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    subject: CorporateCatalogOwnershipQuery,
    request_id: str | None,
) -> CorporateCatalogOwnership:
    await service.authorize(
        db, ctx=ctx, organization_id=organization_id, permission="organization.read"
    )
    await _catalog(db, subject, ctx.account_id)
    can_edit = await entity_profiles.can_edit_profile(
        db,
        ctx=ctx,
        organization_id=organization_id,
        subject_kind="catalog_object",
        subject_id=subject.stable_id,
        owner_assignment=True,
    )
    row = await db.get(OwnershipRow, (organization_id, subject.object_kind, subject.stable_id))
    owner_display_name = None
    if row is not None and row.owner_account_id is not None:
        owner_display_name = await _owner(
            db,
            ctx=ctx,
            organization_id=organization_id,
            subject=subject,
            account_id=row.owner_account_id,
            request_id=request_id,
            can_edit=can_edit,
        )
    return _view(
        organization_id, subject, row, owner_display_name=owner_display_name, can_edit=can_edit
    )


async def write_ownership(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: CorporateCatalogOwnershipRequest,
    request_id: str | None,
) -> CorporateCatalogOwnership:
    fingerprint = service.mutation_fingerprint(
        payload.model_dump(mode="json", exclude={"idempotency_key"})
    )
    _, receipt = await service.authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="entity_profile.owner",
        scope_kind="catalog_object",
        scope_id=payload.stable_id,
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="catalog_ownership.write",
        fingerprint=fingerprint,
        request_id=request_id,
    )
    await _catalog(db, payload, ctx.account_id)
    owner_display_name = None
    if payload.owner_account_id is not None:
        owner_display_name = await _owner(
            db,
            ctx=ctx,
            organization_id=organization_id,
            subject=payload,
            account_id=payload.owner_account_id,
            request_id=request_id,
            can_edit=True,
        )
    if receipt is not None:
        return CorporateCatalogOwnership.model_validate(
            {**receipt.response_body, "owner_display_name": owner_display_name, "can_edit": True}
        )
    row = await db.get(OwnershipRow, (organization_id, payload.object_kind, payload.stable_id))
    if (row.revision if row else 0) != payload.expected_revision:
        raise ApiError(ErrorCategory.PRECONDITION, "ownership revision is stale")
    if row is None:
        row = OwnershipRow(
            organization_id=organization_id,
            object_kind=payload.object_kind,
            stable_id=payload.stable_id,
            owner_account_id=payload.owner_account_id,
            revision=1,
        )
        db.add(row)
    else:
        row.owner_account_id = payload.owner_account_id
        row.revision += 1
    await db.flush()
    response = _view(
        organization_id, payload, row, owner_display_name=owner_display_name, can_edit=True
    )
    await service.store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="catalog_ownership.write",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="catalog_ownership.write",
        target_table="corporate_catalog_ownership",
        target_id=payload.stable_id,
        request_id=request_id,
        payload={
            "object_kind": payload.object_kind,
            "owner_account_id": payload.owner_account_id,
            "revision": row.revision,
        },
    )
    return response


@router.get(PATH, response_model=CorporateCatalogOwnership)
async def get_catalog_ownership(
    organization_id: OrganizationId,
    subject: Annotated[CorporateCatalogOwnershipQuery, Query()],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateCatalogOwnership:
    return await read_ownership(
        db,
        ctx=ctx,
        organization_id=organization_id,
        subject=subject,
        request_id=getattr(request.state, "request_id", None),
    )


@router.put(PATH, response_model=CorporateCatalogOwnership)
async def put_catalog_ownership(
    organization_id: OrganizationId,
    payload: CorporateCatalogOwnershipRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateCatalogOwnership:
    return await write_ownership(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )
