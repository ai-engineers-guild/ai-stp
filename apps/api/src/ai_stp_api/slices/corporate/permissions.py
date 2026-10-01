"""Effective corporate permission matrix for the current tenant principal."""

from typing import Annotated, Literal, cast

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
    CorporatePermissionSource,
)
from ai_stp_platform.corporate_authorization import (
    corporate_effective_permissions,
    role_closure_permissions,
)
from ai_stp_platform.organization_models import (
    CorporatePermissionGrant,
    CorporateRoleBinding,
)

router = APIRouter(tags=["corporate"])
_SCOPES = ("organization", "team", "project", "technology", "catalog_object")

# Scope kinds each resource's handlers actually evaluate against. Everything
# else is organization scope — the matrix must not advertise a scope the API
# never checks (ADR-0220).
_MatrixScope = Literal["organization", "team", "project", "technology", "catalog_object", "member"]
_EffectiveScope = Literal["organization", "team", "project", "technology", "catalog_object"]
_PERMISSION_SCOPES: dict[str, tuple[_MatrixScope, ...]] = {
    "member": ("organization", "member"),
    "project": ("organization", "project"),
    "team": ("organization", "team"),
    "technology": ("organization", "technology"),
    "technology_decision": ("organization", "technology"),
    "technology_team": ("organization", "technology", "team"),
    "project_team": ("organization", "project", "team"),
    "project_technology": ("organization", "project", "technology"),
    "catalog_object": ("organization", "catalog_object"),
    "telemetry": ("organization", "member"),
}


def _definition(permission: str) -> CorporatePermissionDefinition:
    resource, _, action = permission.partition(".")
    return CorporatePermissionDefinition(
        name=permission,
        resource=resource,
        action=action,
        scopes=list(_PERMISSION_SCOPES.get(resource, ("organization",))),
        group=resource,
        create_parent="organization" if action in {"create", "invite"} else None,
    )


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
    grants = list(
        (
            await db.scalars(
                select(CorporatePermissionGrant).where(
                    CorporatePermissionGrant.organization_id == organization_id,
                    CorporatePermissionGrant.account_id == ctx.account_id,
                    CorporatePermissionGrant.principal_type == "user",
                    CorporatePermissionGrant.state == "active",
                )
            )
        ).all()
    )
    role_permissions = await role_closure_permissions(
        db, organization_id=organization_id, roles={binding.role for binding in bindings}
    )
    scope_grants: dict[tuple[str, str], set[str]] = {}

    async def _effective_at(scope_kind: str, scope_id: str) -> set[str]:
        key = (scope_kind, scope_id)
        if key not in scope_grants:
            granted = await corporate_effective_permissions(
                db,
                organization_id=organization_id,
                principal_type="user",
                principal_id=ctx.account_id,
                scope_kind=scope_kind,
                scope_id=scope_id,
            )
            scope_grants[key] = granted or set()
        return scope_grants[key]

    contributions: dict[tuple[str, str, str], list[CorporatePermissionSource]] = {}

    def _record(
        scope_kind: str, scope_id: str, permission: str, source: CorporatePermissionSource
    ) -> None:
        contributions.setdefault((scope_kind, scope_id, permission), []).append(source)

    for binding in bindings:
        scope_kind = binding.scope_kind if binding.scope_kind in _SCOPES else "organization"
        scope_id = binding.scope_id
        effective = await _effective_at(scope_kind, scope_id)
        for permission in sorted(effective & role_permissions.get(binding.role, frozenset())):
            _record(
                scope_kind,
                scope_id,
                permission,
                CorporatePermissionSource(
                    kind="binding",
                    source_id=binding.id,
                    role=binding.role,
                    origin=binding.origin,
                    scope_kind=binding.scope_kind,
                    scope_id=binding.scope_id,
                ),
            )
    for grant in grants:
        scope_kind = grant.scope_kind if grant.scope_kind in _SCOPES else "organization"
        scope_id = grant.scope_id
        effective = await _effective_at(scope_kind, scope_id)
        if grant.permission in effective:
            _record(
                scope_kind,
                scope_id,
                grant.permission,
                CorporatePermissionSource(
                    kind="grant",
                    source_id=grant.id,
                    scope_kind=grant.scope_kind,
                    scope_id=grant.scope_id,
                ),
            )
    effective_rows = [
        CorporateEffectivePermission(
            permission=permission,
            scope_kind=cast(_EffectiveScope, scope_kind),
            scope_id=scope_id,
            sources=sorted({source.role or source.source_id for source in sources}),
            source_records=sources,
        )
        for (scope_kind, scope_id, permission), sources in contributions.items()
    ]
    organization = await service.authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="organization.read",
    )
    return CorporatePermissionMatrix(
        organization_id=organization_id,
        authorization_revision=organization[0].policy_revision,
        definitions=[_definition(permission) for permission in sorted(service.KNOWN_PERMISSIONS)],
        effective=sorted(
            effective_rows,
            key=lambda item: (item.scope_kind, item.scope_id, item.permission),
        ),
    )
