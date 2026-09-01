"""Canonical setup-definition bytes (SPEC-057 REQ-5705, REQ-5706, REQ-5718).

Version 1 remains the catalog-only document. Version 2 adds a bounded embedded
index only when that index is non-empty.
"""

from __future__ import annotations

import base64
import io
import stat
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, cast

from pydantic import BaseModel, ConfigDict, ValidationError

from ai_stp_foundation.canonical import CanonicalizationError, JsonValue, canonize, from_json_bytes
from ai_stp_foundation.digests import digest_bytes
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.refs import ComponentRef
from ai_stp_passports import (
    ArtifactRef,
    ComponentVersionPassport,
    Conflicts,
    EnvVarRequirement,
    GitSource,
    LicenseInfo,
    Permissions,
    derive_revision_id,
    verify_revision_id,
)
from ai_stp_passports.versions import ComponentType, ProjectionKind
from ai_stp_sources.archive import MAX_ARCHIVE_BYTES, reject_secret_name
from ai_stp_sources.errors import (
    CATALOG_COLLISION,
    INCOMPLETE_PASSPORT,
    INTEGRITY_MISMATCH,
    INVALID_SOURCE,
    UNSAFE_ARCHIVE,
    SourceError,
)
from ai_stp_sources.models import SourceSnapshot
from ai_stp_sources.resolve import validate_frozen_snapshot

DEFINITION_V1: Final[str] = "ai-stp-setup-definition/1"
DEFINITION_V2: Final[str] = "ai-stp-setup-definition/2"
PASSPORT_DIGEST_DOMAIN: Final[str] = "ai-stp:passport:v1"
ARTIFACT_DIGEST_DOMAIN: Final[str] = "ai-stp:artifact:v1"
COMPONENT_TREE_FORMAT: Final[str] = "ai-stp-component-tree/1"
MAX_DEFINITION_BYTES: Final[int] = 20 * 1024 * 1024
MAX_EMBEDDED_RECORDS: Final[int] = 500
_ZIP_TIMESTAMP: Final[tuple[int, int, int, int, int, int]] = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class EmbeddedDraft:
    """Authoring input for one non-catalog component after source resolution."""

    snapshot: SourceSnapshot
    component_type: ComponentType
    name: str
    description: str
    license_spdx: str
    harness_id: str
    redistribution_allowed: bool = False
    version: str = "1.0"
    tags: tuple[str, ...] = ("embedded",)
    stable_id: str | None = None
    managed_paths: tuple[str, ...] = ()
    requires_components: tuple[ComponentRef, ...] = ()
    permissions: Permissions | None = None
    required_env: tuple[EnvVarRequirement, ...] = ()
    runtime_requirements: tuple[str, ...] = ()
    harness_ids: tuple[str, ...] = ()
    conflicts: Conflicts | None = None
    upstream_project: str | None = None
    upstream_maintainers: tuple[str, ...] = ()
    projection_kind: ProjectionKind = "native_files"


@dataclass(frozen=True)
class FrozenDefinition:
    """Canonical definition bytes plus the exact component refs they name."""

    format: str
    document: dict[str, JsonValue]
    payload: bytes
    components: tuple[ComponentRef, ...]
    identities: dict[str, str]


class _EmbeddedRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: ComponentRef
    passport: dict[str, object]
    snapshot: dict[str, object]
    artifact_b64: str
    artifact_digest: str
    artifact_size_bytes: int
    passport_digest: str
    passport_size_bytes: int


class _DefinitionDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int
    format: str
    stable_id: str
    version: str
    harness_id: str
    input_digest: str
    components: list[ComponentRef]
    embedded: list[_EmbeddedRecord] = []


def identity_key(coordinate: str, artifact_digest: str) -> str:
    """Reuse key for one frozen source coordinate and artifact digest."""
    return f"{coordinate}#{artifact_digest}"


