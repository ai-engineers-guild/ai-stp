"""Authenticated private revision sync routes (SPEC-025)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_auth_settings, get_db, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.settings import AuthSettings
from ai_stp_api.slices.sync import service
from ai_stp_contracts.http import PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX
from ai_stp_contracts.sync import SyncPushRequest

router = APIRouter(tags=["sync"])

_PULL_KEYS = frozenset({"schema_version", "cursor", "page_size"})


def _resource(model: object, *, status_code: int = 200) -> JSONResponse:
    payload = model.model_dump(mode="json")  # type: ignore[attr-defined]
    return JSONResponse(content=payload, status_code=status_code)


@router.post("/sync/push", response_model=None)
async def push_sync_events(
    request: Request,
    body: SyncPushRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    auth: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> JSONResponse:
    """Push private revision events for the session-bound active device."""
    del request
    result = await service.push_events(
        db,
        ctx=ctx,
        body=body,
        secret=auth.secret_key,
    )
    return _resource(result)


@router.get("/sync/pull", response_model=None)
async def pull_sync_events(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    auth: Annotated[AuthSettings, Depends(get_auth_settings)],
    cursor: Annotated[str | None, Query()] = None,
    page_size: Annotated[int, Query(ge=1, le=PAGE_SIZE_MAX)] = PAGE_SIZE_DEFAULT,
    schema_version: Annotated[int | None, Query()] = None,
) -> JSONResponse:
    """Pull accepted revision events from the account outbox."""
    del schema_version
    unknown = sorted({key for key in request.query_params if key not in _PULL_KEYS})
    if unknown:
        raise ApiError(
            ErrorCategory.VALIDATION,
            "request validation failed",
            details={"fields": ",".join(unknown)},
        )
    try:
        result = await service.pull_events(
            db,
            ctx=ctx,
            secret=auth.secret_key,
            cursor=cursor,
            page_size=page_size,
        )
    except ValidationError as exc:
        raise ApiError(ErrorCategory.VALIDATION, "request validation failed") from exc
    return _resource(result)
