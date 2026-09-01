"""Daily enqueue of at most one official_upstream_sync job per source (SPEC-056 REQ-5602)."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.db import make_engine, make_sessionmaker
from ai_stp_platform.models import OfficialUpstreamSource
from ai_stp_platform.queue.engine import enqueue
from ai_stp_platform.queue.models import Job
from ai_stp_platform.queue.states import JobType
from ai_stp_platform.settings import DatabaseSettings


def idempotency_key(source_id: str, utc_day: str) -> str:
    return f"official-upstream-sync:{source_id}:{utc_day}"


async def enqueue_daily(session: AsyncSession, *, now: datetime | None = None) -> list[Job]:
    """Enqueue one independent job per enabled official source and this UTC day."""
    moment = now or datetime.now(UTC)
    utc_day = moment.date().isoformat()
    sources = list(
        (
            await session.scalars(
                select(OfficialUpstreamSource).where(OfficialUpstreamSource.enabled.is_(True))
            )
        ).all()
    )
    jobs: list[Job] = []
    for source in sources:
        job = await enqueue(
            session,
            job_type=JobType.OFFICIAL_UPSTREAM_SYNC,
            payload={"source_id": source.id},
            idempotency_key=idempotency_key(source.id, utc_day),
        )
        jobs.append(job)
    return jobs


async def _run() -> int:
    database = DatabaseSettings()  # pyright: ignore[reportCallIssue]
    engine = make_engine(database)
    sessionmaker = make_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            jobs = await enqueue_daily(session)
            await session.commit()
    finally:
        await engine.dispose()
    sys.stdout.write(
        json.dumps({"enqueued": len(jobs), "job_ids": [job.id for job in jobs]}) + "\n"
    )
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
