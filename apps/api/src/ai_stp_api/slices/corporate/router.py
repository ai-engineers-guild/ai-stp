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
from ai_stp_api.slices.corporate import (
    assignments,
    directory,
    governance,
    heartbeat,
    overview,
    permissions,
    profiles,
    service,
    telemetry_policy,
    telemetry_rights,
    usage_events,
    usage_reports,
)
from ai_stp_api.slices.corporate.profile_router import router as profile_router
from ai_stp_contracts.corporate import (
    AccountId,
    CorporateAssignmentPlan,
    CorporateAssignmentPlanRequest,
    CorporateAuditExport,
    CorporateAuditList,
    CorporateBinding,
    CorporateBindingList,
    CorporateBindingRequest,
    CorporateBindingUpdateRequest,
    CorporateBootstrapRequest,
    CorporateCatalogAssignment,
    CorporateCatalogAssignmentList,
    CorporateCatalogAssignmentQuery,
    CorporateCatalogAssignmentRequest,
    CorporateCatalogUsageList,
    CorporateCatalogUsageQuery,
    CorporateContext,
    CorporateDeleteRequest,
    CorporateDeleteResult,
    CorporateDistributionRequest,
    CorporateDistributionResult,
    CorporateDistributionStateList,
    CorporateDistributionStateQuery,
    CorporateEffectiveAssignment,
    CorporateEffectiveAssignmentQuery,
    CorporateJobTitleCreateRequest,
    CorporateJobTitleList,
    CorporateJobTitleUpdateRequest,
    CorporateJobTitleView,
    CorporateMember,
    CorporateMemberCreateRequest,
    CorporateMemberList,
    CorporateMemberProfileRequest,
    CorporateMembershipAssignment,
    CorporateMembershipAssignmentRequest,
    CorporateMemberUpdateRequest,
    CorporateOrganization,
    CorporateOverview,
    CorporateProjectCreateRequest,
    CorporateProjectLifecycleRequest,
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
    OrganizationId,
)
from ai_stp_contracts.corporate_directory import CorporateDirectoryQuery, CorporateDirectoryView
from ai_stp_contracts.http import Timestamp

router = APIRouter(tags=["corporate"])
router.include_router(profile_router)
router.include_router(governance.router)
router.include_router(permissions.router)
router.include_router(telemetry_policy.router)
router.include_router(telemetry_rights.router)
router.include_router(heartbeat.router)
router.include_router(usage_events.router)
router.include_router(usage_reports.router)


