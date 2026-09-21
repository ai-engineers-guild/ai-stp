"""Owner workspace read models (SPEC-027 / ADR-0068)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Final, Literal, cast
from uuid import uuid4

from sqlalchemy import String, delete, select, update
from sqlalchemy import cast as sql_cast
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.owner.media_processing import MediaProcessingError, normalize_upload
from ai_stp_api.slices.publish import service as publish_service
from ai_stp_contracts.catalog import (
    ComponentSummary,
    ExternalProductListResponse,
    ExternalProductSummary,
    SetupSummary,
)
from ai_stp_contracts.families import (
    SetupFamilyCreateRequest,
    SetupFamilyOwner,
    SetupFamilyPatchRequest,
)
from ai_stp_contracts.http import PageInfo
from ai_stp_contracts.owner import (
    COMPONENT_MEDIA_PUBLIC_PREFIX,
    OwnerEvidenceRow,
    OwnerExternalProductAttachRequest,
    OwnerExternalProductCreateRequest,
    OwnerLifecycleRequest,
    OwnerLifecycleResponse,
    OwnerObjectCapabilities,
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
from ai_stp_passports.versions import SetupVersionPassport
from ai_stp_platform.catalog_projection import component_summary, setup_summary
from ai_stp_platform.catalog_read import PUBLIC_LIFECYCLES, CatalogIntegrityError, PublicVersionRow
from ai_stp_platform.external_catalog import COUNTRY_CODES, canonical_external_url
from ai_stp_platform.models import (
    AccessGrant,
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
    db: AsyncSession,
    *,
    ctx: AuthContext,
    stable_id: str,
    object_kind: Literal["component", "setup"] = "component",
) -> OwnerPresentationResponse:
    owner_id = await _object_namespace(db, ctx=ctx, stable_id=stable_id, object_kind=object_kind)
    rows = list(
        (
            await db.execute(
                select(CatalogMetadata)
                .where(
                    CatalogMetadata.owner_account_id == owner_id,
                    CatalogMetadata.object_kind == object_kind,
                    CatalogMetadata.stable_id == stable_id,
                )
                .order_by(CatalogMetadata.updated_at.desc(), CatalogMetadata.id.desc())
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise ApiError(ErrorCategory.NOT_FOUND, "object not found")
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
                    ComponentMedia.owner_account_id == owner_id,
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
        canonical_domain=domain,
        primary_url=primary_url,
        name=body.name.strip(),
        description=body.description,
        source_url=body.source_url,
    )
    db.add(product)
    await db.flush()
    for code in sorted(set(body.country_codes)):
        db.add(ExternalProductCountry(external_product_id=product.id, country_code=code))
    from ai_stp_platform.seo.enqueue import enqueue_service_and_countries

    await enqueue_service_and_countries(
        db, domain=domain, country_codes=sorted(set(body.country_codes))
    )
    await db.commit()
    return ExternalProductSummary(
        name=product.name,
        canonical_domain=domain,
        primary_url=primary_url,
        description=product.description,
        source_url=product.source_url,
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
    owner_id = await _object_namespace(
        db,
        ctx=ctx,
        stable_id=stable_id,
        object_kind=cast(Literal["component", "setup"], object_kind),
        capability="edit",
    )
    rows = list(
        (
            await db.execute(
                select(CatalogMetadata).where(
                    CatalogMetadata.owner_account_id == owner_id,
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
    from ai_stp_platform.seo.enqueue import (
        enqueue_seo_build,
        enqueue_service_and_countries,
        mutation_digest,
    )

    await enqueue_seo_build(
        db,
        kind=object_kind,  # type: ignore[arg-type]
        subject_id=stable_id,
        source_digest=mutation_digest(object_kind, stable_id, *sorted(domains)),
    )
    for product in products:
        related = list(
            (
                await db.execute(
                    select(ExternalProductCountry.country_code).where(
                        ExternalProductCountry.external_product_id == product.id
                    )
                )
            ).scalars()
        )
        await enqueue_service_and_countries(
            db,
            domain=product.canonical_domain,
            country_codes=related,
            extra=stable_id,
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
                description=row.description,
                source_url=row.source_url,
                country_codes=sorted(countries.get(row.id, [])),
            )
            for row in products
        ]
    )


async def read_object_external_products(
    db: AsyncSession, *, ctx: AuthContext, object_kind: str, stable_id: str
) -> ExternalProductListResponse:
    owner_id = await _object_namespace(
        db,
        ctx=ctx,
        stable_id=stable_id,
        object_kind=cast(Literal["component", "setup"], object_kind),
        capability="edit",
    )
    metadata_ids = list(
        (
            await db.execute(
                select(CatalogMetadata.id).where(
                    CatalogMetadata.owner_account_id == owner_id,
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
                description=row.description,
                source_url=row.source_url,
                country_codes=sorted(countries.get(row.id, [])),
            )
            for row in products
        ]
    )


async def _object_namespace(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    stable_id: str,
    object_kind: Literal["component", "setup"],
    capability: str = "edit_presentation",
) -> str:
    """Return the object's author account when the caller may manage the object.

    The author always manages the object; otherwise a tenant capability
    (operational ownership, owning-team lead, catalog_object.edit) applies.
    Media and metadata stay under the author's account namespace.
    """
    from ai_stp_platform.models import CatalogIdentity

    identity = await db.get(CatalogIdentity, stable_id)
    author_id = identity.owner_account_id if identity is not None else None
    organization_id = identity.organization_id if identity is not None else None
    if author_id is None or organization_id is None:
        metadata_owner = (
            await db.execute(
                select(CatalogMetadata.owner_account_id, CatalogMetadata.organization_id).where(
                    CatalogMetadata.object_kind == object_kind,
                    CatalogMetadata.stable_id == stable_id,
                )
            )
        ).first()
        if metadata_owner is None:
            raise ApiError(ErrorCategory.NOT_FOUND, "object not found")
        author_id = author_id or metadata_owner.owner_account_id
        organization_id = organization_id or metadata_owner.organization_id
    owned = await db.scalar(
        select(CatalogMetadata.id).where(
            CatalogMetadata.owner_account_id == author_id,
            CatalogMetadata.object_kind == object_kind,
            CatalogMetadata.stable_id == stable_id,
        )
    )
    if owned is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "object not found")
    if author_id == ctx.account_id:
        return author_id
    if organization_id is None:
        raise ApiError(ErrorCategory.PERMISSION, "object management is forbidden")
    from ai_stp_api.slices.corporate.subject_access import catalog_object_capabilities

    capabilities = await catalog_object_capabilities(
        db,
        account_id=ctx.account_id,
        organization_id=organization_id,
        object_kind=object_kind,
        stable_id=stable_id,
    )
    if capability in capabilities or "edit" in capabilities:
        return author_id
    raise ApiError(ErrorCategory.PERMISSION, "object management is forbidden")


async def upload_owner_component_media(
    db: AsyncSession,
    store: AvatarObjectStore,
    *,
    ctx: AuthContext,
    stable_id: str,
    content_type: str,
    payload: bytes,
    object_kind: Literal["component", "setup"] = "component",
) -> dict[str, Any]:
    """Store an object-media upload and return a ready public path for the editor."""
    owner_id = await _object_namespace(db, ctx=ctx, stable_id=stable_id, object_kind=object_kind)
    try:
        kind = validate_component_media_upload(
            content_type=content_type,
            size_bytes=len(payload),
            payload=payload,
        )
        payload = await normalize_upload(payload, content_type)
        validate_component_media_upload(
            content_type=content_type,
            size_bytes=len(payload),
            payload=payload,
        )
    except MediaProcessingError as exc:
        raise ApiError(ErrorCategory.DEPENDENCY, str(exc)) from exc
    except ValueError as exc:
        raise ApiError(ErrorCategory.VALIDATION, str(exc)) from exc
    if not payload:
        raise ApiError(ErrorCategory.VALIDATION, "empty component media payload")

    used_positions = set(
        (
            await db.execute(
                select(ComponentMedia.position).where(
                    ComponentMedia.owner_account_id == owner_id,
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
            owner_account_id=owner_id,
            namespace=f"components/{stable_id}/media",
        )
    except Exception as exc:
        raise ApiError(ErrorCategory.DEPENDENCY, "object storage unavailable") from exc

    # Public delivery path is component-scoped; storage key is content-addressed.
    public_url = f"/v1/media/component/{media_id}"
    db.add(
        ComponentMedia(
            id=media_id,
            stable_id=stable_id,
            owner_account_id=owner_id,
            position=free_position,
            kind=kind,
            source_type="upload",
            state="ready",
            object_key=stored.object_key,
            public_url=public_url,
            content_type=content_type,
            size_bytes=stored.size_bytes,
            content_digest=stored.content_digest,
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
    account_id: str | None,
) -> tuple[bytes, str, bool] | None:
    """Serve ready media when a public version, owner, or active grant permits it."""
    row = await db.get(ComponentMedia, media_id)
    if row is None or row.state != "ready" or not row.object_key:
        return None
    object_kind = "setup" if row.stable_id.startswith("setup_") else "component"
    is_public = (
        await db.scalar(
            select(CatalogMetadata.id).where(
                CatalogMetadata.object_kind == object_kind,
                CatalogMetadata.stable_id == row.stable_id,
                CatalogMetadata.owner_account_id == row.owner_account_id,
                CatalogMetadata.visibility == "public",
                CatalogMetadata.lifecycle_state.in_(tuple(PUBLIC_LIFECYCLES)),
                CatalogMetadata.published_at.is_not(None),
            )
        )
        is not None
    )
    authorized = is_public or account_id == row.owner_account_id
    if not authorized and account_id is not None:
        authorized = (
            await db.scalar(
                select(AccessGrant.id)
                .join(
                    CatalogMetadata,
                    (CatalogMetadata.object_kind == AccessGrant.object_kind)
                    & (CatalogMetadata.stable_id == AccessGrant.stable_id)
                    & CatalogMetadata.version.startswith(sql_cast(AccessGrant.major, String) + ".")
                    & (CatalogMetadata.owner_account_id == AccessGrant.owner_account_id),
                )
                .where(
                    AccessGrant.object_kind == "component",
                    AccessGrant.stable_id == row.stable_id,
                    AccessGrant.owner_account_id == row.owner_account_id,
                    AccessGrant.grantee_account_id == account_id,
                    AccessGrant.state == "active",
                    CatalogMetadata.visibility == "private",
                    CatalogMetadata.published_at.is_not(None),
                )
            )
            is not None
        )
    if not authorized and account_id is not None:
        # Corporate editors preview media of objects they manage.
        from ai_stp_api.slices.corporate.subject_access import (
            catalog_object_capabilities,
        )
        from ai_stp_platform.models import CatalogIdentity

        identity = await db.get(CatalogIdentity, row.stable_id)
        organization_id = identity.organization_id if identity is not None else None
        if organization_id is None:
            organization_id = await db.scalar(
                select(CatalogMetadata.organization_id)
                .where(
                    CatalogMetadata.stable_id == row.stable_id,
                    CatalogMetadata.owner_account_id == row.owner_account_id,
                )
                .limit(1)
            )
        if organization_id is not None:
            authorized = bool(
                await catalog_object_capabilities(
                    db,
                    account_id=account_id,
                    organization_id=organization_id,
                    object_kind=object_kind,
                    stable_id=row.stable_id,
                )
            )
    if not authorized:
        return None
    try:
        body = await store.read_bytes(
            object_key=row.object_key,
            expected_digest=row.content_digest,
            expected_size=row.size_bytes,
        )
    except Exception as exc:
        raise ApiError(ErrorCategory.DEPENDENCY, "object storage unavailable") from exc
    if body is None:
        return None
    return body, row.content_type or "application/octet-stream", is_public


async def update_owner_presentation(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    stable_id: str,
    body: OwnerPresentationUpdateRequest,
    object_kind: Literal["component", "setup"] = "component",
) -> OwnerPresentationResponse:
    owner_id = await _object_namespace(db, ctx=ctx, stable_id=stable_id, object_kind=object_kind)
    await db.execute(
        update(CatalogMetadata)
        .where(
            CatalogMetadata.owner_account_id == owner_id,
            CatalogMetadata.object_kind == object_kind,
            CatalogMetadata.stable_id == stable_id,
        )
        .values(presentation_bio=body.bio)
    )
    existing_rows = list(
        (
            await db.execute(
                select(ComponentMedia).where(
                    ComponentMedia.owner_account_id == owner_id,
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
                    owner_account_id=owner_id,
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
                or previous.owner_account_id != owner_id
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
                    owner_account_id=owner_id,
                    position=position,
                    kind=item.kind,
                    source_type="upload",
                    state="ready",
                    object_key=previous.object_key,
                    public_url=previous.public_url or item.url,
                    content_type=previous.content_type,
                    size_bytes=previous.size_bytes,
                    content_digest=previous.content_digest,
                    alt=item.alt,
                    caption=item.caption or None,
                )
            )
            continue
        rebuilt.append(
            ComponentMedia(
                id=f"media_{uuid4().hex}",
                stable_id=stable_id,
                owner_account_id=owner_id,
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
            ComponentMedia.owner_account_id == owner_id,
            ComponentMedia.stable_id == stable_id,
        )
    )
    # Flush deletes before re-inserting rows that may reuse the same primary keys.
    await db.flush()
    for row in rebuilt:
        db.add(row)
    await db.flush()
    from ai_stp_platform.catalog_search import upsert_catalog_search_projection

    await upsert_catalog_search_projection(db, object_kind=object_kind, stable_id=stable_id)
    return OwnerPresentationResponse(
        schema_version=1,
        stable_id=stable_id,
        bio=body.bio,
        media=list(body.media),
    )


async def read_owner_object_capabilities(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    object_kind: Literal["component", "setup"],
    stable_id: str,
) -> OwnerObjectCapabilities:
    """Resolve which management capabilities the caller holds on the object."""
    from ai_stp_api.slices.corporate.subject_access import catalog_object_capabilities
    from ai_stp_platform.models import CatalogIdentity

    identity = await db.get(CatalogIdentity, stable_id)
    organization_id = identity.organization_id if identity is not None else None
    author_id = identity.owner_account_id if identity is not None else None
    if organization_id is None or author_id is None:
        metadata_owner = (
            await db.execute(
                select(CatalogMetadata.owner_account_id, CatalogMetadata.organization_id).where(
                    CatalogMetadata.object_kind == object_kind,
                    CatalogMetadata.stable_id == stable_id,
                )
            )
        ).first()
        if metadata_owner is None:
            raise ApiError(ErrorCategory.NOT_FOUND, "object not found")
        author_id = author_id or metadata_owner.owner_account_id
        organization_id = organization_id or metadata_owner.organization_id
    if organization_id is None:
        # Legacy pre-scope rows belong to the author only.
        if author_id != ctx.account_id:
            raise ApiError(ErrorCategory.NOT_FOUND, "object not found")
        published = await db.scalar(
            select(CatalogMetadata.id).where(
                CatalogMetadata.stable_id == stable_id,
                CatalogMetadata.published_at.is_not(None),
            )
        )
        capabilities: list[str] = ["edit", "edit_presentation"]
        if published is None:
            capabilities.append("delete")
        return OwnerObjectCapabilities(
            schema_version=1,
            object_kind=object_kind,
            stable_id=stable_id,
            capabilities=cast(list[Literal["edit", "edit_presentation", "delete"]], capabilities),
        )
    capabilities = await catalog_object_capabilities(
        db,
        account_id=ctx.account_id,
        organization_id=organization_id,
        object_kind=object_kind,
        stable_id=stable_id,
    )
    return OwnerObjectCapabilities(
        schema_version=1,
        object_kind=object_kind,
        stable_id=stable_id,
        capabilities=cast(list[Literal["edit", "edit_presentation", "delete"]], capabilities),
    )


async def delete_owner_object(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    stable_id: str,
    object_kind: Literal["component", "setup"],
    request_id: str | None = None,
) -> None:
    """Hard-delete an unpublished object; published versions are immutable."""
    from ai_stp_platform.catalog_ownership_models import (
        CorporateCatalogOwnership,
    )
    from ai_stp_platform.corporate_authorization import has_corporate_permission
    from ai_stp_platform.models import CatalogIdentity
    from ai_stp_platform.organization_models import CorporateCatalogAssignment

    identity = await db.get(CatalogIdentity, stable_id)
    author_id = identity.owner_account_id if identity is not None else None
    organization_id = identity.organization_id if identity is not None else None
    if author_id is None or organization_id is None:
        metadata_owner = (
            await db.execute(
                select(CatalogMetadata.owner_account_id, CatalogMetadata.organization_id).where(
                    CatalogMetadata.object_kind == object_kind,
                    CatalogMetadata.stable_id == stable_id,
                )
            )
        ).first()
        if metadata_owner is None:
            raise ApiError(ErrorCategory.NOT_FOUND, "object not found")
        author_id = author_id or metadata_owner.owner_account_id
        organization_id = organization_id or metadata_owner.organization_id
    rows = list(
        (
            await db.scalars(
                select(CatalogMetadata).where(
                    CatalogMetadata.owner_account_id == author_id,
                    CatalogMetadata.object_kind == object_kind,
                    CatalogMetadata.stable_id == stable_id,
                )
            )
        ).all()
    )
    if not rows:
        raise ApiError(ErrorCategory.NOT_FOUND, "object not found")
    if author_id != ctx.account_id:
        if organization_id is None:
            raise ApiError(ErrorCategory.NOT_FOUND, "object not found")
        allowed = await has_corporate_permission(
            db,
            organization_id=organization_id,
            principal_type="user",
            principal_id=ctx.account_id,
            permission="catalog_object.delete",
            scope_kind="organization",
            scope_id=organization_id,
        )
        if not allowed:
            raise ApiError(ErrorCategory.PERMISSION, "object delete is forbidden")
    if any(row.published_at is not None for row in rows):
        raise ApiError(
            ErrorCategory.CONFLICT,
            "published objects are immutable; retire them instead",
        )
    from ai_stp_platform.github_models import DistributionVisibilityPlan
    from ai_stp_platform.models import (
        CatalogExternalProduct,
        CatalogReaction,
        CatalogUsageAggregate,
        GrantInvitation,
        OfficialUpstreamSource,
        OwnershipClaim,
        OwnershipRevision,
        PublicationPlan,
        SetupFamilyMember,
    )

    metadata_ids = [row.id for row in rows]
    await db.execute(
        delete(DistributionVisibilityPlan).where(
            DistributionVisibilityPlan.metadata_id.in_(metadata_ids)
        )
    )
    await db.execute(
        delete(CatalogExternalProduct).where(
            CatalogExternalProduct.catalog_metadata_id.in_(metadata_ids)
        )
    )
    await db.execute(delete(OwnershipRevision).where(OwnershipRevision.stable_id == stable_id))
    await db.execute(delete(OwnershipClaim).where(OwnershipClaim.stable_id == stable_id))
    await db.execute(
        delete(GrantInvitation).where(
            GrantInvitation.object_kind == object_kind,
            GrantInvitation.stable_id == stable_id,
        )
    )
    await db.execute(
        delete(AccessGrant).where(
            AccessGrant.object_kind == object_kind,
            AccessGrant.stable_id == stable_id,
        )
    )
    await db.execute(
        delete(PublicationPlan).where(
            PublicationPlan.object_kind == object_kind,
            PublicationPlan.stable_id == stable_id,
        )
    )
    await db.execute(
        delete(CatalogReaction).where(
            CatalogReaction.object_kind == object_kind,
            CatalogReaction.stable_id == stable_id,
        )
    )
    await db.execute(
        delete(CatalogUsageAggregate).where(CatalogUsageAggregate.stable_id == stable_id)
    )
    await db.execute(
        delete(OfficialUpstreamSource).where(OfficialUpstreamSource.stable_id == stable_id)
    )
    await db.execute(delete(SetupFamilyMember).where(SetupFamilyMember.stable_id == stable_id))
    await db.execute(
        delete(CorporateCatalogAssignment).where(
            CorporateCatalogAssignment.organization_id == organization_id,
            CorporateCatalogAssignment.object_kind == object_kind,
            CorporateCatalogAssignment.stable_id == stable_id,
        )
    )
    await db.execute(
        delete(CorporateCatalogOwnership).where(
            CorporateCatalogOwnership.organization_id == organization_id,
            CorporateCatalogOwnership.object_kind == object_kind,
            CorporateCatalogOwnership.stable_id == stable_id,
        )
    )
    from ai_stp_platform.organization_models import (
        CorporateCatalogMaintainer,
        CorporateCatalogVerification,
    )

    await db.execute(
        delete(CorporateCatalogMaintainer).where(
            CorporateCatalogMaintainer.organization_id == organization_id,
            CorporateCatalogMaintainer.object_kind == object_kind,
            CorporateCatalogMaintainer.stable_id == stable_id,
        )
    )
    await db.execute(
        delete(CorporateCatalogVerification).where(
            CorporateCatalogVerification.organization_id == organization_id,
            CorporateCatalogVerification.object_kind == object_kind,
            CorporateCatalogVerification.stable_id == stable_id,
        )
    )
    await db.execute(
        delete(ComponentMedia).where(
            ComponentMedia.owner_account_id == author_id,
            ComponentMedia.stable_id == stable_id,
        )
    )
    for row in rows:
        await db.delete(row)
    if identity is not None:
        await db.delete(identity)
    await db.flush()
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="catalog_object.delete",
        target_table="catalog_metadata",
        target_id=stable_id,
        request_id=request_id,
        payload={"object_kind": object_kind, "versions": len(rows)},
    )


def _ts(value: datetime | None) -> str | None:
    if value is None:
        return None
    moment = value if value.tzinfo else value.replace(tzinfo=UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _install_eligible(*, component_verified: bool, lifecycle: str, visibility: str) -> bool:
    return (
        visibility == "public"
        and component_verified
        and lifecycle not in {"blocked", "hidden", "failed", "draft"}
    )


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
                catalog_item=_owner_catalog_item(latest),
            )
        )
        if len(items) >= page_size:
            break

    return OwnerObjectListResponse(
        schema_version=1,
        items=items,
        page=PageInfo(schema_version=1, next_cursor=None, page_size=max(page_size, 1)),
    )


def _owner_catalog_item(metadata: CatalogMetadata) -> ComponentSummary | SetupSummary | None:
    """Project owner-readable bytes through the public card projector."""
    version = getattr(metadata, "version", None)
    passport_digest = getattr(metadata, "passport_digest", None)
    passport_document = getattr(metadata, "passport_document", None)
    if version is None or passport_digest is None or not isinstance(passport_document, dict):
        return None
    updated_at = getattr(metadata, "updated_at", None)
    published_at = (
        getattr(metadata, "published_at", None) or updated_at or datetime(1970, 1, 1, tzinfo=UTC)
    )
    row = PublicVersionRow(
        metadata=metadata,
        passport=cast(dict[str, Any], passport_document),
        passport_digest=passport_digest,
        published_at=published_at,
        trust_lane=metadata.trust_lane or "experimental",
        author_verified=bool(metadata.author_verified),
        component_verified=bool(metadata.component_verified),
        lifecycle=metadata.lifecycle_state,
        stable_id=metadata.stable_id,
        version=version,
        object_kind=metadata.object_kind,
        support_evidence=list(getattr(metadata, "support_evidence", None) or []),
    )
    try:
        if metadata.object_kind == "component":
            return component_summary(row, allow_private=True)
        if metadata.object_kind == "setup":
            return setup_summary(row, allow_private=True)
    except (CatalogIntegrityError, ValueError):
        return None
    return None


async def read_owner_object(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    object_kind: str,
    stable_id: str,
) -> OwnerObjectDetail:
    owner_id = await _object_namespace(
        db,
        ctx=ctx,
        stable_id=stable_id,
        object_kind=cast(Literal["component", "setup"], object_kind),
        capability="edit",
    )
    rows = list(
        (
            await db.execute(
                select(CatalogMetadata)
                .where(
                    CatalogMetadata.owner_account_id == owner_id,
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
                    visibility=row.visibility,
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
    ported_from = None
    related_setup_ids: list[str] = []
    target_gaps = []
    family_view: SetupFamilyOwner | None = None
    if isinstance(row.passport_document, dict):
        raw = row.passport_document.get("description")
        if isinstance(raw, str):
            description = raw[:2000]
        if object_kind == "setup":
            try:
                passport = SetupVersionPassport.model_validate(row.passport_document)
            except (TypeError, ValueError):
                pass
            else:
                ported_from = passport.ported_from
                related_setup_ids = passport.related_setup_ids
            from ai_stp_platform.catalog_families import family_for_setup, project_family

            family = await family_for_setup(db, stable_id)
            if family is not None:
                projected = await project_family(
                    db,
                    family,
                    current_stable_id=stable_id,
                    exact_version=version,
                    authorized_owner_id=ctx.account_id,
                )
                if isinstance(projected, SetupFamilyOwner):
                    family_view = projected
        if object_kind == "component":
            try:
                from ai_stp_passports.versions import ComponentVersionPassport
                from ai_stp_platform.catalog_assessments import load_effective_assessments
                from ai_stp_platform.catalog_targets import owner_target_gaps, project_target_matrix

                component = ComponentVersionPassport.model_validate(row.passport_document)
                assessments = await load_effective_assessments(
                    db, component_stable_id=stable_id, version=version
                )
                target_gaps = owner_target_gaps(
                    project_target_matrix(component, assessments=assessments)
                )
            except (TypeError, ValueError):
                target_gaps = []

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
            visibility=row.visibility,
        ),
        published_at=_ts(row.published_at),
        can_start_publication=can_start_publication(
            lifecycle=row.lifecycle_state,
            published_at=row.published_at,
        ),
        open_publication_plan_id=open_plan_id,
        evidence=evidence,
        description=description,
        ported_from=ported_from,
        related_setup_ids=related_setup_ids,
        target_gaps=target_gaps,
        family=family_view,
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


#: The states an owner transition moves between, and nothing else. `blocked`
#: and `hidden` are moderation outcomes: an author cannot leave them, and an
#: author who could would be undoing a staff decision.
_OWNER_LIFECYCLE: Final[dict[str, tuple[str, str]]] = {
    "deprecate": ("active", "deprecated"),
    "undeprecate": ("deprecated", "active"),
}


async def set_owner_lifecycle(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    object_kind: str,
    stable_id: str,
    version: str,
    body: OwnerLifecycleRequest,
) -> OwnerLifecycleResponse:
    """Deprecate an owned published version, or take the mark off again.

    `deprecated` says the author no longer intends this version to be chosen.
    It is deliberately **not** a restriction: the version stays readable,
    installable and exactly as published, because a published `X.Y` is
    immutable and a lifecycle mark that changed what somebody already depends
    on would be an edit by another name. Anyone who pinned it keeps it working.

    Reversible for the same reason. An author who deprecates by mistake has not
    destroyed anything, and `undeprecate` is the ordinary way back rather than
    a recovery procedure.
    """
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

    expected, resulting = _OWNER_LIFECYCLE[body.action]
    if row.lifecycle_state == resulting:
        # A replay, not a conflict: the version is already where the caller
        # asked it to be, and the idempotency key exists to make that safe.
        return OwnerLifecycleResponse(
            schema_version=1,
            stable_id=stable_id,
            version=version,
            lifecycle=resulting,  # pyright: ignore[reportArgumentType]
            applied=False,
        )
    if row.lifecycle_state != expected:
        raise ApiError(
            ErrorCategory.CONFLICT,
            f"a version in {row.lifecycle_state} cannot be {body.action}d by its author",
        )

    row.lifecycle_state = resulting
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action=f"owner.version_{body.action}",
        target_table="catalog_metadata",
        target_id=str(row.id),
        reason=body.reason,
        payload={
            "stable_id": stable_id,
            "version": version,
            "lifecycle_state": resulting,
        },
    )
    await db.flush()
    from ai_stp_platform.catalog_search import upsert_catalog_search_projection

    await upsert_catalog_search_projection(db, object_kind=object_kind, stable_id=stable_id)
    return OwnerLifecycleResponse(
        schema_version=1,
        stable_id=stable_id,
        version=version,
        lifecycle=resulting,  # pyright: ignore[reportArgumentType]
        applied=True,
    )


async def read_owner_family(db: AsyncSession, *, ctx: AuthContext, family_id: str):
    from ai_stp_platform.catalog_families import FamilyError, project_family
    from ai_stp_platform.models import SetupFamily

    family = await db.get(SetupFamily, family_id)
    if family is None or family.owner_account_id != ctx.account_id:
        raise ApiError(ErrorCategory.NOT_FOUND, "family not found")
    try:
        return await project_family(
            db,
            family,
            current_stable_id=None,
            exact_version=None,
            authorized_owner_id=ctx.account_id,
        )
    except FamilyError as exc:
        raise ApiError(ErrorCategory.VALIDATION, str(exc)) from exc


async def create_owner_family(
    db: AsyncSession, *, ctx: AuthContext, body: SetupFamilyCreateRequest
):
    from ai_stp_platform.catalog_families import FamilyError, create_family, project_family
    from ai_stp_platform.catalog_search import upsert_catalog_search_projection

    try:
        family = await create_family(db, owner_id=ctx.account_id, body=body)
    except FamilyError as exc:
        category = {
            "AI_STP_NOT_FOUND": ErrorCategory.NOT_FOUND,
            "AI_STP_CONFLICT": ErrorCategory.CONFLICT,
            "AI_STP_CATALOG_INTEGRITY": ErrorCategory.CATALOG_INTEGRITY,
        }.get(exc.code, ErrorCategory.VALIDATION)
        raise ApiError(category, str(exc)) from exc
    from sqlalchemy import select

    from ai_stp_platform.models import SetupFamilyMember as FamilyMemberRow

    members = list(
        (
            await db.execute(
                select(FamilyMemberRow).where(FamilyMemberRow.family_id == family.family_id)
            )
        )
        .scalars()
        .all()
    )
    for member in members:
        await upsert_catalog_search_projection(db, object_kind="setup", stable_id=member.stable_id)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="owner.family_created",
        target_table="setup_family",
        target_id=family.family_id,
        reason=body.reason,
        payload={"members": list(body.members)},
    )
    await db.commit()
    return await project_family(
        db,
        family,
        current_stable_id=None,
        exact_version=None,
        authorized_owner_id=ctx.account_id,
    )


async def patch_owner_family(
    db: AsyncSession, *, ctx: AuthContext, family_id: str, body: SetupFamilyPatchRequest
):
    from sqlalchemy import select

    from ai_stp_platform.catalog_families import FamilyError, patch_family, project_family
    from ai_stp_platform.catalog_search import upsert_catalog_search_projection
    from ai_stp_platform.models import SetupFamilyMember as FamilyMemberRow

    try:
        family = await patch_family(db, owner_id=ctx.account_id, family_id=family_id, body=body)
    except FamilyError as exc:
        category = {
            "AI_STP_NOT_FOUND": ErrorCategory.NOT_FOUND,
            "AI_STP_CONFLICT": ErrorCategory.CONFLICT,
            "AI_STP_CATALOG_INTEGRITY": ErrorCategory.CATALOG_INTEGRITY,
        }.get(exc.code, ErrorCategory.VALIDATION)
        raise ApiError(category, str(exc)) from exc
    members = list(
        (
            await db.execute(
                select(FamilyMemberRow).where(FamilyMemberRow.family_id == family.family_id)
            )
        )
        .scalars()
        .all()
    )
    for member in members:
        await upsert_catalog_search_projection(db, object_kind="setup", stable_id=member.stable_id)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="owner.family_updated",
        target_table="setup_family",
        target_id=family.family_id,
        reason=body.reason,
        payload={
            "add_members": list(body.add_members),
            "remove_members": list(body.remove_members),
        },
    )
    await db.commit()
    return await project_family(
        db,
        family,
        current_stable_id=None,
        exact_version=None,
        authorized_owner_id=ctx.account_id,
    )
