"""Real artifact bytes behind the fixture setup, so a native consumer can acquire it."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.catalog_seed import FIXTURE_COMPONENT_ID, FIXTURE_SETUP_ID
from tests.support.component_passports import adaptation_fields

from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_bytes, digest_canonical
from ai_stp_foundation.refs import ComponentRef
from ai_stp_passports import ComponentVersionPassport, ScopeAdaptation, seal_adaptation
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_passports.projections import build_projection
from ai_stp_platform.catalog_search import upsert_catalog_search_projection
from ai_stp_platform.models import CatalogIdentity, CatalogMetadata, ObjectLocation
from ai_stp_platform.storage import ImmutableObjectStore
from ai_stp_sources import freeze_setup_definition

ARTIFACT_DOMAIN = "ai-stp:artifact:v1"
PASSPORT_DOMAIN = "ai-stp:passport:v1"
SURFACES = Path(__file__).resolve().parents[2] / "apps/cli/src/projection/surfaces.json"


def native_surface(harness: str, scope: str) -> dict[str, Any]:
    """The configuration surface the native engine projects `harness` at `scope` through."""
    catalog = json.loads(SURFACES.read_bytes())
    return next(
        item["profile"]
        for item in catalog["profiles"]
        if item["harness_id"] == harness and item["target_scope"] == scope
    )


def projection(harness: str, scope: str = "global") -> tuple[dict[str, JsonValue], bytes]:
    body = f"---\nname: demo\ndescription: Inspect a project.\n---\n# {harness} skill\n".encode()
    fields = adaptation_fields(
        digest=digest_bytes(ARTIFACT_DOMAIN, body), size=len(body), harness_id=harness, scope=scope
    )
    adaptation = cast(list[dict[str, JsonValue]], fields["adaptations"])[0]
    raw = cast(list[dict[str, Any]], adaptation["scope_adaptations"])[0]
    if scope != "global":
        # The engine admits a project projection only through its own surface.
        surface = native_surface(harness, scope)
        raw["required_surface"] = {
            "profile_id": surface["profile_id"],
            "profile_digest": surface["digest"],
            "bundle_format": "ai-stp-bundle/2",
        }
        skills = next(name for name in surface["native_namespaces"] if name.endswith("skills"))
        raw["members"][0]["path"] = f"{skills}/demo/SKILL.md"
    adapted = ScopeAdaptation.model_validate(raw)
    payload = build_projection(adapted, {adapted.members[0].path: body})
    raw = adapted.model_dump(mode="json")
    raw["projection_artifact"] = {
        "digest": digest_bytes(ARTIFACT_DOMAIN, payload),
        "size_bytes": len(payload),
    }
    adaptation["scope_adaptations"] = [raw]
    return seal_adaptation(adaptation).model_dump(mode="json"), payload


@dataclass(frozen=True)
class StoredFixture:
    component: CatalogMetadata
    component_document: dict[str, Any]
    stored: list[Any]
    setup_bytes: Any


async def store_fixture_artifacts(
    db: AsyncSession, store: ImmutableObjectStore, *, harness: str, scope: str = "global"
) -> StoredFixture:
    """Store Claude Code and Codex skill projections and a setup for `harness`.

    The `harness` projection targets `scope`; the other stays global.

    The fixture component 1.2 and setup 1.0 passports are resealed around the
    stored bytes; storage stays bound to each passport's original publisher.
    """
    harnesses = [harness] + [name for name in ("claude-code", "codex") if name != harness]
    component = await _row(db, FIXTURE_COMPONENT_ID, "1.2")
    setup = await _row(db, FIXTURE_SETUP_ID, "1.0")
    return await _reseal(db, store, component, setup, harness, harnesses, scope)


async def _row(db: AsyncSession, stable_id: str, version: str) -> CatalogMetadata:
    return (
        await db.scalars(
            select(CatalogMetadata).where(
                CatalogMetadata.stable_id == stable_id, CatalogMetadata.version == version
            )
        )
    ).one()


async def _clone(db: AsyncSession, source: CatalogMetadata, stable_id: str) -> CatalogMetadata:
    """A new catalog line with the source row's publication, under `stable_id`."""
    columns = {
        column.key: getattr(source, column.key)
        for column in CatalogMetadata.__table__.columns
        if column.key != "id"
    }
    document = dict(source.passport_document or {})
    document["stable_id"] = stable_id
    row = CatalogMetadata(**{**columns, "stable_id": stable_id, "passport_document": document})
    db.add(row)
    name = "native-" + stable_id.replace("_", "-").lower()
    db.add(
        CatalogIdentity(
            stable_id=stable_id,
            owner_account_id=source.owner_account_id,
            canonical_name=name,
            canonical_name_normalized=name,
        )
    )
    await db.flush()
    return row


