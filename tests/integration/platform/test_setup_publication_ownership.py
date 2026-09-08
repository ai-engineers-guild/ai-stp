"""Setup publication ownership survives late jobs and concurrent first writes."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.support.private_distribution import component_version, setup_version

from ai_stp_foundation.ids import new_id
from ai_stp_platform.catalog import create_catalog_metadata_and_enqueue_upload
from ai_stp_platform.identity import IdentityError
from ai_stp_platform.models import Account, CatalogMetadata, PublicationPlan
from ai_stp_platform.publication_logic import execute_publish
from ai_stp_platform.queue.states import Visibility
from ai_stp_platform.safety.policy import POLICY_VERSION

pytestmark = [pytest.mark.platform, pytest.mark.asyncio]


async def test_setup_job_rechecks_line_owner_after_plan_creation(db_session: AsyncSession) -> None:
    owner, actor, stable_id = new_id("account"), new_id("account"), new_id("setup")
    db_session.add_all([Account(id=owner), Account(id=actor)])
    await db_session.flush()
    component, _ = component_version(actor, new_id("component"), "1.0")
    passport, _ = setup_version(actor, stable_id, "1.1", component)
    artifact = passport["artifact"]
    assert isinstance(artifact, dict)
    plan = PublicationPlan(
        id=new_id("plan"),
        object_kind="setup",
        stable_id=stable_id,
        version="1.1",
        visibility="private",
        content_digest=str(artifact["digest"]),
        policy_version=POLICY_VERSION,
        state="publish_planned",
        actor_account_id=actor,
        device_id=new_id("device"),
        passport=passport,
        plan_hash=new_id("plan"),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        idempotency_key=new_id("operation"),
    )
    db_session.add(plan)
    await db_session.flush()
    existing = await create_catalog_metadata_and_enqueue_upload(
        db_session,
        owner_account_id=owner,
        object_kind="setup",
        stable_id=stable_id,
        current_revision_id=str(passport["revision_id"]),
        version="1.0",
        visibility=Visibility.PRIVATE,
        idempotency_key=new_id("operation"),
    )
    with pytest.raises(ValueError, match="catalog line is owned by another account"):
        await execute_publish(db_session, plan_id=plan.id)
    assert plan.state == "publish_planned"
    assert (await db_session.scalars(select(CatalogMetadata))).all() == [existing.metadata]
    assert existing.metadata.owner_account_id == owner


@pytest.mark.parametrize("object_kind", ["component", "setup"])
async def test_concurrent_first_catalog_versions_have_one_owner(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    object_kind: str,
) -> None:
    owners = [new_id("account"), new_id("account")]
    stable_id = new_id(object_kind)
    async with db_sessionmaker() as session, session.begin():
        session.add_all([Account(id=owner) for owner in owners])
    start = asyncio.Barrier(len(owners))

    async def write(owner: str, version: str) -> str | None:
        async with db_sessionmaker() as session:
            await start.wait()
            try:
                async with session.begin():
                    await create_catalog_metadata_and_enqueue_upload(
                        session,
                        owner_account_id=owner,
                        object_kind=object_kind,
                        stable_id=stable_id,
                        current_revision_id="revision_" + "0" * 64,
                        version=version,
                        visibility=Visibility.PRIVATE,
                        idempotency_key=new_id("operation"),
                    )
            except IdentityError as exc:
                assert exc.message == "the catalog line is owned by another account"
                return None
            return owner

    outcomes = await asyncio.gather(write(owners[0], "1.0"), write(owners[1], "1.1"))
    winners = [owner for owner in outcomes if owner is not None]
    assert len(winners) == 1
    async with db_sessionmaker() as session:
        rows = (await session.scalars(select(CatalogMetadata))).all()
        assert len(rows) == 1
        assert rows[0].owner_account_id == winners[0]
