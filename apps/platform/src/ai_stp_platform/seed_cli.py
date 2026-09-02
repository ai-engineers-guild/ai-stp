"""One-shot catalog preparation for compose/deploy (REQ-2405, REQ-2110).

Runs after alembic upgrade and before api/web accept traffic. Idempotent:
re-runs create no duplicate catalog rows. Logs only counts, never secrets.

Two steps, and only one of them belongs everywhere. The integrity reconcile
reads what is published and checks it against the projection's own rules; that
is worth doing wherever a catalogue is served. The fixture seed writes
`fixture-component`, `river-*` and `northwind-*` into the catalogue, and those
are development scaffolding — `REQ-2110` bound the seed to its environment for
exactly this reason, back when Sprint-1 had no validation pipeline and nothing
real to publish.

That era ended. The first-party corpus is published through the ordinary
authenticated pipeline, so on a serving environment the seed adds nothing and
puts twenty-two invented objects on a public site beside the real ones.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.first_party import OWNER_ID as OFFICIAL_ACCOUNT_ID
from ai_stp_contracts.public_profile import ProfileFields, ProfileLink, content_digest
from ai_stp_platform.catalog_reconcile import reconcile_catalog_integrity
from ai_stp_platform.catalog_seed import SeedResult, load_first_party_seed
from ai_stp_platform.db import make_engine, make_sessionmaker
from ai_stp_platform.logging import configure_logging, get_logger
from ai_stp_platform.models import (
    Account,
    AccountAuthorVerification,
    ProfileRevision,
    PublicProfile,
)
from ai_stp_platform.safety.artifact_fetch import close_env_object_store, open_env_object_store
from ai_stp_platform.settings import DatabaseSettings


def configure_logging_from_env() -> None:
    """Configure structured logging to the shared log directory when set."""
    log_dir = Path(
        os.environ.get("AI_STP_API_LOG_DIR") or os.environ.get("AI_STP_WORKER_LOG_DIR") or "logs"
    )
    configure_logging(log_dir)


def fixtures_wanted() -> bool:
    """Whether this environment wants the development fixture corpus.

    Named rather than inferred. `AI_STP_API_ENVIRONMENT` already carries the
    environment's own name (`ADR-0086`), and anything that is not `dev` is a
    place where invented objects would be served to somebody. Setting
    `AI_STP_SEED_FIXTURES` overrides it in either direction, because a
    disposable environment that calls itself something else is a real case and
    guessing at it is not.
    """
    override = os.environ.get("AI_STP_SEED_FIXTURES")
    if override is not None:
        return override.strip().lower() in {"1", "true", "yes", "on"}
    return os.environ.get("AI_STP_API_ENVIRONMENT", "dev").strip().lower() == "dev"


async def ensure_official_publisher(session: AsyncSession) -> bool:
    """Idempotently bootstrap the real publisher in every environment."""
    fields = ProfileFields(
        display_name="AI STP Official",
        bio=(
            "Curated, security-checked snapshots of public open-source components. "
            "Upstream authorship and ownership remain with each named project."
        ),
        links=[ProfileLink(label="AI STP", url="https://ai-stp.com")],
    )
    revision_id = "profile_revision_ai_stp_official_v1"
    owner = await session.get(Account, OFFICIAL_ACCOUNT_ID)
    created = owner is None
    if owner is None:
        owner = Account(id=OFFICIAL_ACCOUNT_ID)
        session.add(owner)
    owner.status = "active"
    owner.show_profile_publicly = True
    owner.allow_publisher_listing = True
    if await session.get(ProfileRevision, revision_id) is None:
        session.add(
            ProfileRevision(
                id=revision_id,
                account_id=OFFICIAL_ACCOUNT_ID,
                lifecycle="published",
                display_name=fields.display_name,
                bio=fields.bio,
                links=[item.model_dump(mode="json") for item in fields.links],
                avatar_asset_id=None,
                content_digest=content_digest(fields),
            )
        )
    profile = await session.get(PublicProfile, OFFICIAL_ACCOUNT_ID)
    if profile is None:
        profile = PublicProfile(account_id=OFFICIAL_ACCOUNT_ID)
        session.add(profile)
    profile.published_revision_id = revision_id
    verification = await session.get(AccountAuthorVerification, OFFICIAL_ACCOUNT_ID)
    if verification is None:
        session.add(
            AccountAuthorVerification(
                account_id=OFFICIAL_ACCOUNT_ID,
                verified=True,
                reason="Platform-operated AI STP Official publisher",
                issued_by_account_id=OFFICIAL_ACCOUNT_ID,
            )
        )
    else:
        verification.verified = True
    await session.flush()
    return created


async def _run() -> int:
    configure_logging_from_env()
    log = get_logger("seed")
    seeding = fixtures_wanted()
    database = DatabaseSettings()  # pyright: ignore[reportCallIssue]
    engine = make_engine(database)
    sessionmaker = make_sessionmaker(engine)
    try:
        store = await open_env_object_store()
        try:
            async with sessionmaker() as session:
                official_created = await ensure_official_publisher(session)
                result = (
                    await load_first_party_seed(session, store=store)
                    if seeding
                    else SeedResult(0, 0, 0, 0)
                )
                report = await reconcile_catalog_integrity(session)
                await session.commit()
        finally:
            await close_env_object_store(store)
        log.info(
            "seed_complete",
            fixtures_seeded=seeding,
            created_accounts=result.created_accounts + int(official_created),
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
