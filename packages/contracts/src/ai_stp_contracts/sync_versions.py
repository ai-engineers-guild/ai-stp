"""Exact version references embedded in private sync payloads (ADR-0173)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from pydantic import TypeAdapter

from ai_stp_contracts.http import Timestamp
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_canonical, is_digest
from ai_stp_foundation.revisions import is_valid_revision_id
from ai_stp_foundation.versioning import VersionError, parse_version
from ai_stp_passports.envelope import PassportEnvelope, verify_revision_id

MAX_VERSIONS = 128
_TIMESTAMP: TypeAdapter[str] = TypeAdapter(Timestamp)


class VersionBindingError(ValueError):
    """Version metadata cannot be linked to the declared immutable snapshot."""


@dataclass(frozen=True)
class VersionBinding:
    stable_id: str
    version: str
    major: int
    minor: int
    passport_digest: str
    revision_id: str
    created_at: str


def parse_binding(raw: Mapping[str, object], stable_id: str) -> VersionBinding:
    fields = ("version", "passport_digest", "revision_id", "created_at")
    if any(not isinstance(raw.get(key), str) or not raw[key] for key in fields):
        raise VersionBindingError("a pulled released version is incomplete")
    try:
        _TIMESTAMP.validate_python(raw["created_at"])
    except ValueError as error:
        raise VersionBindingError("a pulled released version has an invalid timestamp") from error
    number = cast(str, raw["version"])
    try:
        major, minor = parse_version(number)
    except VersionError as error:
        raise VersionBindingError("a pulled released version has an invalid number") from error
    digest = cast(str, raw["passport_digest"])
    revision = cast(str, raw["revision_id"])
    if not is_digest(digest) or not is_valid_revision_id(revision):
        raise VersionBindingError("a pulled released version has an invalid identity")
    return VersionBinding(
        stable_id, number, major, minor, digest, revision, cast(str, raw["created_at"])
    )


def verify_snapshot(raw: object, item: VersionBinding, kind: str) -> PassportEnvelope:
    if not isinstance(raw, dict):
        raise VersionBindingError("a pulled version snapshot is not an object")
    try:
        snapshot = PassportEnvelope.model_validate(raw)
    except ValueError as error:
        raise VersionBindingError("a pulled version snapshot is not a passport envelope") from error
    body = cast(dict[str, JsonValue], snapshot.model_dump(mode="json"))
    if (
        canonize(cast(JsonValue, raw)) != canonize(body)
        or not verify_revision_id(snapshot)
        or snapshot.revision_id != item.revision_id
        or snapshot.stable_id != item.stable_id
        or snapshot.kind != kind
        or snapshot.parent_revision_ids
        or ("version" in body and body["version"] != item.version)
        or digest_canonical("ai-stp:passport:v1", body) != item.passport_digest
    ):
        raise VersionBindingError(
            "a pulled version snapshot does not match its exact version identity"
        )
    return snapshot


def validate_payload(payload: Mapping[str, object], *, stable_id: str, kind: str) -> None:
    rows = payload.get("sync_released_versions", [])
    if not isinstance(rows, list):
        raise VersionBindingError("pulled released versions must be a bounded list")
    version_rows = cast(list[object], rows)
    if len(version_rows) > MAX_VERSIONS:
        raise VersionBindingError("pulled released versions must be a bounded list")
    if version_rows and kind not in {"component", "setup"}:
        raise VersionBindingError("released versions belong only to component or setup events")
    for raw in version_rows:
        if not isinstance(raw, dict):
            raise VersionBindingError("a pulled released version is not an object")
        row = cast(dict[str, object], raw)
        item = parse_binding(row, stable_id)
        if "snapshot" in row:
            verify_snapshot(row["snapshot"], item, kind)
