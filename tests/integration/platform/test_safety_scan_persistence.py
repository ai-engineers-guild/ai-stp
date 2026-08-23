"""PostgreSQL concurrency evidence for durable safety scan identity."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_platform.models import SafetyScanRun
from ai_stp_platform.publication_logic import (
    _persist_safety_run,  # pyright: ignore[reportPrivateUsage]
)
from ai_stp_platform.safety.types import SafetyScanResult

pytestmark = pytest.mark.platform


@pytest.mark.asyncio
async def test_concurrent_workers_share_one_durable_scan(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    safety = SafetyScanResult(
        content_digest=f"sha256:{'a' * 64}",
        policy_version="safety-race-test",
        profile="standard",
        object_kind="component",
        outcomes=[],
        wall_ms=1,
    )

    async def persist() -> str:
        async with db_sessionmaker() as session, session.begin():
            run = await _persist_safety_run(session, safety)
            assert run is not None
            return run.id

    ids = await asyncio.gather(persist(), persist())
    assert ids[0] == ids[1]
    async with db_sessionmaker() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(SafetyScanRun)
            .where(SafetyScanRun.policy_version == "safety-race-test")
        )
    assert count == 1
