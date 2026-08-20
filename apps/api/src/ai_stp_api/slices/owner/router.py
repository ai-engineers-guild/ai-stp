"""Owner workspace read routes (SPEC-027)."""

from __future__ import annotations

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.owner import service
from ai_stp_contracts.http import PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX
from ai_stp_contracts.owner import (
    OwnerExternalProductAttachRequest,
    OwnerExternalProductCreateRequest,
    OwnerPresentationUpdateRequest,
    OwnerStartPublicationRequest,
)
from ai_stp_platform.storage.avatar_store import AvatarObjectStore

router = APIRouter(tags=["owner"])


def _resource(model: object, *, status_code: int = 200) -> JSONResponse:
    payload = model.model_dump(mode="json")  # type: ignore[attr-defined]
    return JSONResponse(content=payload, status_code=status_code)


def _avatar_store(request: Request) -> AvatarObjectStore:
    store = getattr(request.app.state, "avatar_store", None)
    if store is None:
        raise ApiError(ErrorCategory.DEPENDENCY, "object storage unavailable")
    return cast(AvatarObjectStore, store)


@router.post("/owner/external-products", response_model=None)
async def create_external_product(
    body: OwnerExternalProductCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    del ctx  # authentication is required; products are shared curated metadata
    return _resource(await service.create_external_product(db, body=body), status_code=201)


@router.put("/owner/objects/{object_kind}/{stable_id}/external-products", response_model=None)
async def replace_object_external_products(
    object_kind: Literal["component", "setup"],
    stable_id: str,
    body: OwnerExternalProductAttachRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    return _resource(
        await service.replace_object_external_products(
            db, ctx=ctx, object_kind=object_kind, stable_id=stable_id, body=body
        )
    )


@router.get("/owner/objects/{object_kind}/{stable_id}/external-products", response_model=None)
async def read_object_external_products(
    object_kind: Literal["component", "setup"],
    stable_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    return _resource(
        await service.read_object_external_products(
            db, ctx=ctx, object_kind=object_kind, stable_id=stable_id
        )
    )


@router.get("/owner/objects", response_model=None)
async def list_owner_objects(
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    page_size: Annotated[int, Query(ge=1, le=PAGE_SIZE_MAX)] = PAGE_SIZE_DEFAULT,
    object_kind: Annotated[Literal["component", "setup"] | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
) -> JSONResponse:
    del cursor  # opaque cursor reserved; first page is complete for MVP density
    result = await service.list_owner_objects(
        db, ctx=ctx, object_kind=object_kind, page_size=page_size
    )
    return _resource(result)


@router.get("/owner/objects/component/{stable_id}/presentation", response_model=None)
async def read_component_presentation(
    stable_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    return _resource(await service.read_owner_presentation(db, ctx=ctx, stable_id=stable_id))


@router.put("/owner/objects/component/{stable_id}/presentation", response_model=None)
async def update_component_presentation(
    stable_id: str,
    body: OwnerPresentationUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    return _resource(
        await service.update_owner_presentation(db, ctx=ctx, stable_id=stable_id, body=body)
    )


@router.post("/owner/objects/component/{stable_id}/presentation/media", response_model=None)
async def upload_component_presentation_media(
    stable_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    """Upload author image/video for the mutable component gallery (SPEC-035)."""
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
    body = await service.upload_owner_component_media(
        db,
        _avatar_store(request),
        ctx=ctx,
        stable_id=stable_id,
        content_type=content_type,
        payload=payload,
    )
    return JSONResponse(content=body, status_code=201)


@router.get("/media/component/{media_id}", response_model=None)
async def get_component_media(
    media_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Serve ready component media bytes; never expose object keys."""
    result = await service.read_component_media_bytes(db, _avatar_store(request), media_id=media_id)
    if result is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "not found")
    body, content_type = result
    return Response(
        content=body,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/owner/objects/{object_kind}/{stable_id}", response_model=None)
async def read_owner_object(
    object_kind: Literal["component", "setup"],
    stable_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.read_owner_object(
        db, ctx=ctx, object_kind=object_kind, stable_id=stable_id
    )
    return _resource(result)


@router.get(
    "/owner/objects/{object_kind}/{stable_id}/versions/{version}",
    response_model=None,
)
async def read_owner_version(
    object_kind: Literal["component", "setup"],
    stable_id: str,
    version: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.read_owner_version(
        db,
        ctx=ctx,
        object_kind=object_kind,
        stable_id=stable_id,
        version=version,
    )
    return _resource(result)


@router.post(
    "/owner/objects/{object_kind}/{stable_id}/versions/{version}/publication-plans",
    response_model=None,
)
async def start_owner_publication(
    object_kind: Literal["component", "setup"],
    stable_id: str,
    version: str,
    body: OwnerStartPublicationRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    result = await service.start_publication(
        db,
        ctx=ctx,
        object_kind=object_kind,
        stable_id=stable_id,
        version=version,
        body=body,
    )
    return _resource(result, status_code=201)
