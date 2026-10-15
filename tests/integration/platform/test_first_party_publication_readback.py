"""Real PostgreSQL/object-store oracle for the canonical first-party path."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_contracts.first_party import OWNER_ID, FirstPartyVersion
from ai_stp_contracts.first_party import family as first_party_family
from ai_stp_platform.catalog_read import public_version_row
from ai_stp_platform.models import (
    Account,
    AccountAuthorVerification,
    CatalogMetadata,
    EvidenceBinding,
    PublicationPlan,
    ValidationSnapshot,
)
from ai_stp_platform.publication_logic import execute_publish
from ai_stp_platform.settings import StorageSettings
from ai_stp_platform.storage.memory import MemoryObjectClient
from ai_stp_platform.storage.object_store import ImmutableObjectStore

pytestmark = pytest.mark.platform


async def _publish_object(
    session: AsyncSession,
    store: ImmutableObjectStore,
    item: FirstPartyVersion,
    ordinal: int,
) -> None:
    plan_id = f"plan_first_party_{ordinal:02d}_{item.passport.stable_id[-12:]}"
    now = datetime.now(UTC)
    session.add(
        PublicationPlan(
            id=plan_id,
            actor_account_id=OWNER_ID,
            device_id="device_first_party_integration",
            object_kind=item.kind,
            stable_id=item.passport.stable_id,
            version=item.passport.version,
            content_digest=item.passport.artifact.digest,
            policy_version="1",
            plan_hash=f"plan_hash_{ordinal:02d}",
            state="publish_planned",
            passport=item.passport.model_dump(mode="json"),
            attestations=[],
            effects=[],
            component_verified=True,
            idempotency_key=f"first-party-plan-{ordinal:02d}",
            expires_at=now + timedelta(hours=1),
        )
    )
    snapshot_id = f"snapshot_first_party_{ordinal:02d}"
    session.add(
        ValidationSnapshot(
            id=snapshot_id,
            plan_id=plan_id,
            content_digest=item.passport.artifact.digest,
            policy_version="1",
            state="passed",
            component_verified=True,
        )
    )
    await session.flush()
    session.add(
        EvidenceBinding(
            snapshot_id=snapshot_id,
            check_id="first_party_integration",
            result="passed",
            source="integration",
            mandatory=True,
            family="publication",
        )
    )
    await session.flush()
    await execute_publish(session, plan_id=plan_id, store=store)


@pytest.mark.asyncio
async def test_first_party_family_publishes_components_before_setup_and_reads_exact_bytes(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    objects = sorted(
        first_party_family("grok-build", "nddev-builder"), key=lambda item: item.kind != "component"
    )
    assert [item.kind for item in objects] == [
        "component",
        "component",
        "component",
        "component",
        "setup",
    ]

    settings = StorageSettings(
        endpoint="http://memory.test",
        bucket="integration",
        access_key_id="integration",
        secret_access_key="integration",
    )
    store = ImmutableObjectStore(settings=settings, client=MemoryObjectClient())
    for item in objects:
        await store.put_immutable(
            item.artifact,
            expected_digest=item.passport.artifact.digest,
            expected_size=len(item.artifact),
        )

    async with db_sessionmaker() as session:
        session.add(
            Account(
                id=OWNER_ID,
                show_profile_publicly=True,
                allow_publisher_listing=True,
                display_name="AI STP Official",
            )
        )
        session.add(AccountAuthorVerification(account_id=OWNER_ID, verified=True))
        await session.flush()
        for ordinal, item in enumerate(objects):
            await _publish_object(session, store, item, ordinal)
        await session.commit()

        rows = list(
            (
                await session.execute(
                    select(CatalogMetadata).where(
                        CatalogMetadata.stable_id.in_([item.passport.stable_id for item in objects])
                    )
                )
            )
            .scalars()
            .all()
        )

    by_identity = {(row.stable_id, row.version): row for row in rows}
    assert set(by_identity) == {
        (item.passport.stable_id, item.passport.version) for item in objects
    }
    for item in objects:
        row = by_identity[(item.passport.stable_id, item.passport.version)]
        assert row.lifecycle_state == "active"
        assert row.passport_digest == item.passport_digest
        assert row.passport_document is not None
        assert public_version_row(row).passport["stable_id"] == item.passport.stable_id
        assert (
            await store.read_by_digest(
                item.passport.artifact.digest, expected_size=len(item.artifact)
            )
            == item.artifact
        )

        if item.kind == "component":
            published_adaptations = row.passport_document["adaptations"]
            source_adaptations = item.passport.model_dump(mode="json")["adaptations"]
            assert published_adaptations == source_adaptations
        else:
            assert (
                row.passport_document["composition_report_ref"]
                == item.passport.model_dump(mode="json")["composition_report_ref"]
            )
            assert (
                row.passport_document["launch_evidence_ref"]
                == item.passport.model_dump(mode="json")["launch_evidence_ref"]
            )
