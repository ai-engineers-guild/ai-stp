"""Public content reads, repository import and staff publication (SPEC-054)."""

from __future__ import annotations

import hmac
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.settings import Settings
from ai_stp_contracts.content import (
    ContentRepositoryImportRequest,
    StaffContentPublishRequest,
    StaffContentUnpublishRequest,
)
from ai_stp_platform.content.errors import ContentError
from ai_stp_platform.content.service import (
    import_repository_snapshot,
    list_published,
    publish_staff_article,
    read_published,
    repository_state,
    unpublish_staff_article,
)

router = APIRouter(tags=["content"])

_PUBLIC_CACHE = "public, max-age=60"
_CODE_CATEGORY: dict[str, ErrorCategory] = {
    "AI_STP_CONTENT_INVALID": ErrorCategory.CONTENT_INVALID,
    "AI_STP_CONTENT_SOURCE_CONFLICT": ErrorCategory.CONTENT_SOURCE_CONFLICT,
    "AI_STP_CONTENT_STALE": ErrorCategory.CONTENT_STALE,
    "AI_STP_CONTENT_IMPORT_FORBIDDEN": ErrorCategory.CONTENT_IMPORT_FORBIDDEN,
    "AI_STP_NOT_FOUND": ErrorCategory.NOT_FOUND,
}


def _raise(error: ContentError) -> None:
    category = _CODE_CATEGORY.get(error.code, ErrorCategory.INTERNAL)
    raise ApiError(category, error.message) from error


def _etag_matches(sent: str | None, etag: str) -> bool:
    if not sent:
        return False
    quoted = f'"{etag}"'
    return any(part.strip() in {etag, quoted, "*"} for part in sent.split(","))


def _public(payload: object, *, etag: str, if_none_match: str | None) -> Response:
    headers = {"ETag": f'"{etag}"', "Cache-Control": _PUBLIC_CACHE}
    if _etag_matches(if_none_match, etag):
        return Response(status_code=304, headers=headers)
    body = payload.model_dump(mode="json")  # type: ignore[attr-defined]
    return JSONResponse(content=body, headers=headers)


def _resource(model: object) -> JSONResponse:
    return JSONResponse(content=model.model_dump(mode="json"))  # type: ignore[attr-defined]


def _staff_ids(request: Request) -> frozenset[str]:
    settings: Settings = request.app.state.settings
    return settings.auth.admin_ids()


async def require_staff(ctx: AuthContext, staff_ids: frozenset[str]) -> None:
    if ctx.account_id not in staff_ids:
        raise ApiError(ErrorCategory.PERMISSION, "staff allowlist required")


def require_content_import(request: Request) -> None:
    settings: Settings = request.app.state.settings
    expected = settings.content.import_token
    if not expected:
        raise ApiError(
            ErrorCategory.CONTENT_IMPORT_FORBIDDEN, "import credential is not configured"
        )
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        raise ApiError(ErrorCategory.CONTENT_IMPORT_FORBIDDEN, "import credential is missing")
    given = header[7:].strip()
    if not hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8")):
        raise ApiError(ErrorCategory.CONTENT_IMPORT_FORBIDDEN, "import credential is invalid")


@router.get("/content", response_model=None, operation_id="listContent")
async def list_content(
    db: Annotated[AsyncSession, Depends(get_db)],
    locale: Annotated[Literal["ru", "en"], Query()],
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    try:
        result = await list_published(db, locale=locale)
    except ContentError as error:
        _raise(error)
        raise
    return _public(result, etag=result.etag, if_none_match=if_none_match)


@router.get(
    "/content/repository/state",
    response_model=None,
    operation_id="readContentRepositoryState",
)
async def read_content_repository_state(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    require_content_import(request)
    try:
        result = await repository_state(db)
    except ContentError as error:
        _raise(error)
        raise
    return _resource(result)


@router.post(
    "/content/repository/import",
    response_model=None,
    operation_id="importContentRepository",
)
async def import_content_repository(
    body: ContentRepositoryImportRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    require_content_import(request)
    try:
        result = await import_repository_snapshot(db, body)
    except ContentError as error:
        _raise(error)
        raise
    await emit_audit(
        db,
        actor_account_id=None,
        action="content.repository.import",
        target_table="article_repository_state",
        target_id="1",
        payload={
            "generation": result.generation,
            "snapshot_digest": result.snapshot_digest,
            "created": result.created,
            "activated": result.activated,
            "removed": result.removed,
            "unchanged": result.unchanged,
        },
    )
    return _resource(result)


@router.get("/content/{type}/{slug}", response_model=None, operation_id="readContent")
async def read_content(
    type: str,
    slug: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    locale: Annotated[Literal["ru", "en"], Query()],
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    try:
        detail, etag = await read_published(db, article_type=type, slug=slug, locale=locale)
    except ContentError as error:
        _raise(error)
        raise
    return _public(detail, etag=etag, if_none_match=if_none_match)


@router.put(
    "/staff/content/{type}/{slug}",
    response_model=None,
    operation_id="putStaffContent",
)
async def put_staff_content(
    type: str,
    slug: str,
    body: StaffContentPublishRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    await require_staff(ctx, _staff_ids(request))
    try:
        result = await publish_staff_article(
            db,
            article_type=type,
            slug=slug,
            request=body,
            actor_account_id=ctx.account_id,
        )
    except ContentError as error:
        _raise(error)
        raise
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="content.staff.publish",
        target_table="article",
        target_id=result.article_id,
        payload={"active_digest": result.active_digest, "revision_ids": result.revision_ids},
    )
    return _resource(result)


@router.delete(
    "/staff/content/{type}/{slug}",
    response_model=None,
    operation_id="deleteStaffContent",
)
async def delete_staff_content(
    type: str,
    slug: str,
    body: StaffContentUnpublishRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    await require_staff(ctx, _staff_ids(request))
    try:
        result = await unpublish_staff_article(
            db,
            article_type=type,
            slug=slug,
            expected_active_digest=body.expected_active_digest,
        )
    except ContentError as error:
        _raise(error)
        raise
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="content.staff.unpublish",
        target_table="article",
        target_id=result.article_id,
        payload={"unpublished": True},
    )
    return _resource(result)
