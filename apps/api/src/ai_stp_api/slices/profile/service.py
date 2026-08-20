"""Public profile draft/publish/preview and S3-backed avatars (SPEC-028)."""

from __future__ import annotations

import ipaddress
import secrets
from typing import Any, cast
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_contracts.public_profile import (
    ProfileFields,
    ProfileLink,
    content_digest,
    is_empty_profile,
    public_projection,
    validate_avatar_upload,
)
from ai_stp_platform.models import (
    AccountAuthorVerification,
    AvatarAsset,
    OAuthIdentity,
    ProfileRevision,
    PublicProfile,
)
from ai_stp_platform.storage.avatar_store import AvatarObjectStore


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


def _fields_from_revision(row: ProfileRevision) -> ProfileFields:
    links: list[ProfileLink] = []
    raw = cast(object, row.links)
    items = cast(list[object], raw) if isinstance(raw, list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        mapping = cast(dict[str, object], item)
        label = mapping.get("label")
        url = mapping.get("url")
        if isinstance(label, str) and isinstance(url, str):
            links.append(ProfileLink(label=label, url=url))
    return ProfileFields(
        display_name=row.display_name,
        bio=row.bio,
        links=links,
        avatar_asset_id=row.avatar_asset_id,
    )


async def _avatar_url(db: AsyncSession, asset_id: str | None) -> str | None:
    if not asset_id:
        return None
    asset = await db.get(AvatarAsset, asset_id)
    if asset is None or asset.state != "ready":
        return None
    return asset.public_url


async def ensure_profile(db: AsyncSession, account_id: str) -> PublicProfile:
    row = await db.get(PublicProfile, account_id)
    if row is not None:
        return row
    row = PublicProfile(account_id=account_id)
    db.add(row)
    await db.flush()
    return row


async def get_owner_profile(db: AsyncSession, *, account_id: str) -> dict[str, Any]:
    profile = await ensure_profile(db, account_id)
    draft = (
        await db.get(ProfileRevision, profile.draft_revision_id)
        if profile.draft_revision_id
        else None
    )
    published = (
        await db.get(ProfileRevision, profile.published_revision_id)
        if profile.published_revision_id
        else None
    )
    draft_fields = _fields_from_revision(draft) if draft else ProfileFields()
    published_fields = _fields_from_revision(published) if published else None
    editable_revision = draft or published
    editable_fields = (
        _fields_from_revision(editable_revision) if editable_revision else ProfileFields()
    )
    editable_source = "draft" if draft else "published" if published else "empty"
    state = "absent"
    if published is not None and draft is None:
        state = "published"
    elif draft is not None:
        state = "draft"
    return {
        "schema_version": 1,
        "account_id": account_id,
        "state": state,
        "editable": {
            "source": editable_source,
            "base_revision_id": editable_revision.id if editable_revision else None,
            "base_content_digest": (
                editable_revision.content_digest if editable_revision else None
            ),
            "fields": editable_fields.model_dump(),
            "avatar_url": await _avatar_url(db, editable_fields.avatar_asset_id),
        },
        "draft": {
            "revision_id": draft.id if draft else None,
            "content_digest": draft.content_digest if draft else None,
            "fields": draft_fields.model_dump(),
            "avatar_url": await _avatar_url(db, draft_fields.avatar_asset_id),
        },
        "published": (
            {
                "revision_id": published.id,
                "content_digest": published.content_digest,
                "fields": published_fields.model_dump(),
                "avatar_url": await _avatar_url(db, published_fields.avatar_asset_id),
                "projection": public_projection(
                    account_id=account_id,
                    fields=published_fields or ProfileFields(),
                    avatar_public_url=await _avatar_url(
                        db, (published_fields or ProfileFields()).avatar_asset_id
                    ),
                ),
            }
            if published is not None and published_fields is not None
            else None
        ),
    }


async def save_draft(
    db: AsyncSession,
    *,
    account_id: str,
    payload: dict[str, Any],
    if_match: str | None,
) -> dict[str, Any]:
    try:
        links_raw = payload.get("links")
        if links_raw is None:
            link_items: list[object] = []
        elif isinstance(links_raw, list):
            link_items = cast(list[object], links_raw)
        else:
            raise ValueError("links must be a list")
        links = [ProfileLink.model_validate(item) for item in link_items]
        name_raw = payload.get("display_name")
        bio_raw = payload.get("bio")
        avatar_raw = payload.get("avatar_asset_id")
        name_val = name_raw if isinstance(name_raw, str) else None
        bio_val = bio_raw if isinstance(bio_raw, str) else None
        avatar_val = avatar_raw if isinstance(avatar_raw, str) else None
        fields = ProfileFields(
            display_name=name_val,
            bio=bio_val,
            links=links,
            avatar_asset_id=avatar_val,
        )
    except (ValidationError, ValueError, TypeError) as exc:
        raise ApiError(ErrorCategory.VALIDATION, "invalid profile fields") from exc

    profile = await ensure_profile(db, account_id)
    if profile.draft_revision_id and if_match:
        current = await db.get(ProfileRevision, profile.draft_revision_id)
        if current is not None and current.content_digest != if_match.strip():
            raise ApiError(ErrorCategory.PRECONDITION, "precondition failed")

    digest = content_digest(fields)
    revision = ProfileRevision(
        id=_new_id("prevision"),
        account_id=account_id,
        lifecycle="draft",
        display_name=fields.display_name,
        bio=fields.bio,
        links=[{"label": link.label, "url": link.url} for link in fields.links],
        avatar_asset_id=fields.avatar_asset_id,
        content_digest=digest,
    )
    db.add(revision)
    await db.flush()
    profile.draft_revision_id = revision.id
    await db.flush()
    return await get_owner_profile(db, account_id=account_id)


async def owner_preview(db: AsyncSession, *, account_id: str) -> dict[str, Any]:
    profile = await ensure_profile(db, account_id)
    rev_id = profile.draft_revision_id or profile.published_revision_id
    if rev_id is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "profile not found")
    rev = await db.get(ProfileRevision, rev_id)
    if rev is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "profile not found")
    fields = _fields_from_revision(rev)
    return {
        "schema_version": 1,
        "preview": True,
        "lifecycle": rev.lifecycle,
        "content_digest": rev.content_digest,
        "projection": public_projection(
            account_id=account_id,
            fields=fields,
            avatar_public_url=await _avatar_url(db, fields.avatar_asset_id),
        ),
    }


