"""Public document read API (SPEC-031)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_db
from ai_stp_api.slices.documents import service as documents_service

router = APIRouter(tags=["documents"])


@router.get("/documents/{slug}", response_model=None)
async def read_document(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    locale: Annotated[str, Query()] = "en",
) -> JSONResponse:
    body = await documents_service.get_published(db, slug=slug, locale=locale)
    return JSONResponse(
        content=body,
        headers={"Cache-Control": "public, max-age=60"},
    )
