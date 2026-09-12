"""Corporate core HTTP routes."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_db, get_settings, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.settings import Settings
from ai_stp_api.slices.corporate import service
from ai_stp_contracts.corporate import (
    CorporateAuditExport,
    CorporateAuditList,
    CorporateBinding,
    CorporateBindingList,
    CorporateBindingRequest,
    CorporateBindingUpdateRequest,
    CorporateBootstrapRequest,
    CorporateContext,
    CorporateDeleteRequest,
    CorporateDeleteResult,
    CorporateMember,
    CorporateMemberCreateRequest,
    CorporateMemberList,
    CorporateMembershipAssignment,
    CorporateMembershipAssignmentRequest,
    CorporateMemberUpdateRequest,
    CorporateOrganization,
    CorporateProjectCreateRequest,
    CorporateProjectList,
    CorporateProjectUpdateRequest,
    CorporateProjectView,
    CorporateRoleCreateRequest,
    CorporateRoleList,
    CorporateRoleUpdateRequest,
    CorporateRoleView,
    CorporateServicePrincipalCreateRequest,
    CorporateServicePrincipalList,
    CorporateServicePrincipalUpdateRequest,
    CorporateServicePrincipalView,
    CorporateTeamCreateRequest,
    CorporateTeamList,
    CorporateTeamUpdateRequest,
    CorporateTeamView,
)
from ai_stp_contracts.http import Timestamp

router = APIRouter(tags=["corporate"])


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@router.post("/corporate/bootstrap", response_model=CorporateOrganization)
async def bootstrap(
    payload: CorporateBootstrapRequest,
    request: Request,
    bootstrap_secret: Annotated[str, Header(alias="X-AI-STP-Bootstrap-Secret")],
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CorporateOrganization:
    configured = settings.corporate.bootstrap_secret
    if not configured or not secrets.compare_digest(bootstrap_secret, configured):
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "bootstrap authentication failed")
    return await service.bootstrap(db, payload=payload, request_id=_request_id(request))


@router.get("/corporate/organizations/{organization_id}/context", response_model=CorporateContext)
async def read_context(
    organization_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateContext:
    return await service.read_context(
        db, ctx=ctx, organization_id=organization_id, request_id=_request_id(request)
    )


@router.post("/corporate/organizations/{organization_id}/members", response_model=CorporateMember)
async def create_member(
    organization_id: str,
    payload: CorporateMemberCreateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateMember:
    return await service.create_member(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        request_id=_request_id(request),
    )


@router.get(
    "/corporate/organizations/{organization_id}/members", response_model=CorporateMemberList
)
async def list_members(
    organization_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateMemberList:
    return await service.list_members(
        db, ctx=ctx, organization_id=organization_id, request_id=_request_id(request)
    )


@router.patch(
    "/corporate/organizations/{organization_id}/members/{account_id}",
    response_model=CorporateMember,
)
async def update_member(
    organization_id: str,
    account_id: str,
    payload: CorporateMemberUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateMember:
    return await service.update_member(
        db,
        ctx=ctx,
        organization_id=organization_id,
        account_id=account_id,
        payload=payload,
        request_id=_request_id(request),
    )


@router.delete(
    "/corporate/organizations/{organization_id}/members/{account_id}",
    response_model=CorporateDeleteResult,
)
async def delete_member(
    organization_id: str,
    account_id: str,
    payload: CorporateDeleteRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateDeleteResult:
    return await service.delete_member(
        db,
        ctx=ctx,
        organization_id=organization_id,
        account_id=account_id,
        payload=payload,
        request_id=_request_id(request),
    )


@router.get(
    "/corporate/organizations/{organization_id}/members/{account_id}",
    response_model=CorporateMember,
)
async def read_member(
    organization_id: str,
    account_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateMember:
    return await service.read_member(
        db,
        ctx=ctx,
        organization_id=organization_id,
        account_id=account_id,
        request_id=_request_id(request),
    )


@router.post("/corporate/organizations/{organization_id}/bindings", response_model=CorporateBinding)
async def create_binding(
    organization_id: str,
    payload: CorporateBindingRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateBinding:
    return await service.create_binding(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        request_id=_request_id(request),
    )


@router.get(
    "/corporate/organizations/{organization_id}/bindings", response_model=CorporateBindingList
)
async def list_bindings(
    organization_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateBindingList:
    return await service.list_bindings(
        db, ctx=ctx, organization_id=organization_id, request_id=_request_id(request)
    )


@router.get(
    "/corporate/organizations/{organization_id}/bindings/{binding_id}",
    response_model=CorporateBinding,
)
async def read_binding(
    organization_id: str,
    binding_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateBinding:
    return await service.read_binding(
        db,
        ctx=ctx,
        organization_id=organization_id,
        binding_id=binding_id,
        request_id=_request_id(request),
    )


@router.patch(
    "/corporate/organizations/{organization_id}/bindings/{binding_id}",
    response_model=CorporateBinding,
)
async def update_binding(
    organization_id: str,
    binding_id: str,
    payload: CorporateBindingUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateBinding:
    return await service.update_binding(
        db,
        ctx=ctx,
        organization_id=organization_id,
        binding_id=binding_id,
        payload=payload,
        request_id=_request_id(request),
    )


@router.delete(
    "/corporate/organizations/{organization_id}/bindings/{binding_id}",
    response_model=CorporateDeleteResult,
)
async def delete_binding(
    organization_id: str,
    binding_id: str,
    payload: CorporateDeleteRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateDeleteResult:
    return await service.delete_binding(
        db,
        ctx=ctx,
        organization_id=organization_id,
        binding_id=binding_id,
        payload=payload,
        request_id=_request_id(request),
    )


@router.post("/corporate/organizations/{organization_id}/roles", response_model=CorporateRoleView)
async def create_role(
    organization_id: str,
    payload: CorporateRoleCreateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateRoleView:
    return await service.create_role(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        request_id=_request_id(request),
    )


@router.get("/corporate/organizations/{organization_id}/roles", response_model=CorporateRoleList)
async def list_roles(
    organization_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateRoleList:
    return await service.list_roles(
        db, ctx=ctx, organization_id=organization_id, request_id=_request_id(request)
    )


@router.get(
    "/corporate/organizations/{organization_id}/roles/{role_name}",
    response_model=CorporateRoleView,
)
async def read_role(
    organization_id: str,
    role_name: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateRoleView:
    return await service.read_role(
        db,
        ctx=ctx,
        organization_id=organization_id,
        role_name=role_name,
        request_id=_request_id(request),
    )


@router.patch(
    "/corporate/organizations/{organization_id}/roles/{role_name}",
    response_model=CorporateRoleView,
)
async def update_role(
    organization_id: str,
    role_name: str,
    payload: CorporateRoleUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateRoleView:
    return await service.update_role(
        db,
        ctx=ctx,
        organization_id=organization_id,
        role_name=role_name,
        payload=payload,
        request_id=_request_id(request),
    )


@router.delete(
    "/corporate/organizations/{organization_id}/roles/{role_name}",
    response_model=CorporateDeleteResult,
)
async def delete_role(
    organization_id: str,
    role_name: str,
    payload: CorporateDeleteRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateDeleteResult:
    return await service.delete_role(
        db,
        ctx=ctx,
        organization_id=organization_id,
        role_name=role_name,
        payload=payload,
        request_id=_request_id(request),
    )


@router.post(
    "/corporate/organizations/{organization_id}/membership-assignments",
    response_model=CorporateMembershipAssignment,
)
async def assign_member(
    organization_id: str,
    payload: CorporateMembershipAssignmentRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateMembershipAssignment:
    return await service.assign_member(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        request_id=_request_id(request),
    )


@router.post(
    "/corporate/organizations/{organization_id}/projects", response_model=CorporateProjectView
)
async def create_project(
    organization_id: str,
    payload: CorporateProjectCreateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateProjectView:
    return await service.create_project(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        request_id=_request_id(request),
    )


@router.get(
    "/corporate/organizations/{organization_id}/projects", response_model=CorporateProjectList
)
async def list_projects(
    organization_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateProjectList:
    return await service.list_projects(
        db, ctx=ctx, organization_id=organization_id, request_id=_request_id(request)
    )


@router.get(
    "/corporate/organizations/{organization_id}/projects/{project_id}",
    response_model=CorporateProjectView,
)
async def read_project(
    organization_id: str,
    project_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateProjectView:
    return await service.read_project(
        db,
        ctx=ctx,
        organization_id=organization_id,
        project_id=project_id,
        request_id=_request_id(request),
    )


@router.patch(
    "/corporate/organizations/{organization_id}/projects/{project_id}",
    response_model=CorporateProjectView,
)
async def update_project(
    organization_id: str,
    project_id: str,
    payload: CorporateProjectUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateProjectView:
    return await service.update_project(
        db,
        ctx=ctx,
        organization_id=organization_id,
        project_id=project_id,
        payload=payload,
        request_id=_request_id(request),
    )


@router.delete(
    "/corporate/organizations/{organization_id}/projects/{project_id}",
    response_model=CorporateDeleteResult,
)
async def delete_project(
    organization_id: str,
    project_id: str,
    payload: CorporateDeleteRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateDeleteResult:
    return await service.delete_project(
        db,
        ctx=ctx,
        organization_id=organization_id,
        project_id=project_id,
        payload=payload,
        request_id=_request_id(request),
    )


@router.post("/corporate/organizations/{organization_id}/teams", response_model=CorporateTeamView)
async def create_team(
    organization_id: str,
    payload: CorporateTeamCreateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateTeamView:
    return await service.create_team(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        request_id=_request_id(request),
    )


@router.get("/corporate/organizations/{organization_id}/teams", response_model=CorporateTeamList)
async def list_teams(
    organization_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateTeamList:
    return await service.list_teams(
        db, ctx=ctx, organization_id=organization_id, request_id=_request_id(request)
    )


@router.get(
    "/corporate/organizations/{organization_id}/teams/{team_id}",
    response_model=CorporateTeamView,
)
async def read_team(
    organization_id: str,
    team_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateTeamView:
    return await service.read_team(
        db,
        ctx=ctx,
        organization_id=organization_id,
        team_id=team_id,
        request_id=_request_id(request),
    )


@router.patch(
    "/corporate/organizations/{organization_id}/teams/{team_id}",
    response_model=CorporateTeamView,
)
async def update_team(
    organization_id: str,
    team_id: str,
    payload: CorporateTeamUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateTeamView:
    return await service.update_team(
        db,
        ctx=ctx,
        organization_id=organization_id,
        team_id=team_id,
        payload=payload,
        request_id=_request_id(request),
    )


@router.delete(
    "/corporate/organizations/{organization_id}/teams/{team_id}",
    response_model=CorporateDeleteResult,
)
async def delete_team(
    organization_id: str,
    team_id: str,
    payload: CorporateDeleteRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateDeleteResult:
    return await service.delete_team(
        db,
        ctx=ctx,
        organization_id=organization_id,
        team_id=team_id,
        payload=payload,
        request_id=_request_id(request),
    )


@router.post(
    "/corporate/organizations/{organization_id}/service-principals",
    response_model=CorporateServicePrincipalView,
)
async def create_service_principal(
    organization_id: str,
    payload: CorporateServicePrincipalCreateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateServicePrincipalView:
    return await service.create_service_principal(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        request_id=_request_id(request),
    )


@router.get(
    "/corporate/organizations/{organization_id}/service-principals",
    response_model=CorporateServicePrincipalList,
)
async def list_service_principals(
    organization_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateServicePrincipalList:
    return await service.list_service_principals(
        db, ctx=ctx, organization_id=organization_id, request_id=_request_id(request)
    )


@router.get(
    "/corporate/organizations/{organization_id}/service-principals/{service_principal_id}",
    response_model=CorporateServicePrincipalView,
)
async def read_service_principal(
    organization_id: str,
    service_principal_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateServicePrincipalView:
    return await service.read_service_principal(
        db,
        ctx=ctx,
        organization_id=organization_id,
        service_principal_id=service_principal_id,
        request_id=_request_id(request),
    )


@router.patch(
    "/corporate/organizations/{organization_id}/service-principals/{service_principal_id}",
    response_model=CorporateServicePrincipalView,
)
async def update_service_principal(
    organization_id: str,
    service_principal_id: str,
    payload: CorporateServicePrincipalUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateServicePrincipalView:
    return await service.update_service_principal(
        db,
        ctx=ctx,
        organization_id=organization_id,
        service_principal_id=service_principal_id,
        payload=payload,
        request_id=_request_id(request),
    )


@router.delete(
    "/corporate/organizations/{organization_id}/service-principals/{service_principal_id}",
    response_model=CorporateDeleteResult,
)
async def delete_service_principal(
    organization_id: str,
    service_principal_id: str,
    payload: CorporateDeleteRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateDeleteResult:
    return await service.delete_service_principal(
        db,
        ctx=ctx,
        organization_id=organization_id,
        service_principal_id=service_principal_id,
        payload=payload,
        request_id=_request_id(request),
    )


@router.get("/corporate/organizations/{organization_id}/audit", response_model=CorporateAuditList)
async def list_audit(
    organization_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    before_id: Annotated[int | None, Query(ge=1)] = None,
    before_created_at: Timestamp | None = None,
    actor_account_id: Annotated[str | None, Query(max_length=64)] = None,
    action: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
    target_id: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
    created_from: Timestamp | None = None,
    created_to: Timestamp | None = None,
) -> CorporateAuditList:
    return await service.list_audit(
        db,
        ctx=ctx,
        organization_id=organization_id,
        before_id=before_id,
        before_created_at=before_created_at,
        actor_account_id=actor_account_id,
        action=action,
        target_id=target_id,
        created_from=created_from,
        created_to=created_to,
        request_id=_request_id(request),
    )


@router.get(
    "/corporate/organizations/{organization_id}/audit/export",
    response_model=CorporateAuditExport,
)
async def export_audit(
    organization_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    before_id: Annotated[int | None, Query(ge=1)] = None,
    before_created_at: Timestamp | None = None,
    actor_account_id: Annotated[str | None, Query(max_length=64)] = None,
    action: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
    target_id: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
    created_from: Timestamp | None = None,
    created_to: Timestamp | None = None,
) -> CorporateAuditExport:
    return await service.export_audit(
        db,
        ctx=ctx,
        organization_id=organization_id,
        before_id=before_id,
        before_created_at=before_created_at,
        actor_account_id=actor_account_id,
        action=action,
        target_id=target_id,
        created_from=created_from,
        created_to=created_to,
        request_id=_request_id(request),
    )
