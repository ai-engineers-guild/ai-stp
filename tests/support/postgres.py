"""Shared PostgreSQL machinery for tests that need a real database.

Both platform conftests carried their own copy of these helpers; the CLI↔API
boundary tests need them a third time. One copy lives here — the fixture
wrappers stay in each tree's conftest because pytest resolves fixtures by
closure, and the root conftest marks `pg` from the same fixture names.

Everything is keyed off `AI_STP_TEST_DB_URL`; without it every consumer skips
rather than failing, because a missing service is not a failed check.
"""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from collections.abc import Generator
from contextlib import contextmanager

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

TEST_DB_ENV = "AI_STP_TEST_DB_URL"
_VALID_DATABASE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def run_sync(coro: object) -> None:
    """Drive a coroutine from a sync fixture."""
    asyncio.run(coro)  # type: ignore[arg-type]


def database_name() -> str:
    return f"ai_stp_it_{uuid.uuid4().hex[:24]}"


def quote_identifier(identifier: str) -> str:
    if not _VALID_DATABASE_NAME.fullmatch(identifier):
        raise ValueError(f"unsafe PostgreSQL identifier: {identifier!r}")
    return f'"{identifier}"'


def url_with_database(url: str, database: str) -> str:
    from sqlalchemy.engine import make_url

    # str(URL) redacts the password as "***"; render explicitly for a usable DSN.
    return make_url(url).set(database=database).render_as_string(hide_password=False)


async def execute_admin(url: str, statement: str) -> None:
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


@contextmanager
def isolated_database(skip_reason: str) -> Generator[str, None, None]:
    """Create a temporary database and drop it; skip when no server is set."""
    template_url = os.environ.get(TEST_DB_ENV)
    if not template_url:
        pytest.skip(skip_reason)

    database = database_name()
    quoted = quote_identifier(database)
    admin_url = url_with_database(template_url, "postgres")
    run_sync(execute_admin(admin_url, f"CREATE DATABASE {quoted} TEMPLATE template0"))
    try:
        yield url_with_database(template_url, database)
    finally:
        run_sync(execute_admin(admin_url, f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)"))


@contextmanager
def migrated_template() -> Generator[str | None, None, None]:
    """One fully migrated database per xdist worker; tests clone it.

    Applying the whole Alembic chain per test multiplied the migration cost by
    the worker count against one PostgreSQL instance. The chain runs once per
    worker here; each test then creates its own database with
    `CREATE DATABASE ... TEMPLATE`, which is a file-level copy rather than a
    replay of every migration.
    """
    template_url = os.environ.get(TEST_DB_ENV)
    if not template_url:
        yield None
        return

    admin_url = url_with_database(template_url, "postgres")
    database = database_name()
    quoted = quote_identifier(database)
    run_sync(execute_admin(admin_url, f"CREATE DATABASE {quoted} TEMPLATE template0"))
    saved = os.environ.get("AI_STP_DB_URL")
    os.environ["AI_STP_DB_URL"] = url_with_database(template_url, database)
    try:
        command.upgrade(Config("alembic.ini"), "head")
        yield database
    finally:
        if saved is None:
            os.environ.pop("AI_STP_DB_URL", None)
        else:
            os.environ["AI_STP_DB_URL"] = saved
        run_sync(execute_admin(admin_url, f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)"))


@contextmanager
def migrated_database(
    template: str | None, monkeypatch: pytest.MonkeyPatch, *, skip_reason: str
) -> Generator[str, None, None]:
    """Clone the per-worker migrated template into a disposable database."""
    if template is None:
        pytest.skip(skip_reason)

    template_url = os.environ[TEST_DB_ENV]
    database = database_name()
    quoted = quote_identifier(database)
    admin_url = url_with_database(template_url, "postgres")
    run_sync(
        execute_admin(
            admin_url,
            f"CREATE DATABASE {quoted} TEMPLATE {quote_identifier(template)}",
        )
    )
    url = url_with_database(template_url, database)
    monkeypatch.setenv("AI_STP_DB_URL", url)
    try:
        yield url
    finally:
        run_sync(execute_admin(admin_url, f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)"))
