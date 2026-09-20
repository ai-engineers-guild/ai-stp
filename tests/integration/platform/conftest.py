"""PostgreSQL integration fixtures for platform storage tests.

The machinery lives in `tests/support/postgres.py`; fixture names stay
identical because the root conftest marks `pg` from them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.support.postgres import (
    TEST_DB_ENV,
    isolated_database,
    migrated_database,
    migrated_template,
)


@pytest.fixture()
def isolated_database_url() -> Iterator[str]:
    """Create a temporary PostgreSQL database and remove it after one test."""
    with isolated_database(f"{TEST_DB_ENV} is required for PostgreSQL integration tests") as url:
        yield url


@pytest.fixture(scope="session")
def pg_migrated_template() -> Iterator[str | None]:
    """One fully migrated database per xdist worker; individual tests clone it.

    Session scope never calls `pytest.skip`: a skip there would abandon every
    test in the worker, not just the ones that need the database. Without
    `TEST_DB_ENV` this yields None and the function-scoped fixture below skips
    through `isolated_database_url`, exactly as before.
    """
    with migrated_template() as database:
        yield database


@pytest.fixture()
def migrated_database_url(
    pg_migrated_template: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[str]:
    """Clone the per-worker migrated template into a disposable database.

    The skip message matches `isolated_database_url`: the same environment
    variable gates both, and a test that needs migrations needs the server
    behind it just as much.
    """
    with migrated_database(
        pg_migrated_template,
        monkeypatch,
        skip_reason=f"{TEST_DB_ENV} is required for PostgreSQL integration tests",
    ) as url:
        yield url


@pytest.fixture()
async def db_session(
    migrated_database_url: str,
) -> AsyncIterator[AsyncSession]:
    """Yield a transaction-isolated async session for one test."""
    engine = create_async_engine(migrated_database_url)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            sessionmaker = async_sessionmaker(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            async with sessionmaker() as session:
                yield session
            if transaction.is_active:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.fixture()
async def db_sessionmaker(
    migrated_database_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Yield a sessionmaker bound to one isolated migrated database."""
    engine = create_async_engine(migrated_database_url)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
