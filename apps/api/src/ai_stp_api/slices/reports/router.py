"""Report and staff moderation routes (SPEC-026)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.session import AuthContext
from ai_stp_api.settings import Settings
from ai_stp_api.slices.reports import service
from ai_stp_contracts.http import PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX
from ai_stp_contracts.reports import (
    ReportCaseCreateRequest,
    StaffLifecycleRequest,
    StaffTriageRequest,
)

router = APIRouter(tags=["reports"])


def _resource(model: object, *, status_code: int = 200) -> JSONResponse:
    payload = model.model_dump(mode="json")  # type: ignore[attr-defined]
    return JSONResponse(content=payload, status_code=status_code)


def _staff_ids(request: Request) -> frozenset[str]:
    settings: Settings = request.app.state.settings
    return settings.auth.admin_ids()


@router.post("/reports", response_model=None)
async def create_report_case(
    body: ReportCaseCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.create_report(db, ctx=ctx, body=body)
    return _resource(result, status_code=201)


@router.post("/requests", response_model=None)
async def create_request_case(
    body: ReportCaseCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.create_report(db, ctx=ctx, body=body)
    return _resource(result, status_code=201)


@router.get("/reports", response_model=None)
async def list_report_cases(
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.list_reports(db, ctx=ctx)
    return _resource(result)


@router.get("/requests", response_model=None)
async def list_request_cases(
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.list_reports(db, ctx=ctx)
    return _resource(result)


@router.get("/requests/{case_id}", response_model=None)
async def read_request_case(
    case_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.read_own_report(db, ctx=ctx, case_id=case_id)
    return _resource(result)


@router.get("/staff/reports", response_model=None)
async def list_staff_reports(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    page_size: Annotated[int, Query(ge=1, le=PAGE_SIZE_MAX)] = PAGE_SIZE_DEFAULT,
) -> JSONResponse:
    result = await service.list_staff_reports(
        db, ctx=ctx, staff_ids=_staff_ids(request), page_size=page_size
    )
    return _resource(result)


@router.get("/staff/reports/{case_id}", response_model=None)
async def read_staff_report(
    case_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.read_staff_report(
        db, ctx=ctx, staff_ids=_staff_ids(request), case_id=case_id
    )
    return _resource(result)


@router.post("/staff/reports/{case_id}/triage", response_model=None)
async def staff_triage_report(
    case_id: str,
    body: StaffTriageRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.staff_triage(
        db,
        ctx=ctx,
        staff_ids=_staff_ids(request),
        case_id=case_id,
        body=body,
    )
    return _resource(result)


@router.post("/staff/versions/lifecycle", response_model=None)
async def staff_version_lifecycle(
    body: StaffLifecycleRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.staff_lifecycle(db, ctx=ctx, staff_ids=_staff_ids(request), body=body)
    return _resource(result)
