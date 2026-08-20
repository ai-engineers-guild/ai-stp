"""PostgreSQL outbox behaviour for catalog writes and queue idempotency."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_platform.catalog import create_catalog_metadata_and_enqueue_upload
from ai_stp_platform.models import Account, CatalogMetadata
from ai_stp_platform.queue.engine import enqueue
from ai_stp_platform.queue.models import Job
from ai_stp_platform.queue.states import JobType, Visibility

pytestmark = pytest.mark.platform


async def _create_account(
    sessionmaker: async_sessionmaker[AsyncSession],
    account_id: str,
) -> None:
    async with sessionmaker() as session, session.begin():
        session.add(Account(id=account_id))


@pytest.mark.asyncio
async def test_catalog_write_rollback_removes_metadata_and_enqueue(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """If enqueue escapes the caller transaction, rollback leaves an orphan job."""
    account_id = "account_outbox_rollback"
    await _create_account(db_sessionmaker, account_id)

    with pytest.raises(RuntimeError, match="force rollback"):
        async with db_sessionmaker() as session:
            async with session.begin():
                await create_catalog_metadata_and_enqueue_upload(
                    session,
                    owner_account_id=account_id,
                    object_kind="component",
                    stable_id="component_outbox_rollback",
                    current_revision_id="revision_" + "a" * 64,
                    visibility=Visibility.PRIVATE,
                    idempotency_key="catalog-outbox-rollback",
                )
                raise RuntimeError("force rollback")

    async with db_sessionmaker() as session:
        metadata_count = await session.scalar(select(func.count()).select_from(CatalogMetadata))
        job_count = await session.scalar(select(func.count()).select_from(Job))

    assert metadata_count == 0
    assert job_count == 0


@pytest.mark.asyncio
async def test_enqueue_duplicate_idempotency_key_has_single_effect(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """If queue idempotency is broken, duplicate producer retries create two jobs."""
    async with db_sessionmaker() as session, session.begin():
        first = await enqueue(
            session,
            job_type=JobType.UPLOAD,
            payload={"stable_id": "component_enqueue_idempotent"},
            idempotency_key="queue-idempotent",
        )
        second = await enqueue(
            session,
            job_type=JobType.UPLOAD,
            payload={"stable_id": "component_enqueue_idempotent_retry"},
            idempotency_key="queue-idempotent",
        )

    async with db_sessionmaker() as session:
        job_count = await session.scalar(select(func.count()).select_from(Job))

    assert first.id == second.id
    assert job_count == 1
