"""Build report fixtures through the published Python CLI's real local writers."""

from __future__ import annotations

import sqlite3
from typing import Any, cast

from ai_stp_cli.local import cache, component_passports, content, revisions, versions
from ai_stp_cli.local.setup_versions import MemberRef, passport_content
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.ids import new_id

AT = "2026-10-08T00:00:00.000Z"
DEVICE = "device_test"
OWNER = "account_01ARZ3NDEKTSV4RRFFQ69G5FAV"


def release_instruction(
    connection: sqlite3.Connection,
    *,
    harness_id: str,
    payload: bytes,
    managed_path: str,
    extra_adaptations: list[dict[str, Any]] | None = None,
) -> tuple[str, str, str]:
    stored_content = content.put(connection, payload, at=AT)
    source = {
        "harness_id": harness_id,
        "content_digest": stored_content.digest,
        "content_format": "ai-stp-component-file/1",
        "managed_paths": [managed_path],
        "scope": "global",
        "projection_kind": "native_files",
        "declared_key": "",
        "source_locator": managed_path,
        "native_ids": [],
    }
    values: dict[str, Any] = {
        "name": "report-instruction",
        "description": "A complete report interoperability fixture.",
        "tags": ["quality"],
        "source": {
            "repository": "https://github.com/example/report-instruction",
            "commit": "a" * 40,
            "path": "instructions/report",
        },
        "harness_id": harness_id,
        "component_type": "instruction",
        "projection_kind": "native_files",
        "scope": "global",
        "license": {"spdx_id": "MIT", "redistribution_allowed": True},
        "content_format": "ai-stp-component-file/1",
        "content_digest": stored_content.digest,
        "byte_length": len(payload),
        "managed_paths": [managed_path],
        "native_ids": [],
        "adaptation_contents": [source, *(extra_adaptations or [])],
    }
    document: dict[str, Any] = {
        "schema_version": 1,
        "kind": "component",
        "stable_id": new_id("component"),
        "owner_id": OWNER,
        "created_at": AT,
        "visibility": "private",
        "parent_revision_ids": [],
        "facts": {
            name: {"value": value, "origin": "observed", "confirmation": "none", "observed_at": AT}
            for name, value in values.items()
        },
    }
    stored = revisions.commit(connection, document, device_id=DEVICE)
    passport, revision_id = component_passports.materialize_version_passport(
        connection, stored.stable_id, "1.0", device_id=DEVICE, at=AT
    )
    digest = cache.digest_of(cast(JsonValue, passport.model_dump(mode="json")))
    versions.record(
        connection,
        stable_id=stored.stable_id,
        version="1.0",
        passport_digest=digest,
        revision_id=revision_id,
        at=AT,
    )
    return stored.stable_id, "1.0", digest


def record_setup(
    connection: sqlite3.Connection, *, harness_id: str, member: tuple[str, str, str]
) -> tuple[str, str]:
    stable_id = new_id("setup")
    passport = passport_content(
        connection,
        stable_id=stable_id,
        version="1.0",
        owner_id=OWNER,
        project_id=new_id("project"),
        harness_id=harness_id,
        snapshot="sha256:" + "b" * 64,
        members=(MemberRef(*member),),
        at=AT,
    )
    stored = revisions.commit(connection, passport, device_id=DEVICE)
    digest = cache.digest_of(cast(JsonValue, stored.envelope.model_dump(mode="json")))
    versions.record(
        connection,
        stable_id=stable_id,
        version="1.0",
        passport_digest=digest,
        revision_id=stored.revision_id,
        at=AT,
    )
    return stable_id, digest
