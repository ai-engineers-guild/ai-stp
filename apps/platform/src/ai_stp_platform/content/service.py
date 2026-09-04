"""Atomic article publication for repository import and staff API (SPEC-054)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.content import (
    CONTENT_LOCALES,
    CONTENT_SLUG_PATTERN,
    CONTENT_TYPES,
    ContentDetail,
    ContentListResponse,
    ContentLocale,
    ContentRepositoryImportRequest,
    ContentRepositoryImportResponse,
    ContentRepositoryState,
    ContentSnapshotEntry,
    ContentSummary,
    ContentType,
    StaffContentPublishRequest,
    StaffContentPublishResponse,
    StaffContentUnpublishResponse,
)
from ai_stp_platform.content.digests import (
    active_digest,
    article_identity,
    article_revision_id,
    public_list_etag,
    revision_content_digest,
)
from ai_stp_platform.content.enqueue import enqueue_article_seo_effect
from ai_stp_platform.content.errors import ContentError
from ai_stp_platform.content.markdown import validate_article_body
from ai_stp_platform.content.orm import (
    Article,
    ArticleActive,
    ArticleRepositoryState,
    ArticleRevision,
)
from ai_stp_platform.content.snapshot import parse_published_date, verify_snapshot_digests


def _now() -> datetime:
    return datetime.now(UTC)


def _as_locale(value: str) -> ContentLocale:
    if value not in CONTENT_LOCALES:
        raise ContentError("AI_STP_CONTENT_INVALID", "locale must be ru or en")
    return value  # type: ignore[return-value]


def _as_type(value: str) -> ContentType:
    return value  # type: ignore[return-value]


def _require_identity(article_type: str, slug: str) -> str:
    if article_type not in CONTENT_TYPES:
        raise ContentError("AI_STP_CONTENT_INVALID", "unknown article type")
    if re.fullmatch(CONTENT_SLUG_PATTERN, slug) is None or len(slug) > 120:
        raise ContentError("AI_STP_CONTENT_INVALID", "invalid slug")
    return article_identity(article_type, slug)


def _summary(article: Article, revision: ArticleRevision) -> ContentSummary:
    return ContentSummary(
        schema_version=1,
        type=_as_type(article.article_type),
        slug=article.slug,
        locale=_as_locale(revision.locale),
        title=revision.title,
        description=revision.description,
        published_at=revision.published_at,
        tags=list(revision.tags),
        revision_id=revision.id,
        content_digest=revision.content_digest,
        source_kind=article.source_kind,  # type: ignore[arg-type]
        cover_image=revision.cover_image,
        cover_alt=revision.cover_alt,
    )


def _detail(article: Article, revision: ArticleRevision) -> ContentDetail:
    summary = _summary(article, revision)
    return ContentDetail(
        **summary.model_dump(),
        body=revision.body,
        source_ref=revision.source_ref,
        source_path=revision.source_path,
    )


async def _state_for_update(session: AsyncSession) -> ArticleRepositoryState:
    row = await session.scalar(
        select(ArticleRepositoryState).where(ArticleRepositoryState.id == 1).with_for_update()
    )
    if row is None:
        raise ContentError("AI_STP_CONTENT_INVALID", "repository state is missing")
    return row


async def _revision_for(
    session: AsyncSession,
    *,
    article: Article,
    locale: str,
    title: str,
    description: str,
    published_at: str,
    tags: list[str],
    body: str,
    source_kind: str,
    source_ref: str | None,
    source_path: str | None,
    cover_image: str | None,
    cover_alt: str | None,
    actor_account_id: str | None,
    now: datetime,
) -> tuple[ArticleRevision, bool]:
    ordered_tags = sorted(tags)
    digest = revision_content_digest(
        article_type=article.article_type,
        slug=article.slug,
        locale=locale,
        title=title,
        description=description,
        published_at=published_at,
        tags=ordered_tags,
        body=body,
        source_kind=source_kind,
        source_ref=source_ref,
        source_path=source_path,
        cover_image=cover_image,
        cover_alt=cover_alt,
    )
    existing = await session.scalar(
        select(ArticleRevision).where(
            ArticleRevision.article_id == article.id,
            ArticleRevision.locale == locale,
            ArticleRevision.content_digest == digest,
        )
    )
    if existing is not None:
        return existing, False
    row = ArticleRevision(
        id=article_revision_id(article_id=article.id, locale=locale, content_digest=digest),
        article_id=article.id,
        locale=locale,
        title=title,
        description=description,
        published_at=published_at,
        tags=ordered_tags,
        body=body,
        content_digest=digest,
        source_kind=source_kind,
        source_ref=source_ref,
        source_path=source_path,
        cover_image=cover_image,
        cover_alt=cover_alt,
        actor_account_id=actor_account_id,
        created_at=now,
    )
    session.add(row)
    await session.flush()
    return row, True


async def _set_active(
    session: AsyncSession,
    *,
    article_id: str,
    locale: str,
    revision_id: str,
    now: datetime,
    current: ArticleActive | None,
) -> str:
    if current is None:
        session.add(
            ArticleActive(
                article_id=article_id,
                locale=locale,
                revision_id=revision_id,
                updated_at=now,
            )
        )
        return "activated"
    if current.revision_id == revision_id:
        return "unchanged"
    current.revision_id = revision_id
    current.updated_at = now
    return "activated"


async def repository_state(session: AsyncSession) -> ContentRepositoryState:
    row = await session.scalar(select(ArticleRepositoryState).where(ArticleRepositoryState.id == 1))
    if row is None:
        raise ContentError("AI_STP_CONTENT_INVALID", "repository state is missing")
    return ContentRepositoryState(
        schema_version=1,
        generation=row.generation,
        snapshot_digest=row.snapshot_digest,
        commit=row.commit,
    )


async def import_repository_snapshot(
    session: AsyncSession,
    snapshot: ContentRepositoryImportRequest,
    *,
    now: datetime | None = None,
) -> ContentRepositoryImportResponse:
    """Replace only the repository-owned active set. Errors leave generation unchanged."""
    moment = now or _now()
    verify_snapshot_digests(snapshot, now=moment)
    state = await _state_for_update(session)
    if state.snapshot_digest is not None and snapshot.snapshot_digest == state.snapshot_digest:
        active_count = len(
            (
                await session.execute(
                    select(ArticleActive).join(Article).where(Article.source_kind == "repository")
                )
            )
            .scalars()
            .all()
        )
        return ContentRepositoryImportResponse(
            schema_version=1,
            generation=state.generation,
            snapshot_digest=snapshot.snapshot_digest,
            created=0,
            activated=0,
            removed=0,
            unchanged=active_count,
        )
    if snapshot.expected_generation != state.generation:
        raise ContentError("AI_STP_CONTENT_STALE", "expected generation does not match")

    articles = list((await session.execute(select(Article).with_for_update())).scalars())
    by_id = {row.id: row for row in articles}
    incoming_ids = {article_identity(entry.type, entry.slug) for entry in snapshot.entries}
    for identity in incoming_ids:
        existing = by_id.get(identity)
        if existing is not None and existing.source_kind != "repository":
            raise ContentError(
                "AI_STP_CONTENT_SOURCE_CONFLICT",
                "identity already belongs to another source owner",
            )

    grouped: dict[str, dict[str, ContentSnapshotEntry]] = {}
    for entry in snapshot.entries:
        identity = article_identity(entry.type, entry.slug)
        grouped.setdefault(identity, {})[entry.locale] = entry

    current_actives = list((await session.execute(select(ArticleActive))).scalars())
    current_map = {(row.article_id, row.locale): row for row in current_actives}
    created = 0
    activated = 0
    unchanged = 0
    changed: list[tuple[str, str, str]] = []
    kept: set[tuple[str, str]] = set()

    for identity, locales in grouped.items():
        entry_en = locales["en"]
        article = by_id.get(identity)
        if article is None:
            article = Article(
                id=identity,
                article_type=entry_en.type,
                slug=entry_en.slug,
                source_kind="repository",
                created_at=moment,
            )
            session.add(article)
            await session.flush()
            by_id[identity] = article
        for locale, entry in locales.items():
            revision, is_new = await _revision_for(
                session,
                article=article,
                locale=locale,
                title=entry.title,
                description=entry.description,
                published_at=entry.published_at,
                tags=list(entry.tags),
                body=entry.body,
                source_kind="repository",
                source_ref=entry.source_ref,
                source_path=entry.source_path,
                cover_image=entry.cover_image,
                cover_alt=entry.cover_alt,
                actor_account_id=None,
                now=moment,
            )
            if is_new:
                created += 1
            outcome = await _set_active(
                session,
                article_id=identity,
                locale=locale,
                revision_id=revision.id,
                now=moment,
                current=current_map.get((identity, locale)),
            )
            kept.add((identity, locale))
            if outcome == "unchanged":
                unchanged += 1
            else:
                activated += 1
                changed.append((identity, locale, revision.content_digest))

    removed = 0
    for (article_id, locale), pointer in current_map.items():
        if (article_id, locale) in kept:
            continue
        owner = by_id.get(article_id)
        if owner is None or owner.source_kind != "repository":
            continue
        await session.execute(delete(ArticleActive).where(ArticleActive.id == pointer.id))
        removed += 1
        changed.append((article_id, locale, f"removed:{state.generation + 1}"))

    state.generation += 1
    state.snapshot_digest = snapshot.snapshot_digest
    state.commit = snapshot.commit
    state.updated_at = moment
    for article_id, locale, source_digest in changed:
        await enqueue_article_seo_effect(
            session,
            article_id=article_id,
            locales=[locale],
            source_digest=source_digest,
        )
    await session.flush()
    return ContentRepositoryImportResponse(
        schema_version=1,
        generation=state.generation,
        snapshot_digest=snapshot.snapshot_digest,
        created=created,
        activated=activated,
        removed=removed,
        unchanged=unchanged,
    )


async def _current_active_pair(session: AsyncSession, article_id: str) -> dict[str, ArticleActive]:
    rows = list(
        (await session.execute(select(ArticleActive).where(ArticleActive.article_id == article_id)))
        .scalars()
        .all()
    )
    return {row.locale: row for row in rows}


async def _pair_digest(session: AsyncSession, pointers: Mapping[str, ArticleActive]) -> str | None:
    del session
    if not pointers:
        return None
    if set(pointers) != set(CONTENT_LOCALES):
        raise ContentError("AI_STP_CONTENT_INVALID", "active article is missing a locale")
    return active_digest({locale: pointers[locale].revision_id for locale in CONTENT_LOCALES})


async def publish_staff_article(
    session: AsyncSession,
    *,
    article_type: str,
    slug: str,
    request: StaffContentPublishRequest,
    actor_account_id: str,
    now: datetime | None = None,
) -> StaffContentPublishResponse:
    moment = now or _now()
    today = moment.date()
    for locale in CONTENT_LOCALES:
        translation = getattr(request.translations, locale)
        parse_published_date(translation.published_at, today=today)
        validate_article_body(translation.body)
    await _state_for_update(session)
    identity = _require_identity(article_type, slug)
    article = await session.scalar(select(Article).where(Article.id == identity).with_for_update())
    if article is not None and article.source_kind != "staff":
        raise ContentError(
            "AI_STP_CONTENT_SOURCE_CONFLICT",
            "identity already belongs to another source owner",
        )
    pointers = await _current_active_pair(session, identity) if article is not None else {}
    current_digest = await _pair_digest(session, pointers) if pointers else None
    if request.expected_active_digest != current_digest:
        raise ContentError("AI_STP_CONTENT_STALE", "expected active digest does not match")
    if article is None:
        article = Article(
            id=identity,
            article_type=article_type,
            slug=slug,
            source_kind="staff",
            created_at=moment,
        )
        session.add(article)
        await session.flush()

    revision_ids: dict[str, str] = {}
    details: dict[str, ContentDetail] = {}
    changed: list[tuple[str, str]] = []
    for locale in CONTENT_LOCALES:
        translation = getattr(request.translations, locale)
        revision, _created = await _revision_for(
            session,
            article=article,
            locale=locale,
            title=translation.title,
            description=translation.description,
            published_at=translation.published_at,
            tags=list(translation.tags),
            body=translation.body,
            source_kind="staff",
            source_ref=None,
            source_path=None,
            cover_image=translation.cover_image,
            cover_alt=translation.cover_alt,
            actor_account_id=actor_account_id,
            now=moment,
        )
        outcome = await _set_active(
            session,
            article_id=identity,
            locale=locale,
            revision_id=revision.id,
            now=moment,
            current=pointers.get(locale),
        )
        revision_ids[locale] = revision.id
        details[locale] = _detail(article, revision)
        if outcome != "unchanged":
            changed.append((locale, revision.content_digest))
    digest = active_digest(revision_ids)
    for locale, source_digest in changed:
        await enqueue_article_seo_effect(
            session,
            article_id=identity,
            locales=[locale],
            source_digest=source_digest,
        )
    await session.flush()
    return StaffContentPublishResponse(
        schema_version=1,
        article_id=identity,
        active_digest=digest,
        revision_ids={
            _as_locale(locale): revision_id for locale, revision_id in revision_ids.items()
        },
        articles={_as_locale(locale): detail for locale, detail in details.items()},
    )


async def unpublish_staff_article(
    session: AsyncSession,
    *,
    article_type: str,
    slug: str,
    expected_active_digest: str | None,
    now: datetime | None = None,
) -> StaffContentUnpublishResponse:
    moment = now or _now()
    await _state_for_update(session)
    identity = _require_identity(article_type, slug)
    article = await session.scalar(select(Article).where(Article.id == identity).with_for_update())
    if article is None:
        raise ContentError("AI_STP_NOT_FOUND", "article not found")
    if article.source_kind != "staff":
        raise ContentError(
            "AI_STP_CONTENT_SOURCE_CONFLICT",
            "identity already belongs to another source owner",
        )
    pointers = await _current_active_pair(session, identity)
    if not pointers:
        return StaffContentUnpublishResponse(schema_version=1, article_id=identity)
    current_digest = await _pair_digest(session, pointers)
    if expected_active_digest != current_digest:
        raise ContentError("AI_STP_CONTENT_STALE", "expected active digest does not match")
    for locale, pointer in pointers.items():
        await session.execute(delete(ArticleActive).where(ArticleActive.id == pointer.id))
        await enqueue_article_seo_effect(
            session,
            article_id=identity,
            locales=[locale],
            source_digest=f"removed:{moment.date().isoformat()}",
        )
    await session.flush()
    return StaffContentUnpublishResponse(schema_version=1, article_id=identity)


def _date_ordinal(value: str) -> int:
    year, month, day = (int(part) for part in value.split("-"))
    return year * 10000 + month * 100 + day


async def list_published(session: AsyncSession, *, locale: str) -> ContentListResponse:
    locale_key = _as_locale(locale)
    rows = list(
        (
            await session.execute(
                select(ArticleActive, Article, ArticleRevision)
                .join(Article, Article.id == ArticleActive.article_id)
                .join(ArticleRevision, ArticleRevision.id == ArticleActive.revision_id)
                .where(ArticleActive.locale == locale_key)
            )
        ).all()
    )
    ordered = sorted(
        rows,
        key=lambda item: (-_date_ordinal(item[2].published_at), item[1].id),
    )
    items = [_summary(article, revision) for _pointer, article, revision in ordered]
    etag = public_list_etag(
        [
            {"article_id": article.id, "revision_id": revision.id}
            for _p, article, revision in ordered
        ]
    )
    return ContentListResponse(schema_version=1, etag=etag, items=items)


async def read_published(
    session: AsyncSession, *, article_type: str, slug: str, locale: str
) -> tuple[ContentDetail, str]:
    locale_key = _as_locale(locale)
    identity = article_identity(article_type, slug)
    row = (
        await session.execute(
            select(ArticleActive, Article, ArticleRevision)
            .join(Article, Article.id == ArticleActive.article_id)
            .join(ArticleRevision, ArticleRevision.id == ArticleActive.revision_id)
            .where(
                ArticleActive.article_id == identity,
                ArticleActive.locale == locale_key,
            )
        )
    ).first()
    if row is None:
        raise ContentError("AI_STP_NOT_FOUND", "article not found")
    _pointer, article, revision = row
    return _detail(article, revision), revision.content_digest
