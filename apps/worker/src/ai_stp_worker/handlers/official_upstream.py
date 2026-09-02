"""official_upstream_sync job (SPEC-056 REQ-5603 / REQ-5604)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.official_upstream.github import FetchFn
from ai_stp_platform.official_upstream.sync import run_sync
from ai_stp_platform.storage.object_store import ImmutableObjectStore


async def handle_official_upstream_sync(
    session: AsyncSession,
    payload: Mapping[str, object],
    *,
    fetch: FetchFn | None = None,
    store: ImmutableObjectStore | None = None,
    now: object = None,
) -> None:
    source_id = payload.get("source_id")
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("official_upstream_sync requires source_id")
    moment = now if isinstance(now, datetime) else None
    await run_sync(session, source_id, fetch=fetch, store=store, now=moment)
