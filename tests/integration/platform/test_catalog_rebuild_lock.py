"""A rebuild coordinates with ordinary SQL writers (SPEC-034 REQ-3434)."""

from __future__ import annotations

import pytest

# The driver owns the SQLSTATE but does not distribute typing stubs.
from asyncpg.exceptions import LockNotAvailableError  # pyright: ignore[reportMissingTypeStubs]
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ai_stp_platform.catalog_search import lock_catalog_search_projection
from ai_stp_platform.models import CatalogSearchProjection

pytestmark = pytest.mark.platform


@pytest.mark.asyncio
async def test_rebuild_lock_preserves_readers_and_excludes_a_concurrent_writer(
    migrated_database_url: str,
) -> None:
    engine = create_async_engine(migrated_database_url)
    try:
        sessions = async_sessionmaker(engine)
        async with sessions() as rebuilding, sessions() as other:
            await lock_catalog_search_projection(rebuilding)
            await other.execute(text("SET LOCAL lock_timeout = '250ms'"))
            await other.execute(select(CatalogSearchProjection.id).limit(1))
            with pytest.raises(DBAPIError) as failure:
                await other.execute(delete(CatalogSearchProjection))
            assert getattr(failure.value.orig, "sqlstate", None) == LockNotAvailableError.sqlstate
    finally:
        await engine.dispose()
