"""Tenant-scoped technology HTTP surface; all mutations are revision guarded."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.technology import service
from ai_stp_contracts.context import OrganizationId, RemoteProjectId
from ai_stp_contracts.technology import (
    CategoryId,
    CategoryList,
    CategoryView,
    CategoryWriteRequest,
    ProjectTeamList,
    ProjectTeamView,
    ProjectTeamWriteRequest,
    ProjectTechnologyList,
    ProjectTechnologyView,
    ProjectTechnologyWriteRequest,
    TeamId,
    TechnologyDecisionRequest,
    TechnologyDecisionView,
    TechnologyId,
    TechnologyLandscapeQuery,
    TechnologyLandscapeView,
    TechnologyLifecycleRequest,
    TechnologyList,
    TechnologyTeamList,
    TechnologyTeamView,
    TechnologyTeamWriteRequest,
    TechnologyView,
    TechnologyWriteRequest,
)

router = APIRouter(prefix="/corporate/organizations/{organization_id}", tags=["technology"])
Db = Annotated[AsyncSession, Depends(get_db)]
Auth = Annotated[AuthContext, Depends(require_auth)]


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
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=256)] = 128,
) -> TechnologyList:
    return await service.list_technologies(
        db,
        ctx=ctx,
        organization_id=organization_id,
        include_archived=include_archived,
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
