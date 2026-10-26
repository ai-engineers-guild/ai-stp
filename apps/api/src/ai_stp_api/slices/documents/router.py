"""Public document read API (SPEC-031)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from ai_stp_api.deps import Db
from ai_stp_api.slices.documents import service as documents_service

router = APIRouter(tags=["documents"])


@router.get("/documents/{slug}", response_model=None)
async def read_document(
    slug: str,
    db: Db,
    locale: Annotated[str, Query()] = "en",
    revision_id: Annotated[str | None, Query()] = None,
) -> JSONResponse:
    body = await documents_service.get_published(
        db, slug=slug, locale=locale, revision_id=revision_id
    )
    return JSONResponse(
        content=body,
        headers={"Cache-Control": "public, max-age=60"},
    )
