"""PostgreSQL usage increments stay atomic per keyed window (SPEC-051 REQ-5108)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_platform.catalog_usage import (
    ARTIFACT_DOWNLOAD,
    DETAIL_VIEW,
    CatalogUsagePolicy,
    record_usage,
)
from ai_stp_platform.models import CatalogUsageAggregate

pytestmark = pytest.mark.platform

STABLE_ID = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
SECRET = "integration-catalog-usage-secret-32b!"
NOW = datetime(2026, 8, 17, 12, 0, 0, tzinfo=UTC)


def _policy() -> CatalogUsagePolicy:
    return CatalogUsagePolicy(enabled=True, secret=SECRET)


async def test_concurrent_same_window_detail_view_records_one_usage_metrics_increment(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async def once() -> bool:
        async with db_sessionmaker() as session:
            changed = await record_usage(
                session,
                policy=_policy(),
                action=DETAIL_VIEW,
                stable_id=STABLE_ID,
                network_signal="203.0.113.10",
                now=NOW,
            )
            await session.commit()
            return changed

    results = await asyncio.gather(once(), once(), once())
    assert results.count(True) == 1
    async with db_sessionmaker() as session:
        row = await session.get(CatalogUsageAggregate, STABLE_ID)
        assert row is not None
        assert row.detail_views_count == 1
        assert row.artifact_downloads_count == 0


async def test_detail_view_and_artifact_download_windows_increment_independently(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    policy = _policy()
    later = datetime(2026, 8, 17, 14, 0, 0, tzinfo=UTC)
    async with db_sessionmaker() as session:
        assert await record_usage(
            session,
            policy=policy,
            action=DETAIL_VIEW,
            stable_id=STABLE_ID,
            network_signal="203.0.113.10",
            now=NOW,
        )
        assert await record_usage(
            session,
            policy=policy,
            action=ARTIFACT_DOWNLOAD,
            stable_id=STABLE_ID,
            network_signal="203.0.113.10",
            now=NOW,
        )
        assert await record_usage(
            session,
            policy=policy,
            action=DETAIL_VIEW,
            stable_id=STABLE_ID,
            network_signal="203.0.113.10",
            now=later,
        )
        await session.commit()
    async with db_sessionmaker() as session:
        row = await session.get(CatalogUsageAggregate, STABLE_ID)
        assert row is not None
        assert row.detail_views_count == 2
        assert row.artifact_downloads_count == 1
