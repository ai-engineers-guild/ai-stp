"""HTTP routes for public profile owner, publisher, and media (SPEC-028)."""

from __future__ import annotations

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.profile import service as profile_service
from ai_stp_platform.storage.avatar_store import AvatarObjectStore

router = APIRouter(tags=["profile"])


def _avatar_store(request: Request) -> AvatarObjectStore:
    store = getattr(request.app.state, "avatar_store", None)
    if store is None:
        raise ApiError(ErrorCategory.DEPENDENCY, "object storage unavailable")
    return cast(AvatarObjectStore, store)


async def _json_object(request: Request) -> dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise ApiError(ErrorCategory.VALIDATION, "invalid body")
    return cast(dict[str, Any], payload)


@router.get("/account/public-profile", response_model=None)
async def owner_public_profile(
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    body = await profile_service.get_owner_profile(db, account_id=ctx.account_id)
    return JSONResponse(content=body)


@router.put("/account/public-profile/draft", response_model=None)
async def put_public_profile_draft(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    del idempotency_key
    payload = await _json_object(request)
    body = await profile_service.save_draft(
        db,
        account_id=ctx.account_id,
        payload=payload,
        if_match=if_match,
    )
    return JSONResponse(content=body)


@router.get("/account/public-profile/preview", response_model=None)
async def preview_public_profile(
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    body = await profile_service.owner_preview(db, account_id=ctx.account_id)
    return JSONResponse(content=body, headers={"Cache-Control": "private, no-store"})


@router.post("/account/public-profile/publish", response_model=None)
async def publish_public_profile(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    if not idempotency_key:
        raise ApiError(ErrorCategory.VALIDATION, "idempotency key required")
    payload = await _json_object(request)
    digest = payload.get("content_digest")
    if not isinstance(digest, str) or not digest:
        raise ApiError(ErrorCategory.VALIDATION, "content_digest required")
    body = await profile_service.publish_profile(
        db,
        account_id=ctx.account_id,
        expected_digest=digest,
        idempotency_key=idempotency_key,
    )
    return JSONResponse(content=body)


@router.post("/account/public-profile/avatar", response_model=None)
async def upload_avatar(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    """Upload avatar image bytes; writes processed object to S3/RustFS."""
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    payload: bytes
    if content_type.startswith("multipart/"):
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise ApiError(ErrorCategory.VALIDATION, "file required")
        raw = await upload.read()  # type: ignore[misc]
        if not isinstance(raw, (bytes, bytearray)):
            raise ApiError(ErrorCategory.VALIDATION, "file required")
        payload = bytes(raw)
        content_type = str(getattr(upload, "content_type", None) or "application/octet-stream")
        content_type = content_type.split(";")[0].strip().lower()
    else:
        payload = await request.body()
    if not content_type:
        raise ApiError(ErrorCategory.VALIDATION, "content-type required")
    store = _avatar_store(request)
    body = await profile_service.create_avatar_from_bytes(
        db,
        store,
        account_id=ctx.account_id,
        content_type=content_type,
        payload=payload,
        source="upload",
    )
    return JSONResponse(content=body, status_code=201)


@router.post("/account/public-profile/avatar/from-identity", response_model=None)
async def avatar_from_identity(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    payload = await _json_object(request)
    provider = payload.get("provider")
    if not isinstance(provider, str):
        raise ApiError(ErrorCategory.VALIDATION, "provider required")
    store = _avatar_store(request)
    body = await profile_service.create_avatar_from_identity(
        db,
        store,
        account_id=ctx.account_id,
        provider=provider,
    )
    return JSONResponse(content=body, status_code=201)


@router.get("/media/avatars/{asset_id}", response_model=None)
async def get_avatar_media(
    asset_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Serve processed avatar bytes; never provider source URL."""
    store = _avatar_store(request)
    result = await profile_service.read_avatar_bytes(db, store, asset_id=asset_id)
    if result is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "not found")
    body, content_type = result
    return Response(
        content=body,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/publishers/{account_id}", response_model=None)
async def public_publisher(
    account_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    if not account_id.startswith("account_"):
        raise ApiError(ErrorCategory.NOT_FOUND, "not found")
    body = await profile_service.get_public_publisher(db, account_id=account_id)
    if body is None:
        author_verified = await profile_service.get_author_verified(db, account_id=account_id)
        return JSONResponse(
            content={
                "schema_version": 1,
                "kind": "public_profile",
                "account_id": account_id,
                "display_name": None,
                "bio": None,
                "links": [],
                "avatar_url": None,
                "empty": True,
                "author_verified": author_verified,
            }
        )
    return JSONResponse(content=body)
