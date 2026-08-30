"""Refresh outdated SEO revisions (SPEC-053 REQ-5320)."""

from __future__ import annotations

import asyncio
import json
import sys

from ai_stp_platform.db import make_engine, make_sessionmaker
from ai_stp_platform.seo.enqueue import enqueue_refresh_for_active
from ai_stp_platform.seo.settings import load_seo_settings
from ai_stp_platform.settings import DatabaseSettings


async def _run() -> int:
    settings = load_seo_settings()
    database = DatabaseSettings()  # pyright: ignore[reportCallIssue]
    engine = make_engine(database)
    sessionmaker = make_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            builds, enrichments = await enqueue_refresh_for_active(session, settings=settings)
            await session.commit()
    finally:
        await engine.dispose()
    sys.stdout.write(json.dumps({"builds": builds, "enrichments": enrichments}) + "\n")
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
