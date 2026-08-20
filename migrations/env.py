"""Alembic environment for the shared platform schema (SPEC-018, #79 owns the tree)."""

from __future__ import annotations

import asyncio
import os

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from ai_stp_platform import models as _platform_models  # noqa: F401  register Sprint-1 metadata
from ai_stp_platform.db import Base
from ai_stp_platform.queue import models as _models  # noqa: F401  register Job metadata

target_metadata = Base.metadata


def _database_url() -> str:
    url = os.environ.get("AI_STP_DB_URL")
    if not url:
        raise RuntimeError("AI_STP_DB_URL is required for migrations")
    return url


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_database_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
