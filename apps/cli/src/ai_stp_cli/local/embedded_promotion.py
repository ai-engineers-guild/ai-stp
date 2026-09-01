# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
"""Extract one embedded component into a local catalog version (REQ-5714, REQ-5716).

The setup definition is not rewritten. Local and Git forks stay embedded until
this explicit command records a catalog identity and the ordinary publication
plan succeeds. Setup publication never calls this module.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, content, revisions, versions
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.ids import is_valid_id, new_id
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_sources.definition import (
    decode_embedded_artifact,
    try_parse_setup_definition,
    validate_setup_definition,
)


@dataclass(frozen=True)
class MaterializedPromotion:
    """Local catalog coordinates produced from one embedded record."""

    setup_id: str
    setup_version: str
    source_component_id: str
    catalog_stable_id: str
    catalog_version: str
    reused_passport: bool
    still_embedded: bool


def materialize(
    connection: sqlite3.Connection,
    *,
    setup_id: str,
    version: str,
    component_id: str,
    device_id: str,
    at: str,
) -> MaterializedPromotion:
    """Copy one embedded passport/artifact into the local version store."""
    if not is_valid_id(component_id, "component"):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the update requires an exact component identifier, not a name",
            details={"given": component_id},
        )
    recorded = versions.held(connection, setup_id, version)
    if recorded is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the setup version points to a missing passport",
            details={"stable_id": setup_id, "version": version},
        )
    stored = revisions.get(connection, recorded.revision_id)
    if stored is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the setup version points to a missing passport",
            details={"stable_id": setup_id, "version": version},
        )
    passport = stored.envelope.model_dump(mode="json")
    artifact = passport.get("artifact")
    if not isinstance(artifact, dict) or not isinstance(artifact.get("digest"), str):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this setup version has no embedded component to promote",
            details={"stable_id": setup_id, "version": version},
        )
    definition = validate_setup_definition(content.get(connection, str(artifact["digest"])))
    record = _embedded_record(definition, component_id)
    packed = decode_embedded_artifact(str(record.get("artifact_b64") or ""))
    raw_passport = record.get("passport")
    if not isinstance(raw_passport, dict):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "an embedded component record is not complete",
        )
    document = dict(raw_passport)
    reused = _public_fields_complete(document)
    catalog_id = str(document.get("stable_id") or "") if reused else new_id("component")
    catalog_version = str(document.get("version") or "1.0") if reused else "1.0"
    if not reused:
        document["stable_id"] = catalog_id
        document["version"] = catalog_version
        document["parent_revision_ids"] = []
    document.pop("revision_id", None)
    document["revision_id"] = derive_revision_id(document)
    stored_artifact = content.put(connection, packed, at=at)
    document["artifact"] = {
        "digest": stored_artifact.digest,
        "size_bytes": stored_artifact.byte_length,
    }
    connection.execute(
        "INSERT OR IGNORE INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
        (catalog_id, at),
    )
    committed = revisions.commit(connection, document, device_id=device_id)
    versions.record(
        connection,
        stable_id=catalog_id,
        version=catalog_version,
        passport_digest=cache.digest_of(
            cast(JsonValue, committed.envelope.model_dump(mode="json"))
        ),
        revision_id=committed.revision_id,
        at=at,
    )
    remaining = embedded_component_ids(connection, str(artifact["digest"]))
    return MaterializedPromotion(
        setup_id=setup_id,
        setup_version=version,
        source_component_id=component_id,
        catalog_stable_id=catalog_id,
        catalog_version=catalog_version,
        reused_passport=reused,
        still_embedded=component_id in remaining,
    )


def embedded_component_ids(connection: sqlite3.Connection, artifact_digest: str) -> frozenset[str]:
    """Stable ids stored only in the setup definition embedded index."""
    document = try_parse_setup_definition(content.get(connection, artifact_digest))
    if document is None:
        return frozenset()
    return _embedded_ids(document)


def _embedded_ids(definition: dict[str, JsonValue]) -> frozenset[str]:
    raw = definition.get("embedded")
    if not isinstance(raw, list):
        return frozenset()
    found: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        ref = item.get("ref")
        if isinstance(ref, dict):
            stable_id = str(ref.get("stable_id") or "")
            if stable_id:
                found.add(stable_id)
    return frozenset(found)


def _embedded_record(definition: dict[str, JsonValue], component_id: str) -> dict[str, JsonValue]:
    raw = definition.get("embedded")
    if not isinstance(raw, list) or not raw:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this setup version has no embedded component to promote",
        )
    for item in raw:
        if not isinstance(item, dict):
            continue
        ref = item.get("ref")
        if isinstance(ref, dict) and str(ref.get("stable_id") or "") == component_id:
            return item
    raise CliFailure(
        "AI_STP_NOT_FOUND",
        "the named embedded component is not in this setup",
        details={"component_id": component_id},
    )


def _public_fields_complete(passport: dict[str, JsonValue]) -> bool:
    owner = str(passport.get("owner_id") or "")
    name = str(passport.get("name") or "")
    description = str(passport.get("description") or "")
    source = passport.get("source")
    license_info = passport.get("license")
    if not owner or not name or not description:
        return False
    if not isinstance(source, dict) or not source:
        return False
    if not isinstance(license_info, dict):
        return False
    if not str(license_info.get("spdx_id") or ""):
        return False
    return license_info.get("redistribution_allowed") is True
