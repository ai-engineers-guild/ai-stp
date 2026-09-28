"""Public SEO reads. Session cookies are never consulted."""

from __future__ import annotations

import base64

from sqlalchemy import Integer, cast, func, select, tuple_
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
from ai_stp_platform.seo.sitemap import render_sitemap_index, render_urlset
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


async def list_eligible_urls_page(
    session: AsyncSession,
    *,
    kind: SeoSubjectKind,
    locale: str,
    origin: str,
    limit: int,
    offset: int,
) -> list[SeoSitemapUrl]:
    """One bounded window of the eligible-URL set: the sitemap shard asks for
    exactly one page, so materializing the whole set first is the same O(n)
    mistake the catalog page made."""
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
                .limit(limit)
                .offset(offset)
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
    limit = sitemap_shard_limit()
    for kind in ("component", "setup", "article", "service", "country"):
        for locale in ("en", "ru"):
            # The index needs shard boundaries and per-shard lastmod, not the
            # URLs themselves: number the eligible rows, bucket by shard, and
            # aggregate — one grouped row per shard instead of a full
            # materialization per (kind, locale) pair.
            numbered = (
                select(
                    func.row_number().over(order_by=SeoActiveRevision.subject_id).label("position"),
                    SeoRevision.profile["modified_at"].as_string().label("lastmod"),
                )
                .join(SeoRevision, SeoRevision.id == SeoActiveRevision.revision_id)
                .where(
                    SeoActiveRevision.subject_kind == kind,
                    SeoActiveRevision.locale == locale,
                    SeoActiveRevision.index_eligible.is_(True),
                    SeoRevision.state == "active",
                )
                .subquery()
            )
            # Integer division truncates the bucket; the cast keeps the
            # expression typed Integer instead of SQLAlchemy's Numeric
            # inference, so `page` arrives as a whole number.
            bucket = cast((numbered.c.position - 1) / limit + 1, Integer).label("page")
            grouped = (
                select(
                    bucket,
                    func.max(numbered.c.lastmod).label("lastmod"),
                )
                .group_by(bucket)
                .order_by(bucket)
            )
            for page, lastmod in (await session.execute(grouped)).all():
                if lastmod is None:
                    continue
                latest = max(latest, lastmod)
                shards.append(
                    SeoIndexShardRef(
                        loc=sitemap_shard_url(origin, kind, locale, page),  # type: ignore[arg-type]
                        lastmod=lastmod,
                    )
                )
                built.append(
                    SeoSitemapShard(
                        generation=generation,
                        kind=kind,  # type: ignore[arg-type]
                        locale=locale,  # type: ignore[arg-type]
                        page=page,
                        urls=[],
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
    limit = sitemap_shard_limit()
    # The shard serves exactly one page: bound the query instead of
    # materializing the whole set and slicing it in Python.
    urls = await list_eligible_urls_page(
        session,
        kind=kind,
        locale=locale,
        origin=origin,
        limit=limit,
        offset=(page - 1) * limit,
    )
    if not urls:
        raise SubjectMissing(f"{kind}-{locale}-{page}")
    generation = await current_generation(session)
    render_urlset(urls)
    return SeoSitemapShard(
        generation=generation,
        kind=kind,
        locale=locale,  # type: ignore[arg-type]
        page=page,
        urls=urls,
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
    if cursor:
        # The cursor names the last served sort key, so the next page is a
        # range scan on the (kind, subject_id, locale) unique index — not a
        # full materialization that Python then re-slices.
        after_kind, after_id, after_locale = decode_catalog_cursor(cursor)
        stmt = stmt.where(
            tuple_(
                SeoActiveRevision.subject_kind,
                SeoActiveRevision.subject_id,
                SeoActiveRevision.locale,
            )
            > (after_kind, after_id, after_locale)
        )
    # One extra row answers has-more without a second query.
    rows = list((await session.execute(stmt.limit(page_size + 1))).all())
    has_more = len(rows) > page_size
    window = rows[:page_size]
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
    if has_more and window:
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
