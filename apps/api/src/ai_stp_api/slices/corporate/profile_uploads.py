"""Profile-authorized uploads reuse incumbent processing, storage and delivery."""

import hashlib
import secrets
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import entity_profiles, service
from ai_stp_api.slices.owner.media_processing import MediaProcessingError, normalize_upload
from ai_stp_api.slices.profile.service import create_avatar_from_bytes
from ai_stp_contracts.corporate_profiles import EntityProfileSubject, EntityProfileUploadResponse
from ai_stp_contracts.owner import validate_component_media_upload
from ai_stp_platform.models import AvatarAsset
from ai_stp_platform.storage.avatar_store import AvatarObjectStore


async def upload(
    db: AsyncSession,
    store: AvatarObjectStore,
    *,
    ctx: AuthContext,
    organization_id: str,
    subject: EntityProfileSubject,
    purpose: Literal["avatar", "media"],
    payload: bytes,
    content_type: str,
    expected_revision: int,
    authorization_revision: int,
    idempotency_key: str,
    request_id: str | None,
) -> EntityProfileUploadResponse:
    operation = "entity.profile.upload"
    fingerprint = service.mutation_fingerprint(
        {
            **subject.model_dump(),
            "purpose": purpose,
            "digest": hashlib.sha256(payload).hexdigest(),
            "content_type": content_type,
            "expected_revision": expected_revision,
            "authorization_revision": authorization_revision,
        }
    )
    _, receipt = await service.authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="entity_profile.update",
        scope_kind=subject.subject_kind,
        scope_id=subject.subject_id,
        authorization_revision=authorization_revision,
        idempotency_key=idempotency_key,
        operation=operation,
        fingerprint=fingerprint,
        request_id=request_id,
    )
    if receipt is not None:
        return EntityProfileUploadResponse.model_validate(receipt.response_body)
    row = await entity_profiles.profile_target(db, organization_id, subject, lock=True)
    if (row.profile_revision or 0) != expected_revision:
        raise ApiError(ErrorCategory.PRECONDITION, "profile revision is stale")
    if purpose == "avatar":
        result = await create_avatar_from_bytes(
            db, store, account_id=ctx.account_id, content_type=content_type, payload=payload
        )
        response = EntityProfileUploadResponse(
            avatar_asset_id=result["avatar_asset_id"],
            media_id=result["avatar_asset_id"],
            public_url=result["public_url"],
            kind="image",
            size_bytes=result["size_bytes"],
        )
    else:
        try:
            kind = validate_component_media_upload(
                content_type=content_type, size_bytes=len(payload), payload=payload
            )
            payload = await normalize_upload(payload, content_type)
            validate_component_media_upload(
                content_type=content_type, size_bytes=len(payload), payload=payload
            )
        except MediaProcessingError as exc:
            raise ApiError(ErrorCategory.DEPENDENCY, str(exc)) from exc
        except ValueError as exc:
            raise ApiError(ErrorCategory.VALIDATION, str(exc)) from exc
        # AvatarAsset is the incumbent processed upload record and public byte delivery.
        asset_id = f"avatar_{secrets.token_hex(12)}"
        try:
            stored = await store.put_avatar(
                asset_id=asset_id,
                payload=payload,
                content_type=content_type,
                owner_account_id=ctx.account_id,
                # Reuse the incumbent processed asset namespace and delivery route.
                # Tenant/subject attachment is enforced by profile PUT via asset ownership.
                namespace="users/avatars",
            )
        except Exception as exc:
            raise ApiError(ErrorCategory.DEPENDENCY, "object storage unavailable") from exc
        db.add(
            AvatarAsset(
                id=asset_id,
                account_id=ctx.account_id,
                state="ready",
                content_type=content_type,
                size_bytes=stored.size_bytes,
                public_url=stored.public_path,
                object_key=stored.object_key,
                content_digest=stored.content_digest,
                source="upload",
            )
        )
        await db.flush()
        response = EntityProfileUploadResponse(
            avatar_asset_id=asset_id,
            media_id=asset_id,
            public_url=stored.public_path,
            kind=kind,
            size_bytes=stored.size_bytes,
        )
    await service.store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=idempotency_key,
        operation=operation,
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action=operation,
        target_table="avatar_asset",
        target_id=response.avatar_asset_id,
        request_id=request_id,
    )
    return response
