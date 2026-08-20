"""Grant invitation and access grant routes (SPEC-026)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.grants import service
from ai_stp_contracts.grants import (
    DirectGrantCreateRequest,
    GrantAcceptRequest,
    GrantInvitationCreateRequest,
    GrantRevokeRequest,
)

router = APIRouter(tags=["grants"])


def _resource(model: object, *, status_code: int = 200) -> JSONResponse:
    payload = model.model_dump(mode="json")  # type: ignore[attr-defined]
    return JSONResponse(content=payload, status_code=status_code)


@router.post("/grants/invitations", response_model=None)
async def create_grant_invitation(
    body: GrantInvitationCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.create_invitation(db, ctx=ctx, body=body)
    return _resource(result, status_code=201)


@router.get("/grants", response_model=None)
async def list_grants(
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.list_grants(db, ctx=ctx)
    return _resource(result)


@router.post("/grants/direct", response_model=None)
async def create_direct_grant(
    body: DirectGrantCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.create_direct_grant(db, ctx=ctx, body=body)
    return _resource(result, status_code=201)


@router.post("/grants/invitations/{invitation_id}/accept", response_model=None)
async def accept_grant_invitation(
    invitation_id: str,
    body: GrantAcceptRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.accept_invitation(db, ctx=ctx, invitation_id=invitation_id, body=body)
    return _resource(result)


@router.post("/grants/invitations/{invitation_id}/revoke", response_model=None)
async def revoke_grant_invitation(
    invitation_id: str,
    body: GrantRevokeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.revoke_invitation(db, ctx=ctx, invitation_id=invitation_id, body=body)
    return _resource(result)


@router.post("/grants/{grant_id}/revoke", response_model=None)
async def revoke_access_grant(
    grant_id: str,
    body: GrantRevokeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.revoke_grant(db, ctx=ctx, grant_id=grant_id, body=body)
    return _resource(result)
