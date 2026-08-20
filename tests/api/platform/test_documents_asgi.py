"""ASGI tests for public documents (SPEC-031)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.app import create_app
from ai_stp_api.settings import Settings
from ai_stp_api.slices.documents import service as documents_service

pytestmark = pytest.mark.platform


@pytest_asyncio.fixture
async def harness(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession]]]:
    settings = settings_factory(database_url=migrated_database_url)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app.state.sessionmaker


@pytest.mark.asyncio
async def test_public_document_only_published_and_renders_safe_html(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, sessionmaker = harness
    missing = await client.get("/v1/documents/privacy")
    assert missing.status_code == 404

    async with sessionmaker() as db:
        await documents_service.publish_revision(
            db,
            slug="privacy",
            kind="privacy",
            locale="en",
            title="Privacy",
            markdown_source="## Privacy\n\nWe process account data. [More](https://example.com/p)",
            source_ref="abc123",
            source_path="docs/legal/privacy.md",
        )
        await db.commit()

    ok = await client.get("/v1/documents/privacy", params={"locale": "en"})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["slug"] == "privacy"
    assert body["lifecycle"] == "published"
    assert body["source_ref"] == "abc123"
    assert body["source_path"] == "docs/legal/privacy.md"
    assert 'rel="noopener noreferrer"' in body["html"]
    assert "<script" not in body["html"].lower()
    assert "Cache-Control" in ok.headers

    # Supersession: new revision becomes the only published one for locale.
    async with sessionmaker() as db:
        await documents_service.publish_revision(
            db,
            slug="privacy",
            kind="privacy",
            locale="en",
            title="Privacy v2",
            markdown_source="## Privacy v2\n\nUpdated text.",
            source_ref="def456",
            source_path="docs/legal/privacy.md",
        )
        await db.commit()

    v2 = await client.get("/v1/documents/privacy", params={"locale": "en"})
    assert v2.status_code == 200
    assert v2.json()["title"] == "Privacy v2"
    assert "Updated text" in v2.json()["html"]


@pytest.mark.asyncio
async def test_document_locale_fallback(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, sessionmaker = harness
    async with sessionmaker() as db:
        await documents_service.publish_revision(
            db,
            slug="cookies",
            kind="cookies",
            locale="en",
            title="Cookies",
            markdown_source="Cookie policy body for agents and humans.",
        )
        await db.commit()

    # Unknown locale falls back to en.
    response = await client.get("/v1/documents/cookies", params={"locale": "de"})
    assert response.status_code == 200
    assert response.json()["locale"] == "en"
    assert response.json()["title"] == "Cookies"
