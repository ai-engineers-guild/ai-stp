"""Atomic article publication and SEO side effects (SPEC-054)."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.unit.platform.article_fixtures import (
    NOW,
    empty_snapshot,
    pair_snapshot,
    staff_payload,
)

from ai_stp_platform.content.errors import ContentError
from ai_stp_platform.content.orm import Article, ArticleActive, ArticleRevision
from ai_stp_platform.content.service import (
    import_repository_snapshot,
    list_published,
    publish_staff_article,
    unpublish_staff_article,
)
from ai_stp_platform.models import Account
from ai_stp_platform.queue.models import Job
from ai_stp_platform.seo.settings import SeoSettings
from ai_stp_worker.handlers.seo_build import handle_seo_build

pytestmark = pytest.mark.platform


@pytest.mark.asyncio
async def test_repository_import_is_atomic_and_repeatable(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    snapshot = pair_snapshot()
    async with db_sessionmaker() as session, session.begin():
        first = await import_repository_snapshot(session, snapshot, now=NOW)
        second = await import_repository_snapshot(session, snapshot, now=NOW)
        assert first.generation == 1
        assert first.created == 2
        assert first.activated == 2
        assert second.generation == 1
        assert second.created == 0
        assert second.activated == 0
        removed = await import_repository_snapshot(
            session, empty_snapshot(expected_generation=1), now=NOW
        )
        assert removed.removed == 2
        assert removed.generation == 2
        revisions = (
            await session.execute(select(func.count()).select_from(ArticleRevision))
        ).scalar_one()
        actives = (
            await session.execute(select(func.count()).select_from(ArticleActive))
        ).scalar_one()
        assert revisions == 2
        assert actives == 0


@pytest.mark.asyncio
async def test_stale_generation_and_source_conflict_leave_state(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with db_sessionmaker() as session, session.begin():
        await import_repository_snapshot(session, pair_snapshot(), now=NOW)
        with pytest.raises(ContentError) as stale:
            await import_repository_snapshot(
                session,
                pair_snapshot(body_en="Changed body.", expected_generation=0),
                now=NOW,
            )
        assert stale.value.code == "AI_STP_CONTENT_STALE"
        session.add(Account(id="account_staff"))
        await session.flush()
        await publish_staff_article(
            session,
            article_type="article",
            slug="staff-note",
            request=staff_payload(),
            actor_account_id="account_staff",
            now=NOW,
        )
        collision = pair_snapshot(slug="staff-note", expected_generation=1)
        with pytest.raises(ContentError) as conflict:
            await import_repository_snapshot(session, collision, now=NOW)
        assert conflict.value.code == "AI_STP_CONTENT_SOURCE_CONFLICT"
        listed = await list_published(session, locale="en")
        slugs = {item.slug for item in listed.items}
        assert "safe-setup" in slugs
        assert "staff-note" in slugs


@pytest.mark.asyncio
async def test_staff_cannot_take_repository_identity(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with db_sessionmaker() as session, session.begin():
        await import_repository_snapshot(session, pair_snapshot(), now=NOW)
        with pytest.raises(ContentError) as conflict:
            await publish_staff_article(
                session,
                article_type="article",
                slug="safe-setup",
                request=staff_payload(),
                actor_account_id="account_staff",
                now=NOW,
            )
        assert conflict.value.code == "AI_STP_CONTENT_SOURCE_CONFLICT"
        owner = await session.get(Article, "article:safe-setup")
        assert owner is not None
        assert owner.source_kind == "repository"


@pytest.mark.asyncio
async def test_seo_job_failure_keeps_publication(
    db_sessionmaker: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_STP_SEO_PUBLIC_ORIGIN", "https://example.test")
    async with db_sessionmaker() as session, session.begin():
        await import_repository_snapshot(session, pair_snapshot(), now=NOW)
        listed = await list_published(session, locale="en")
        assert listed.items
        jobs = list((await session.execute(select(Job))).scalars())
        assert jobs

        async def boom(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("seo worker failed")

        monkeypatch.setattr("ai_stp_worker.handlers.seo_build.activate_base_revision", boom)
        with pytest.raises(RuntimeError, match="seo worker failed"):
            await handle_seo_build(
                session,
                {
                    "subject_kind": "article",
                    "subject_id": "article:safe-setup",
                    "locale": "en",
                },
                settings=SeoSettings(public_origin="https://example.test"),
                now=NOW,
            )
        still = await list_published(session, locale="en")
        assert [item.slug for item in still.items] == [item.slug for item in listed.items]


@pytest.mark.asyncio
async def test_staff_unpublish_keeps_history(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with db_sessionmaker() as session, session.begin():
        session.add(Account(id="account_staff"))
        await session.flush()
        published = await publish_staff_article(
            session,
            article_type="article",
            slug="staff-note",
            request=staff_payload(),
            actor_account_id="account_staff",
            now=NOW,
        )
        await unpublish_staff_article(
            session,
            article_type="article",
            slug="staff-note",
            expected_active_digest=published.active_digest,
            now=NOW,
        )
        listed = await list_published(session, locale="en")
        assert listed.items == []
        revisions = (
            await session.execute(select(func.count()).select_from(ArticleRevision))
        ).scalar_one()
        assert revisions == 2
        again = await unpublish_staff_article(
            session,
            article_type="article",
            slug="staff-note",
            expected_active_digest="sha256:" + "0" * 64,
            now=NOW,
        )
        assert again.unpublished is True
