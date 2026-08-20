"""Compatibility handler for queued github_archive jobs (SPEC-049)."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession


async def handle_github_archive(session: AsyncSession, payload: Mapping[str, object]) -> None:
    """Complete a superseded derived archive job without calling GitHub."""
    del session, payload
