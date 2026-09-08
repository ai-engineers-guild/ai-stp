"""ASGI evidence for verified artifact delivery (issue #212)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any, cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.api.platform.conftest import make_settings
from tests.support.catalog_seed import (
    FIXTURE_COMPONENT_ID,
    FIXTURE_SETUP_ID,
    PASSPORT_DIGEST_DOMAIN,
    SEED_OWNER_ACCOUNT_ID,
    load_fixture_seed,
)

from ai_stp_api.app import create_app
from ai_stp_api.errors import CATEGORY_CODE, ErrorCategory
from ai_stp_api.session import issue_session
from ai_stp_contracts.private_access import CliPrivateVersionResponse
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_bytes, digest_canonical
from ai_stp_foundation.ids import new_id
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_platform.models import AccessGrant, Account, CatalogMetadata, ObjectLocation
from ai_stp_platform.storage import ImmutableObjectStore, MemoryObjectClient
from ai_stp_platform.storage.object_store import ARTIFACT_DIGEST_DOMAIN

pytestmark = pytest.mark.platform


@pytest_asyncio.fixture
async def artifact_harness(
    migrated_database_url: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession], MemoryObjectClient, str]]:
    settings = make_settings(
        tmp_path_factory.mktemp("catalog-artifacts"),
        database_url=migrated_database_url,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with app.state.sessionmaker() as session:
            await load_fixture_seed(session)
            payload = b"verified catalog artifact"
            digest = digest_bytes(ARTIFACT_DIGEST_DOMAIN, payload)
            store = ImmutableObjectStore(settings=settings.storage, client=app.state.object_client)
            rows = (
                (
                    await session.execute(
                        select(CatalogMetadata).where(
                            CatalogMetadata.stable_id.in_((FIXTURE_COMPONENT_ID, FIXTURE_SETUP_ID)),
                            CatalogMetadata.version.in_(("1.2", "1.0")),
                        )
                    )
                )
                .scalars()
                .all()
            )
            for row in rows:
                if (row.stable_id, row.version) not in {
                    (FIXTURE_COMPONENT_ID, "1.2"),
                    (FIXTURE_SETUP_ID, "1.0"),
                }:
                    continue
                passport = dict(row.passport_document or {})
                passport["artifact"] = {"digest": digest, "size_bytes": len(payload)}
                row.passport_document = passport
                stored = await store.put_immutable(
                    payload,
                    expected_digest=digest,
                    expected_size=len(payload),
                    owner_account_id=row.owner_account_id,
                )
                session.add(
                    ObjectLocation(
                        catalog_metadata_id=row.id,
                        purpose="artifact",
                        object_key=stored.key,
                        digest=digest,
                        content_id=stored.content_id,
                        size_bytes=len(payload),
                        bucket=stored.bucket,
                        owner_account_id=row.owner_account_id,
                    )
                )
            await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app.state.sessionmaker, app.state.object_client, payload.decode()


async def test_public_component_and_setup_artifacts_return_verified_bytes(
    artifact_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], MemoryObjectClient, str],
) -> None:
    client, _sessionmaker, _object_client, payload = artifact_harness
    paths = (
        f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}/versions/1.2/artifact",
        f"/v1/catalog/setups/{FIXTURE_SETUP_ID}/versions/1.0/artifact",
    )
    for path in paths:
        response = await client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/octet-stream"
        assert response.content == payload.encode()


async def test_corrupted_artifact_is_not_streamed_or_enumerated(
    artifact_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], MemoryObjectClient, str],
) -> None:
    client, _sessionmaker, object_client, _payload = artifact_harness
    component_key = next(iter(object_client.objects))
    object_client.objects[component_key]["body"] = b"corrupted"

    response = await client.get(
        f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}/versions/1.2/artifact"
    )

    # Nothing of the corrupt object reaches the caller, and the object key is
    # never named. That is the property this test exists for.
    assert response.headers["content-type"] != "application/octet-stream"
    assert b"corrupted" not in response.content
    body = response.json()
    assert "object_key" not in response.text

    # The version is public and reachable, so a miss would be a lie about state
    # the caller can already see in search (ADR-0079, SPEC-021 REQ-2108).
    assert response.status_code == 500
    assert body["error"]["code"] == CATEGORY_CODE[ErrorCategory.CATALOG_INTEGRITY]


async def test_private_artifact_has_the_same_not_found_surface(
    artifact_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], MemoryObjectClient, str],
) -> None:
    client, sessionmaker, _object_client, _payload = artifact_harness
    async with sessionmaker() as session:
        row = await session.scalar(
            select(CatalogMetadata).where(
                CatalogMetadata.stable_id == FIXTURE_SETUP_ID,
                CatalogMetadata.version == "1.0",
            )
        )
        assert row is not None
        row.visibility = "private"
        await session.commit()

    response = await client.get(f"/v1/catalog/setups/{FIXTURE_SETUP_ID}/versions/1.0/artifact")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == CATEGORY_CODE[ErrorCategory.NOT_FOUND]


async def test_private_artifact_owner_grantee_and_revocation_matrix(
    artifact_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], MemoryObjectClient, str],
) -> None:
    client, sessionmaker, _object_client, payload = artifact_harness
    async with sessionmaker() as session:
        row = await session.scalar(
            select(CatalogMetadata).where(
                CatalogMetadata.stable_id == FIXTURE_COMPONENT_ID,
                CatalogMetadata.version == "1.2",
            )
        )
        assert row is not None
        passport = dict(row.passport_document or {})
        passport["visibility"] = "private"
        passport["revision_id"] = derive_revision_id(cast(dict[str, JsonValue], passport))
        row.visibility = "private"
        row.passport_document = passport
        row.passport_digest = digest_canonical(
            PASSPORT_DIGEST_DOMAIN, cast(dict[str, JsonValue], passport)
        )

        grantee = Account(id=new_id("account"))
        outsider = Account(id=new_id("account"))
        foreign_owner = Account(id=new_id("account"))
        session.add_all([grantee, outsider, foreign_owner])
        await session.flush()
        owner_session = await issue_session(
            session,
            account_id=SEED_OWNER_ACCOUNT_ID,
            device_id=None,
            ttl_seconds=3600,
        )
        grantee_session = await issue_session(
            session, account_id=grantee.id, device_id=None, ttl_seconds=3600
        )
        outsider_session = await issue_session(
            session, account_id=outsider.id, device_id=None, ttl_seconds=3600
        )
        grant = AccessGrant(
            id=new_id("grant"),
            object_kind="component",
            stable_id=FIXTURE_COMPONENT_ID,
            major=1,
            owner_account_id=SEED_OWNER_ACCOUNT_ID,
            grantee_account_id=grantee.id,
            state="active",
        )
        session.add(grant)
        await session.commit()

    artifact_path = f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}/versions/1.2/artifact"
    private_path = f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}/versions/1.2/private"
    owner_headers = {"Authorization": f"Bearer {owner_session.raw_token}"}
    grantee_headers = {"Authorization": f"Bearer {grantee_session.raw_token}"}
    outsider_headers = {"Authorization": f"Bearer {outsider_session.raw_token}"}

    assert (await client.get(artifact_path)).status_code == 404
    owner_artifact = await client.get(artifact_path, headers=owner_headers)
    assert owner_artifact.status_code == 200
    assert owner_artifact.content == payload.encode()
    grantee_artifact = await client.get(artifact_path, headers=grantee_headers)
    assert grantee_artifact.status_code == 200
    assert grantee_artifact.content == payload.encode()
    assert (await client.get(artifact_path, headers=outsider_headers)).status_code == 404
    for headers in (owner_headers, grantee_headers):
        metadata_response = await client.get(private_path, headers=headers)
        assert metadata_response.status_code == 200
        metadata = CliPrivateVersionResponse.model_validate(metadata_response.json())
        assert metadata.passport["stable_id"] == FIXTURE_COMPONENT_ID
        assert metadata.passport_digest == row.passport_digest

    async with sessionmaker() as session:
        persisted = await session.get(AccessGrant, grant.id)
        assert persisted is not None
        persisted.state = "revoked"
        await session.commit()
    assert (await client.get(artifact_path, headers=grantee_headers)).status_code == 404
    assert (await client.get(private_path, headers=grantee_headers)).status_code == 404

    async with sessionmaker() as session:
        persisted = await session.get(AccessGrant, grant.id)
        assert persisted is not None
        persisted.state = "active"
        persisted.major = 2
        await session.commit()
    assert (await client.get(artifact_path, headers=grantee_headers)).status_code == 404

    async with sessionmaker() as session:
        persisted = await session.get(AccessGrant, grant.id)
        assert persisted is not None
        persisted.major = 1
        persisted.owner_account_id = foreign_owner.id
        await session.commit()
    assert (await client.get(artifact_path, headers=grantee_headers)).status_code == 404


def _unparsable_passport(_passport: dict[str, Any]) -> Any:
    return "not-an-object"


def _without_artifact_section(passport: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in passport.items() if key != "artifact"}


def _declared_mismatch(passport: dict[str, Any]) -> dict[str, Any]:
    return {**passport, "artifact": {"digest": "sha256:" + "9" * 64, "size_bytes": 1}}


@pytest.mark.parametrize(
    ("mutate", "label"),
    [
        (_unparsable_passport, "passport document is not an object"),
        (_without_artifact_section, "passport declares no artifact"),
        (_declared_mismatch, "declared artifact disagrees with the stored object"),
    ],
    ids=["unparsable-passport", "no-artifact-section", "declared-mismatch"],
)
async def test_a_reachable_version_with_broken_artifact_metadata_reports_integrity(
    artifact_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], MemoryObjectClient, str],
    mutate: Callable[[dict[str, Any]], Any],
    label: str,
) -> None:
    """Each way the passport can fail its artifact boundary is an integrity failure.

    The version stays public and reachable in search, so answering a miss would
    describe state the caller can already see (ADR-0079, SPEC-021 REQ-2108).
    """
    client, sessionmaker, _object_client, _payload = artifact_harness
    async with sessionmaker() as session:
        row = await session.scalar(
            select(CatalogMetadata).where(
                CatalogMetadata.stable_id == FIXTURE_COMPONENT_ID,
                CatalogMetadata.version == "1.2",
            )
        )
        assert row is not None
        row.passport_document = mutate(dict(row.passport_document or {}))
        await session.commit()

    response = await client.get(
        f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}/versions/1.2/artifact"
    )

    assert response.status_code == 500, label
    assert response.json()["error"]["code"] == CATEGORY_CODE[ErrorCategory.CATALOG_INTEGRITY]
    assert response.headers["content-type"] != "application/octet-stream"


async def test_a_dangling_object_reference_reports_integrity_not_absence(
    artifact_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], MemoryObjectClient, str],
) -> None:
    """Metadata promises bytes the store does not hold — a dangling reference."""
    client, _sessionmaker, object_client, _payload = artifact_harness
    component_key = next(iter(object_client.objects))
    del object_client.objects[component_key]

    response = await client.get(
        f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}/versions/1.2/artifact"
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == CATEGORY_CODE[ErrorCategory.CATALOG_INTEGRITY]


@pytest.mark.parametrize(
    ("lifecycle", "expected"),
    [("active", 200), ("deprecated", 200), ("blocked", 404), ("hidden", 404)],
)
async def test_deprecation_is_a_signal_and_the_bytes_stay_available(
    artifact_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], MemoryObjectClient, str],
    lifecycle: str,
    expected: int,
) -> None:
    """`SPEC-007` `REQ-730`: deprecating must not break an already resolved pin.

    Measured on the live catalogue before this was fixed: reading a deprecated
    version answered 200 and fetching its bytes answered 404, because
    `catalog_read.PUBLIC_LIFECYCLES` admitted `deprecated` and this query
    required `active`. Two independent decisions about what one state means,
    and neither written down.

    A published `X.Y` is immutable and consumers pin exact versions — a setup
    passport pins its components by exact digest — so refusing the bytes breaks
    every pin that already resolved. That is a far larger act than an author
    saying "do not choose this next time", and it is what `blocked` and
    `hidden` are for. Both stay refused here, which is the control: without
    them this test would pass on a filter that admitted everything.
    """
    client, sessionmaker, _object_client, _payload = artifact_harness
    async with sessionmaker() as session:
        row = await session.scalar(
            select(CatalogMetadata).where(
                CatalogMetadata.stable_id == FIXTURE_SETUP_ID,
                CatalogMetadata.version == "1.0",
            )
        )
        assert row is not None
        row.lifecycle_state = lifecycle
        await session.commit()

    response = await client.get(f"/v1/catalog/setups/{FIXTURE_SETUP_ID}/versions/1.0/artifact")
    assert response.status_code == expected, f"{lifecycle}: {response.status_code}"