@router.get(
    "/corporate/organizations/{organization_id}/directory", response_model=CorporateDirectoryView
)
async def read_directory(
    organization_id: OrganizationId,
    query: Annotated[CorporateDirectoryQuery, Query()],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateDirectoryView:
    return await directory.read_directory(
        db,
        ctx=ctx,
        organization_id=organization_id,
        query=query,
        request_id=_request_id(request),
    )


@router.get("/corporate/organizations/{organization_id}/overview", response_model=CorporateOverview)
async def read_overview(
    organization_id: OrganizationId,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateOverview:
    return await overview.read_overview(
        db, ctx=ctx, organization_id=organization_id, request_id=_request_id(request)
    )


@router.patch(
    "/corporate/organizations/{organization_id}/members/{account_id}/profile",
    response_model=CorporateMember,
)
async def update_member_profile(
    organization_id: OrganizationId,
    account_id: AccountId,
    payload: CorporateMemberProfileRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateMember:
    return await profiles.update_member_profile(
        db,
        ctx=ctx,
        organization_id=organization_id,
        account_id=account_id,
        payload=payload,
        request_id=_request_id(request),
    )


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@router.get(
    "/corporate/organizations/{organization_id}/projects/{project_id}/members",
    response_model=CorporateMemberList,
)
async def list_project_members(
    organization_id: str,
    project_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateMemberList:
    return await service.list_project_members(
        db,
        ctx=ctx,
        organization_id=organization_id,
        project_id=project_id,
        request_id=_request_id(request),
    )


@router.get(
    "/corporate/organizations/{organization_id}/members/{account_id}/projects",
    response_model=CorporateProjectList,
)
async def list_member_projects(
    organization_id: str,
    account_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateProjectList:
    return await service.list_member_projects(
        db,
        ctx=ctx,
        organization_id=organization_id,
        account_id=account_id,
        request_id=_request_id(request),
    )


@router.get(
    "/corporate/organizations/{organization_id}/catalog-assignments",
    response_model=CorporateCatalogAssignmentList,
)
async def list_catalog_assignments(
    organization_id: str,
    query: Annotated[CorporateCatalogAssignmentQuery, Query()],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateCatalogAssignmentList:
    return await assignments.list_assignments(
        db, ctx=ctx, organization_id=organization_id, query=query, request_id=_request_id(request)
    )


@router.get(
    "/corporate/organizations/{organization_id}/catalog-assignments/effective",
    response_model=CorporateEffectiveAssignment,
)
async def read_effective_assignment(
    organization_id: str,
    query: Annotated[CorporateEffectiveAssignmentQuery, Query()],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateEffectiveAssignment:
    return await assignments.resolve_effective(
        db, ctx=ctx, organization_id=organization_id, query=query, request_id=_request_id(request)
    )


@router.get(
    "/corporate/organizations/{organization_id}/catalog-usage",
    response_model=CorporateCatalogUsageList,
)
async def list_catalog_usage(
    organization_id: str,
    query: Annotated[CorporateCatalogUsageQuery, Query()],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateCatalogUsageList:
    return await assignments.list_usage(
        db, ctx=ctx, organization_id=organization_id, query=query, request_id=_request_id(request)
    )


@router.put(
    "/corporate/organizations/{organization_id}/catalog-assignments",
    response_model=CorporateCatalogAssignment,
)
async def write_catalog_assignment(
    organization_id: str,
    payload: CorporateCatalogAssignmentRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateCatalogAssignment:
    return await assignments.write_assignment(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        request_id=_request_id(request),
    )


@router.post(
    "/corporate/organizations/{organization_id}/catalog-assignments/distribution",
    response_model=CorporateDistributionResult,
)
async def distribute_catalog_assignment(
    organization_id: str,
    payload: CorporateDistributionRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateDistributionResult:
    return await assignments.distribute_assignment(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        request_id=_request_id(request),
    )


@router.get(
    "/corporate/organizations/{organization_id}/catalog-assignments/distribution",
    response_model=CorporateDistributionStateList,
)
async def list_catalog_assignment_distribution(
    organization_id: str,
    query: Annotated[CorporateDistributionStateQuery, Query()],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateDistributionStateList:
    return await assignments.list_distribution(
        db, ctx=ctx, organization_id=organization_id, query=query, request_id=_request_id(request)
    )


@router.post(
    "/corporate/organizations/{organization_id}/catalog-assignments/plan",
    response_model=CorporateAssignmentPlan,
)
async def plan_catalog_assignments(
    organization_id: str,
    payload: CorporateAssignmentPlanRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateAssignmentPlan:
    return await assignments.plan_assignments(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        request_id=_request_id(request),
    )


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


@router.post(
    "/corporate/organizations/{organization_id}/job-titles",
    response_model=CorporateJobTitleView,
)
async def create_job_title(
    organization_id: str,
    payload: CorporateJobTitleCreateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateJobTitleView:
    return await service.create_job_title(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        request_id=_request_id(request),
    )


@router.get(
    "/corporate/organizations/{organization_id}/job-titles",
    response_model=CorporateJobTitleList,
)
async def list_job_titles(
    organization_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateJobTitleList:
    return await service.list_job_titles(
        db,
        ctx=ctx,
        organization_id=organization_id,
        request_id=_request_id(request),
    )


@router.patch(
    "/corporate/organizations/{organization_id}/job-titles/{job_title_id}",
    response_model=CorporateJobTitleView,
)
async def update_job_title(
    organization_id: str,
    job_title_id: str,
    payload: CorporateJobTitleUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateJobTitleView:
    return await service.update_job_title(
        db,
        ctx=ctx,
        organization_id=organization_id,
        job_title_id=job_title_id,
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


@router.post(
    "/corporate/organizations/{organization_id}/projects/{project_id}/lifecycle",
    response_model=CorporateProjectView,
)
async def change_project_lifecycle(
    organization_id: str,
    project_id: str,
    payload: CorporateProjectLifecycleRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateProjectView:
    return await service.change_project_lifecycle(
        db,
        ctx=ctx,
        organization_id=organization_id,
        project_id=project_id,
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
