"""SEO persistence and job idempotency (SPEC-053)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.unit.platform.article_fixtures import seed_published_article

from ai_stp_contracts.seo import SEO_TEMPLATE_VERSION
from ai_stp_platform.queue.models import Job
from ai_stp_platform.queue.states import JobType
from ai_stp_platform.seo.enqueue import (
    enqueue_refresh_for_active,
    enqueue_seo_build,
)
from ai_stp_platform.seo.materialize import activate_base_revision, rollback_to_base
from ai_stp_platform.seo.orm import SeoActiveRevision, SeoFactSnapshot, SeoRevision
from ai_stp_platform.seo.settings import SeoSettings
from ai_stp_worker.handlers.seo_build import handle_seo_build
from ai_stp_worker.handlers.seo_enrich import handle_seo_enrich

pytestmark = pytest.mark.platform

NOW = datetime(2026, 8, 1, tzinfo=UTC)
SUBJECT = "article:safe-setup"
BUILD_PAYLOAD = {"subject_kind": "article", "subject_id": SUBJECT, "locale": "en"}


@pytest.mark.asyncio
async def test_seo_build_is_idempotent_and_activates_base(
    db_sessionmaker: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_STP_SEO_PUBLIC_ORIGIN", "https://example.test")
    monkeypatch.setenv("AI_STP_SEO_ENRICHMENT_ENABLED", "false")
    settings = SeoSettings()
    async with db_sessionmaker() as session, session.begin():
        await seed_published_article(session, now=NOW)
        await handle_seo_build(session, BUILD_PAYLOAD, settings=settings, now=NOW)
        await handle_seo_build(session, BUILD_PAYLOAD, settings=settings, now=NOW)
        snapshots = list((await session.execute(select(SeoFactSnapshot))).scalars())
        pointers = list((await session.execute(select(SeoActiveRevision))).scalars())
        assert len(snapshots) == 1
        assert len(pointers) == 1
        assert pointers[0].index_eligible is True


@pytest.mark.asyncio
async def test_enqueue_same_coordinates_is_one_job(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with db_sessionmaker() as session, session.begin():
        digest = "sha256:" + "1" * 64
        await enqueue_seo_build(session, kind="article", subject_id=SUBJECT, source_digest=digest)
        await enqueue_seo_build(session, kind="article", subject_id=SUBJECT, source_digest=digest)
        jobs = list((await session.execute(select(Job))).scalars())
        assert len(jobs) == 2  # one per locale
        keys = {job.idempotency_key for job in jobs}
        assert len(keys) == 2


@pytest.mark.asyncio
async def test_disabled_enrichment_leaves_base_active(
    db_sessionmaker: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_STP_SEO_PUBLIC_ORIGIN", "https://example.test")
    settings = SeoSettings(enrichment_enabled=False)
    async with db_sessionmaker() as session, session.begin():
        await seed_published_article(session, now=NOW)
        await handle_seo_build(session, BUILD_PAYLOAD, settings=settings, now=NOW)
        pointer = (await session.execute(select(SeoActiveRevision))).scalar_one()

        async def fetch(**_kwargs: object) -> dict[str, object]:
            raise AssertionError("disabled enrichment must not call a model")

        await handle_seo_enrich(
            session,
            {
                "subject_kind": "article",
                "subject_id": SUBJECT,
                "locale": "en",
                "snapshot_id": pointer.snapshot_id,
                "source_digest": pointer.snapshot_id,
                "template_version": settings.template_version,
            },
            settings=settings,
            fetch=fetch,
            now=NOW,
        )
        active = await session.get(SeoActiveRevision, pointer.id)
        assert active is not None
        assert active.revision_id == pointer.revision_id


@pytest.mark.asyncio
async def test_rollback_returns_to_template_revision(
    db_sessionmaker: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_STP_SEO_PUBLIC_ORIGIN", "https://example.test")
    settings = SeoSettings()
    async with db_sessionmaker() as session, session.begin():
        await seed_published_article(session, now=NOW)
        revision = await activate_base_revision(
            session,
            kind="article",
            subject_id=SUBJECT,
            locale="en",
            settings=settings,
            now=NOW,
        )
        rolled = await rollback_to_base(
            session, kind="article", subject_id=SUBJECT, locale="en", now=NOW
        )
        assert rolled.id == revision.id
        assert rolled.generator_kind == "template"


@pytest.mark.asyncio
async def test_template_rebuild_creates_new_revision_same_snapshot(
    db_sessionmaker: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_STP_SEO_PUBLIC_ORIGIN", "https://example.test")
    async with db_sessionmaker() as session, session.begin():
        await seed_published_article(session, now=NOW)
        first = await activate_base_revision(
            session,
            kind="article",
            subject_id=SUBJECT,
            locale="en",
            settings=SeoSettings(template_version="seo-template-v1"),
            now=NOW,
        )
        second = await activate_base_revision(
            session,
            kind="article",
            subject_id=SUBJECT,
            locale="en",
            settings=SeoSettings(template_version="seo-template-v2"),
            now=NOW,
        )
        assert first.id != second.id
        assert first.snapshot_id == second.snapshot_id
        pointer = (await session.execute(select(SeoActiveRevision))).scalar_one()
        assert pointer.revision_id == second.id
        assert pointer.generation >= 2


@pytest.mark.asyncio
async def test_refresh_rebuilds_outdated_template_before_enrichment(
    db_sessionmaker: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_STP_SEO_PUBLIC_ORIGIN", "https://example.test")
    async with db_sessionmaker() as session, session.begin():
        await seed_published_article(session, now=NOW)
        await activate_base_revision(
            session,
            kind="article",
            subject_id=SUBJECT,
            locale="en",
            settings=SeoSettings(template_version="seo-template-v1"),
            now=NOW,
        )
        builds, enrichments = await enqueue_refresh_for_active(
            session,
            settings=SeoSettings(
                enrichment_enabled=True,
                template_version=SEO_TEMPLATE_VERSION,
                public_origin="https://example.test",
            ),
        )
        jobs = list((await session.execute(select(Job))).scalars())
        assert (builds, enrichments) == (1, 0)
        assert any(
            job.job_type == JobType.SEO_BUILD.value
            and job.payload["template_version"] == SEO_TEMPLATE_VERSION
            for job in jobs
        )
        assert not any(job.job_type == JobType.SEO_ENRICH.value for job in jobs)


@pytest.mark.asyncio
async def test_service_enqueue_covers_service_and_country(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    from ai_stp_platform.seo.enqueue import enqueue_service_and_countries

    async with db_sessionmaker() as session, session.begin():
        await enqueue_service_and_countries(
            session, domain="kaspi.kz", country_codes=["KZ"], extra="attach"
        )
        jobs = list((await session.execute(select(Job))).scalars())
        pairs = {(job.payload["subject_kind"], job.payload["subject_id"]) for job in jobs}
        assert ("service", "kaspi.kz") in pairs
        assert ("country", "KZ") in pairs


@pytest.mark.asyncio
async def test_enrichment_invalid_output_leaves_base_active(
    db_sessionmaker: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_STP_SEO_PUBLIC_ORIGIN", "https://example.test")
    settings = SeoSettings(
        enrichment_enabled=True,
        enrichment_url="http://litellm.test/v1/chat/completions",
    )
    async with db_sessionmaker() as session, session.begin():
        await seed_published_article(session, now=NOW)
        await handle_seo_build(
            session,
            BUILD_PAYLOAD,
            settings=SeoSettings(enrichment_enabled=False, public_origin="https://example.test"),
            now=NOW,
        )
        pointer = (await session.execute(select(SeoActiveRevision))).scalar_one()
        active_id = pointer.revision_id

        async def fetch(**_kwargs: object) -> dict[str, object]:
            return {"choices": [{"message": {"content": "not-json{"}}]}

        await handle_seo_enrich(
            session,
            {
                "subject_kind": "article",
                "subject_id": SUBJECT,
                "locale": "en",
                "snapshot_id": pointer.snapshot_id,
                "source_digest": pointer.snapshot_id,
                "template_version": settings.template_version,
            },
            settings=settings,
            fetch=fetch,
            now=NOW,
        )
        refreshed = await session.get(SeoActiveRevision, pointer.id)
        assert refreshed is not None
        assert refreshed.revision_id == active_id


@pytest.mark.asyncio
async def test_enrichment_retries_low_quality_candidate_with_feedback(
    db_sessionmaker: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_STP_SEO_PUBLIC_ORIGIN", "https://example.test")
    settings = SeoSettings(
        enrichment_enabled=True,
        enrichment_url="http://litellm.test/v1/chat/completions",
        public_origin="https://example.test",
    )
    async with db_sessionmaker() as session, session.begin():
        await seed_published_article(session, now=NOW)
        await handle_seo_build(
            session,
            BUILD_PAYLOAD,
            settings=SeoSettings(
                enrichment_enabled=False,
                public_origin="https://example.test",
                template_version="seo-template-v2",
            ),
            now=NOW,
        )
        await handle_seo_build(
            session,
            BUILD_PAYLOAD,
            settings=SeoSettings(enrichment_enabled=False, public_origin="https://example.test"),
            now=NOW,
        )
        pointer = (await session.execute(select(SeoActiveRevision))).scalar_one()
        calls: list[dict[str, object]] = []

        async def fetch(**kwargs: object) -> dict[str, object]:
            body = kwargs["body"]
            assert isinstance(body, dict)
            calls.append(cast(dict[str, object], body))
            content: object = (
                {
                    "title": "Build a setup",
                    "description": "Thin description.",
                    "summary": "Thin summary.",
                    "search_intents": ["setup"],
                    "sections": [],
                    "social_title": "Build a setup",
                    "social_description": "Thin description.",
                    "social_image_alt": "Build a setup",
                }
                if len(calls) == 1
                else {
                    "title": "Build a setup from exact component versions",
                    "description": (
                        "Learn how to assemble an ai_stp setup from exact component versions, "
                        "preserve reproducibility, and avoid accidental dependency drift."
                    ),
                    "summary": (
                        "This guide explains the setup assembly sequence in ai_stp. It shows why "
                        "pinning component versions keeps the resulting configuration repeatable."
                    ),
                    "search_intents": [
                        "build ai stp setup",
                        "pin component versions",
                        "reproducible agent configuration",
                    ],
                    "sections": [],
                    "social_title": "Build a reproducible ai_stp setup",
                    "social_description": "Assemble a setup from exact component versions.",
                    "social_image_alt": "Diagram for building an ai_stp setup",
                }
            )
            return {"choices": [{"message": {"content": content}}]}

        await handle_seo_enrich(
            session,
            {
                "subject_kind": "article",
                "subject_id": SUBJECT,
                "locale": "en",
                "snapshot_id": pointer.snapshot_id,
                "source_digest": pointer.snapshot_id,
                "template_version": settings.template_version,
            },
            settings=settings,
            fetch=fetch,
            now=NOW,
        )
        refreshed = await session.get(SeoActiveRevision, pointer.id)
        assert refreshed is not None
        revision = await session.get(SeoRevision, refreshed.revision_id)
        assert revision is not None and revision.generator_kind == "model"
        generator = revision.profile["generator"]
        assert isinstance(generator, dict)
        assert generator["template_version"] == settings.template_version
        assert len(calls) == 2
        retry_messages = calls[1]["messages"]
        assert "retry_feedback" in str(retry_messages)
