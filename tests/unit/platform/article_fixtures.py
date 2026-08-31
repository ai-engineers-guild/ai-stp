"""Builders for SPEC-054 article snapshots. Values come from contract constants."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.content import (
    CONTENT_REPOSITORY,
    ContentRepositoryImportRequest,
    ContentSnapshotEntry,
    StaffContentPublishRequest,
    StaffContentTranslation,
    StaffContentTranslations,
)
from ai_stp_platform.content.digests import (
    article_identity,
    article_revision_id,
    revision_content_digest,
    snapshot_digest,
)
from ai_stp_platform.content.orm import Article, ArticleActive, ArticleRevision

NOW = datetime(2026, 8, 12, tzinfo=UTC)
COMMIT = "a" * 40


def localized_entry(
    *,
    locale: str,
    title: str,
    body: str,
    slug: str = "safe-setup",
    article_type: str = "article",
    description: str | None = None,
    published_at: str = "2026-08-12",
    tags: list[str] | None = None,
) -> ContentSnapshotEntry:
    ordered = sorted(tags or ["setup"])
    source_path = f"docs-user-facing/content/{locale}/article-{slug}.md"
    digest = revision_content_digest(
        article_type=article_type,
        slug=slug,
        locale=locale,
        title=title,
        description=description or f"{title} description",
        published_at=published_at,
        tags=ordered,
        body=body,
        source_kind="repository",
        source_ref=COMMIT,
        source_path=source_path,
    )
    return ContentSnapshotEntry(
        type=article_type,  # type: ignore[arg-type]
        slug=slug,
        locale=locale,  # type: ignore[arg-type]
        title=title,
        description=description or f"{title} description",
        published_at=published_at,
        tags=ordered,
        body=body,
        content_digest=digest,
        source_kind="repository",
        source_ref=COMMIT,
        source_path=source_path,
    )


def pair_snapshot(
    *,
    expected_generation: int = 0,
    slug: str = "safe-setup",
    body_en: str = "Use exact versions.",
    body_ru: str = "Tochnye versii.",
    title_en: str = "Build a setup",
    title_ru: str = "Sobrati setup",
) -> ContentRepositoryImportRequest:
    entries = [
        localized_entry(locale="en", title=title_en, body=body_en, slug=slug),
        localized_entry(locale="ru", title=title_ru, body=body_ru, slug=slug),
    ]
    digest = snapshot_digest(
        repository=CONTENT_REPOSITORY,
        commit=COMMIT,
        entries=[item.model_dump(mode="json") for item in entries],
    )
    return ContentRepositoryImportRequest(
        schema_version=1,
        repository=CONTENT_REPOSITORY,
        commit=COMMIT,
        snapshot_digest=digest,
        expected_generation=expected_generation,
        entries=entries,
    )


def empty_snapshot(
    *, expected_generation: int, commit: str = COMMIT
) -> ContentRepositoryImportRequest:
    digest = snapshot_digest(repository=CONTENT_REPOSITORY, commit=commit, entries=[])
    return ContentRepositoryImportRequest(
        schema_version=1,
        repository=CONTENT_REPOSITORY,
        commit=commit,
        snapshot_digest=digest,
        expected_generation=expected_generation,
        entries=[],
    )


def staff_payload(
    *,
    expected_active_digest: str | None = None,
    body_en: str = "Staff body EN.",
    body_ru: str = "Staff body RU.",
) -> StaffContentPublishRequest:
    return StaffContentPublishRequest(
        schema_version=1,
        expected_active_digest=expected_active_digest,
        translations=StaffContentTranslations(
            en=StaffContentTranslation(
                title="staff-title-en",
                description="staff-description-en",
                published_at="2026-08-12",
                tags=["note"],
                body=body_en,
            ),
            ru=StaffContentTranslation(
                title="staff-title-ru",
                description="staff-description-ru",
                published_at="2026-08-12",
                tags=["note"],
                body=body_ru,
            ),
        ),
    )


async def seed_published_article(
    session: AsyncSession,
    *,
    body: str = "Use exact versions.",
    now: datetime | None = None,
    article_type: str = "article",
    slug: str = "safe-setup",
    locale: str = "en",
    title: str = "Build a setup",
    description: str = "How to assemble a setup from exact versions.",
    published_at: str = "2026-08-01",
    tags: list[str] | None = None,
) -> str:
    """Insert one active localized article for SEO collector tests."""
    moment = now or NOW
    ordered = sorted(tags or ["setup"])
    identity = article_identity(article_type, slug)
    digest = revision_content_digest(
        article_type=article_type,
        slug=slug,
        locale=locale,
        title=title,
        description=description,
        published_at=published_at,
        tags=ordered,
        body=body,
        source_kind="repository",
        source_ref=None,
        source_path=None,
    )
    revision_pk = article_revision_id(article_id=identity, locale=locale, content_digest=digest)
    session.add(
        Article(
            id=identity,
            article_type=article_type,
            slug=slug,
            source_kind="repository",
            created_at=moment,
        )
    )
    await session.flush()
    session.add(
        ArticleRevision(
            id=revision_pk,
            article_id=identity,
            locale=locale,
            title=title,
            description=description,
            published_at=published_at,
            tags=ordered,
            body=body,
            content_digest=digest,
            source_kind="repository",
            source_ref=None,
            source_path=None,
            actor_account_id=None,
            created_at=moment,
        )
    )
    await session.flush()
    session.add(
        ArticleActive(
            article_id=identity,
            locale=locale,
            revision_id=revision_pk,
            updated_at=moment,
        )
    )
    await session.flush()
    return identity
