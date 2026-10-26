"""Anonymous and authenticated complaint intake routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ai_stp_api.deps import Db, optional_auth
from ai_stp_api.session import AuthContext
from ai_stp_api.settings import Settings
from ai_stp_api.slices.complaints import service
from ai_stp_contracts.complaints import ComplaintCreateRequest

router = APIRouter(tags=["complaints"])


@router.post("/complaints", response_model=None)
async def create_complaint(
    request: Request,
    body: ComplaintCreateRequest,
    db: Db,
    ctx: Annotated[AuthContext | None, Depends(optional_auth)],
) -> JSONResponse:
    settings: Settings = request.app.state.settings
    result = await service.create_complaint(db, ctx=ctx, body=body, limits=settings.complaint)
    payload = result.model_dump(mode="json")
    return JSONResponse(content=payload, status_code=201)