async def publish_profile(
    db: AsyncSession,
    *,
    account_id: str,
    expected_digest: str,
    idempotency_key: str,
) -> dict[str, Any]:
    del idempotency_key
    profile = await ensure_profile(db, account_id)
    if not profile.draft_revision_id:
        raise ApiError(ErrorCategory.VALIDATION, "no draft to publish")
    draft = await db.get(ProfileRevision, profile.draft_revision_id)
    if draft is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "profile not found")
    if draft.content_digest != expected_digest:
        raise ApiError(ErrorCategory.PRECONDITION, "precondition failed")
    fields = _fields_from_revision(draft)
    if is_empty_profile(fields):
        if profile.published_revision_id:
            old = await db.get(ProfileRevision, profile.published_revision_id)
            if old is not None:
                old.lifecycle = "superseded"
        profile.published_revision_id = None
        profile.draft_revision_id = None
        await db.flush()
        return {
            "schema_version": 1,
            "operation_id": _new_id("op"),
            "published": False,
            "account_id": account_id,
        }

    if profile.published_revision_id:
        old = await db.get(ProfileRevision, profile.published_revision_id)
        if old is not None:
            old.lifecycle = "superseded"
    draft.lifecycle = "published"
    profile.published_revision_id = draft.id
    profile.draft_revision_id = None
    await db.flush()
    return {
        "schema_version": 1,
        "operation_id": _new_id("op"),
        "published": True,
        "content_digest": draft.content_digest,
        "projection": public_projection(
            account_id=account_id,
            fields=fields,
            avatar_public_url=await _avatar_url(db, fields.avatar_asset_id),
        ),
    }


