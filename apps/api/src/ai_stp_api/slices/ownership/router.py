"""Ownership claim and staff decision routes (SPEC-057 REQ-5717)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.session import AuthContext
from ai_stp_api.settings import Settings
from ai_stp_api.slices.ownership import service
from ai_stp_contracts.ownership import OwnershipClaimCreateRequest, OwnershipClaimDecisionRequest

router = APIRouter(tags=["ownership"])


def _resource(model: object, *, status_code: int = 200) -> JSONResponse:
    payload = model.model_dump(mode="json")  # type: ignore[attr-defined]
    return JSONResponse(content=payload, status_code=status_code)


def _staff_ids(request: Request) -> frozenset[str]:
    settings: Settings = request.app.state.settings
    return settings.auth.admin_ids()


@router.post("/ownership-claims", response_model=None)
async def create_ownership_claim(
    body: OwnershipClaimCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.create_claim(db, ctx=ctx, body=body)
    return _resource(result, status_code=201)


@router.get("/ownership-claims/{claim_id}", response_model=None)
async def read_ownership_claim(
    claim_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.read_claim(db, ctx=ctx, claim_id=claim_id, staff_ids=_staff_ids(request))
    return _resource(result)


@router.post("/staff/ownership-claims/{claim_id}/approve", response_model=None)
async def approve_ownership_claim(
    claim_id: str,
    body: OwnershipClaimDecisionRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.decide_claim(
        db,
        ctx=ctx,
        staff_ids=_staff_ids(request),
        claim_id=claim_id,
        body=body,
        approved=True,
    )
    return _resource(result)


@router.post("/staff/ownership-claims/{claim_id}/deny", response_model=None)
async def deny_ownership_claim(
    claim_id: str,
    body: OwnershipClaimDecisionRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.decide_claim(
        db,
        ctx=ctx,
        staff_ids=_staff_ids(request),
        claim_id=claim_id,
        body=body,
        approved=False,
    )
    return _resource(result)


@router.get("/owner/objects/component/{stable_id}/ownership-revisions", response_model=None)
async def list_ownership_revisions(
    stable_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.list_revisions(
        db, ctx=ctx, stable_id=stable_id, staff_ids=_staff_ids(request)
    )
    return _resource(result)
