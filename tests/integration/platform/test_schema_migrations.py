"""Executable PostgreSQL migration checks for SPEC-020."""

from __future__ import annotations

import asyncio

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.platform


async def _scalar(database_url: str, statement: str) -> object:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text(statement))
    finally:
        await engine.dispose()


def _version(database_url: str) -> object:
    return asyncio.run(_scalar(database_url, "SELECT version_num FROM alembic_version"))


def test_migrations_upgrade_repeat_downgrade_and_upgrade_again(
    isolated_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broken migration chain fails upgrade idempotency or downgrade compatibility."""
    from alembic.script import ScriptDirectory

    monkeypatch.setenv("AI_STP_DB_URL", isolated_database_url)
    config = Config("alembic.ini")
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1, f"branched migration history: {sorted(heads)}"
    head = heads[0]

    command.upgrade(config, "head")
    command.upgrade(config, "head")
    assert _version(isolated_database_url) == head

    command.downgrade(config, "0001_create_job")
    assert _version(isolated_database_url) == "0001_create_job"
    assert asyncio.run(_scalar(isolated_database_url, "SELECT to_regclass('public.job')")) == "job"
    assert (
        asyncio.run(_scalar(isolated_database_url, "SELECT to_regclass('public.catalog_metadata')"))
        is None
    )

    command.upgrade(config, "head")
    assert _version(isolated_database_url) == head