async def store_harness_setup(
    db: AsyncSession, store: ImmutableObjectStore, *, harness: str, index: int
) -> StoredFixture:
    """A separate component and setup line projecting one skill to `harness` at project scope.

    Each harness gets its own stable ids, so one checkout can hold the setups of
    every harness at once without one resealed line replacing another.
    """
    suffix = f"01JQZK7B8N4M6P2R9T5V0X{index:04d}"
    component = await _clone(db, await _row(db, FIXTURE_COMPONENT_ID, "1.2"), f"component_{suffix}")
    setup = await _clone(db, await _row(db, FIXTURE_SETUP_ID, "1.0"), f"setup_{suffix}")
    stored = await _reseal(db, store, component, setup, harness, [harness], "project")
    for row in (component, setup):
        await upsert_catalog_search_projection(
            db, object_kind=row.object_kind, stable_id=row.stable_id
        )
    return stored


async def _reseal(
    db: AsyncSession,
    store: ImmutableObjectStore,
    component: CatalogMetadata,
    setup: CatalogMetadata,
    harness: str,
    harnesses: list[str],
    scope: str,
) -> StoredFixture:
    """Reseal `component` around real skill projections and `setup` around it."""
    adaptations, payloads = zip(
        *(projection(name, scope if name == harness else "global") for name in harnesses),
        strict=True,
    )
    document: dict[str, Any] = dict(component.passport_document or {})
    document["adaptations"] = list(adaptations)
    document["artifact"] = {
        "digest": digest_bytes(ARTIFACT_DOMAIN, payloads[0]),
        "size_bytes": len(payloads[0]),
    }
    document = ComponentVersionPassport.model_validate(document).model_dump(mode="json")
    document["revision_id"] = derive_revision_id(document)
    component.passport_document = document
    component.current_revision_id = document["revision_id"]
    component.passport_digest = digest_canonical(PASSPORT_DOMAIN, document)
    stored = [
        await store.put_immutable(
            payload,
            expected_digest=digest_bytes(ARTIFACT_DOMAIN, payload),
            expected_size=len(payload),
            owner_account_id=str(document["owner_id"]),
        )
        for payload in payloads
    ]
    setup_document: dict[str, Any] = dict(setup.passport_document or {})
    reference = ComponentRef(
        stable_id=component.stable_id,
        version=str(component.version),
        passport_digest=component.passport_digest,
    )
    definition = freeze_setup_definition(
        setup_id=setup.stable_id,
        version=str(setup.version),
        harness_id=harness,
        input_digest="sha256:" + "0" * 64,
        publisher_id=str(setup_document["owner_id"]),
        created_at=document["created_at"],
        catalog_members=(reference,),
        embedded_members=(),
    )
    setup_bytes = await store.put_immutable(
        definition.payload,
        expected_digest=digest_bytes(ARTIFACT_DOMAIN, definition.payload),
        expected_size=len(definition.payload),
        owner_account_id=str(setup_document["owner_id"]),
    )
    setup_document.update(
        harness_id=harness,
        # No exact harness release or platform is declared: the consumer runs no
        # vendor, on every native CI platform.
        supported_harness_versions=[],
        supported_os=[],
        supported_arch=[],
        artifact_format=definition.format,
        components=[
            {
                "stable_id": component.stable_id,
                "version": component.version,
                "passport_digest": component.passport_digest,
            }
        ],
        artifact={"digest": setup_bytes.digest, "size_bytes": setup_bytes.size_bytes},
    )
    setup_document["revision_id"] = derive_revision_id(setup_document)
    setup.passport_document = setup_document
    setup.current_revision_id = setup_document["revision_id"]
    setup.passport_digest = digest_canonical(PASSPORT_DOMAIN, setup_document)
    for row, artifact, publisher in (
        (component, stored[0], document["owner_id"]),
        (setup, setup_bytes, setup_document["owner_id"]),
    ):
        db.add(
            ObjectLocation(
                catalog_metadata_id=row.id,
                purpose="artifact",
                owner_account_id=str(publisher),
                bucket=artifact.bucket,
                object_key=artifact.key,
                digest=artifact.digest,
                content_id=artifact.content_id,
                size_bytes=artifact.size_bytes,
            )
        )
    return StoredFixture(component, document, stored, setup_bytes)
