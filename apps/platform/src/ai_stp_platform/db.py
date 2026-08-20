"""Async database access for the platform layer.

Owns the declarative base, the async engine and the session factory. Contains
no business rules: functional behaviour lives in the queue engine and the
readiness probes.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from ai_stp_platform.settings import DatabaseSettings


class Base(DeclarativeBase):
    """Declarative base for every platform ORM entity."""


def make_engine(settings: DatabaseSettings) -> AsyncEngine:
    """Build the async engine from validated database settings."""
    return create_async_engine(
        settings.url,
        pool_size=settings.pool_size,
        pool_pre_ping=True,
        connect_args={"command_timeout": settings.command_timeout_seconds},
    )


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build a session factory bound to the engine."""
    return async_sessionmaker(engine, expire_on_commit=False)
