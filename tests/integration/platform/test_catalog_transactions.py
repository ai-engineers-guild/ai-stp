"""Catalog metadata, queue atomicity and fixture idempotency against PostgreSQL."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.support.catalog_seed import (
    SEED_ACCOUNT_IDS,
    load_fixture_seed,
    seed_corpus,
    upsert_seed_version,
)

from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_platform.catalog import create_catalog_metadata_and_enqueue_upload
from ai_stp_platform.models import Account, CatalogMetadata, ComponentMedia
from ai_stp_platform.queue.models import Job
from ai_stp_platform.queue.states import JobType, Visibility

pytestmark = [pytest.mark.platform, pytest.mark.asyncio]


async def test_catalog_write_and_upload_job_commit_or_rollback_together(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    owner = new_id("account")
    async with db_sessionmaker() as session, session.begin():
        session.add(Account(id=owner))
    for commit in (False, True):
        stable_id = new_id("component")
        async with db_sessionmaker() as session:
            result = await create_catalog_metadata_and_enqueue_upload(
                session,
                owner_account_id=owner,
                object_kind="component",
                stable_id=stable_id,
                current_revision_id="revision_" + "a" * 64,
                visibility=Visibility.PRIVATE,
                idempotency_key=new_id("operation"),
            )
            row_id, job_id = result.metadata.id, result.job.id
            assert result.job.job_type == JobType.UPLOAD
            assert result.job.payload == {
                "catalog_metadata_id": row_id,
                "stable_id": stable_id,
                "visibility": str(Visibility.PRIVATE),
            }
            if commit:
                await session.commit()
            else:
                await session.rollback()
        async with db_sessionmaker() as reader:
            assert (await reader.get(CatalogMetadata, row_id) is not None) is commit
            assert (await reader.get(Job, job_id) is not None) is commit


async def test_fixture_seed_reuses_versions_and_media_on_repeat(db_session: AsyncSession) -> None:
    first = await load_fixture_seed(db_session)
    second = await load_fixture_seed(db_session)
    assert first.created_accounts == len(SEED_ACCOUNT_IDS)
    assert first.created_versions == len(seed_corpus())
    assert second.created_accounts == second.created_versions == 0
    assert second.reused_versions == first.created_versions
    assert await db_session.scalar(select(func.count()).select_from(Account)) == len(
        SEED_ACCOUNT_IDS
    )
    assert await db_session.scalar(select(func.count()).select_from(CatalogMetadata)) == len(
        seed_corpus()
    )
    media = (await db_session.scalars(select(ComponentMedia))).all()
    assert len(media) == 1
    assert media[0].position == 0 and media[0].state == "ready"


async def test_fixture_setup_upsert_preserves_exact_lineage(db_session: AsyncSession) -> None:
    await load_fixture_seed(db_session)
    original = next(passport for kind, passport, *_ in seed_corpus() if kind == "setup")
    origin = {
        "stable_id": original["stable_id"],
        "version": original["version"],
        "passport_digest": digest_canonical("ai-stp:passport:v1", original),
    }
    passport = dict(original)
    passport.update(
        stable_id=new_id("setup"), ported_from=origin, related_setup_ids=[original["stable_id"]]
    )
    passport["revision_id"] = derive_revision_id(passport)
    row, created = await upsert_seed_version(
        db_session,
        object_kind="setup",
        passport=passport,
        published_at_wire=str(passport["created_at"]),
        passport_digest=digest_canonical("ai-stp:passport:v1", passport),
    )
    assert created
    assert row.passport_document is not None
    assert row.passport_document["ported_from"] == origin
    assert row.passport_document["related_setup_ids"] == [original["stable_id"]]
