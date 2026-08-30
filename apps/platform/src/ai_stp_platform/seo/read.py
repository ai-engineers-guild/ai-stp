"""Public SEO reads. Session cookies are never consulted."""

from __future__ import annotations

import base64

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.http import PageInfo
from ai_stp_contracts.seo import (
    SEO_SITEMAP_SHARD_LIMIT,
    SEO_SNAPSHOT_DOMAIN,
    SeoCatalogEntry,
    SeoCatalogPage,
    SeoIndexResponse,
    SeoIndexShardRef,
    SeoProfileDocument,
    SeoPublicProfile,
    SeoSitemapShard,
    SeoSitemapUrl,
    SeoSubjectKind,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_platform.seo.collectors import SubjectMissing
from ai_stp_platform.seo.markdown import render_subject_markdown
from ai_stp_platform.seo.materialize import existing_locale_urls
from ai_stp_platform.seo.orm import SeoActiveRevision, SeoGeneration, SeoRevision
from ai_stp_platform.seo.settings import load_seo_settings
from ai_stp_platform.seo.sitemap import render_sitemap_index, render_urlset, split_urls
from ai_stp_platform.seo.urls import markdown_url, sitemap_shard_url


async def current_generation(session: AsyncSession) -> int:
    value = await session.scalar(select(SeoGeneration.value).where(SeoGeneration.id == 1))
    return int(value or 0)


async def read_active_profile(
    session: AsyncSession,
    *,
    kind: SeoSubjectKind,
    subject_id: str,
    locale: str,
) -> SeoPublicProfile:
    """Return the active revision with hreflang computed at read time."""
    pointer = await session.scalar(
        select(SeoActiveRevision).where(
            SeoActiveRevision.subject_kind == kind,
            SeoActiveRevision.subject_id == subject_id,
            SeoActiveRevision.locale == locale,
        )
    )
    if pointer is None:
        raise SubjectMissing(subject_id)
    revision = await session.get(SeoRevision, pointer.revision_id)
    if revision is None or revision.state != "active":
        raise SubjectMissing(subject_id)
    profile = SeoProfileDocument.model_validate(revision.profile)
    origin = load_seo_settings().public_origin
    locales = await existing_locale_urls(session, kind=kind, subject_id=subject_id, origin=origin)
    profile = profile.model_copy(update={"alternates": locales})
    return SeoPublicProfile(
        revision_id=revision.id,
        snapshot_id=revision.snapshot_id,
        generation=pointer.generation,
        etag=revision.profile_digest,
        profile=profile,
    )


async def read_revision_profile(session: AsyncSession, revision_id: str) -> SeoProfileDocument:
    revision = await session.get(SeoRevision, revision_id)
    if revision is None:
        raise SubjectMissing(revision_id)
    return SeoProfileDocument.model_validate(revision.profile)


async def list_eligible_urls(
    session: AsyncSession,
    *,
    kind: SeoSubjectKind,
    locale: str,
    origin: str,
) -> list[SeoSitemapUrl]:
    rows = list(
        (
            await session.execute(
                select(SeoActiveRevision, SeoRevision)
                .join(SeoRevision, SeoRevision.id == SeoActiveRevision.revision_id)
                .where(
                    SeoActiveRevision.subject_kind == kind,
                    SeoActiveRevision.locale == locale,
                    SeoActiveRevision.index_eligible.is_(True),
                    SeoRevision.state == "active",
                )
                .order_by(SeoActiveRevision.subject_id)
            )
        ).all()
    )
    urls: list[SeoSitemapUrl] = []
    for pointer, revision in rows:
        profile = SeoProfileDocument.model_validate(revision.profile)
        locales = await existing_locale_urls(
            session,
            kind=pointer.subject_kind,  # type: ignore[arg-type]
            subject_id=pointer.subject_id,
            origin=origin,
        )
        urls.append(
            SeoSitemapUrl(
                loc=profile.canonical_url,
                lastmod=profile.modified_at,
                alternates=locales,
            )
        )
    return urls


async def read_sitemap_index(session: AsyncSession, *, origin: str) -> SeoIndexResponse:
    generation = await current_generation(session)
    shards: list[SeoIndexShardRef] = []
    built: list[SeoSitemapShard] = []
    latest = "1970-01-01T00:00:00.000Z"
    for kind in ("component", "setup", "article", "service", "country"):
        for locale in ("en", "ru"):
            urls = await list_eligible_urls(
                session,
                kind=kind,
                locale=locale,
                origin=origin,  # type: ignore[arg-type]
            )
            pages = split_urls(urls, sitemap_shard_limit())
            for index, page_urls in enumerate(pages, start=1):
                if not page_urls and index > 1:
                    continue
                if not page_urls:
                    continue
                lastmod = max(item.lastmod for item in page_urls)
                latest = max(latest, lastmod)
                shards.append(
                    SeoIndexShardRef(
                        loc=sitemap_shard_url(origin, kind, locale, index),  # type: ignore[arg-type]
                        lastmod=lastmod,
                    )
                )
                built.append(
                    SeoSitemapShard(
                        generation=generation,
                        kind=kind,  # type: ignore[arg-type]
                        locale=locale,  # type: ignore[arg-type]
                        page=index,
                        urls=page_urls,
                    )
                )
    if built:
        render_sitemap_index(origin, built, latest)
    etag = digest_canonical(
        SEO_SNAPSHOT_DOMAIN,
        index_etag_payload(generation, [item.loc for item in shards]),
    )
    return SeoIndexResponse(generation=generation, etag=etag, shards=shards)


async def read_sitemap_shard(
    session: AsyncSession,
    *,
    kind: SeoSubjectKind,
    locale: str,
    page: int,
    origin: str,
) -> SeoSitemapShard:
    if page < 1:
        raise SubjectMissing(str(page))
    urls = await list_eligible_urls(session, kind=kind, locale=locale, origin=origin)
    pages = split_urls(urls, sitemap_shard_limit())
    if page > len(pages) or not pages[page - 1]:
        raise SubjectMissing(f"{kind}-{locale}-{page}")
    generation = await current_generation(session)
    render_urlset(pages[page - 1])
    return SeoSitemapShard(
        generation=generation,
        kind=kind,
        locale=locale,  # type: ignore[arg-type]
        page=page,
        urls=pages[page - 1],
    )


def encode_catalog_cursor(kind: str, subject_id: str, locale: str) -> str:
    raw = f"{kind}\n{subject_id}\n{locale}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_catalog_cursor(cursor: str) -> tuple[str, str, str]:
    padding = "=" * (-len(cursor) % 4)
    raw = base64.urlsafe_b64decode(cursor + padding).decode("ascii")
    kind, subject_id, locale = raw.split("\n", 2)
    return kind, subject_id, locale


async def read_catalog_page(
    session: AsyncSession,
    *,
    locale: str | None,
    kind: SeoSubjectKind | None,
    cursor: str | None,
    page_size: int,
    origin: str,
) -> SeoCatalogPage:
    stmt = (
        select(SeoActiveRevision, SeoRevision)
        .join(SeoRevision, SeoRevision.id == SeoActiveRevision.revision_id)
        .where(
            SeoActiveRevision.index_eligible.is_(True),
            SeoRevision.state == "active",
        )
        .order_by(
            SeoActiveRevision.subject_kind,
            SeoActiveRevision.subject_id,
            SeoActiveRevision.locale,
        )
    )
    if locale is not None:
        stmt = stmt.where(SeoActiveRevision.locale == locale)
    if kind is not None:
        stmt = stmt.where(SeoActiveRevision.subject_kind == kind)
    rows = list((await session.execute(stmt)).all())
    start = 0
    if cursor:
        after_kind, after_id, after_locale = decode_catalog_cursor(cursor)
        for index, (pointer, _revision) in enumerate(rows):
            key = (pointer.subject_kind, pointer.subject_id, pointer.locale)
            if key > (after_kind, after_id, after_locale):
                start = index
                break
            if key == (after_kind, after_id, after_locale):
                start = index + 1
                break
        else:
            start = len(rows)
    window = rows[start : start + page_size]
    items: list[SeoCatalogEntry] = []
    for pointer, revision in window:
        profile = SeoProfileDocument.model_validate(revision.profile)
        if not render_subject_markdown(profile).strip():
            continue
        items.append(
            SeoCatalogEntry(
                kind=pointer.subject_kind,  # type: ignore[arg-type]
                subject_id=pointer.subject_id,
                locale=pointer.locale,  # type: ignore[arg-type]
                canonical_url=profile.canonical_url,
                title=profile.title,
                description=profile.description,
                markdown_url=markdown_url(
                    origin,
                    pointer.subject_kind,
                    pointer.subject_id,  # type: ignore[arg-type]
                ),
                revision_id=revision.id,
                modified_at=profile.modified_at,
            )
        )
    next_cursor = None
    if start + page_size < len(rows) and window:
        last = window[-1][0]
        next_cursor = encode_catalog_cursor(last.subject_kind, last.subject_id, last.locale)
    generation = await current_generation(session)
    return SeoCatalogPage(
        generation=generation,
        items=items,
        page=PageInfo(next_cursor=next_cursor, page_size=page_size),
    )


def sitemap_shard_limit() -> int:
    return SEO_SITEMAP_SHARD_LIMIT


def index_etag_payload(generation: int, locs: list[str]) -> JsonValue:
    payload: dict[str, JsonValue] = {"generation": generation, "shards": list(locs)}
    return payload
