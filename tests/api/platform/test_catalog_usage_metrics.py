"""Public catalog usage counters stay additive, success-only, and gated."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.api.platform.conftest import TEST_CURSOR_SECRET, make_settings

from ai_stp_api.app import create_app
from ai_stp_api.settings import CatalogSettings
from ai_stp_contracts.catalog import CatalogUsageMetrics
from ai_stp_foundation.canonical import canonize
from ai_stp_foundation.digests import digest_bytes
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_platform.catalog_projection import PASSPORT_DIGEST_DOMAIN
from ai_stp_platform.catalog_seed import FIXTURE_COMPONENT_ID, load_first_party_seed
from ai_stp_platform.models import CatalogMetadata, CatalogUsageAggregate, ObjectLocation
from ai_stp_platform.storage import ImmutableObjectStore
from ai_stp_platform.storage.object_store import ARTIFACT_DIGEST_DOMAIN

pytestmark = pytest.mark.platform

_USAGE_SECRET = "test-catalog-usage-secret-32-bytes!!"


def _usage_catalog(*, enabled: bool) -> CatalogSettings:
    return CatalogSettings(
        cursor_signing_secret=TEST_CURSOR_SECRET,
        usage_enabled=enabled,
        usage_secret=_USAGE_SECRET if enabled else "",
    )


@pytest_asyncio.fixture
async def usage_client(
    migrated_database_url: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession]]]:
    settings = make_settings(
        tmp_path_factory.mktemp("catalog-usage"),
        database_url=migrated_database_url,
        catalog=_usage_catalog(enabled=True),
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with app.state.sessionmaker() as session:
            await load_first_party_seed(session)
            payload = b"usage-counter-artifact"
            digest = digest_bytes(ARTIFACT_DIGEST_DOMAIN, payload)
            store = ImmutableObjectStore(settings=settings.storage, client=app.state.object_client)
            stored = await store.put_immutable(
                payload, expected_digest=digest, expected_size=len(payload)
            )
            row = (
                await session.execute(
                    select(CatalogMetadata).where(
                        CatalogMetadata.stable_id == FIXTURE_COMPONENT_ID,
                        CatalogMetadata.version == "1.2",
                    )
                )
            ).scalar_one()
            passport = dict(row.passport_document or {})
            passport["artifact"] = {"digest": digest, "size_bytes": len(payload)}
            passport["revision_id"] = derive_revision_id(passport)
            row.passport_document = passport
            row.passport_digest = digest_bytes(PASSPORT_DIGEST_DOMAIN, canonize(passport))
            session.add(
                ObjectLocation(
                    catalog_metadata_id=row.id,
                    purpose="artifact",
                    object_key=stored.key,
                    digest=digest,
                    content_id=stored.content_id,
                    size_bytes=len(payload),
                )
            )
            await session.commit()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app.state.sessionmaker


@pytest_asyncio.fixture
async def disabled_usage_client(
    migrated_database_url: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession]]]:
    settings = make_settings(
        tmp_path_factory.mktemp("catalog-usage-off"),
        database_url=migrated_database_url,
        catalog=_usage_catalog(enabled=False),
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with app.state.sessionmaker() as session:
            await load_first_party_seed(session)
            await session.commit()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app.state.sessionmaker


async def test_disabled_usage_omits_metrics_and_does_not_record(
    disabled_usage_client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, sessionmaker = disabled_usage_client
    detail = await client.get(f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}")
    listed = await client.get(
        "/v1/catalog/components", params={"page_size": "20", "include_experimental": "true"}
    )
    version = await client.get(f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}/versions/1.2")
    assert detail.status_code == 200
    assert listed.status_code == 200
    assert version.status_code == 200
    assert detail.json()["summary"]["usage_metrics"] is None
    assert listed.json()["experimental"][0]["usage_metrics"] is None
    assert version.json()["usage_metrics"] is None
    async with sessionmaker() as session:
        assert (await session.scalar(select(CatalogUsageAggregate))) is None


async def test_detail_and_card_share_one_aggregate_without_false_repeat(
    usage_client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, _sessionmaker = usage_client
    first = await client.get(f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}")
    second = await client.get(f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}")
    listed = await client.get(
        "/v1/catalog/components", params={"page_size": "20", "include_experimental": "true"}
    )
    version = await client.get(f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}/versions/1.2")
    assert first.status_code == 200
    metrics = first.json()["summary"]["usage_metrics"]
    assert metrics == {"schema_version": 1, "detail_views_count": 1, "artifact_downloads_count": 0}
    assert second.json()["summary"]["usage_metrics"] == metrics
    assert listed.json()["experimental"][0]["usage_metrics"] == metrics
    assert version.json()["usage_metrics"] == metrics
    assert version.json()["trust"]["component_verified"] is False
    assert version.json()["trust"]["author_verified"] is False


async def test_search_and_metadata_do_not_count_as_detail_views(
    usage_client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, _sessionmaker = usage_client
    await client.get(
        "/v1/catalog/components", params={"page_size": "20", "include_experimental": "true"}
    )
    await client.get(f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}/versions/1.2")
    detail = await client.get(f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}")
    assert detail.json()["summary"]["usage_metrics"]["detail_views_count"] == 1


async def test_successful_artifact_get_counts_download_not_install(
    usage_client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, _sessionmaker = usage_client
    path = f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}/versions/1.2/artifact"
    downloaded = await client.get(path)
    head = await client.head(path)
    missing = await client.get(
        f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}/versions/1.0/artifact"
    )
    detail = await client.get(f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}")
    assert downloaded.status_code == 200
    assert head.is_client_error
    assert missing.status_code == 404
    metrics = detail.json()["summary"]["usage_metrics"]
    projected = CatalogUsageMetrics.model_validate(metrics)
    assert projected.artifact_downloads_count == 1
    assert projected.detail_views_count == 1
    assert detail.json()["summary"]["latest_trust"]["trust_lane"] == "experimental"
    assert "install" not in metrics
