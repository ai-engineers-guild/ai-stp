"""Readiness probes for required dependencies (SPEC-017 REQ-1708).

Each probe collapses any failure to a boolean so readiness can report which
dependency is not ready without leaking internal detail. Liveness never calls
these: it must stay independent of dependencies.
"""

from __future__ import annotations

from functools import cache

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_platform.settings import StorageSettings

# Closed set of dependency names reported by readiness.
DEPENDENCIES: tuple[str, ...] = ("database", "migrations", "storage")


async def check_database(sessionmaker: async_sessionmaker[AsyncSession]) -> bool:
    """Report whether the database answers a trivial query."""
    try:
        async with sessionmaker() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@cache
def migration_head() -> str | None:
    """The Alembic head this build ships, read once per process.

    It is a property of the deployed code. Parsing every revision file took most
    of a readiness call, synchronously, on the event loop. A failed read raises
    and is not cached, so the next probe tries again.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()


async def check_migrations(sessionmaker: async_sessionmaker[AsyncSession]) -> bool:
    """Report whether the database revision has reached the Alembic head."""
    try:
        head = migration_head()
        async with sessionmaker() as session:
            result = await session.execute(text("SELECT version_num FROM alembic_version"))
            return result.scalar_one_or_none() == head
    except Exception:
        return False


async def check_storage(settings: StorageSettings) -> bool:
    """Report whether the object storage endpoint is reachable."""
    try:
        async with httpx.AsyncClient(timeout=settings.health_timeout_seconds) as client:
            response = await client.get(settings.endpoint)
        return response.status_code < 500
    except Exception:
        return False


async def readiness_report(
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    storage: StorageSettings,
) -> dict[str, bool]:
    """Probe every required dependency and return their readiness by name."""
    database = await check_database(sessionmaker)
    migrations = await check_migrations(sessionmaker) if database else False
    storage_ready = await check_storage(storage)
    return {"database": database, "migrations": migrations, "storage": storage_ready}


def not_ready(report: dict[str, bool]) -> list[str]:
    """List dependencies that are not ready, in the closed order."""
    return [name for name in DEPENDENCIES if not report.get(name, False)]
