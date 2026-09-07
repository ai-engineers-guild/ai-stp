"""Exact historical/current context estimates through PostgreSQL and the API."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any, cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.support.catalog_seed import seed_corpus

from ai_stp_api.app import create_app
from ai_stp_api.errors import CATEGORY_CODE, ErrorCategory
from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_contracts.context_estimator import EstimatorInput, estimate_context, estimator_for
from ai_stp_contracts.first_party import versions as canonical_versions
from ai_stp_contracts.impact import ExactCoordinate
from ai_stp_foundation.canonical import JsonValue, canonize, from_json_bytes
from ai_stp_foundation.digests import digest_bytes
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import parse_timestamp
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_passports.versions import ComponentVersionPassport
from ai_stp_platform.models import Account, CatalogMetadata, ObjectLocation
from ai_stp_platform.storage import ImmutableObjectStore, MemoryObjectClient
from ai_stp_platform.storage.object_store import ARTIFACT_DIGEST_DOMAIN
from ai_stp_sources import EmbeddedDraft, SourceSnapshot, freeze_setup_definition
from ai_stp_sources.files import files_digest

pytestmark = pytest.mark.platform
PASSPORT_DOMAIN = "ai-stp:passport:v1"


class ContextObjects(MemoryObjectClient):
    def __init__(self) -> None:
        super().__init__()
        self.reads = 0
        self.unavailable = False

    async def get_object_bytes(self, *, bucket: str, key: str) -> bytes | None:
        self.reads += 1
        if self.unavailable:
            raise ConnectionError("test storage outage")
        return await super().get_object_bytes(bucket=bucket, key=key)


@dataclass
class ContextHarness:
    client: AsyncClient
    sessions: async_sessionmaker[AsyncSession]
    store: ImmutableObjectStore
    objects: ContextObjects


@pytest_asyncio.fixture
async def context_harness(
    migrated_database_url: str, settings_factory: Callable[..., Settings]
) -> AsyncIterator[ContextHarness]:
    settings = settings_factory(database_url=migrated_database_url)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        objects = ContextObjects()
        app.state.object_client = objects
        store = ImmutableObjectStore(settings=settings.storage, client=objects)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield ContextHarness(client, app.state.sessionmaker, store, objects)


def _sealed(document: dict[str, Any]) -> dict[str, Any]:
    document["revision_id"] = derive_revision_id(cast(dict[str, JsonValue], document))
    return document


def _legacy_component(
    payload: bytes, *, component_type: str = "skill", visibility: str = "public"
) -> dict[str, Any]:
    document = dict(
        next(
            row[1]
            for row in seed_corpus()
            if row[0] == "component" and row[1]["component_type"] == component_type
        )
    )
    adaptation = document.pop("adaptations")[0]
    document.pop("origin_harness_id", None)
    document.update(
        stable_id=new_id("component"),
        harness_id=adaptation["harness_id"],
        visibility=visibility,
        artifact={
            "digest": digest_bytes(ARTIFACT_DIGEST_DOMAIN, payload),
            "size_bytes": len(payload),
        },
    )
    return _sealed(document)


async def _record(h: ContextHarness, document: dict[str, Any], payload: bytes | None) -> str:
    digest = digest_bytes(PASSPORT_DOMAIN, canonize(cast(JsonValue, document)))
    async with h.sessions() as db:
        if await db.get(Account, document["owner_id"]) is None:
            db.add(Account(id=document["owner_id"]))
            await db.flush()
        row = CatalogMetadata(
            owner_account_id=document["owner_id"],
            object_kind=document["kind"],
            stable_id=document["stable_id"],
            version=document["version"],
            current_revision_id=document["revision_id"],
            visibility=document["visibility"],
            lifecycle_state="active",
            name=document["name"],
            published_at=parse_timestamp(document["created_at"]),
            passport_document=document,
            passport_digest=digest,
            trust_lane="experimental",
            author_verified=False,
            component_verified=False,
        )
        db.add(row)
        await db.flush()
        db.add(
            ObjectLocation(
                catalog_metadata_id=row.id,
                purpose="artifact",
                object_key=h.store.key_for_digest(document["artifact"]["digest"]),
                digest=document["artifact"]["digest"],
                content_id=document["artifact"]["digest"],
                size_bytes=document["artifact"]["size_bytes"],
            )
        )
        await db.commit()
    if payload is not None:
        await h.store.put_immutable(
            payload,
            expected_digest=document["artifact"]["digest"],
            expected_size=document["artifact"]["size_bytes"],
        )
    return digest


def _url(document: dict[str, Any]) -> str:
    return (
        f"/v1/catalog/{document['kind']}s/{document['stable_id']}"
        f"/versions/{document['version']}/context-budget"
    )


@pytest.mark.asyncio
async def test_historical_component_uses_original_digest_and_the_shared_estimator(
    context_harness: ContextHarness,
) -> None:
    h = context_harness
    payload = "A small café skill with exact bytes.".encode()
    document = _legacy_component(payload)
    digest = await _record(h, document, payload)
    response = await h.client.get(_url(document))
    assert response.status_code == 200, response.text
    estimator = estimator_for("ai-stp:unicode-chars-div4/1")
    assert estimator is not None
    expected = estimate_context(
        [
            EstimatorInput(
                ExactCoordinate(
                    stable_id=document["stable_id"],
                    version=document["version"],
                    passport_digest=digest,
                ),
                "skill",
                (payload,),
            )
        ],
        estimator,
    )
    assert response.json()["tokens"] == expected.components[0].tokens
    assert response.json()["coordinate"]["passport_digest"] == digest
    assert response.json()["status"] == expected.components[0].status
    assert "A small" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["missing", "corrupt", "storage_failure"])
async def test_artifact_failures_remain_distinct_and_never_become_zero(
    context_harness: ContextHarness, state: str
) -> None:
    h = context_harness
    payload = b"Some exact instructions."
    document = _legacy_component(payload)
    await _record(h, document, None if state == "missing" else payload)
    if state == "corrupt":
        for row in h.objects.objects.values():
            row["body"] = b"corrupt"
    h.objects.unavailable = state == "storage_failure"
    response = await h.client.get(_url(document))
    if state == "storage_failure":
        assert response.json()["error"]["code"] == CATEGORY_CODE[ErrorCategory.DEPENDENCY]
    else:
        assert response.status_code == 200
        assert response.json()["status"] == "unavailable"
        assert response.json()["tokens"] is None
        assert response.json()["reason"] == (
            "artifact_unavailable" if state == "missing" else "artifact_corrupt"
        )


@pytest.mark.asyncio
async def test_private_owner_can_measure_but_outsiders_cannot_read_bytes(
    context_harness: ContextHarness,
) -> None:
    h = context_harness
    payload = b"Private instructions"
    document = _legacy_component(payload, visibility="private")
    await _record(h, document, payload)
    async with h.sessions() as db:
        owner = await issue_session(
            db, account_id=document["owner_id"], device_id=None, ttl_seconds=3600
        )
        other = Account(id=new_id("account"))
        db.add(other)
        await db.flush()
        outsider = await issue_session(db, account_id=other.id, device_id=None, ttl_seconds=3600)
        await db.commit()
    for headers in [{}, {"Authorization": f"Bearer {outsider.raw_token}"}]:
        response = await h.client.get(_url(document), headers=headers)
        assert response.status_code == 404
    assert h.objects.reads == 0
    response = await h.client.get(
        _url(document), headers={"Authorization": f"Bearer {owner.raw_token}"}
    )
    assert response.status_code == 200
    assert response.json()["tokens"] is not None


@pytest.mark.asyncio
async def test_runtime_component_needs_no_static_artifact_read(
    context_harness: ContextHarness,
) -> None:
    h = context_harness
    document = _legacy_component(b"runtime schema", component_type="mcp")
    await _record(h, document, None)
    h.objects.unavailable = True
    response = await h.client.get(_url(document))
    assert response.status_code == 200
    assert response.json()["status"] == "not_applicable"
    assert response.json()["tokens"] is None
    assert h.objects.reads == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_member", [False, True])
async def test_setup_budget_closes_over_legacy_exact_references(
    context_harness: ContextHarness, missing_member: bool
) -> None:
    h = context_harness
    payload = b"One exact skill"
    component = _legacy_component(payload)
    component_digest = await _record(h, component, None if missing_member else payload)
    setup = dict(next(row[1] for row in seed_corpus() if row[0] == "setup"))
    setup_payload = b"exact setup artifact"
    setup.update(
        stable_id=new_id("setup"),
        harness_id=component["harness_id"],
        components=[
            {
                "stable_id": component["stable_id"],
                "version": component["version"],
                "passport_digest": component_digest,
            }
        ],
        artifact={
            "digest": digest_bytes(ARTIFACT_DIGEST_DOMAIN, setup_payload),
            "size_bytes": len(setup_payload),
        },
    )
    setup = _sealed(setup)
    await _record(h, setup, setup_payload)
    response = await h.client.get(_url(setup))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == ("unavailable" if missing_member else "ready")
    assert response.json()["unavailable_components"] == int(missing_member)
    if not missing_member:
        assert response.json()["total_tokens"] == (len(payload.decode()) + 3) // 4
    else:
        assert response.json()["components"][0]["tokens"] is None


@pytest.mark.asyncio
async def test_current_projection_counts_members_instead_of_archive_metadata(
    context_harness: ContextHarness,
) -> None:
    h = context_harness
    item = next(
        item
        for item in canonical_versions()
        if isinstance(item.passport, ComponentVersionPassport)
        and item.passport.component_type == "instruction"
    )
    assert isinstance(item.passport, ComponentVersionPassport)
    document = item.passport.model_dump(mode="json")
    await _record(h, document, item.artifact)
    response = await h.client.get(
        _url(document), params={"estimator_profile": "ai-stp:utf8-bytes/1"}
    )
    assert response.status_code == 200, response.text
    scope = item.passport.adaptations[0].scope_adaptations[0]
    expected = sum(
        member.content_artifact.size_bytes
        for member in scope.members
        if member.content_artifact is not None
    )
    assert response.json()["tokens"] == expected
    assert response.json()["tokens"] != len(item.artifact)


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["none", "outer_ref", "embedded_identity"])
async def test_embedded_setup_estimate_verifies_the_exact_member_graph(
    context_harness: ContextHarness, tamper: str
) -> None:
    h = context_harness
    setup = dict(next(row[1] for row in seed_corpus() if row[0] == "setup"))
    setup["stable_id"] = new_id("setup")
    files = {"SKILL.md": b"# Embedded context\nAn exact skill.\n"}
    frozen = freeze_setup_definition(
        setup_id=setup["stable_id"],
        version=setup["version"],
        harness_id=setup["harness_id"],
        input_digest=files_digest(files),
        publisher_id=setup["owner_id"],
        created_at=setup["created_at"],
        catalog_members=(),
        catalog_ids=frozenset(),
        embedded_members=(
            EmbeddedDraft(
                snapshot=SourceSnapshot(
                    kind="path",
                    canonical_coordinate="path:skills/context",
                    exact_identity="skills/context",
                    component_digest=files_digest(files),
                    files=files,
                ),
                component_type="skill",
                name="embedded-context",
                description="Exact embedded context fixture.",
                license_spdx="MIT",
                harness_id=setup["harness_id"],
                target_scope="global",
                stable_id=new_id("component"),
                managed_paths=("skills/context/SKILL.md",),
            ),
        ),
    )
    setup["components"] = [ref.model_dump(mode="json") for ref in frozen.components]
    if tamper == "outer_ref":
        setup["components"][0]["passport_digest"] = digest_bytes(
            PASSPORT_DOMAIN, b"a different passport"
        )
    payload = frozen.payload
    if tamper == "embedded_identity":
        definition = cast(dict[str, Any], from_json_bytes(payload))
        definition["embedded"][0]["ref"]["stable_id"] = new_id("component")
        payload = canonize(cast(JsonValue, definition))
    setup["artifact"] = {
        "digest": digest_bytes(ARTIFACT_DIGEST_DOMAIN, payload),
        "size_bytes": len(payload),
    }
    setup = _sealed(setup)
    await _record(h, setup, payload)
    response = await h.client.get(_url(setup), params={"estimator_profile": "ai-stp:utf8-bytes/1"})
    if tamper != "none":
        assert response.json()["error"]["code"] == CATEGORY_CODE[ErrorCategory.VALIDATION]
    else:
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "ready"
        assert response.json()["total_tokens"] == sum(map(len, files.values()))
        assert (
            response.json()["components"][0]["component"]["stable_id"]
            == frozen.components[0].stable_id
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("pointer", ["relocated", "missing", "wrong_digest"])
async def test_context_reads_the_persisted_artifact_location(
    context_harness: ContextHarness, pointer: str
) -> None:
    h = context_harness
    payload = b"Exact instructions stored under the previous object prefix."
    document = _legacy_component(payload)
    await _record(h, document, payload)
    async with h.sessions() as db:
        location = await db.scalar(select(ObjectLocation))
        assert location is not None
        if pointer == "relocated":
            (bucket, old_key), record = next(iter(h.objects.objects.items()))
            new_key = "retained-prefix/" + old_key
            h.objects.objects[(bucket, new_key)] = h.objects.objects.pop((bucket, old_key))
            location.object_key = new_key
            assert record["body"] == payload
        elif pointer == "missing":
            await db.delete(location)
        else:
            location.digest = digest_bytes(ARTIFACT_DIGEST_DOMAIN, b"different artifact")
        await db.commit()
    response = await h.client.get(_url(document))
    assert response.status_code == 200, response.text
    if pointer == "relocated":
        assert response.json()["status"] == "estimated"
        assert response.json()["utf8_bytes"] == len(payload)
    else:
        assert response.json()["status"] == "unavailable"
        assert response.json()["reason"] == (
            "artifact_unavailable" if pointer == "missing" else "artifact_corrupt"
        )
        assert h.objects.reads == 0
