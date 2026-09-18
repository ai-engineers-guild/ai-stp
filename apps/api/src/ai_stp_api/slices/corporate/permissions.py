"""Effective corporate permission matrix for the current tenant principal."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import service
from ai_stp_contracts.corporate import OrganizationId
from ai_stp_contracts.corporate_governance import (
    CorporateEffectivePermission,
    CorporatePermissionDefinition,
    CorporatePermissionMatrix,
)
from ai_stp_platform.corporate_authorization import has_corporate_permission
from ai_stp_platform.organization_models import CorporateRoleBinding

router = APIRouter(tags=["corporate"])
_SCOPES = ("organization", "team", "project", "technology", "catalog_object")


@router.get(
    "/corporate/organizations/{organization_id}/permissions/matrix",
    response_model=CorporatePermissionMatrix,
)
async def read_permission_matrix(
    organization_id: OrganizationId,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporatePermissionMatrix:
    await service.authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="role.read",
    )
    bindings = list(
        (
            await db.scalars(
                select(CorporateRoleBinding).where(
                    CorporateRoleBinding.organization_id == organization_id,
                    CorporateRoleBinding.account_id == ctx.account_id,
                    CorporateRoleBinding.principal_type == "user",
                    CorporateRoleBinding.state == "active",
                )
            )
        ).all()
    )
    definitions = [
        CorporatePermissionDefinition(
            name=permission,
            scopes=list(_SCOPES),
            group=permission.split(".", 1)[0],
        )
        for permission in sorted(service.KNOWN_PERMISSIONS)
    ]
    effective: list[CorporateEffectivePermission] = []
    for binding in bindings:
        scope_kind = binding.scope_kind if binding.scope_kind in _SCOPES else "organization"
        scope_id = organization_id if binding.scope_id == "*" else binding.scope_id
        for permission in sorted(service.KNOWN_PERMISSIONS):
            if await has_corporate_permission(
                db,
                organization_id=organization_id,
                principal_type="user",
                principal_id=ctx.account_id,
                permission=permission,
                scope_kind=scope_kind,
                scope_id=scope_id,
            ):
                existing = next(
                    (
                        item
                        for item in effective
                        if item.permission == permission
                        and item.scope_kind == scope_kind
                        and item.scope_id == scope_id
                    ),
                    None,
                )
                if existing is None:
                    effective.append(
                        CorporateEffectivePermission(
                            permission=permission,
                            scope_kind=scope_kind,
                            scope_id=scope_id,
                            sources=[binding.role],
                        )
                    )
                elif binding.role not in existing.sources:
                    existing.sources.append(binding.role)
    organization = await service.authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="organization.read",
    )
    return CorporatePermissionMatrix(
        organization_id=organization_id,
        authorization_revision=organization[0].policy_revision,
        definitions=definitions,
        effective=sorted(
            effective,
            key=lambda item: (item.scope_kind, item.scope_id, item.permission),
        ),
    )
