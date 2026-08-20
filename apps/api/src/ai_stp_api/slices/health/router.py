"""Health slice: independent liveness and dependency-aware readiness (SPEC-017)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.readiness import not_ready, readiness_report

router = APIRouter(tags=["health"])


def _pass_fail(ok: bool) -> str:
    return "pass" if ok else "fail"


@router.get("/health/live")
async def liveness(request: Request) -> JSONResponse:
    """Report process liveness without touching any dependency (REQ-1707).

    Resource body matches ``LivenessResponse`` (no CLI success envelope).
    """
    del request
    return JSONResponse(content={"schema_version": 1, "status": "alive"}, status_code=200)


@router.get("/health/ready")
async def readiness(request: Request) -> JSONResponse:
    """Report readiness; false until migrations and dependencies are usable (REQ-1708).

    Resource body matches ``ReadinessResponse`` (checks use pass/fail, not booleans).
    """
    settings = request.app.state.settings
    sessionmaker = request.app.state.sessionmaker
    report = await readiness_report(sessionmaker=sessionmaker, storage=settings.storage)
    checks = {
        "database": _pass_fail(bool(report.get("database"))),
        "migrations": _pass_fail(bool(report.get("migrations"))),
        # Contract field is object_storage; probe key remains "storage" internally.
        "object_storage": _pass_fail(bool(report.get("storage"))),
    }
    ready = not not_ready(report)
    body = {
        "schema_version": 1,
        "status": "ready" if ready else "not_ready",
        "checks": checks,
        "checked_at": format_timestamp(datetime.now(UTC)),
    }
    return JSONResponse(content=body, status_code=200 if ready else 503)
