"""Real artifact bytes behind the fixture setup, so a native consumer can acquire it."""

from __future__ import annotations

from dataclasses import dataclass
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
from ai_stp_platform.models import CatalogMetadata, ObjectLocation
from ai_stp_platform.storage import ImmutableObjectStore
from ai_stp_sources import freeze_setup_definition

ARTIFACT_DOMAIN = "ai-stp:artifact:v1"
PASSPORT_DOMAIN = "ai-stp:passport:v1"


def projection(harness: str, scope: str = "global") -> tuple[dict[str, JsonValue], bytes]:
    body = f"---\nname: demo\ndescription: Inspect a project.\n---\n# {harness} skill\n".encode()
    fields = adaptation_fields(
        digest=digest_bytes(ARTIFACT_DOMAIN, body), size=len(body), harness_id=harness, scope=scope
    )
    adaptation = cast(list[dict[str, JsonValue]], fields["adaptations"])[0]
    adapted = ScopeAdaptation.model_validate(cast(list[object], adaptation["scope_adaptations"])[0])
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
    adaptations, payloads = zip(
        *(
            projection(name, scope if name == harness else "global")
            for name in ("claude-code", "codex")
        ),
        strict=True,
    )
    component = (
        await db.scalars(
            select(CatalogMetadata).where(
                CatalogMetadata.stable_id == FIXTURE_COMPONENT_ID,
                CatalogMetadata.version == "1.2",
            )
        )
    ).one()
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
    setup = (
        await db.scalars(
            select(CatalogMetadata).where(
                CatalogMetadata.stable_id == FIXTURE_SETUP_ID,
                CatalogMetadata.version == "1.0",
            )
        )
    ).one()
    setup_document: dict[str, Any] = dict(setup.passport_document or {})
    reference = ComponentRef(
        stable_id=FIXTURE_COMPONENT_ID,
        version="1.2",
        passport_digest=component.passport_digest,
    )
    definition = freeze_setup_definition(
        setup_id=FIXTURE_SETUP_ID,
        version="1.0",
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
        artifact_format=definition.format,
        components=[
            {
                "stable_id": FIXTURE_COMPONENT_ID,
                "version": "1.2",
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
