"""Authenticated owner visibility plan endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from ai_stp_api.deps import Db, require_auth
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.visibility import service
from ai_stp_contracts.private_access import VisibilityPlanCreateRequest, VisibilityPlanResponse
from ai_stp_contracts.publication import PublicationConfirmRequest

router = APIRouter(prefix="/access/visibility/plans", tags=["visibility"])


@router.post("", response_model=VisibilityPlanResponse, status_code=201)
async def create_visibility_plan(
    body: VisibilityPlanCreateRequest,
    db: Db,
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> VisibilityPlanResponse:
    return await service.create(db, ctx=ctx, body=body)


@router.get("/{plan_id}", response_model=VisibilityPlanResponse)
async def read_visibility_plan(
    plan_id: str,
    db: Db,
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> VisibilityPlanResponse:
    return await service.status(db, ctx=ctx, plan_id=plan_id)


@router.post("/{plan_id}/confirm", response_model=VisibilityPlanResponse)
async def confirm_visibility_plan(
    plan_id: str,
    body: PublicationConfirmRequest,
    db: Db,
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> VisibilityPlanResponse:
    return await service.confirm(db, ctx=ctx, plan_id=plan_id, body=body)
