"""Load public subject aggregates for the five SEO kinds."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.seo import SeoSubjectKind
from ai_stp_platform.content.orm import Article, ArticleActive, ArticleRevision
from ai_stp_platform.models import (
    CatalogExternalProduct,
    CatalogMetadata,
    ExternalProduct,
    ExternalProductCountry,
    ProfileRevision,
    PublicProfile,
)
from ai_stp_platform.seo.facts import (
    PublicSubjectFacts,
    article_body_digest,
    as_object_list,
    as_object_map,
    as_str_list,
    parse_locale,
)


class SubjectMissing(LookupError):
    """No public aggregate exists for the requested subject."""


def _aware(moment: datetime | None) -> datetime:
    if moment is None:
        return datetime(2020, 1, 1, tzinfo=UTC)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment


async def _author_name(session: AsyncSession, account_id: str | None) -> str:
    if not account_id:
        return ""
    profile = await session.get(PublicProfile, account_id)
    if profile is None or profile.published_revision_id is None:
        return ""
    revision = await session.get(ProfileRevision, profile.published_revision_id)
    if revision is None or not revision.display_name:
        return ""
    return revision.display_name


async def collect_component_or_setup(
    session: AsyncSession,
    *,
    kind: SeoSubjectKind,
    subject_id: str,
    locale: str,
) -> PublicSubjectFacts:
    rows = list(
        (
            await session.execute(
                select(CatalogMetadata).where(
                    CatalogMetadata.object_kind == kind,
                    CatalogMetadata.stable_id == subject_id,
                    CatalogMetadata.visibility == "public",
                    CatalogMetadata.published_at.is_not(None),
                )
            )
        ).scalars()
    )
    if not rows:
        raise SubjectMissing(subject_id)
    latest = max(rows, key=lambda row: (_aware(row.published_at), row.version or ""))
    passport = dict(latest.passport_document or {})
    name = str(latest.name or passport.get("name") or subject_id)
    description = str(passport.get("description") or "")
    tags = tuple(as_str_list(passport.get("tags")))
    versions = [
        {"version": row.version, "published_at": _aware(row.published_at).isoformat()}
        for row in sorted(rows, key=lambda item: item.version or "")
        if row.version
    ]
    services = list(
        (
            await session.execute(
                select(ExternalProduct)
                .join(
                    CatalogExternalProduct,
                    CatalogExternalProduct.external_product_id == ExternalProduct.id,
                )
                .where(CatalogExternalProduct.catalog_metadata_id == latest.id)
            )
        ).scalars()
    )
    author = await _author_name(session, latest.owner_account_id)
    required_env: list[object] = []
    for item in as_object_list(passport.get("required_env")):
        mapping = as_object_map(item)
        if mapping is None:
            required_env.append(item)
        else:
            required_env.append({"name": mapping.get("name"), "purpose": mapping.get("purpose")})
    permission_parts: list[str] = []
    permissions = as_object_map(passport.get("permissions"))
    if permissions is not None:
        for group in permissions.values():
            permission_parts.extend(str(item) for item in as_object_list(group))
    source = as_object_map(passport.get("source"))
    extras: dict[str, object] = {
        "purpose": str(passport.get("purpose") or description),
        "compatibility": " ".join(as_str_list(passport.get("supported_os"))),
        "supported_os": as_str_list(passport.get("supported_os")),
        "required_env": required_env,
        "permissions": " ".join(permission_parts),
        "permission_groups": permissions or {},
        "requires_credentials": bool(passport.get("requires_credentials")),
        "requires_authorization": passport.get("requires_authorization"),
        "runtime_requirements": as_str_list(passport.get("runtime_requirements")),
        "provides_capabilities": as_str_list(passport.get("provides_capabilities")),
        "entry_points": as_str_list(passport.get("entry_points")),
        "projection_kind": passport.get("projection_kind"),
        "license": passport.get("license"),
        "author_verified": latest.author_verified,
        "component_verified": latest.component_verified,
        "trust_lane": latest.trust_lane,
        "source_repository": None if source is None else source.get("repository"),
        "author_name": author,
        "versions": versions,
        "services": [
            {"canonical_domain": product.canonical_domain, "name": product.name}
            for product in services
        ],
        "harness_id": passport.get("harness_id"),
        "component_type": passport.get("component_type"),
        "version": latest.version,
    }
    return PublicSubjectFacts(
        kind=kind,
        subject_id=subject_id,
        source_revision=latest.current_revision_id,
        locale=parse_locale(locale),
        name=name,
        description=description,
        summary=description,
        lifecycle=latest.lifecycle_state,
        visibility=latest.visibility,
        published_at=_aware(latest.published_at),
        modified_at=_aware(latest.updated_at),
        tags=tags,
        extras=extras,
    )


async def collect_article(
    session: AsyncSession, *, subject_id: str, locale: str
) -> PublicSubjectFacts:
    active = await session.scalar(
        select(ArticleActive).where(
            ArticleActive.article_id == subject_id, ArticleActive.locale == locale
        )
    )
    if active is None:
        raise SubjectMissing(subject_id)
    revision = await session.get(ArticleRevision, active.revision_id)
    if revision is None:
        raise SubjectMissing(subject_id)
    article = await session.get(Article, revision.article_id)
    if article is None:
        raise SubjectMissing(subject_id)
    excerpt = " ".join(revision.body.split())[:800]
    published = datetime.fromisoformat(f"{revision.published_at}T00:00:00+00:00")
    return PublicSubjectFacts(
        kind="article",
        subject_id=subject_id,
        source_revision=revision.id,
        locale=parse_locale(locale),
        name=revision.title,
        description=revision.description,
        summary=excerpt or revision.description,
        lifecycle="active",
        visibility="public",
        published_at=published,
        modified_at=_aware(revision.created_at),
        tags=tuple(str(tag) for tag in revision.tags),
        extras={
            "article_type": article.article_type,
            "slug": article.slug,
            "body_excerpt": excerpt,
            "body_digest": article_body_digest(revision.body),
            "author_name": "",
        },
    )


async def collect_service(
    session: AsyncSession, *, subject_id: str, locale: str
) -> PublicSubjectFacts:
    product = await session.scalar(
        select(ExternalProduct).where(ExternalProduct.canonical_domain == subject_id)
    )
    if product is None:
        raise SubjectMissing(subject_id)
    countries = list(
        (
            await session.execute(
                select(ExternalProductCountry.country_code).where(
                    ExternalProductCountry.external_product_id == product.id
                )
            )
        ).scalars()
    )
    objects = list(
        (
            await session.execute(
                select(CatalogMetadata)
                .join(
                    CatalogExternalProduct,
                    CatalogExternalProduct.catalog_metadata_id == CatalogMetadata.id,
                )
                .where(
                    CatalogExternalProduct.external_product_id == product.id,
                    CatalogMetadata.visibility == "public",
                    CatalogMetadata.lifecycle_state == "active",
                )
            )
        ).scalars()
    )
    seen: set[tuple[str, str]] = set()
    related: list[dict[str, str]] = []
    for row in objects:
        key = (row.object_kind, row.stable_id)
        if key in seen:
            continue
        seen.add(key)
        related.append(
            {
                "object_kind": row.object_kind,
                "stable_id": row.stable_id,
                "name": row.name or row.stable_id,
            }
        )
    description = product.description or ""
    return PublicSubjectFacts(
        kind="service",
        subject_id=subject_id,
        source_revision=str(product.id),
        locale=parse_locale(locale),
        name=product.name,
        description=description,
        summary=description or product.name,
        lifecycle="active",
        visibility="public",
        published_at=_aware(product.created_at),
        modified_at=_aware(product.updated_at),
        tags=tuple(countries),
        extras={
            "canonical_domain": product.canonical_domain,
            "primary_url": product.primary_url,
            "source_url": product.source_url,
            "description": description,
            "countries": sorted(countries),
            "objects": related,
            "objects_text": ", ".join(item["name"] for item in related),
        },
    )


async def collect_country(
    session: AsyncSession, *, subject_id: str, locale: str
) -> PublicSubjectFacts:
    code = subject_id.upper()
    product_ids = list(
        (
            await session.execute(
                select(ExternalProductCountry.external_product_id).where(
                    ExternalProductCountry.country_code == code
                )
            )
        ).scalars()
    )
    products = (
        list(
            (
                await session.execute(
                    select(ExternalProduct)
                    .where(ExternalProduct.id.in_(product_ids))
                    .order_by(ExternalProduct.name)
                )
            ).scalars()
        )
        if product_ids
        else []
    )
    related_objects: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    latest = datetime(2020, 1, 1, tzinfo=UTC)
    for product in products:
        latest = max(latest, _aware(product.updated_at))
        rows = list(
            (
                await session.execute(
                    select(CatalogMetadata)
                    .join(
                        CatalogExternalProduct,
                        CatalogExternalProduct.catalog_metadata_id == CatalogMetadata.id,
                    )
                    .where(
                        CatalogExternalProduct.external_product_id == product.id,
                        CatalogMetadata.visibility == "public",
                    )
                )
            ).scalars()
        )
        for row in rows:
            key = (row.object_kind, row.stable_id)
            if key in seen:
                continue
            seen.add(key)
            related_objects.append(
                {
                    "object_kind": row.object_kind,
                    "stable_id": row.stable_id,
                    "name": row.name or row.stable_id,
                }
            )
    services = [
        {"canonical_domain": product.canonical_domain, "name": product.name} for product in products
    ]
    return PublicSubjectFacts(
        kind="country",
        subject_id=code,
        source_revision=code,
        locale=parse_locale(locale),
        name=code,
        description=code,
        summary=code,
        lifecycle="active" if products else "unavailable",
        visibility="public",
        published_at=latest,
        modified_at=latest,
        tags=(),
        extras={
            "country_code": code,
            "services": services,
            "objects": related_objects,
            "objects_text": ", ".join(item["name"] for item in related_objects),
        },
    )


async def collect_subject(
    session: AsyncSession,
    *,
    kind: SeoSubjectKind,
    subject_id: str,
    locale: str,
) -> PublicSubjectFacts:
    if kind in {"component", "setup"}:
        return await collect_component_or_setup(
            session, kind=kind, subject_id=subject_id, locale=locale
        )
    if kind == "article":
        return await collect_article(session, subject_id=subject_id, locale=locale)
    if kind == "service":
        return await collect_service(session, subject_id=subject_id, locale=locale)
    if kind == "country":
        return await collect_country(session, subject_id=subject_id, locale=locale)
    raise SubjectMissing(subject_id)
