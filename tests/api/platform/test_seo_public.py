"""Public SEO reads stay anonymous and cacheable (SPEC-053 REQ-5327)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.unit.platform.article_fixtures import seed_published_article

from ai_stp_api.settings import Settings
from ai_stp_platform.seo.settings import SeoSettings
from ai_stp_worker.handlers.seo_build import handle_seo_build

pytestmark = pytest.mark.platform

NOW = datetime(2026, 8, 1, tzinfo=UTC)
SUBJECT = "article:safe-setup"


@pytest.mark.asyncio
async def test_public_seo_read_has_no_session_and_public_cache(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_STP_SEO_PUBLIC_ORIGIN", "http://test")
    client, sessionmaker, _settings = db_api_client
    async with sessionmaker() as session, session.begin():
        await seed_published_article(session, now=NOW)
        await handle_seo_build(
            session,
            {"subject_kind": "article", "subject_id": SUBJECT, "locale": "en"},
            settings=SeoSettings(public_origin="http://test"),
            now=NOW,
        )
    response = await client.get(
        "/v1/seo/subjects/article/article:safe-setup",
        params={"locale": "en", "schema_version": 1},
    )
    assert response.status_code == 200
    assert "public" in response.headers["cache-control"]
    assert "cookie" not in response.request.headers
    payload = response.json()
    assert payload["profile"]["robots"] in {"index,follow", "noindex,follow"}
    assert payload["profile"]["canonical_url"].endswith("/en/content/article/safe-setup")
    sitemap = await client.get("/v1/seo/sitemap")
    assert sitemap.status_code == 200
    assert "public" in sitemap.headers["cache-control"]
    missing = await client.get(
        "/v1/seo/subjects/article/article:missing",
        params={"locale": "en", "schema_version": 1},
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_sitemap_shards_split_and_serve_disjoint_pages(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shard boundaries now live in SQL: the index must number the same
    buckets the paged shard query serves, or a shard ref could point at an
    empty window."""
    monkeypatch.setenv("AI_STP_SEO_PUBLIC_ORIGIN", "http://test")
    monkeypatch.setattr("ai_stp_platform.seo.read.sitemap_shard_limit", lambda: 1)
    client, sessionmaker, _settings = db_api_client
    async with sessionmaker() as session, session.begin():
        for slug in ("safe-setup", "second-setup"):
            await seed_published_article(session, now=NOW, slug=slug, title=f"Title {slug}")
            await handle_seo_build(
                session,
                {
                    "subject_kind": "article",
                    "subject_id": f"article:{slug}",
                    "locale": "en",
                },
                settings=SeoSettings(public_origin="http://test"),
                now=NOW,
            )
    index = await client.get("/v1/seo/sitemap")
    assert index.status_code == 200
    article_shards = [
        ref for ref in index.json()["shards"] if "/sitemaps/article-en-" in ref["loc"]
    ]
    assert len(article_shards) == 2
    first = await client.get("/v1/seo/sitemaps/article/en/1")
    second = await client.get("/v1/seo/sitemaps/article/en/2")
    assert first.status_code == 200
    assert second.status_code == 200
    first_urls = [item["loc"] for item in first.json()["urls"]]
    second_urls = [item["loc"] for item in second.json()["urls"]]
    assert len(first_urls) == 1
    assert len(second_urls) == 1
    assert first_urls[0] != second_urls[0]
    beyond = await client.get("/v1/seo/sitemaps/article/en/3")
    assert beyond.status_code == 404
