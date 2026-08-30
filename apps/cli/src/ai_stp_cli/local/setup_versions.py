"""Full private SetupVersion passports from one confirmed exact composition."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Final, cast

from pydantic import ValidationError

from ai_stp_cli.local import content, revisions
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_passports import ComponentVersionPassport, SetupVersionPassport, seal_envelope

DEFINITION_FORMAT: Final[str] = "ai-stp-setup-definition/1"
PRIVATE_LICENSE: Final[str] = "LicenseRef-AI-STP-Private-Composite"


@dataclass(frozen=True)
class MemberRef:
    """The exact component identity a setup freezes."""

    stable_id: str
    version: str
    passport_digest: str

    def as_json(self) -> dict[str, JsonValue]:
        return {
            "stable_id": self.stable_id,
            "version": self.version,
            "passport_digest": self.passport_digest,
        }


def passport_content(
    connection: sqlite3.Connection,
    *,
    stable_id: str,
    version: str,
    owner_id: str,
    project_id: str,
    harness_id: str,
    snapshot: str,
    members: tuple[MemberRef, ...],
    at: str,
) -> dict[str, JsonValue]:
    """Build and validate a full passport, storing its independent artifact."""
    ordered = tuple(sorted(members, key=lambda item: (item.stable_id, item.version)))
    member_documents: list[JsonValue] = [item.as_json() for item in ordered]
    definition: dict[str, JsonValue] = {
        "schema_version": 1,
        "format": DEFINITION_FORMAT,
        "stable_id": stable_id,
        "version": version,
        "harness_id": harness_id,
        "input_digest": snapshot,
        "components": member_documents,
    }
    definition_bytes = canonize(definition)
    artifact = content.put(connection, definition_bytes, at=at)
    aggregate = _aggregate(connection, ordered)
    passport: dict[str, JsonValue] = {
        "schema_version": 1,
        "kind": "setup",
        "stable_id": stable_id,
        "owner_id": owner_id,
        "created_at": at,
        "visibility": "private",
        "parent_revision_ids": [],
        "facts": {
            "harness_id": _fact(harness_id, at),
            "project_id": _fact(project_id, at),
            "members": _fact(member_documents, at),
            "snapshot": _fact(snapshot, at),
            "member_metadata_complete": _fact(aggregate.complete, at),
        },
        "name": f"{harness_id} local setup",
        "description": "Private setup frozen from an exact local selection.",
        "version": version,
        "tags": ["local-setup"],
        "source": None,
        "artifact": {"digest": artifact.digest, "size_bytes": artifact.byte_length},
        "harness_id": harness_id,
        "required_env": aggregate.required_env,
        "requires_credentials": aggregate.requires_credentials,
        "requires_authorization": aggregate.requires_authorization,
        "permissions": aggregate.permissions,
        "external_endpoints": list(aggregate.external_endpoints),
        "license": {
            "spdx_id": aggregate.license_id,
            "redistribution_allowed": aggregate.redistribution_allowed,
        },
        "compatibility_evidence_refs": [],
        "purpose": "Apply the confirmed component composition to the selected harness.",
        "target_role": "local-project",
        # A locally discovered setup has no published posture: it was read off a
        # machine, not off a `setups/<posture>/` tree.
        "posture": None,
        "supported_tasks": [],
        "components": member_documents,
        "ported_from": None,
        "related_setup_ids": [],
        "execution_profile": "full-auto",
        "supported_harness_versions": [],
        "supported_os": [],
        "supported_arch": [],
        "composition_report_ref": None,
        "conversion_report_ref": None,
        "install_evidence_ref": None,
        "launch_evidence_ref": None,
        "artifact_format": DEFINITION_FORMAT,
        "member_metadata_complete": aggregate.complete,
    }
    sealed = seal_envelope(passport)
    validated = SetupVersionPassport.model_validate(sealed.model_dump(mode="json"))
    return cast(dict[str, JsonValue], validated.model_dump(mode="json", exclude={"revision_id"}))


@dataclass(frozen=True)
class _Aggregate:
    complete: bool
    required_env: list[JsonValue]
    requires_credentials: bool
    requires_authorization: str
    permissions: dict[str, JsonValue]
    external_endpoints: tuple[str, ...]
    license_id: str
    redistribution_allowed: bool


def _aggregate(connection: sqlite3.Connection, members: tuple[MemberRef, ...]) -> _Aggregate:
    complete = True
    required: dict[str, str] = {}
    credentials = False
    authorization = "none"
    permissions: dict[str, set[str]] = {"filesystem": set(), "network": set(), "process": set()}
    endpoints: set[str] = set()
    licenses: set[str] = set()
    redistributable = True

    for member in members:
        revision = _member_revision(connection, member)
        try:
            passport = ComponentVersionPassport.model_validate(
                revision.envelope.model_dump(mode="json")
            )
        except ValidationError:
            complete = False
            continue
        for item in passport.required_env:
            required.setdefault(item.name, item.purpose)
        credentials = credentials or passport.requires_credentials
        authorization = _stronger(authorization, passport.requires_authorization)
        for category in permissions:
            permissions[category].update(getattr(passport.permissions, category))
        endpoints.update(passport.external_endpoints)
        licenses.add(passport.license.spdx_id)
        redistributable = redistributable and passport.license.redistribution_allowed

    license_id = " AND ".join(sorted(licenses)) if complete and licenses else PRIVATE_LICENSE
    required_env: list[JsonValue] = [
        {"name": name, "purpose": purpose} for name, purpose in sorted(required.items())
    ]
    permission_values: dict[str, JsonValue] = {
        name: cast(JsonValue, sorted(values)) for name, values in permissions.items()
    }
    return _Aggregate(
        complete=complete,
        required_env=required_env,
        requires_credentials=credentials,
        requires_authorization=authorization,
        permissions=permission_values,
        external_endpoints=tuple(sorted(endpoints)),
        license_id=license_id,
        redistribution_allowed=complete and redistributable,
    )


def _member_revision(connection: sqlite3.Connection, member: MemberRef) -> revisions.StoredRevision:
    from ai_stp_cli.local import versions

    recorded = versions.held(connection, member.stable_id, member.version)
    if recorded is None or recorded.passport_digest != member.passport_digest:
        raise RuntimeError("confirmed setup member no longer matches its exact version")
    revision = revisions.get(connection, recorded.revision_id)
    if revision is None:
        raise RuntimeError("confirmed setup member has no passport revision")
    return revision


def _stronger(current: str, offered: str) -> str:
    order = {"none": 0, "user_account": 1, "external_service": 2}
    return offered if order[offered] > order[current] else current


def _fact(value: JsonValue, at: str) -> JsonValue:
    return {"value": value, "origin": "derived", "confirmation": "none", "observed_at": at}
