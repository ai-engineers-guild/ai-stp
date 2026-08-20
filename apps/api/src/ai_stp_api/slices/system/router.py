"""System slice: service metadata and safe diagnostics (SPEC-017, REQ-2411)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

router = APIRouter(tags=["system"])


async def _schema_revision(request: Request) -> str | None:
    """Return the applied Alembic revision when the database answers.

    Never returns connection strings, host names or other reconnaissance detail.
    """
    sessionmaker = getattr(request.app.state, "sessionmaker", None)
    if sessionmaker is None:
        return None
    try:
        async with sessionmaker() as session:
            result = await session.execute(text("SELECT version_num FROM alembic_version"))
            value = result.scalar_one_or_none()
            return str(value) if value is not None else None
    except Exception:
        return None


@router.get("/system/version")
async def version(request: Request) -> JSONResponse:
    """Report version, commit and schema identity without secrets (REQ-2411).

    Resource body (no CLI success envelope) matches SystemVersionResponse.
    """
    settings = request.app.state.settings
    schema_revision = await _schema_revision(request)
    return JSONResponse(
        content={
            "schema_version": 1,
            "version": settings.service.version,
            "environment": settings.service.environment,
            "git_commit": settings.service.git_commit,
            "schema_revision": schema_revision,
        },
        status_code=200,
    )