def local_component_identity(known: dict[str, str], key: str) -> str:
    """Create or reuse one local component identity for a frozen source."""
    existing = known.get(key)
    if existing is not None:
        return existing
    minted = new_id("component")
    known[key] = minted
    return minted


def _embedded_sort_key(item: dict[str, JsonValue]) -> str:
    ref = item.get("ref")
    if not isinstance(ref, dict):
        return ""
    stable_id = ref.get("stable_id")
    return stable_id if isinstance(stable_id, str) else ""


def encode_component_ref(ref: ComponentRef) -> dict[str, JsonValue]:
    """Exact ref JSON; omit a null variant to keep version-1 catalog bytes."""
    document: dict[str, JsonValue] = {
        "stable_id": ref.stable_id,
        "version": ref.version,
        "passport_digest": ref.passport_digest,
    }
    if ref.variant_id is not None:
        document["variant_id"] = ref.variant_id
    return document


def pack_component_tree(files: Mapping[str, bytes]) -> bytes:
    """Deterministic component-tree zip; reject secret-like names."""
    ordered = sorted((path.replace("\\", "/"), content) for path, content in files.items())
    for path, _content in ordered:
        if path.startswith("/") or "\\" in path or ":" in path.split("/", 1)[0]:
            raise SourceError(INVALID_SOURCE, "embedded artifact path is absolute or unsafe")
        reject_secret_name(path)
    if sum(len(content) for _path, content in ordered) > MAX_ARCHIVE_BYTES:
        raise SourceError(UNSAFE_ARCHIVE, "embedded artifact exceeds the accepted size")
    manifest: dict[str, JsonValue] = {
        "format": COMPONENT_TREE_FORMAT,
        "files": [
            {
                "path": path,
                "digest": digest_bytes(ARTIFACT_DIGEST_DOMAIN, content),
                "byte_length": len(content),
                "mode": 0o644,
            }
            for path, content in ordered
        ],
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        members: list[tuple[str, bytes]] = [("component.json", canonize(manifest))]
        members.extend((f"files/{path}", content) for path, content in ordered)
        for name, payload in members:
            info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, payload)
    packed = output.getvalue()
    if len(packed) > MAX_ARCHIVE_BYTES:
        raise SourceError(UNSAFE_ARCHIVE, "embedded artifact exceeds the accepted size")
    return packed


