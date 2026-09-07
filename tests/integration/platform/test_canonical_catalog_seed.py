"""Canonical seed identity, artifact closure and immutability (SPEC-021)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ai_stp_api.slices.catalog.artifact_service import read_public_artifact
from ai_stp_contracts.first_party import PASSPORT_DIGEST_DOMAIN, versions
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_bytes, digest_canonical
from ai_stp_foundation.harnesses import SUPPORT_TIERS, HarnessId
from ai_stp_passports.envelope import seal_envelope
from ai_stp_passports.versions import SetupVersionPassport
from ai_stp_platform.catalog_seed import CorpusSeedConflict, load_first_party_seed
from ai_stp_platform.models import CatalogMetadata, CatalogSearchProjection, ObjectLocation
from ai_stp_platform.settings import StorageSettings
from ai_stp_platform.storage import ImmutableObjectStore, MemoryObjectClient

pytestmark = pytest.mark.platform


def _store() -> ImmutableObjectStore:
    return ImmutableObjectStore(
        settings=StorageSettings(
            endpoint="http://127.0.0.1:9000",
            bucket="canonical-seed-test",
            access_key_id="test-access",
            secret_access_key="test-secret",
        ),
        client=MemoryObjectClient(),
    )


@pytest.mark.asyncio
async def test_canonical_seed_preserves_exact_graph_and_serves_every_artifact(
    db_session: AsyncSession,
) -> None:
    store = _store()
    corpus = versions()
    expected = {
        (item.kind, item.passport.stable_id, item.passport.version): item for item in corpus
    }
    first = await load_first_party_seed(db_session, store=store)
    rows = (await db_session.scalars(select(CatalogMetadata))).all()
    assert {(row.object_kind, row.stable_id, row.version) for row in rows} == set(expected)
    assert first.created_versions == len(expected)
    for row in rows:
        assert row.version is not None
        item = expected[(row.object_kind, row.stable_id, row.version)]
        assert row.passport_document == item.passport.model_dump(mode="json")
        assert row.passport_digest == item.passport_digest
        assert row.component_verified is False
        assert (
            await read_public_artifact(
                db_session,
                store=store,
                object_kind=item.kind,
                stable_id=item.passport.stable_id,
                version=item.passport.version,
            )
            == item.artifact
        )
    locations = (await db_session.scalars(select(ObjectLocation))).all()
    assert len(locations) == len(expected)
    second = await load_first_party_seed(db_session, store=store)
    assert second.created_versions == 0
    assert second.reused_versions == len(expected)
    assert second.artifacts_written == 0


@pytest.mark.asyncio
async def test_canonical_reseed_preserves_private_blocked_version(
    db_session: AsyncSession,
) -> None:
    store = _store()
    await load_first_party_seed(db_session, store=store)
    item = versions()[0]
    row = await db_session.scalar(
        select(CatalogMetadata).where(CatalogMetadata.stable_id == item.passport.stable_id)
    )
    assert row is not None
    row.visibility = "private"
    row.lifecycle_state = "blocked"
    row.presentation_bio = "Owner-controlled presentation"
    await db_session.flush()
    await load_first_party_seed(db_session, store=store)
    assert row.visibility == "private"
    assert row.lifecycle_state == "blocked"
    assert row.presentation_bio == "Owner-controlled presentation"


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["artifact", "passport_digest"])
async def test_canonical_seed_refuses_tampering_before_creating_rows(
    db_session: AsyncSession, tamper: str
) -> None:
    item = versions()[0]
    changed = (
        item.model_copy(update={"artifact": item.artifact + b"changed"})
        if tamper == "artifact"
        else item.model_copy(
            update={"passport_digest": digest_bytes(PASSPORT_DIGEST_DOMAIN, b"changed")}
        )
    )
    before = await db_session.scalar(select(func.count()).select_from(CatalogMetadata))
    with pytest.raises(CorpusSeedConflict):
        await load_first_party_seed(db_session, store=_store(), objects=(changed,))
    assert await db_session.scalar(select(func.count()).select_from(CatalogMetadata)) == before


@pytest.mark.asyncio
async def test_canonical_seed_without_storage_creates_no_placeholder_metadata(
    db_session: AsyncSession,
) -> None:
    before = await db_session.scalar(select(func.count()).select_from(CatalogMetadata))
    with pytest.raises(CorpusSeedConflict):
        await load_first_party_seed(db_session, store=None)
    assert await db_session.scalar(select(func.count()).select_from(CatalogMetadata)) == before


@pytest.mark.asyncio
async def test_canonical_seed_keeps_setup_lineage(db_session: AsyncSession) -> None:
    corpus = versions()
    target, source = [item for item in corpus if item.kind == "setup"][:2]
    origin = {
        "stable_id": source.passport.stable_id,
        "version": source.passport.version,
        "passport_digest": source.passport_digest,
    }
    body = target.passport.model_dump(mode="json")
    body.update(ported_from=origin, related_setup_ids=[source.passport.stable_id])
    passport = SetupVersionPassport.model_validate(seal_envelope(body).model_dump(mode="json"))
    changed = target.model_copy(
        update={
            "passport": passport,
            "passport_digest": digest_canonical(
                PASSPORT_DIGEST_DOMAIN, cast(JsonValue, passport.model_dump(mode="json"))
            ),
        }
    )
    await load_first_party_seed(
        db_session,
        store=_store(),
        objects=tuple(changed if item is target else item for item in corpus),
    )
    stored = await db_session.scalar(
        select(CatalogMetadata).where(CatalogMetadata.stable_id == passport.stable_id)
    )
    assert stored is not None and stored.passport_document is not None
    assert stored.passport_document["ported_from"] == origin
    assert stored.passport_document["related_setup_ids"] == [source.passport.stable_id]


@pytest.mark.asyncio
async def test_production_bootstrap_rebuilds_existing_catalog_without_development_seeding(
    migrated_database_url: str, tmp_path: Path
) -> None:
    """A new search table must not make already-published objects disappear."""
    engine = create_async_engine(migrated_database_url)
    try:
        sessions = async_sessionmaker(engine)
        async with sessions() as session:
            await load_first_party_seed(session, store=_store())
            expected = set((await session.scalars(select(CatalogMetadata.stable_id))).all())
            await session.execute(delete(CatalogSearchProjection))
            await session.commit()
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("AI_STP_STORAGE_") and key != "AI_STP_SEED_FIXTURES"
        }
        env.update(
            AI_STP_DB_URL=migrated_database_url,
            AI_STP_API_ENVIRONMENT="prod",
            AI_STP_API_LOG_DIR=str(tmp_path / "logs"),
        )
        result = subprocess.run(
            [sys.executable, "-m", "ai_stp_platform.seed_cli"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        async with sessions() as session:
            rows = (await session.scalars(select(CatalogSearchProjection))).all()
            assert {row.stable_id for row in rows} == expected
            for row in rows:
                assert row.harness_ids
                assert {SUPPORT_TIERS[cast(HarnessId, harness)] for harness in row.harness_ids} == {
                    row.support_tier
                }
            assert set((await session.scalars(select(CatalogMetadata.stable_id))).all()) == expected
    finally:
        await engine.dispose()
