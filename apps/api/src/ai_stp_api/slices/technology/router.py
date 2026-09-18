"""Tenant-scoped technology HTTP surface; all mutations are revision guarded."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.technology import competences, detection, merge, service
from ai_stp_contracts.context import OrganizationId, RemoteProjectId
from ai_stp_contracts.corporate import AccountId
from ai_stp_contracts.technology import (
    CategoryId,
    CategoryLifecycleRequest,
    CategoryList,
    CategoryView,
    CategoryWriteRequest,
    EmployeeTechnologyList,
    EmployeeTechnologyRequest,
    EmployeeTechnologyView,
    MappingVersion,
    ProjectActivityRequest,
    ProjectActivityView,
    ProjectTeamList,
    ProjectTeamView,
    ProjectTeamWriteRequest,
    ProjectTechnologyList,
    ProjectTechnologyView,
    ProjectTechnologyWriteRequest,
    RelationshipListQuery,
    TeamId,
    TechnologyDecisionRequest,
    TechnologyDecisionView,
    TechnologyId,
    TechnologyLandscapePolicyRequest,
    TechnologyLandscapePolicyView,
    TechnologyLandscapeQuery,
    TechnologyLandscapeView,
    TechnologyLifecycleRequest,
    TechnologyList,
    TechnologyMappingRequest,
    TechnologyMappingView,
    TechnologyMergePlanQuery,
    TechnologyMergePlanView,
    TechnologyMergeRequest,
    TechnologyMergeResult,
    TechnologyMutation,
    TechnologyScanId,
    TechnologyScanRequest,
    TechnologyScanResult,
    TechnologyScanView,
    TechnologySearch,
    TechnologySeedRequest,
    TechnologySeedResult,
    TechnologyTeamList,
    TechnologyTeamView,
    TechnologyTeamWriteRequest,
    TechnologyView,
    TechnologyWriteRequest,
)

router = APIRouter(prefix="/corporate/organizations/{organization_id}", tags=["technology"])
Db = Annotated[AsyncSession, Depends(get_db)]
Auth = Annotated[AuthContext, Depends(require_auth)]


@router.get("/members/{account_id}/technologies", response_model=EmployeeTechnologyList)
async def list_member_technologies(
    organization_id: OrganizationId,
    account_id: AccountId,
    request: Request,
    db: Db,
    ctx: Auth,
    include_history: bool = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=256)] = 128,
) -> EmployeeTechnologyList:
    return await competences.list_competences(
        db,
        ctx=ctx,
        organization_id=organization_id,
        account_id=account_id,
        technology_id=None,
        query=RelationshipListQuery(include_history=include_history, offset=offset, limit=limit),
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/technologies/{technology_id}/employees", response_model=EmployeeTechnologyList)
async def list_technology_employees(
    organization_id: OrganizationId,
    technology_id: TechnologyId,
    request: Request,
    db: Db,
    ctx: Auth,
    include_history: bool = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=256)] = 128,
) -> EmployeeTechnologyList:
    return await competences.list_competences(
        db,
        ctx=ctx,
        organization_id=organization_id,
        account_id=None,
        technology_id=technology_id,
        query=RelationshipListQuery(include_history=include_history, offset=offset, limit=limit),
        request_id=getattr(request.state, "request_id", None),
    )


@router.put("/employee-technologies", response_model=EmployeeTechnologyView)
async def write_employee_technology(
    organization_id: OrganizationId,
    payload: EmployeeTechnologyRequest,
    request: Request,
    db: Db,
    ctx: Auth,
) -> EmployeeTechnologyView:
    return await competences.write_competence(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )


@router.delete("/technology-categories/{category_id}", response_model=CategoryView)
async def remove_category(
    organization_id: OrganizationId,
    category_id: CategoryId,
    payload: TechnologyMutation,
    request: Request,
    db: Db,
    ctx: Auth,
) -> CategoryView:
    return await service.change_category_lifecycle(
        db,
        ctx=ctx,
        organization_id=organization_id,
        category_id=category_id,
        payload=CategoryLifecycleRequest(**payload.model_dump(), target="archived"),
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("/technology-categories/{category_id}/lifecycle", response_model=CategoryView)
async def change_category_lifecycle(
    organization_id: OrganizationId,
    category_id: CategoryId,
    payload: CategoryLifecycleRequest,
    request: Request,
    db: Db,
    ctx: Auth,
) -> CategoryView:
    return await service.change_category_lifecycle(
        db,
        ctx=ctx,
        organization_id=organization_id,
        category_id=category_id,
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )


@router.delete("/technologies/{technology_id}/decision", response_model=TechnologyDecisionView)
async def clear_technology_decision(
    organization_id: OrganizationId,
    technology_id: TechnologyId,
    payload: TechnologyMutation,
    request: Request,
    db: Db,
    ctx: Auth,
) -> TechnologyDecisionView:
    cleared = TechnologyDecisionRequest(
        **payload.model_dump(), lead_account_id=None, approved=False, adoption="none"
    )
    return await service.write_technology_decision(
        db,
        ctx=ctx,
        organization_id=organization_id,
        technology_id=technology_id,
        payload=cleared,
        request_id=getattr(request.state, "request_id", None),
        remove=True,
    )


@router.get(
    "/projects/{project_id}/technologies/{technology_id}", response_model=ProjectTechnologyView
)
async def read_project_technology(
    organization_id: OrganizationId,
    project_id: RemoteProjectId,
    technology_id: TechnologyId,
    request: Request,
    db: Db,
    ctx: Auth,
) -> ProjectTechnologyView:
    return await service.read_project_technology(
        db,
        ctx=ctx,
        organization_id=organization_id,
        project_id=project_id,
        technology_id=technology_id,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/projects/{project_id}/technology-scans/{scan_id}", response_model=TechnologyScanView)
async def read_scan(
    organization_id: OrganizationId,
    project_id: RemoteProjectId,
    scan_id: TechnologyScanId,
    request: Request,
    db: Db,
    ctx: Auth,
) -> TechnologyScanView:
    return await detection.read_scan(
        db,
        ctx=ctx,
        organization_id=organization_id,
        project_id=project_id,
        scan_id=scan_id,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/technology-mappings/{version}", response_model=TechnologyMappingView)
async def read_mapping(
    organization_id: OrganizationId, version: MappingVersion, request: Request, db: Db, ctx: Auth
) -> TechnologyMappingView:
    return await detection.read_mapping(
        db,
        ctx=ctx,
        organization_id=organization_id,
        version=version,
        request_id=getattr(request.state, "request_id", None),
    )


@router.put("/technology-mappings/{version}", response_model=TechnologyMappingView)
async def publish_mapping(
    organization_id: OrganizationId,
    version: MappingVersion,
    payload: TechnologyMappingRequest,
    request: Request,
    db: Db,
    ctx: Auth,
) -> TechnologyMappingView:
    return await detection.publish_mapping(
        db,
        ctx=ctx,
        organization_id=organization_id,
        version=version,
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("/projects/{project_id}/technology-scans", response_model=TechnologyScanResult)
async def publish_scan(
    organization_id: OrganizationId,
    project_id: RemoteProjectId,
    payload: TechnologyScanRequest,
    request: Request,
    db: Db,
    ctx: Auth,
) -> TechnologyScanResult:
    return await detection.publish_scan(
        db,
        ctx=ctx,
        organization_id=organization_id,
        project_id=project_id,
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/technologies/{technology_id}/merge-plan", response_model=TechnologyMergePlanView)
async def read_merge_plan(
    organization_id: OrganizationId,
    technology_id: TechnologyId,
    request: Request,
    db: Db,
    ctx: Auth,
    filters: Annotated[TechnologyMergePlanQuery, Query()],
) -> TechnologyMergePlanView:
    return await merge.read_merge_plan(
        db,
        ctx=ctx,
        organization_id=organization_id,
        source_id=technology_id,
        target_id=filters.target_id,
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("/technologies/{technology_id}/merge", response_model=TechnologyMergeResult)
async def merge_technology(
    organization_id: OrganizationId,
    technology_id: TechnologyId,
    payload: TechnologyMergeRequest,
    request: Request,
    db: Db,
    ctx: Auth,
) -> TechnologyMergeResult:
    return await merge.merge_technology(
        db,
        ctx=ctx,
        organization_id=organization_id,
        source_id=technology_id,
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/technology-landscape-policy", response_model=TechnologyLandscapePolicyView)
async def read_landscape_policy(
    organization_id: OrganizationId,
    request: Request,
    db: Db,
    ctx: Auth,
) -> TechnologyLandscapePolicyView:
    return await service.read_landscape_policy(
        db,
        ctx=ctx,
        organization_id=organization_id,
        request_id=getattr(request.state, "request_id", None),
    )


@router.put("/technology-landscape-policy", response_model=TechnologyLandscapePolicyView)
async def write_landscape_policy(
    organization_id: OrganizationId,
    payload: TechnologyLandscapePolicyRequest,
    request: Request,
    db: Db,
    ctx: Auth,
) -> TechnologyLandscapePolicyView:
    return await service.write_landscape_policy(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/projects/{project_id}/activity", response_model=ProjectActivityView)
async def read_project_activity(
    organization_id: OrganizationId,
    project_id: RemoteProjectId,
    request: Request,
    db: Db,
    ctx: Auth,
) -> ProjectActivityView:
    return await service.read_project_activity(
        db,
        ctx=ctx,
        organization_id=organization_id,
        project_id=project_id,
        request_id=getattr(request.state, "request_id", None),
    )


@router.put("/projects/{project_id}/activity", response_model=ProjectActivityView)
async def write_project_activity(
    organization_id: OrganizationId,
    project_id: RemoteProjectId,
    payload: ProjectActivityRequest,
    request: Request,
    db: Db,
    ctx: Auth,
) -> ProjectActivityView:
    return await service.write_project_activity(
        db,
        ctx=ctx,
        organization_id=organization_id,
        project_id=project_id,
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("/technology-seed", response_model=TechnologySeedResult)
async def import_seed(
    organization_id: OrganizationId,
    payload: TechnologySeedRequest,
    request: Request,
    db: Db,
    ctx: Auth,
) -> TechnologySeedResult:
    return await service.import_seed(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/technology-landscape", response_model=TechnologyLandscapeView)
async def read_landscape(
    organization_id: OrganizationId,
    request: Request,
    db: Db,
    ctx: Auth,
    filters: Annotated[TechnologyLandscapeQuery, Query()],
) -> TechnologyLandscapeView:
    return await service.read_landscape(
        db,
        ctx=ctx,
        organization_id=organization_id,
        filters=filters,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/technology-categories/{category_id}", response_model=CategoryView)
async def read_category(
    organization_id: OrganizationId,
    category_id: CategoryId,
    request: Request,
    db: Db,
    ctx: Auth,
) -> CategoryView:
    return await service.read_category(
        db,
        ctx=ctx,
        organization_id=organization_id,
        category_id=category_id,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/projects/{project_id}/teams", response_model=ProjectTeamList)
async def list_project_teams(
    organization_id: OrganizationId,
    project_id: RemoteProjectId,
    request: Request,
    db: Db,
    ctx: Auth,
    include_history: bool = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=256)] = 128,
) -> ProjectTeamList:
    return await service.list_project_teams(
        db,
        ctx=ctx,
        organization_id=organization_id,
        project_id=project_id,
        team_id=None,
        include_history=include_history,
        offset=offset,
        limit=limit,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/teams/{team_id}/projects", response_model=ProjectTeamList)
async def list_team_projects(
    organization_id: OrganizationId,
    team_id: TeamId,
    request: Request,
    db: Db,
    ctx: Auth,
    include_history: bool = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=256)] = 128,
) -> ProjectTeamList:
    return await service.list_project_teams(
        db,
        ctx=ctx,
        organization_id=organization_id,
        team_id=team_id,
        project_id=None,
        include_history=include_history,
        offset=offset,
        limit=limit,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/technologies/{technology_id}/responsible-teams", response_model=TechnologyTeamList)
async def list_technology_teams(
    organization_id: OrganizationId,
    technology_id: TechnologyId,
    request: Request,
    db: Db,
    ctx: Auth,
    include_history: bool = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=256)] = 128,
) -> TechnologyTeamList:
    return await service.list_technology_teams(
        db,
        ctx=ctx,
        organization_id=organization_id,
        technology_id=technology_id,
        team_id=None,
        include_history=include_history,
        offset=offset,
        limit=limit,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/teams/{team_id}/technologies", response_model=TechnologyTeamList)
async def list_team_technologies(
    organization_id: OrganizationId,
    team_id: TeamId,
    request: Request,
    db: Db,
    ctx: Auth,
    include_history: bool = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=256)] = 128,
) -> TechnologyTeamList:
    return await service.list_technology_teams(
        db,
        ctx=ctx,
        organization_id=organization_id,
        team_id=team_id,
        technology_id=None,
        include_history=include_history,
        offset=offset,
        limit=limit,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/projects/{project_id}/technologies", response_model=ProjectTechnologyList)
async def list_project_technologies(
    organization_id: OrganizationId,
    project_id: RemoteProjectId,
    request: Request,
    db: Db,
    ctx: Auth,
    include_history: bool = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=256)] = 128,
) -> ProjectTechnologyList:
    return await service.list_project_technologies(
        db,
        ctx=ctx,
        organization_id=organization_id,
        project_id=project_id,
        technology_id=None,
        include_history=include_history,
        offset=offset,
        limit=limit,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/technologies/{technology_id}/projects", response_model=ProjectTechnologyList)
async def list_technology_projects(
    organization_id: OrganizationId,
    technology_id: TechnologyId,
    request: Request,
    db: Db,
    ctx: Auth,
    include_history: bool = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=256)] = 128,
) -> ProjectTechnologyList:
    return await service.list_project_technologies(
        db,
        ctx=ctx,
        organization_id=organization_id,
        technology_id=technology_id,
        project_id=None,
        include_history=include_history,
        offset=offset,
        limit=limit,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/technologies/{technology_id}/decision", response_model=TechnologyDecisionView)
async def read_technology_decision(
    organization_id: OrganizationId,
    technology_id: TechnologyId,
    request: Request,
    db: Db,
    ctx: Auth,
) -> TechnologyDecisionView:
    return await service.read_technology_decision(
        db,
        ctx=ctx,
        organization_id=organization_id,
        technology_id=technology_id,
        request_id=getattr(request.state, "request_id", None),
    )


@router.put("/projects/{project_id}/teams", response_model=ProjectTeamView)
async def write_project_team(
    organization_id: OrganizationId,
    project_id: RemoteProjectId,
    payload: ProjectTeamWriteRequest,
    request: Request,
    db: Db,
    ctx: Auth,
) -> ProjectTeamView:
    return await service.write_project_team(
        db,
        ctx=ctx,
        organization_id=organization_id,
        project_id=project_id,
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )


@router.put("/technologies/{technology_id}/responsible-teams", response_model=TechnologyTeamView)
async def write_technology_team(
    organization_id: OrganizationId,
    technology_id: TechnologyId,
    payload: TechnologyTeamWriteRequest,
    request: Request,
    db: Db,
    ctx: Auth,
) -> TechnologyTeamView:
    return await service.write_technology_team(
        db,
        ctx=ctx,
        organization_id=organization_id,
        technology_id=technology_id,
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )


@router.put("/technologies/{technology_id}/decision", response_model=TechnologyDecisionView)
async def write_technology_decision(
    organization_id: OrganizationId,
    technology_id: TechnologyId,
    payload: TechnologyDecisionRequest,
    request: Request,
    db: Db,
    ctx: Auth,
) -> TechnologyDecisionView:
    return await service.write_technology_decision(
        db,
        ctx=ctx,
        organization_id=organization_id,
        technology_id=technology_id,
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/technology-categories", response_model=CategoryList)
async def list_categories(
    organization_id: OrganizationId, request: Request, db: Db, ctx: Auth
) -> CategoryList:
    return await service.list_categories(
        db,
        ctx=ctx,
        organization_id=organization_id,
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("/technology-categories", response_model=CategoryView)
async def create_category(
    organization_id: OrganizationId,
    payload: CategoryWriteRequest,
    request: Request,
    db: Db,
    ctx: Auth,
) -> CategoryView:
    return await service.write_category(
        db,
        ctx=ctx,
        organization_id=organization_id,
        category_id=None,
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("/technologies", response_model=TechnologyView)
async def create_technology(
    organization_id: OrganizationId,
    payload: TechnologyWriteRequest,
    request: Request,
    db: Db,
    ctx: Auth,
) -> TechnologyView:
    return await service.write_technology(
        db,
        ctx=ctx,
        organization_id=organization_id,
        technology_id=None,
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )


@router.put("/technology-categories/{category_id}", response_model=CategoryView)
async def write_category(
    organization_id: OrganizationId,
    category_id: CategoryId,
    payload: CategoryWriteRequest,
    request: Request,
    db: Db,
    ctx: Auth,
) -> CategoryView:
    return await service.write_category(
        db,
        ctx=ctx,
        organization_id=organization_id,
        category_id=category_id,
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/technologies", response_model=TechnologyList)
async def list_technologies(
    organization_id: OrganizationId,
    request: Request,
    db: Db,
    ctx: Auth,
    include_archived: bool = False,
    query: TechnologySearch | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=256)] = 128,
) -> TechnologyList:
    return await service.list_technologies(
        db,
        ctx=ctx,
        organization_id=organization_id,
        include_archived=include_archived,
        search=query,
        offset=offset,
        limit=limit,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/technologies/{technology_id}", response_model=TechnologyView)
async def read_technology(
    organization_id: OrganizationId,
    technology_id: TechnologyId,
    request: Request,
    db: Db,
    ctx: Auth,
) -> TechnologyView:
    return await service.read_technology(
        db,
        ctx=ctx,
        organization_id=organization_id,
        technology_id=technology_id,
        request_id=getattr(request.state, "request_id", None),
    )


@router.put("/technologies/{technology_id}", response_model=TechnologyView)
async def write_technology(
    organization_id: OrganizationId,
    technology_id: TechnologyId,
    payload: TechnologyWriteRequest,
    request: Request,
    db: Db,
    ctx: Auth,
) -> TechnologyView:
    return await service.write_technology(
        db,
        ctx=ctx,
        organization_id=organization_id,
        technology_id=technology_id,
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )


@router.patch("/technologies/{technology_id}/lifecycle", response_model=TechnologyView)
async def change_lifecycle(
    organization_id: OrganizationId,
    technology_id: TechnologyId,
    payload: TechnologyLifecycleRequest,
    request: Request,
    db: Db,
    ctx: Auth,
) -> TechnologyView:
    return await service.change_lifecycle(
        db,
        ctx=ctx,
        organization_id=organization_id,
        technology_id=technology_id,
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )


@router.put("/projects/{project_id}/technologies", response_model=ProjectTechnologyView)
async def write_project_technology(
    organization_id: OrganizationId,
    project_id: RemoteProjectId,
    payload: ProjectTechnologyWriteRequest,
    request: Request,
    db: Db,
    ctx: Auth,
) -> ProjectTechnologyView:
    return await service.write_project_technology(
        db,
        ctx=ctx,
        organization_id=organization_id,
        project_id=project_id,
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )
