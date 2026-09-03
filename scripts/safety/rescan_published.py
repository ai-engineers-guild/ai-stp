#!/usr/bin/env python3
"""Re-run the safety suite on a published catalog version and replace checks_summary.

Does not bump X.Y. Does not rewrite passport bytes. Operator-only: run inside
the worker-safety image so scanner CLIs are on PATH.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from sqlalchemy import delete, select

from ai_stp_platform.db import make_engine, make_sessionmaker
from ai_stp_platform.models import CatalogMetadata, ObjectLocation, SafetyScanRun
from ai_stp_platform.publication_logic import _persist_safety_run
from ai_stp_platform.safety.artifact_fetch import close_env_object_store, open_env_object_store
from ai_stp_platform.safety.orchestrator import clear_safety_cache, run_safety_suite
from ai_stp_platform.safety.percent import build_checks_summary
from ai_stp_platform.safety.policy import POLICY_VERSION
from ai_stp_platform.settings import DatabaseSettings

KEEP_SOURCES = frozenset(
    {"platform_structure_verified", "platform_digest_verified", "author_attested"}
)


def _public_outcomes(bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in bindings:
        item: dict[str, Any] = {
            "check_id": row.get("check_id"),
            "result": row.get("result"),
            "mandatory": bool(row.get("mandatory", True)),
            "source": row.get("source"),
        }
        summary = row.get("finding_summary")
        if isinstance(summary, dict):
            item["findings"] = summary.get("count")
            item["paths"] = summary.get("paths")
            item["rules"] = summary.get("rule_ids")
        rows.append(item)
    return rows


async def rescan(*, stable_id: str, version: str) -> dict[str, Any]:
    database = DatabaseSettings()  # pyright: ignore[reportCallIssue]
    engine = make_engine(database)
    sessionmaker = make_sessionmaker(engine)
    store = await open_env_object_store()
    if store is None:
        raise RuntimeError("object store is unavailable")
    try:
        async with sessionmaker() as session:
            row = await session.scalar(
                select(CatalogMetadata).where(
                    CatalogMetadata.stable_id == stable_id,
                    CatalogMetadata.version == version,
                )
            )
            if row is None:
                raise RuntimeError(f"catalog row missing: {stable_id}@{version}")
            location = await session.scalar(
                select(ObjectLocation).where(
                    ObjectLocation.catalog_metadata_id == row.id,
                    ObjectLocation.purpose == "artifact",
                )
            )
            if location is None:
                raise RuntimeError("artifact location missing")
            digest = location.digest
            size = location.size_bytes
            passport = dict(row.passport_document or {})
            previous = dict(row.checks_summary or {})
            kept = [
                item
                for item in list(previous.get("checks") or [])
                if isinstance(item, dict) and str(item.get("source") or "") in KEEP_SOURCES
            ]
            await session.execute(
                delete(SafetyScanRun).where(
                    SafetyScanRun.content_digest == digest,
                    SafetyScanRun.policy_version == POLICY_VERSION,
                )
            )
            await session.commit()
            metadata_id = row.id

        payload = await store.read_by_digest(digest, expected_size=int(size))
        if payload is None:
            raise RuntimeError(f"artifact missing for {digest}")

        clear_safety_cache()
        safety = await run_safety_suite(
            passport=passport,
            content_digest=digest,
            policy_version=POLICY_VERSION,
            object_kind="component",
            artifact_bytes=payload,
            use_cache=False,
        )
        merged = kept + safety.bindings()
        summary = build_checks_summary(merged)

        async with sessionmaker() as session:
            row = await session.get(CatalogMetadata, metadata_id)
            if row is None:
                raise RuntimeError("catalog row disappeared")
            row.checks_summary = summary
            await _persist_safety_run(session, safety)
            await session.commit()

        return {
            "stable_id": stable_id,
            "version": version,
            "digest": digest,
            "policy_version": POLICY_VERSION,
            "wall_ms": safety.wall_ms,
            "status": summary["status"],
            "passed": summary["passed"],
            "failed": summary["failed"],
            "warning": summary["warning"],
            "not_run": summary["not_run"],
            "percent": summary["checks_passed_percent"],
            "checks": _public_outcomes(merged),
        }
    finally:
        await close_env_object_store(store)
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stable-id", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    try:
        result = asyncio.run(rescan(stable_id=args.stable_id, version=args.version))
    except Exception as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        return 1
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
