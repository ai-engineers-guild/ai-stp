"""Operator-only local command for Official inventory (SPEC-056 REQ-5601)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence

from ai_stp_platform.db import make_engine, make_sessionmaker
from ai_stp_platform.official_upstream.enqueue import enqueue_daily
from ai_stp_platform.official_upstream.errors import OfficialUpstreamError
from ai_stp_platform.official_upstream.ledger import reconcile_delivery
from ai_stp_platform.official_upstream.manifest import (
    official_status,
    reconcile_official_manifest,
    validate_checked_in_manifest,
)
from ai_stp_platform.official_upstream.source import disable_source
from ai_stp_platform.settings import DatabaseSettings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reconcile and inspect the Git-owned Official inventory. No HTTP endpoint."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("reconcile", help="Project the checked-in manifest into PostgreSQL.")
    sub.add_parser("status", help="Read projected Official sources and the manifest digest.")
    sub.add_parser("validate", help="Validate the checked-in Official manifest without writing.")
    retry = sub.add_parser("retry", help="Enqueue an audited sync for one enabled source.")
    retry.add_argument("--id", dest="source_id", required=True)
    disable = sub.add_parser("disable", help="Stop future enqueue without deleting history.")
    disable.add_argument("--id", dest="source_id", required=True)
    sub.add_parser("reconcile-delivery", help="Repair missing Official sync handoffs.")
    return parser


async def _execute(args: argparse.Namespace) -> dict[str, object]:
    if args.command == "validate":
        manifest = validate_checked_in_manifest()
        return {
            "digest": manifest.digest(),
            "entries": len(manifest.entries),
            "schema_version": manifest.schema_version,
        }
    database = DatabaseSettings()  # pyright: ignore[reportCallIssue]
    engine = make_engine(database)
    sessionmaker = make_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            if args.command == "reconcile":
                report = await reconcile_official_manifest(session)
                await session.commit()
                return {
                    "digest": report.digest,
                    "added": report.added,
                    "changed": report.changed,
                    "disabled": report.disabled,
                    "removed": report.removed,
                    "preserved": report.preserved,
                    "unchanged": report.unchanged,
                }
            if args.command == "status":
                return await official_status(session)
            if args.command == "retry":
                jobs = await enqueue_daily(session, force=True, source_id=str(args.source_id))
                await session.commit()
                return {"enqueued": len(jobs), "job_ids": [job.id for job in jobs]}
            if args.command == "disable":
                source = await disable_source(session, str(args.source_id))
                await session.commit()
                return {"disabled": source is not None, "id": str(args.source_id)}
            repairs = await reconcile_delivery(session)
            await session.commit()
            return {"repairs": repairs}
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        result = asyncio.run(_execute(args))
    except OfficialUpstreamError as error:
        sys.stderr.write(f"{error.code}: {error.message}\n")
        return 1
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