async def create_avatar_from_bytes(
    db: AsyncSession,
    store: AvatarObjectStore,
    *,
    account_id: str,
    content_type: str,
    payload: bytes,
    source: str = "upload",
) -> dict[str, Any]:
    try:
        validate_avatar_upload(content_type=content_type, size_bytes=len(payload))
    except ValueError as exc:
        raise ApiError(ErrorCategory.VALIDATION, str(exc)) from exc
    if not payload:
        raise ApiError(ErrorCategory.VALIDATION, "empty avatar payload")

    asset_id = _new_id("avatar")
    asset = AvatarAsset(
        id=asset_id,
        account_id=account_id,
        state="processing",
        content_type=content_type,
        size_bytes=len(payload),
        public_url=None,
        object_key=None,
        content_digest=None,
        source=source,
    )
    db.add(asset)
    await db.flush()

    try:
        stored = await store.put_avatar(
            asset_id=asset_id,
            payload=payload,
            content_type=content_type,
        )
    except Exception as exc:
        asset.state = "rejected"
        await db.flush()
        raise ApiError(ErrorCategory.DEPENDENCY, "object storage unavailable") from exc

    asset.state = "ready"
    asset.object_key = stored.object_key
    asset.content_digest = stored.content_digest
    asset.public_url = stored.public_path
    asset.size_bytes = stored.size_bytes
    await db.flush()
    return {
        "schema_version": 1,
        "avatar_asset_id": asset_id,
        "state": asset.state,
        "public_url": asset.public_url,
        "object_key": asset.object_key,
        "content_digest": asset.content_digest,
        "size_bytes": asset.size_bytes,
    }


def _reject_ssrf_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ApiError(ErrorCategory.VALIDATION, "avatar source must be https")
    host = parsed.hostname or ""
    if not host or host.lower() in {"localhost", "metadata.google.internal"}:
        raise ApiError(ErrorCategory.VALIDATION, "avatar source host not allowed")
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ApiError(ErrorCategory.VALIDATION, "avatar source host not allowed")
    except ValueError:
        # Hostname not an IP literal — DNS is resolved by httpx; still block obvious local names.
        if host.endswith(".local") or host.endswith(".internal"):
            raise ApiError(ErrorCategory.VALIDATION, "avatar source host not allowed") from None


async def create_avatar_from_identity(
    db: AsyncSession,
    store: AvatarObjectStore,
    *,
    account_id: str,
    provider: str,
    http_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    if provider not in {"github", "google"}:
        raise ApiError(ErrorCategory.VALIDATION, "unsupported avatar provider")
    result = await db.execute(
        select(OAuthIdentity).where(
            OAuthIdentity.account_id == account_id,
            OAuthIdentity.provider == provider,
            OAuthIdentity.state == "linked",
        )
    )
    identity = result.scalar_one_or_none()
    if identity is None:
        raise ApiError(
            ErrorCategory.VALIDATION,
            f"no linked {provider} identity; link the account first",
        )
    if not identity.avatar_url:
        raise ApiError(
            ErrorCategory.VALIDATION,
            f"linked {provider} identity has no avatar URL; re-link the identity",
        )
    source_url = identity.avatar_url
    _reject_ssrf_url(source_url)

    client = http_client or httpx.AsyncClient(timeout=10.0, follow_redirects=True, max_redirects=3)
    owns_client = http_client is None
    try:
        response = await client.get(source_url)
        if response.status_code >= 400:
            raise ApiError(ErrorCategory.DEPENDENCY, "avatar source fetch failed")
        content_type = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        payload = response.content
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError(ErrorCategory.DEPENDENCY, "avatar source fetch failed") from exc
    finally:
        if owns_client:
            await client.aclose()

    return await create_avatar_from_bytes(
        db,
        store,
        account_id=account_id,
        content_type=content_type,
        payload=payload,
        source=provider,
    )


async def get_public_publisher(db: AsyncSession, *, account_id: str) -> dict[str, Any] | None:
    profile = await db.get(PublicProfile, account_id)
    if profile is None or not profile.published_revision_id:
        return None
    rev = await db.get(ProfileRevision, profile.published_revision_id)
    if rev is None or rev.lifecycle != "published":
        return None
    fields = _fields_from_revision(rev)
    if is_empty_profile(fields):
        return None
    return public_projection(
        account_id=account_id,
        fields=fields,
        avatar_public_url=await _avatar_url(db, fields.avatar_asset_id),
        author_verified=await get_author_verified(db, account_id=account_id),
    )


async def get_author_verified(db: AsyncSession, *, account_id: str) -> bool:
    row = await db.get(AccountAuthorVerification, account_id)
    return bool(row and row.verified)


async def read_avatar_bytes(
    db: AsyncSession,
    store: AvatarObjectStore,
    *,
    asset_id: str,
) -> tuple[bytes, str] | None:
    asset = await db.get(AvatarAsset, asset_id)
    if asset is None or asset.state != "ready" or not asset.object_key:
        return None
    body = await store.read_bytes(object_key=asset.object_key)
    if body is None:
        return None
    return body, asset.content_type
