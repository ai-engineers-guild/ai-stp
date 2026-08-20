"""One-shot first-party catalog seed for compose/deploy (REQ-2405, REQ-2110).

Runs after alembic upgrade and before api/web accept traffic. Idempotent:
re-runs create no duplicate catalog rows. Logs only counts, never secrets.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from ai_stp_platform.catalog_reconcile import reconcile_catalog_integrity
from ai_stp_platform.catalog_seed import load_first_party_seed
from ai_stp_platform.db import make_engine, make_sessionmaker
from ai_stp_platform.logging import configure_logging, get_logger
from ai_stp_platform.safety.artifact_fetch import close_env_object_store, open_env_object_store
from ai_stp_platform.settings import DatabaseSettings


def configure_logging_from_env() -> None:
    """Configure structured logging to the shared log directory when set."""
    log_dir = Path(
        os.environ.get("AI_STP_API_LOG_DIR") or os.environ.get("AI_STP_WORKER_LOG_DIR") or "logs"
    )
    configure_logging(log_dir)


async def _run() -> int:
    configure_logging_from_env()
    log = get_logger("seed")
    database = DatabaseSettings()  # pyright: ignore[reportCallIssue]
    engine = make_engine(database)
    sessionmaker = make_sessionmaker(engine)
    try:
        store = await open_env_object_store()
        try:
            async with sessionmaker() as session:
                result = await load_first_party_seed(session, store=store)
                report = await reconcile_catalog_integrity(session)
                await session.commit()
        finally:
            await close_env_object_store(store)
        log.info(
            "seed_complete",
            created_accounts=result.created_accounts,
            created_versions=result.created_versions,
            reused_versions=result.reused_versions,
            artifacts_written=result.artifacts_written,
            catalog_checked=report.checked,
            catalog_unreadable=len(report.unreadable),
        )
        return 0
    except Exception:
        log.exception("seed_failed")
        return 1
    finally:
        await engine.dispose()


def main() -> None:
    """CLI entry for ``python -m ai_stp_platform.seed_cli``."""
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
