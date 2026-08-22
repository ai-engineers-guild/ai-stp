"""PostgreSQL integration fixtures for platform storage tests."""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DB_ENV = "AI_STP_TEST_DB_URL"
_VALID_DATABASE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def _run(coro: object) -> None:
    asyncio.run(coro)  # type: ignore[arg-type]


def _database_name() -> str:
    return f"ai_stp_it_{uuid.uuid4().hex[:24]}"


def _quote_identifier(identifier: str) -> str:
    if not _VALID_DATABASE_NAME.fullmatch(identifier):
        raise ValueError(f"unsafe PostgreSQL identifier: {identifier!r}")
    return f'"{identifier}"'


def _url_with_database(url: str, database: str) -> str:
    from sqlalchemy.engine import make_url

    # str(URL) redacts the password as "***"; render explicitly for a usable DSN.
    return make_url(url).set(database=database).render_as_string(hide_password=False)


async def _execute_admin(url: str, statement: str) -> None:
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


@pytest.fixture()
def isolated_database_url() -> Iterator[str]:
    """Create a temporary PostgreSQL database and remove it after one test."""
    template_url = os.environ.get(TEST_DB_ENV)
    if not template_url:
        pytest.skip(f"{TEST_DB_ENV} is required for PostgreSQL integration tests")

    database = _database_name()
    quoted = _quote_identifier(database)
    admin_url = _url_with_database(template_url, "postgres")
    _run(_execute_admin(admin_url, f"CREATE DATABASE {quoted} TEMPLATE template0"))
    try:
        yield _url_with_database(template_url, database)
    finally:
        _run(_execute_admin(admin_url, f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)"))


@pytest.fixture(scope="session")
def pg_migrated_template() -> Iterator[str | None]:
    """One fully migrated database per xdist worker; individual tests clone it.

    Applying the whole Alembic chain inside `migrated_database_url` made every
    database test pay the migration cost again, and under xdist that cost
    multiplied by the worker count against one PostgreSQL instance. The chain
    is applied once per worker process here instead; each test then creates its
    own database with `CREATE DATABASE ... TEMPLATE`, which is a file-level
    copy rather than a replay of every migration.

    Session scope never calls `pytest.skip`: a skip there would abandon every
    test in the worker, not just the ones that need the database. Without
    `TEST_DB_ENV` this yields None and the function-scoped fixture below skips
    through `isolated_database_url`, exactly as before.
    """
    template_url = os.environ.get(TEST_DB_ENV)
    if not template_url:
        yield None
        return

    admin_url = _url_with_database(template_url, "postgres")
    database = _database_name()
    quoted = _quote_identifier(database)
    _run(_execute_admin(admin_url, f"CREATE DATABASE {quoted} TEMPLATE template0"))
    saved = os.environ.get("AI_STP_DB_URL")
    os.environ["AI_STP_DB_URL"] = _url_with_database(template_url, database)
    try:
        command.upgrade(Config("alembic.ini"), "head")
        yield database
    finally:
        if saved is None:
            os.environ.pop("AI_STP_DB_URL", None)
        else:
            os.environ["AI_STP_DB_URL"] = saved
        _run(_execute_admin(admin_url, f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)"))


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
    if pg_migrated_template is None:
        pytest.skip(f"{TEST_DB_ENV} is required for PostgreSQL integration tests")
    template_url = os.environ[TEST_DB_ENV]
    database = _database_name()
    quoted = _quote_identifier(database)
    admin_url = _url_with_database(template_url, "postgres")
    _run(
        _execute_admin(
            admin_url,
            f"CREATE DATABASE {quoted} TEMPLATE {_quote_identifier(pg_migrated_template)}",
        )
    )
    url = _url_with_database(template_url, database)
    monkeypatch.setenv("AI_STP_DB_URL", url)
    try:
        yield url
    finally:
        _run(_execute_admin(admin_url, f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)"))


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
