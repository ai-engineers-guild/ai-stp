"""Additive shared profile routes preserve legacy entity contracts."""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.media_upload import read_media_upload
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import entity_profiles, profile_uploads
from ai_stp_contracts.corporate import OrganizationId
from ai_stp_contracts.corporate_profiles import (
    EntityProfileKind,
    EntityProfileSubject,
    EntityProfileUploadResponse,
    EntityProfileView,
    EntityProfileWriteRequest,
    TechnologyOwnerRequest,
)
from ai_stp_contracts.http import IdempotencyKey
from ai_stp_contracts.owner import COMPONENT_MEDIA_MAX_BYTES
from ai_stp_contracts.public_profile import AVATAR_MAX_BYTES
from ai_stp_contracts.technology import TechnologyId
from ai_stp_platform.storage.avatar_store import AvatarObjectStore

router = APIRouter(tags=["corporate"])
PROFILE_PATH = (
    "/corporate/organizations/{organization_id}/entity-profiles/{subject_kind}/{subject_id}"
)


@router.post(
    "/corporate/organizations/{organization_id}/profiles/{kind}/{id}/media",
    response_model=EntityProfileUploadResponse,
)
async def upload_profile_media(
    organization_id: OrganizationId,
    kind: EntityProfileKind,
    id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    purpose: Literal["avatar", "media"],
    expected_revision: Annotated[int, Query(ge=0)],
    authorization_revision: Annotated[int, Query(ge=1)],
    idempotency_key: Annotated[IdempotencyKey, Header(alias="Idempotency-Key")],
) -> EntityProfileUploadResponse:
    store = getattr(request.app.state, "avatar_store", None)
    if store is None:
        raise ApiError(ErrorCategory.DEPENDENCY, "object storage unavailable")
    payload, content_type = await read_media_upload(
        request,
        max_bytes=AVATAR_MAX_BYTES if purpose == "avatar" else COMPONENT_MEDIA_MAX_BYTES,
    )
    return await profile_uploads.upload(
        db,
        cast(AvatarObjectStore, store),
        ctx=ctx,
        organization_id=organization_id,
        subject=_subject(kind, id),
        purpose=purpose,
        payload=payload,
        content_type=content_type,
        expected_revision=expected_revision,
        authorization_revision=authorization_revision,
        idempotency_key=idempotency_key,
        request_id=getattr(request.state, "request_id", None),
    )


def _subject(kind: EntityProfileKind, identity: str) -> EntityProfileSubject:
    try:
        return EntityProfileSubject(subject_kind=kind, subject_id=identity)
    except ValidationError as exc:
        raise ApiError(ErrorCategory.VALIDATION, "profile identity does not match kind") from exc


@router.get(PROFILE_PATH, response_model=EntityProfileView)
async def read_entity_profile(
    organization_id: OrganizationId,
    subject_kind: EntityProfileKind,
    subject_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> EntityProfileView:
    return await entity_profiles.read_profile(
        db, ctx=ctx, organization_id=organization_id, subject=_subject(subject_kind, subject_id)
    )


@router.put(PROFILE_PATH, response_model=EntityProfileView)
async def write_entity_profile(
    organization_id: OrganizationId,
    subject_kind: EntityProfileKind,
    subject_id: str,
    payload: EntityProfileWriteRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> EntityProfileView:
    return await entity_profiles.write_profile(
        db,
        ctx=ctx,
        organization_id=organization_id,
        subject=_subject(subject_kind, subject_id),
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )


@router.put(
    "/corporate/organizations/{organization_id}/technologies/{technology_id}/owner",
    response_model=EntityProfileView,
)
async def write_technology_owner(
    organization_id: OrganizationId,
    technology_id: TechnologyId,
    payload: TechnologyOwnerRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> EntityProfileView:
    return await entity_profiles.write_profile(
        db,
        ctx=ctx,
        organization_id=organization_id,
        subject=EntityProfileSubject(subject_kind="technology", subject_id=technology_id),
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )
