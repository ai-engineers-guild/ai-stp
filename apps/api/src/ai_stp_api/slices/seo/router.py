"""Public SEO reads and authenticated rollback (SPEC-053)."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_contracts.http import PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX
from ai_stp_contracts.seo import (
    SEO_OG_HEIGHT,
    SEO_OG_WIDTH,
    SeoRollbackRequest,
    SeoSubjectKind,
)
from ai_stp_foundation.revisions import REVISION_ID_PATTERN
from ai_stp_platform.seo.collectors import SubjectMissing
from ai_stp_platform.seo.materialize import rollback_to_base
from ai_stp_platform.seo.og import png_dimensions, render_og_png
from ai_stp_platform.seo.read import (
    read_active_profile,
    read_catalog_page,
    read_revision_profile,
    read_sitemap_index,
    read_sitemap_shard,
)
from ai_stp_platform.seo.settings import load_seo_settings

router = APIRouter(tags=["seo"])


def _public(model: object, *, etag: str | None = None) -> JSONResponse:
    payload = model.model_dump(mode="json")  # type: ignore[attr-defined]
    headers = {"Cache-Control": "public, max-age=60"}
    if etag:
        headers["ETag"] = etag
    return JSONResponse(content=payload, headers=headers)


def _private(model: object, *, status_code: int = 200) -> JSONResponse:
    payload = model.model_dump(mode="json")  # type: ignore[attr-defined]
    return JSONResponse(
        content=payload,
        status_code=status_code,
        headers={"Cache-Control": "private, no-store"},
    )


def _kind(value: str) -> SeoSubjectKind:
    if value not in {"component", "setup", "article", "service", "country"}:
        raise ApiError(ErrorCategory.VALIDATION, "invalid subject kind")
    return cast(SeoSubjectKind, value)


@router.get("/seo/subjects/{subject_kind}/{subject_id}", response_model=None)
async def read_seo_profile(
    request: Request,
    subject_kind: str,
    subject_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    locale: Annotated[str, Query()] = "en",
    schema_version: Annotated[int, Query()] = 1,
) -> JSONResponse:
    del request
    if schema_version != 1:
        raise ApiError(ErrorCategory.VALIDATION, "unsupported schema version")
    if locale not in {"ru", "en"}:
        raise ApiError(ErrorCategory.VALIDATION, "invalid locale")
    try:
        profile = await read_active_profile(
            db, kind=_kind(subject_kind), subject_id=subject_id, locale=locale
        )
    except SubjectMissing as exc:
        raise ApiError(ErrorCategory.NOT_FOUND, "seo revision not found") from exc
    return _public(profile, etag=profile.etag)


@router.get("/seo/sitemap", response_model=None)
async def read_seo_sitemap_index(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    origin = load_seo_settings().public_origin
    index = await read_sitemap_index(db, origin=origin)
    return _public(index, etag=index.etag)


@router.get("/seo/sitemaps/{subject_kind}/{locale}/{page}", response_model=None)
async def read_seo_sitemap_shard(
    subject_kind: str,
    locale: str,
    page: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    if locale not in {"ru", "en"}:
        raise ApiError(ErrorCategory.VALIDATION, "invalid locale")
    origin = load_seo_settings().public_origin
    try:
        shard = await read_sitemap_shard(
            db, kind=_kind(subject_kind), locale=locale, page=page, origin=origin
        )
    except SubjectMissing as exc:
        raise ApiError(ErrorCategory.NOT_FOUND, "sitemap shard not found") from exc
    return _public(shard)


@router.get("/seo/catalog", response_model=None)
async def read_seo_catalog(
    db: Annotated[AsyncSession, Depends(get_db)],
    locale: Annotated[str | None, Query()] = None,
    kind: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    page_size: Annotated[int, Query(ge=1, le=PAGE_SIZE_MAX)] = PAGE_SIZE_DEFAULT,
    schema_version: Annotated[int, Query()] = 1,
) -> JSONResponse:
    if schema_version != 1:
        raise ApiError(ErrorCategory.VALIDATION, "unsupported schema version")
    if locale is not None and locale not in {"ru", "en"}:
        raise ApiError(ErrorCategory.VALIDATION, "invalid locale")
    typed_kind = _kind(kind) if kind is not None else None
    page = await read_catalog_page(
        db,
        locale=locale,
        kind=typed_kind,
        cursor=cursor,
        page_size=page_size,
        origin=load_seo_settings().public_origin,
    )
    return _public(page)


@router.get("/seo/og/{revision_id}", response_model=None)
async def read_seo_og_image(
    revision_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    import re

    if re.fullmatch(REVISION_ID_PATTERN, revision_id) is None:
        raise ApiError(ErrorCategory.VALIDATION, "invalid revision id")
    try:
        profile = await read_revision_profile(db, revision_id)
    except SubjectMissing as exc:
        raise ApiError(ErrorCategory.NOT_FOUND, "og image not found") from exc
    try:
        png = render_og_png(profile)
        width, height = png_dimensions(png)
    except ValueError as exc:
        raise ApiError(ErrorCategory.SEO_RENDER_FAILED, "og render failed") from exc
    if width != SEO_OG_WIDTH or height != SEO_OG_HEIGHT:
        raise ApiError(ErrorCategory.SEO_RENDER_FAILED, "og render failed")
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Content-Disposition": f'inline; filename="{revision_id}.png"',
        },
    )


@router.post("/seo/subjects/{subject_kind}/{subject_id}/rollback", response_model=None)
async def rollback_seo_revision(
    subject_kind: str,
    subject_id: str,
    body: SeoRollbackRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    del ctx
    try:
        revision = await rollback_to_base(
            db, kind=_kind(subject_kind), subject_id=subject_id, locale=body.locale
        )
    except SubjectMissing as exc:
        raise ApiError(ErrorCategory.NOT_FOUND, "seo revision not found") from exc
    from ai_stp_contracts.seo import SeoRollbackResponse

    return _private(
        SeoRollbackResponse(
            subject_kind=_kind(subject_kind),
            subject_id=subject_id,
            locale=body.locale,
            revision_id=revision.id,
            generator_kind=revision.generator_kind,  # type: ignore[arg-type]
        )
    )
