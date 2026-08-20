"""Owner workspace read models (SPEC-027 / ADR-0068)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.publish import service as publish_service
from ai_stp_contracts.catalog import ExternalProductListResponse, ExternalProductSummary
from ai_stp_contracts.http import PageInfo
from ai_stp_contracts.owner import (
    COMPONENT_MEDIA_PUBLIC_PREFIX,
    OwnerEvidenceRow,
    OwnerExternalProductAttachRequest,
    OwnerExternalProductCreateRequest,
    OwnerObjectDetail,
    OwnerObjectListResponse,
    OwnerObjectSummary,
    OwnerPresentationMedia,
    OwnerPresentationResponse,
    OwnerPresentationUpdateRequest,
    OwnerStartPublicationRequest,
    OwnerVersionDetail,
    OwnerVersionSummary,
    is_component_media_public_url,
    validate_component_media_upload,
)
from ai_stp_contracts.publication import (
    PublicationPlanCreateRequest,
    PublicationPlanResponse,
)
from ai_stp_platform.external_catalog import COUNTRY_CODES, canonical_external_url
from ai_stp_platform.models import (
    CatalogExternalProduct,
    CatalogMetadata,
    ComponentMedia,
    EvidenceBinding,
    ExternalProduct,
    ExternalProductCountry,
    PublicationPlan,
    ValidationSnapshot,
)
from ai_stp_platform.storage.avatar_store import AvatarObjectStore


async def read_owner_presentation(
    db: AsyncSession, *, ctx: AuthContext, stable_id: str
) -> OwnerPresentationResponse:
    rows = list(
        (
            await db.execute(
                select(CatalogMetadata)
                .where(
                    CatalogMetadata.owner_account_id == ctx.account_id,
                    CatalogMetadata.object_kind == "component",
                    CatalogMetadata.stable_id == stable_id,
                )
                .order_by(CatalogMetadata.updated_at.desc(), CatalogMetadata.id.desc())
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise ApiError(ErrorCategory.NOT_FOUND, "component not found")
    latest = rows[0]
    bio = latest.presentation_bio
    if bio is None and isinstance(latest.passport_document, dict):
        value = latest.passport_document.get("description")
        bio = value if isinstance(value, str) else ""
    media_rows = list(
        (
            await db.execute(
                select(ComponentMedia)
                .where(
                    ComponentMedia.owner_account_id == ctx.account_id,
                    ComponentMedia.stable_id == stable_id,
                    ComponentMedia.state == "ready",
                )
                .order_by(ComponentMedia.position)
            )
        )
        .scalars()
        .all()
    )
    media = [
        OwnerPresentationMedia(
            kind=item.kind,  # type: ignore[arg-type]
            url=(item.youtube_video_id or "")
            if item.kind == "youtube"
            else (item.public_url or ""),
            alt=item.alt,
            caption=item.caption or "",
        )
        for item in media_rows
    ]
    return OwnerPresentationResponse(
        schema_version=1, stable_id=stable_id, bio=bio or "", media=media
    )


async def create_external_product(
    db: AsyncSession, *, body: OwnerExternalProductCreateRequest
) -> ExternalProductSummary:
    canonical = canonical_external_url(body.primary_url)
    if canonical is None:
        raise ApiError(ErrorCategory.VALIDATION, "primary_url must be a shallow public HTTPS URL")
    primary_url, domain = canonical
    invalid = sorted(set(body.country_codes) - COUNTRY_CODES)
    if invalid:
        raise ApiError(
            ErrorCategory.VALIDATION,
            "unknown country code",
            details={"country_codes": ",".join(invalid)},
        )
    if await db.scalar(
        select(ExternalProduct.id).where(ExternalProduct.canonical_domain == domain)
    ):
        raise ApiError(ErrorCategory.CONFLICT, "service domain already exists")
    normalized_name = "".join(
        character for character in body.name.casefold() if character.isalnum()
    )
    products = list((await db.execute(select(ExternalProduct))).scalars())
    similar = [
        row.canonical_domain
        for row in products
        if "".join(character for character in row.name.casefold() if character.isalnum())
        == normalized_name
    ]
    if similar:
        raise ApiError(
            ErrorCategory.CONFLICT,
            "similar service name exists",
            details={"candidates": ",".join(similar)},
        )
    product = ExternalProduct(
        canonical_domain=domain, primary_url=primary_url, name=body.name.strip()
    )
    db.add(product)
    await db.flush()
    for code in sorted(set(body.country_codes)):
        db.add(ExternalProductCountry(external_product_id=product.id, country_code=code))
    await db.commit()
    return ExternalProductSummary(
        name=product.name,
        canonical_domain=domain,
        primary_url=primary_url,
        country_codes=sorted(set(body.country_codes)),
    )


async def replace_object_external_products(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    object_kind: str,
    stable_id: str,
    body: OwnerExternalProductAttachRequest,
) -> ExternalProductListResponse:
    rows = list(
        (
            await db.execute(
                select(CatalogMetadata).where(
                    CatalogMetadata.owner_account_id == ctx.account_id,
                    CatalogMetadata.object_kind == object_kind,
                    CatalogMetadata.stable_id == stable_id,
                )
            )
        ).scalars()
    )
    if not rows:
        raise ApiError(ErrorCategory.NOT_FOUND, "object not found")
    domains = sorted({domain.lower() for domain in body.canonical_domains})
    products = (
        list(
            (
                await db.execute(
                    select(ExternalProduct).where(ExternalProduct.canonical_domain.in_(domains))
                )
            ).scalars()
        )
        if domains
        else []
    )
    if len(products) != len(domains):
        raise ApiError(ErrorCategory.VALIDATION, "unknown service domain")
    metadata_ids = [row.id for row in rows]
    await db.execute(
        delete(CatalogExternalProduct).where(
            CatalogExternalProduct.catalog_metadata_id.in_(metadata_ids)
        )
    )
    for metadata_id in metadata_ids:
        for product in products:
            db.add(
                CatalogExternalProduct(
                    catalog_metadata_id=metadata_id, external_product_id=product.id
                )
            )
    await db.commit()
    country_rows = list((await db.execute(select(ExternalProductCountry))).scalars())
    countries: dict[int, list[str]] = {}
    for row in country_rows:
        countries.setdefault(row.external_product_id, []).append(row.country_code)
    return ExternalProductListResponse(
        items=[
            ExternalProductSummary(
                name=row.name,
                canonical_domain=row.canonical_domain,
                primary_url=row.primary_url,
                country_codes=sorted(countries.get(row.id, [])),
            )
            for row in products
        ]
    )


async def read_object_external_products(
    db: AsyncSession, *, ctx: AuthContext, object_kind: str, stable_id: str
) -> ExternalProductListResponse:
    metadata_ids = list(
        (
            await db.execute(
                select(CatalogMetadata.id).where(
                    CatalogMetadata.owner_account_id == ctx.account_id,
                    CatalogMetadata.object_kind == object_kind,
                    CatalogMetadata.stable_id == stable_id,
                )
            )
        ).scalars()
    )
    if not metadata_ids:
        raise ApiError(ErrorCategory.NOT_FOUND, "object not found")
    products = list(
        (
            await db.execute(
                select(ExternalProduct)
                .join(
                    CatalogExternalProduct,
                    CatalogExternalProduct.external_product_id == ExternalProduct.id,
                )
                .where(CatalogExternalProduct.catalog_metadata_id.in_(metadata_ids))
                .distinct()
                .order_by(ExternalProduct.name)
            )
        ).scalars()
    )
    country_rows = list((await db.execute(select(ExternalProductCountry))).scalars())
    countries: dict[int, list[str]] = {}
    for row in country_rows:
        countries.setdefault(row.external_product_id, []).append(row.country_code)
    return ExternalProductListResponse(
        items=[
            ExternalProductSummary(
                name=row.name,
                canonical_domain=row.canonical_domain,
                primary_url=row.primary_url,
                country_codes=sorted(countries.get(row.id, [])),
            )
            for row in products
        ]
    )


async def _require_owned_component(db: AsyncSession, *, ctx: AuthContext, stable_id: str) -> None:
    owned = await db.scalar(
        select(CatalogMetadata.id).where(
            CatalogMetadata.owner_account_id == ctx.account_id,
            CatalogMetadata.object_kind == "component",
            CatalogMetadata.stable_id == stable_id,
        )
    )
    if owned is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "component not found")


async def upload_owner_component_media(
    db: AsyncSession,
    store: AvatarObjectStore,
    *,
    ctx: AuthContext,
    stable_id: str,
    content_type: str,
    payload: bytes,
) -> dict[str, Any]:
    """Store author upload and return a ready public media path for the editor."""
    await _require_owned_component(db, ctx=ctx, stable_id=stable_id)
    try:
        kind = validate_component_media_upload(content_type=content_type, size_bytes=len(payload))
    except ValueError as exc:
        raise ApiError(ErrorCategory.VALIDATION, str(exc)) from exc
    if not payload:
        raise ApiError(ErrorCategory.VALIDATION, "empty component media payload")

    used_positions = set(
        (
            await db.execute(
                select(ComponentMedia.position).where(
                    ComponentMedia.owner_account_id == ctx.account_id,
                    ComponentMedia.stable_id == stable_id,
                )
            )
        )
        .scalars()
        .all()
    )
    free_position = next((index for index in range(5) if index not in used_positions), None)
    if free_position is None:
        raise ApiError(ErrorCategory.VALIDATION, "media gallery is full")

    media_id = f"media_{uuid4().hex}"
    try:
        stored = await store.put_avatar(
            asset_id=media_id,
            payload=payload,
            content_type=content_type,
        )
    except Exception as exc:
        raise ApiError(ErrorCategory.DEPENDENCY, "object storage unavailable") from exc

    # Public delivery path is component-scoped; storage key is content-addressed.
    public_url = f"/v1/media/component/{media_id}"
    db.add(
        ComponentMedia(
            id=media_id,
            stable_id=stable_id,
            owner_account_id=ctx.account_id,
            position=free_position,
            kind=kind,
            source_type="upload",
            state="ready",
            object_key=stored.object_key,
            public_url=public_url,
            content_type=content_type,
            size_bytes=stored.size_bytes,
            alt="Uploaded media",
            caption=None,
        )
    )
    await db.flush()
    return {
        "schema_version": 1,
        "media_id": media_id,
        "kind": kind,
        "public_url": public_url,
        "content_type": content_type,
        "size_bytes": stored.size_bytes,
        "state": "ready",
    }


async def read_component_media_bytes(
    db: AsyncSession,
    store: AvatarObjectStore,
    *,
    media_id: str,
) -> tuple[bytes, str] | None:
    """Serve ready component media bytes by public media id."""
    row = await db.get(ComponentMedia, media_id)
    if row is None or row.state != "ready" or not row.object_key:
        return None
    body = await store.read_bytes(object_key=row.object_key)
    if body is None:
        return None
    return body, row.content_type or "application/octet-stream"


async def update_owner_presentation(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    stable_id: str,
    body: OwnerPresentationUpdateRequest,
) -> OwnerPresentationResponse:
    await _require_owned_component(db, ctx=ctx, stable_id=stable_id)
    await db.execute(
        update(CatalogMetadata)
        .where(
            CatalogMetadata.owner_account_id == ctx.account_id,
            CatalogMetadata.object_kind == "component",
            CatalogMetadata.stable_id == stable_id,
        )
        .values(presentation_bio=body.bio)
    )
    existing_rows = list(
        (
            await db.execute(
                select(ComponentMedia).where(
                    ComponentMedia.owner_account_id == ctx.account_id,
                    ComponentMedia.stable_id == stable_id,
                )
            )
        )
        .scalars()
        .all()
    )
    existing_by_id = {row.id: row for row in existing_rows}
    rebuilt: list[ComponentMedia] = []
    for position, item in enumerate(body.media):
        if item.kind == "youtube":
            rebuilt.append(
                ComponentMedia(
                    id=f"media_{uuid4().hex}",
                    stable_id=stable_id,
                    owner_account_id=ctx.account_id,
                    position=position,
                    kind="youtube",
                    source_type="youtube",
                    state="ready",
                    public_url=None,
                    youtube_video_id=item.url,
                    alt=item.alt,
                    caption=item.caption or None,
                )
            )
            continue
        if is_component_media_public_url(item.url):
            media_id = item.url[len(COMPONENT_MEDIA_PUBLIC_PREFIX) :]
            previous = existing_by_id.get(media_id)
            if (
                previous is None
                or previous.owner_account_id != ctx.account_id
                or previous.stable_id != stable_id
                or previous.source_type != "upload"
                or not previous.object_key
            ):
                raise ApiError(ErrorCategory.VALIDATION, "unknown uploaded media reference")
            if previous.kind != item.kind:
                raise ApiError(ErrorCategory.VALIDATION, "uploaded media kind mismatch")
            rebuilt.append(
                ComponentMedia(
                    id=media_id,
                    stable_id=stable_id,
                    owner_account_id=ctx.account_id,
                    position=position,
                    kind=item.kind,
                    source_type="upload",
                    state="ready",
                    object_key=previous.object_key,
                    public_url=previous.public_url or item.url,
                    content_type=previous.content_type,
                    size_bytes=previous.size_bytes,
                    alt=item.alt,
                    caption=item.caption or None,
                )
            )
            continue
        rebuilt.append(
            ComponentMedia(
                id=f"media_{uuid4().hex}",
                stable_id=stable_id,
                owner_account_id=ctx.account_id,
                position=position,
                kind=item.kind,
                source_type="github",
                state="ready",
                public_url=item.url,
                youtube_video_id=None,
                alt=item.alt,
                caption=item.caption or None,
            )
        )
    await db.execute(
        delete(ComponentMedia).where(
            ComponentMedia.owner_account_id == ctx.account_id,
            ComponentMedia.stable_id == stable_id,
        )
    )
    # Flush deletes before re-inserting rows that may reuse the same primary keys.
    await db.flush()
    for row in rebuilt:
        db.add(row)
    await db.flush()
    return OwnerPresentationResponse(
        schema_version=1,
        stable_id=stable_id,
        bio=body.bio,
        media=list(body.media),
    )


def _ts(value: datetime | None) -> str | None:
    if value is None:
        return None
    moment = value if value.tzinfo else value.replace(tzinfo=UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _install_eligible(*, component_verified: bool, lifecycle: str) -> bool:
    return component_verified and lifecycle not in {"blocked", "hidden", "failed", "draft"}


def can_start_publication(*, lifecycle: str, published_at: datetime | None) -> bool:
    return published_at is None and lifecycle in {"draft", "ready", "failed", "stale"}


async def list_owner_objects(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    object_kind: str | None = None,
    page_size: int = 20,
) -> OwnerObjectListResponse:
    stmt = select(CatalogMetadata).where(CatalogMetadata.owner_account_id == ctx.account_id)
    if object_kind in {"component", "setup"}:
        stmt = stmt.where(CatalogMetadata.object_kind == object_kind)
    stmt = stmt.order_by(CatalogMetadata.updated_at.desc(), CatalogMetadata.id.desc())
    rows = list((await db.execute(stmt)).scalars().all())

    # Collapse versions into one object summary by (kind, stable_id).
    by_key: dict[tuple[str, str], list[CatalogMetadata]] = {}
    for row in rows:
        key = (row.object_kind, row.stable_id)
        by_key.setdefault(key, []).append(row)

    items: list[OwnerObjectSummary] = []
    for (kind, stable_id), versions in by_key.items():
        latest = versions[0]
        for candidate in versions:
            if (
                candidate.published_at
                and (latest.published_at is None or candidate.published_at > latest.published_at)
            ) or candidate.updated_at > latest.updated_at:
                latest = candidate
        name = latest.name or stable_id
        updated = _ts(latest.updated_at) or "1970-01-01T00:00:00.000Z"
        items.append(
            OwnerObjectSummary(
                schema_version=1,
                object_kind=kind,  # type: ignore[arg-type]
                stable_id=stable_id,
                name=name,
                latest_version=latest.version,
                visibility="public" if latest.visibility == "public" else "private",
                lifecycle_state=latest.lifecycle_state,  # type: ignore[arg-type]
                trust_lane=latest.trust_lane,  # type: ignore[arg-type]
                author_verified=bool(latest.author_verified),
                component_verified=bool(latest.component_verified),
                updated_at=updated,
            )
        )
        if len(items) >= page_size:
            break

    return OwnerObjectListResponse(
        schema_version=1,
        items=items,
        page=PageInfo(schema_version=1, next_cursor=None, page_size=max(page_size, 1)),
    )


async def read_owner_object(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    object_kind: str,
    stable_id: str,
) -> OwnerObjectDetail:
    rows = list(
        (
            await db.execute(
                select(CatalogMetadata)
                .where(
                    CatalogMetadata.owner_account_id == ctx.account_id,
                    CatalogMetadata.object_kind == object_kind,
                    CatalogMetadata.stable_id == stable_id,
                )
                .order_by(CatalogMetadata.version.desc())
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise ApiError(ErrorCategory.NOT_FOUND, "object not found")
    name = rows[0].name or stable_id
    versions: list[OwnerVersionSummary] = []
    for row in rows:
        if not row.version:
            continue
        versions.append(
            OwnerVersionSummary(
                schema_version=1,
                version=row.version,
                content_digest=row.passport_digest,
                lifecycle_state=row.lifecycle_state,  # type: ignore[arg-type]
                visibility="public" if row.visibility == "public" else "private",
                trust_lane=row.trust_lane,  # type: ignore[arg-type]
                author_verified=bool(row.author_verified),
                component_verified=bool(row.component_verified),
                install_eligible=_install_eligible(
                    component_verified=bool(row.component_verified),
                    lifecycle=row.lifecycle_state,
                ),
                published_at=_ts(row.published_at),
                can_start_publication=can_start_publication(
                    lifecycle=row.lifecycle_state,
                    published_at=row.published_at,
                )
                and row.visibility in {"private", "public"},
            )
        )
    return OwnerObjectDetail(
        schema_version=1,
        object_kind=object_kind,  # type: ignore[arg-type]
        stable_id=stable_id,
        name=name,
        versions=versions,
    )


async def read_owner_version(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    object_kind: str,
    stable_id: str,
    version: str,
) -> OwnerVersionDetail:
    row = await db.scalar(
        select(CatalogMetadata).where(
            CatalogMetadata.owner_account_id == ctx.account_id,
            CatalogMetadata.object_kind == object_kind,
            CatalogMetadata.stable_id == stable_id,
            CatalogMetadata.version == version,
        )
    )
    if row is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "version not found")

    evidence: list[OwnerEvidenceRow] = []
    open_plan_id = ""
    plan = await db.scalar(
        select(PublicationPlan)
        .where(
            PublicationPlan.actor_account_id == ctx.account_id,
            PublicationPlan.object_kind == object_kind,
            PublicationPlan.stable_id == stable_id,
            PublicationPlan.version == version,
        )
        .order_by(PublicationPlan.created_at.desc())
        .limit(1)
    )
    if plan is not None:
        if plan.state in {
            "ready",
            "validating",
            "publish_planned",
            "failed",
            "stale",
            "published",
        }:
            open_plan_id = plan.id
        snapshot = await db.scalar(
            select(ValidationSnapshot).where(ValidationSnapshot.plan_id == plan.id)
        )
        if snapshot is not None:
            bindings = list(
                (
                    await db.execute(
                        select(EvidenceBinding).where(EvidenceBinding.snapshot_id == snapshot.id)
                    )
                )
                .scalars()
                .all()
            )
            for binding in bindings:
                evidence.append(
                    OwnerEvidenceRow(
                        schema_version=1,
                        check_id=binding.check_id,
                        result=binding.result,
                        source=binding.source,
                        expires_at=_ts(binding.expires_at),
                    )
                )

    description = ""
    if isinstance(row.passport_document, dict):
        raw = row.passport_document.get("description")
        if isinstance(raw, str):
            description = raw[:2000]

    return OwnerVersionDetail(
        schema_version=1,
        object_kind=object_kind,  # type: ignore[arg-type]
        stable_id=stable_id,
        name=row.name or stable_id,
        version=version,
        content_digest=row.passport_digest,
        lifecycle_state=row.lifecycle_state,  # type: ignore[arg-type]
        visibility="public" if row.visibility == "public" else "private",
        trust_lane=row.trust_lane,  # type: ignore[arg-type]
        author_verified=bool(row.author_verified),
        component_verified=bool(row.component_verified),
        install_eligible=_install_eligible(
            component_verified=bool(row.component_verified),
            lifecycle=row.lifecycle_state,
        ),
        published_at=_ts(row.published_at),
        can_start_publication=can_start_publication(
            lifecycle=row.lifecycle_state,
            published_at=row.published_at,
        ),
        open_publication_plan_id=open_plan_id,
        evidence=evidence,
        description=description,
    )


async def start_publication(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    object_kind: str,
    stable_id: str,
    version: str,
    body: OwnerStartPublicationRequest,
) -> PublicationPlanResponse:
    """Create a publication plan from server-stored passport for an owned version."""
    row = await db.scalar(
        select(CatalogMetadata).where(
            CatalogMetadata.owner_account_id == ctx.account_id,
            CatalogMetadata.object_kind == object_kind,
            CatalogMetadata.stable_id == stable_id,
            CatalogMetadata.version == version,
        )
    )
    if row is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "version not found")
    passport = dict(row.passport_document or {})
    digest = row.passport_digest
    if not digest:
        # Fall back to artifact digest in passport when seed/draft omitted column.
        artifact = passport.get("artifact")
        if isinstance(artifact, Mapping):
            artifact_fields = cast(Mapping[str, object], artifact)
            artifact_digest = artifact_fields.get("digest")
            if isinstance(artifact_digest, str):
                digest = artifact_digest
    if not digest:
        raise ApiError(ErrorCategory.VALIDATION, "version has no content digest for publication")
    create = PublicationPlanCreateRequest(
        schema_version=1,
        object_kind=object_kind,  # type: ignore[arg-type]
        stable_id=stable_id,
        version=version,
        content_digest=digest,  # type: ignore[arg-type]
        policy_version=body.policy_version,
        passport=passport,
        attestations=[],
        idempotency_key=body.idempotency_key,  # type: ignore[arg-type]
        device_id=body.device_id,  # type: ignore[arg-type]
    )
    return await publish_service.create_plan(db, ctx=ctx, body=create)