def _b64url(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _unb64url(text: str) -> bytes:
    padded = text + "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise SourceError(INTEGRITY_MISMATCH, "embedded artifact is not base64url") from exc


def decode_embedded_artifact(artifact_b64: str) -> bytes:
    """Decode one bounded base64url artifact record."""
    return _unb64url(artifact_b64)


def unpack_component_tree(payload: bytes) -> dict[str, bytes]:
    """Read packed component-tree zip members; reject traversal and secrets."""
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise SourceError(UNSAFE_ARCHIVE, "embedded artifact exceeds the accepted size")
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise SourceError(UNSAFE_ARCHIVE, "embedded artifact is not a component tree") from exc
    files: dict[str, bytes] = {}
    with archive:
        names = archive.namelist()
        if "component.json" not in names:
            raise SourceError(UNSAFE_ARCHIVE, "embedded artifact is not a component tree")
        for name in names:
            if name.endswith("/") or name == "component.json":
                continue
            if not name.startswith("files/"):
                raise SourceError(UNSAFE_ARCHIVE, "embedded artifact has an unexpected member")
            relative = name.removeprefix("files/")
            if (
                not relative
                or relative.startswith("/")
                or "\\" in relative
                or ".." in relative.split("/")
            ):
                raise SourceError(UNSAFE_ARCHIVE, "embedded artifact path is absolute or unsafe")
            reject_secret_name(relative)
            files[relative] = archive.read(name)
    return files


def _passport_digest(document: Mapping[str, object]) -> str:
    return digest_bytes(PASSPORT_DIGEST_DOMAIN, canonize(cast(JsonValue, dict(document))))


def _snapshot_record(snapshot: SourceSnapshot) -> dict[str, JsonValue]:
    if snapshot.kind == "path":
        relative = snapshot.canonical_coordinate.removeprefix("path:")
        if (
            relative.startswith("/")
            or relative.startswith("\\")
            or (len(relative) >= 2 and relative[1] == ":")
        ):
            raise SourceError(INVALID_SOURCE, "local absolute paths are not accepted")
    dumped = snapshot.model_dump(mode="json", exclude={"files", "fetched_at"})
    return cast(dict[str, JsonValue], dumped)


def _git_source(snapshot: SourceSnapshot) -> dict[str, JsonValue] | None:
    if snapshot.kind != "git" or snapshot.repository_url is None or snapshot.subpath is None:
        return None
    source = GitSource(
        repository=snapshot.repository_url,
        commit=snapshot.exact_identity,
        path=snapshot.subpath,
    )
    return cast(dict[str, JsonValue], source.model_dump(mode="json"))


def _fact(value: JsonValue, *, at: str, origin: str = "derived") -> JsonValue:
    return {"value": value, "origin": origin, "confirmation": "none", "observed_at": at}


def _build_passport(
    draft: EmbeddedDraft,
    *,
    stable_id: str,
    artifact: ArtifactRef,
    publisher_id: str,
    created_at: str,
) -> dict[str, JsonValue]:
    facts: dict[str, JsonValue] = {
        "snapshot_publisher": _fact(publisher_id, at=created_at),
        "upstream_source": _fact(
            draft.snapshot.canonical_coordinate, at=created_at, origin="observed"
        ),
    }
    if draft.upstream_project is not None:
        facts["upstream_project"] = _fact(draft.upstream_project, at=created_at, origin="observed")
    if draft.upstream_maintainers:
        facts["upstream_maintainers"] = _fact(
            list(draft.upstream_maintainers), at=created_at, origin="observed"
        )
    body: dict[str, JsonValue] = {
        "schema_version": 1,
        "kind": "component",
        "stable_id": stable_id,
        "owner_id": publisher_id,
        "created_at": created_at,
        "visibility": "private",
        "parent_revision_ids": [],
        "facts": facts,
        "name": draft.name,
        "description": draft.description,
        "version": draft.version,
        "tags": list(draft.tags),
        "source": _git_source(draft.snapshot),
        "artifact": {"digest": artifact.digest, "size_bytes": artifact.size_bytes},
        "harness_id": draft.harness_id,
        "required_env": [item.model_dump(mode="json") for item in draft.required_env],
        "requires_credentials": False,
        "requires_authorization": "none",
        "permissions": (draft.permissions or Permissions()).model_dump(mode="json"),
        "external_endpoints": [],
        "license": LicenseInfo(
            spdx_id=draft.license_spdx,
            redistribution_allowed=draft.redistribution_allowed,
        ).model_dump(mode="json"),
        "compatibility_evidence_refs": [],
        "runtime_requirements": list(draft.runtime_requirements),
        "component_type": draft.component_type,
        "projection_kind": draft.projection_kind,
        "variant_id": None,
        "provides_capabilities": [],
        "requires_components": [encode_component_ref(item) for item in draft.requires_components],
        "requires_capabilities": [],
        "conflicts": (draft.conflicts or Conflicts()).model_dump(mode="json"),
        "managed_paths": list(draft.managed_paths),
        "native_ids": [],
        "harness_ids": list(draft.harness_ids),
        "artifact_format": COMPONENT_TREE_FORMAT,
    }
    try:
        candidate = dict(body)
        candidate["revision_id"] = derive_revision_id(candidate)
        passport = ComponentVersionPassport.model_validate(candidate)
        dumped = cast(dict[str, JsonValue], passport.model_dump(mode="json"))
        dumped["revision_id"] = derive_revision_id(dumped)
        passport = ComponentVersionPassport.model_validate(dumped)
    except (ValidationError, ValueError) as exc:
        raise SourceError(INCOMPLETE_PASSPORT, "embedded passport is incomplete") from exc
    if not verify_revision_id(passport):
        raise SourceError(INCOMPLETE_PASSPORT, "embedded passport revision is not canonical")
    if "reactions" in dumped or "publisher_page" in dumped or "catalog" in dumped:
        raise SourceError(INCOMPLETE_PASSPORT, "embedded passport must not carry catalog metadata")
    return dumped


def freeze_setup_definition(
    *,
    setup_id: str,
    version: str,
    harness_id: str,
    input_digest: str,
    publisher_id: str,
    created_at: str,
    catalog_members: tuple[ComponentRef, ...],
    embedded_members: tuple[EmbeddedDraft, ...],
    catalog_ids: frozenset[str] = frozenset(),
    known_identities: Mapping[str, str] | None = None,
) -> FrozenDefinition:
    """Freeze catalog and resolved non-catalog members into definition v1 or v2."""
    if len(embedded_members) > MAX_EMBEDDED_RECORDS:
        raise SourceError(UNSAFE_ARCHIVE, "embedded index exceeds the accepted size")
    identities = dict(known_identities or {})
    catalog_ids = catalog_ids | frozenset(item.stable_id for item in catalog_members)
    components: list[ComponentRef] = list(catalog_members)
    embedded_records: list[dict[str, JsonValue]] = []
    seen_keys: dict[str, ComponentRef] = {}
    seen_refs: dict[tuple[str, str], str] = {}

    for draft in embedded_members:
        validate_frozen_snapshot(draft.snapshot)
        snapshot_record = _snapshot_record(draft.snapshot)
        packed = pack_component_tree(draft.snapshot.files)
        artifact = ArtifactRef(
            digest=digest_bytes(ARTIFACT_DIGEST_DOMAIN, packed),
            size_bytes=len(packed),
        )
        key = identity_key(draft.snapshot.canonical_coordinate, artifact.digest)
        previous = seen_keys.get(key)
        if previous is not None:
            continue
        stable_id = draft.stable_id or local_component_identity(identities, key)
        identities[key] = stable_id
        if stable_id in catalog_ids:
            raise SourceError(
                CATALOG_COLLISION, "embedded identity collides with a catalog component"
            )
        passport = _build_passport(
            draft,
            stable_id=stable_id,
            artifact=artifact,
            publisher_id=publisher_id,
            created_at=created_at,
        )
        passport_bytes = canonize(passport)
        passport_digest = _passport_digest(passport)
        ref = ComponentRef(
            stable_id=stable_id, version=draft.version, passport_digest=passport_digest
        )
        duplicate = seen_refs.get((ref.stable_id, ref.version))
        if duplicate is not None and duplicate != passport_digest:
            raise SourceError(INTEGRITY_MISMATCH, "duplicate ref with different bytes")
        seen_refs[(ref.stable_id, ref.version)] = passport_digest
        seen_keys[key] = ref
        components.append(ref)
        embedded_records.append(
            {
                "ref": encode_component_ref(ref),
                "passport": passport,
                "snapshot": snapshot_record,
                "artifact_b64": _b64url(packed),
                "artifact_digest": artifact.digest,
                "artifact_size_bytes": artifact.size_bytes,
                "passport_digest": passport_digest,
                "passport_size_bytes": len(passport_bytes),
            }
        )

    ordered_components = tuple(sorted(components, key=lambda item: (item.stable_id, item.version)))
    document: dict[str, JsonValue] = {
        "schema_version": 1 if not embedded_records else 2,
        "format": DEFINITION_V1 if not embedded_records else DEFINITION_V2,
        "stable_id": setup_id,
        "version": version,
        "harness_id": harness_id,
        "input_digest": input_digest,
        "components": [encode_component_ref(item) for item in ordered_components],
    }
    if embedded_records:
        document["embedded"] = [
            cast(JsonValue, item) for item in sorted(embedded_records, key=_embedded_sort_key)
        ]
    payload = canonize(document)
    if len(payload) > MAX_DEFINITION_BYTES:
        raise SourceError(UNSAFE_ARCHIVE, "setup definition exceeds the accepted size")
    validate_setup_definition(payload, catalog_ids=catalog_ids)
    return FrozenDefinition(
        format=str(document["format"]),
        document=document,
        payload=payload,
        components=ordered_components,
        identities=identities,
    )


def validate_setup_definition(
    payload: bytes,
    *,
    catalog_ids: frozenset[str] = frozenset(),
) -> dict[str, JsonValue]:
    """Reject unknown fields, digest/size mismatch, collisions, and unbounded bytes."""
    if len(payload) > MAX_DEFINITION_BYTES:
        raise SourceError(UNSAFE_ARCHIVE, "setup definition exceeds the accepted size")
    parsed = from_json_bytes(payload)
    if not isinstance(parsed, dict):
        raise SourceError(INVALID_SOURCE, "setup definition is not an object")
    try:
        document = _DefinitionDocument.model_validate(parsed)
    except ValidationError as exc:
        raise SourceError(
            INVALID_SOURCE, "setup definition has unknown or incomplete fields"
        ) from exc
    if document.format == DEFINITION_V1:
        if document.schema_version != 1 or document.embedded:
            raise SourceError(
                INVALID_SOURCE, "version 1 definition must not carry an embedded index"
            )
        return cast(dict[str, JsonValue], parsed)
    if document.format != DEFINITION_V2 or document.schema_version != 2:
        raise SourceError(INVALID_SOURCE, "setup definition format is not supported")
    if not document.embedded:
        raise SourceError(
            INVALID_SOURCE, "version 2 definition requires a non-empty embedded index"
        )
    if len(document.embedded) > MAX_EMBEDDED_RECORDS:
        raise SourceError(UNSAFE_ARCHIVE, "embedded index exceeds the accepted size")
    for record in document.embedded:
        if record.ref.stable_id in catalog_ids:
            raise SourceError(
                CATALOG_COLLISION, "embedded identity collides with a catalog component"
            )
        artifact = _unb64url(record.artifact_b64)
        if len(artifact) != record.artifact_size_bytes:
            raise SourceError(INTEGRITY_MISMATCH, "embedded artifact size does not match")
        if digest_bytes(ARTIFACT_DIGEST_DOMAIN, artifact) != record.artifact_digest:
            raise SourceError(INTEGRITY_MISMATCH, "embedded artifact digest does not match")
        passport_document = cast(dict[str, JsonValue], record.passport)
        passport_bytes = canonize(passport_document)
        if len(passport_bytes) != record.passport_size_bytes:
            raise SourceError(INTEGRITY_MISMATCH, "embedded passport size does not match")
        if _passport_digest(passport_document) != record.passport_digest:
            raise SourceError(INTEGRITY_MISMATCH, "embedded passport digest does not match")
        if record.ref.passport_digest != record.passport_digest:
            raise SourceError(INTEGRITY_MISMATCH, "embedded ref digest does not match the passport")
        try:
            ComponentVersionPassport.model_validate(record.passport)
        except ValidationError as exc:
            raise SourceError(INCOMPLETE_PASSPORT, "embedded passport is incomplete") from exc
        if any(key in record.passport for key in ("reactions", "publisher_page", "catalog")):
            raise SourceError(
                INCOMPLETE_PASSPORT, "embedded passport must not carry catalog metadata"
            )
    return cast(dict[str, JsonValue], parsed)


def try_parse_setup_definition(payload: bytes) -> dict[str, JsonValue] | None:
    """Return a v1/v2 definition object, or None when the artifact is not one."""
    try:
        return validate_setup_definition(payload)
    except (SourceError, CanonicalizationError, UnicodeDecodeError, ValueError):
        return None


def definition_has_embedded(payload: bytes) -> bool:
    """True when stored bytes are definition version 2 with a non-empty index."""
    document = try_parse_setup_definition(payload)
    if document is None:
        return False
    return document.get("format") == DEFINITION_V2
