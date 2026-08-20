"""Publication routes (SPEC-026)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_db, get_settings, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.settings import Settings
from ai_stp_api.slices.publish import service
from ai_stp_contracts.publication import PublicationConfirmRequest, PublicationPlanCreateRequest
from ai_stp_platform.safety.workdir import MAX_ARTIFACT_BYTES
from ai_stp_platform.storage.object_store import ImmutableObjectStore

router = APIRouter(tags=["publications"])


async def _bounded_body(request: Request, *, max_bytes: int) -> bytes:
    """Read an ASGI body without buffering more than the accepted maximum."""
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError as exc:
            raise ApiError(ErrorCategory.VALIDATION, "invalid content-length") from exc
        if declared < 0 or declared > max_bytes:
            raise ApiError(
                ErrorCategory.VALIDATION,
                "artifact exceeds the accepted size",
            )

    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > max_bytes:
            raise ApiError(
                ErrorCategory.VALIDATION,
                "artifact exceeds the accepted size",
            )
        payload.extend(chunk)
    return bytes(payload)


def _resource(model: object, *, status_code: int = 200) -> JSONResponse:
    payload = model.model_dump(mode="json")  # type: ignore[attr-defined]
    return JSONResponse(content=payload, status_code=status_code)


@router.post("/publications/plans", response_model=None)
async def create_publication_plan(
    body: PublicationPlanCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.create_plan(db, ctx=ctx, body=body)
    return _resource(result, status_code=201)


@router.get("/publications/plans/{plan_id}", response_model=None)
async def read_publication_plan(
    plan_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.read_plan(db, ctx=ctx, plan_id=plan_id)
    return _resource(result)


@router.put("/publications/plans/{plan_id}/artifact", response_model=None)
async def bind_publication_artifact(
    plan_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONResponse:
    payload = await _bounded_body(request, max_bytes=MAX_ARTIFACT_BYTES)
    store = ImmutableObjectStore(settings=settings.storage, client=request.app.state.object_client)
    result = await service.bind_artifact(db, ctx=ctx, plan_id=plan_id, payload=payload, store=store)
    return _resource(result)


@router.post("/publications/plans/{plan_id}/confirm", response_model=None)
async def confirm_publication_plan(
    plan_id: str,
    body: PublicationConfirmRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONResponse:
    store = ImmutableObjectStore(settings=settings.storage, client=request.app.state.object_client)
    result = await service.confirm_plan(db, ctx=ctx, plan_id=plan_id, body=body, store=store)
    return _resource(result)
