"""Authenticated selection impact route (SPEC-047). Blast radius is CLI-only (SPEC-049)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_contracts.impact import AccountSelectionImpactQuery
from ai_stp_platform.selection_impact import (
    SelectionInvalid,
    SelectionNotFound,
    account_impact,
)
from ai_stp_platform.storage.object_store import ImmutableObjectStore

router = APIRouter(tags=["selection"])


def _resource(model: object) -> JSONResponse:
    payload = model.model_dump(mode="json")  # type: ignore[attr-defined]
    return JSONResponse(content=payload, status_code=200)


def _store(request: Request) -> ImmutableObjectStore | None:
    client = getattr(request.app.state, "object_client", None)
    settings = getattr(request.app.state, "settings", None)
    if client is None or settings is None:
        return None
    return ImmutableObjectStore(settings=settings.storage, client=client)


@router.get("/selection/impact", response_model=None)
async def read_selection_impact(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    candidate_id: Annotated[str, Query()],
    candidate_version: Annotated[str, Query()],
    baseline_id: Annotated[str | None, Query()] = None,
    baseline_version: Annotated[str | None, Query()] = None,
    project_id: Annotated[str | None, Query()] = None,
    estimator_profile: Annotated[str, Query()] = "ai-stp:utf8-bytes/1",
) -> JSONResponse:
    try:
        query = AccountSelectionImpactQuery(
            candidate_id=candidate_id,
            candidate_version=candidate_version,
            baseline_id=baseline_id,
            baseline_version=baseline_version,
            project_id=project_id,
            estimator_profile=estimator_profile,  # type: ignore[arg-type]
        )
    except ValidationError as exc:
        raise ApiError(
            ErrorCategory.VALIDATION,
            "request validation failed",
            details={"fields": ",".join(str(error["loc"]) for error in exc.errors())},
        ) from exc
    try:
        result = await account_impact(
            db, account_id=ctx.account_id, query=query, store=_store(request)
        )
    except SelectionNotFound as exc:
        raise ApiError(ErrorCategory.NOT_FOUND, "catalog object not found") from exc
    except SelectionInvalid as exc:
        raise ApiError(ErrorCategory.VALIDATION, str(exc)) from exc
    return _resource(result)
