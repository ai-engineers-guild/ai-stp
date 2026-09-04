"""Enqueue official_upstream_sync jobs (SPEC-056 REQ-5602)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.db import make_engine, make_sessionmaker
from ai_stp_platform.models import AuditEvent, OfficialUpstreamSource
from ai_stp_platform.official_upstream import OFFICIAL_ACCOUNT_ID
from ai_stp_platform.official_upstream.errors import INVALID_SOURCE, OfficialUpstreamError
from ai_stp_platform.official_upstream.ledger import (
    create_attempt_and_outbox,
    dispatch_outbox,
    source_is_schedulable,
)
from ai_stp_platform.queue.models import Job
from ai_stp_platform.settings import DatabaseSettings


def idempotency_key(source_id: str, utc_day: str) -> str:
    return f"official-upstream-sync:{source_id}:{utc_day}"


def manual_idempotency_key(source_id: str, moment: datetime) -> str:
    stamp = moment.strftime("%Y%m%dT%H%M%S%f")
    return f"official-upstream-sync:{source_id}:manual:{stamp}"


async def _enabled_sources(
    session: AsyncSession, source_id: str | None
) -> list[OfficialUpstreamSource]:
    if source_id is None:
        return [
            source
            for source in (await session.scalars(select(OfficialUpstreamSource))).all()
            if source_is_schedulable(source)
        ]
    source = await session.get(OfficialUpstreamSource, source_id)
    if source is None:
        raise OfficialUpstreamError(INVALID_SOURCE, "source is missing")
    if not source_is_schedulable(source):
        raise OfficialUpstreamError(INVALID_SOURCE, "source is disabled")
    return [source]


async def enqueue_daily(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    source_id: str | None = None,
    force: bool = False,
) -> list[Job]:
    """Enqueue sync jobs. The scheduler path is one job per source and UTC day."""
    moment = now or datetime.now(UTC)
    utc_day = moment.date().isoformat()
    jobs: list[Job] = []
    for source in await _enabled_sources(session, source_id):
        trigger = f"manual:{moment.strftime('%Y%m%dT%H%M%S%f')}" if force else utc_day
        _attempt, outbox = await create_attempt_and_outbox(
            session,
            source,
            trigger_key=trigger,
            utc_day=moment,
            provenance="manual" if force else "daily",
        )
        job = await dispatch_outbox(session, outbox)
        if force:
            session.add(
                AuditEvent(
                    actor_account_id=OFFICIAL_ACCOUNT_ID,
                    action="official_upstream.sync_enqueued",
                    target_table="official_upstream_source",
                    target_id=source.id,
                    payload={
                        "job_id": job.id,
                        "force": True,
                        "utc_day": utc_day,
                        "attempt_id": _attempt.id,
                    },
                )
            )
        jobs.append(job)
    return jobs


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Enqueue official upstream sync jobs in PostgreSQL. No HTTP endpoint."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Enqueue a new audited job even if today's scheduler job already exists.",
    )
    parser.add_argument(
        "--id",
        dest="source_id",
        help="Enqueue one enabled source. Omit to enqueue every enabled source.",
    )
    return parser


async def _execute(force: bool, source_id: str | None) -> dict[str, object]:
    database = DatabaseSettings()  # pyright: ignore[reportCallIssue]
    engine = make_engine(database)
    sessionmaker = make_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            jobs = await enqueue_daily(session, force=force, source_id=source_id)
            await session.commit()
    finally:
        await engine.dispose()
    return {
        "enqueued": len(jobs),
        "force": force,
        "job_ids": [job.id for job in jobs],
        "source_ids": [job.payload["source_id"] for job in jobs],
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    source_id = None if args.source_id is None else str(args.source_id)
    try:
        result = asyncio.run(_execute(force=bool(args.force), source_id=source_id))
    except OfficialUpstreamError as error:
        sys.stderr.write(f"{error.code}: {error.message}\n")
        return 1
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
