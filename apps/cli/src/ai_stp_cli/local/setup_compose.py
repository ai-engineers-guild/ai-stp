"""Freeze and record a new mixed-source setup (SPEC-057 REQ-5705)."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator
from ulid import ULID

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, content, revisions, versions
from ai_stp_cli.local.composition import rule_for
from ai_stp_cli.local.database import transaction
from ai_stp_contracts.machine_help import (
    SetupComposeMember,
    SetupComposePlan,
    SetupComposeResult,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_bytes, digest_canonical
from ai_stp_foundation.harnesses import HARNESS_IDS
from ai_stp_foundation.ids import is_valid_id
from ai_stp_foundation.refs import ComponentRef
from ai_stp_passports import SetupVersionPassport
from ai_stp_passports.versions import ComponentType
from ai_stp_sources.definition import (
    EmbeddedDraft,
    FrozenDefinition,
    freeze_setup_definition,
    pack_component_tree,
)
from ai_stp_sources.models import SourceIntent, SourceSnapshot

PLAN_DOMAIN = "ai-stp:plan:v1"
ARTIFACT_DOMAIN = "ai-stp:artifact:v1"
PASSPORT_DOMAIN = "ai-stp:passport:v1"
_SOURCE: TypeAdapter[SourceIntent] = TypeAdapter(SourceIntent)


class ComposeComponent(BaseModel):
    """One manifest member; catalog members need no duplicated metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: dict[str, object]
    component_type: ComponentType | None = None
    name: str | None = None
    description: str | None = None
    license_spdx: str | None = None
    redistribution_allowed: bool = False
    version: Annotated[str, Field(pattern=r"^\d+\.\d+$")] = "1.0"
    managed_paths: tuple[str, ...] = ()
    upstream_project: str | None = None
    upstream_maintainers: tuple[str, ...] = ()
    runtime_requirements: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _embedded_metadata(self) -> ComposeComponent:
        if self.source.get("kind") != "catalog" and not all(
            (self.component_type, self.name, self.description, self.license_spdx)
        ):
            raise ValueError(
                "non-catalog components require component_type, name, description and license_spdx"
            )
        return self


class ComposeManifest(BaseModel):
    """Bounded authoring document read by setup compose."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    name: Annotated[str, Field(min_length=1, max_length=160)]
    description: Annotated[str, Field(min_length=1, max_length=4000)]
    harness_id: str
    version: Annotated[str, Field(pattern=r"^\d+\.\d+$")] = "1.0"
    tags: Annotated[tuple[str, ...], Field(min_length=1, max_length=32)]
    components: Annotated[tuple[ComposeComponent, ...], Field(min_length=1, max_length=500)]

    @model_validator(mode="after")
    def _known_harness(self) -> ComposeManifest:
        if self.harness_id not in HARNESS_IDS:
            raise ValueError("harness_id is unknown")
        return self


@dataclass(frozen=True)
class CatalogMaterial:
    ref: ComponentRef
    passport: dict[str, JsonValue]
    artifact: bytes


@dataclass(frozen=True)
class ResolvedComposition:
    manifest: ComposeManifest
    frozen: FrozenDefinition
    catalog: tuple[CatalogMaterial, ...]
    plan_digest: str
    created_at: str


def parse_manifest(document: object) -> ComposeManifest:
    try:
        return ComposeManifest.model_validate(document)
    except ValidationError as exc:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the setup composition manifest is invalid",
            details={
                "fields": ",".join(".".join(str(part) for part in e["loc"]) for e in exc.errors())
            },
        ) from exc


def source_intent(component: ComposeComponent) -> SourceIntent:
    try:
        return _SOURCE.validate_python(component.source)
    except ValidationError as exc:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "a setup component source is invalid") from exc


def compose(
    *,
    manifest: ComposeManifest,
    setup_id: str,
    publisher_id: str,
    created_at: str,
    snapshots: Sequence[tuple[ComposeComponent, SourceSnapshot]],
    catalog: Sequence[CatalogMaterial],
) -> ResolvedComposition:
    if not is_valid_id(setup_id, "setup"):
        raise CliFailure("AI_STP_VALIDATION_ERROR", "a valid setup id is required")
    catalog_refs = tuple(item.ref for item in catalog)
    embedded = tuple(
        EmbeddedDraft(
            snapshot=snapshot,
            component_type=cast(ComponentType, item.component_type),
            name=cast(str, item.name),
            description=cast(str, item.description),
            license_spdx=cast(str, item.license_spdx),
            harness_id=manifest.harness_id,
            redistribution_allowed=item.redistribution_allowed,
            version=item.version,
            managed_paths=item.managed_paths,
            upstream_project=item.upstream_project,
            upstream_maintainers=item.upstream_maintainers,
            runtime_requirements=tuple(
                sorted(set(item.runtime_requirements) | set(_source_runtime_requirements(snapshot)))
            ),
            harness_ids=tuple(
                harness
                for harness in sorted(HARNESS_IDS)
                if rule_for(cast(str, item.component_type), harness) is not None
            ),
            stable_id=_embedded_id(publisher_id, snapshot),
        )
        for item, snapshot in snapshots
    )
    input_digest = digest_canonical(PLAN_DOMAIN, cast(JsonValue, manifest.model_dump(mode="json")))
    frozen = freeze_setup_definition(
        setup_id=setup_id,
        version=manifest.version,
        harness_id=manifest.harness_id,
        input_digest=input_digest,
        publisher_id=publisher_id,
        created_at=created_at,
        catalog_members=catalog_refs,
        embedded_members=embedded,
        catalog_ids=frozenset(item.stable_id for item in catalog_refs),
    )
    definition_digest = digest_bytes(ARTIFACT_DOMAIN, frozen.payload)
    plan_digest = digest_canonical(
        PLAN_DOMAIN,
        {
            "setup_id": setup_id,
            "publisher_id": publisher_id,
            "manifest": cast(JsonValue, manifest.model_dump(mode="json")),
            "definition_digest": definition_digest,
        },
    )
    return ResolvedComposition(manifest, frozen, tuple(catalog), plan_digest, created_at)


def _embedded_id(publisher_id: str, snapshot: SourceSnapshot) -> str:
    """Stable opaque identity for the same publisher and exact source bytes."""
    artifact_digest = digest_bytes(ARTIFACT_DOMAIN, pack_component_tree(snapshot.files))
    material = (f"{publisher_id}\0{snapshot.canonical_coordinate}\0{artifact_digest}").encode()
    return f"component_{ULID.from_bytes(hashlib.sha256(material).digest()[:16])}"


def _source_runtime_requirements(snapshot: SourceSnapshot) -> tuple[str, ...]:
    evidence = snapshot.package_evidence
    if evidence is None:
        return ()
    return {
        "npm": ("node",),
        "pypi": ("python",),
        "crates.io": ("cargo",),
        "go": ("go",),
        "pub.dev": ("dart",),
    }[evidence.ecosystem]


def plan_view(resolved: ResolvedComposition) -> SetupComposePlan:
    embedded_ids: set[str] = set()
    raw_embedded = resolved.frozen.document.get("embedded", [])
    if isinstance(raw_embedded, list):
        for item in raw_embedded:
            if not isinstance(item, dict):
                continue
            ref = item.get("ref")
            if isinstance(ref, dict):
                embedded_ids.add(str(ref.get("stable_id") or ""))
    sources = {
        item.ref.stable_id: f"catalog:{item.ref.stable_id}@{item.ref.version}"
        for item in resolved.catalog
    }
    for item in cast(list[object], resolved.frozen.document.get("embedded", [])):
        record = cast(dict[str, object], item)
        ref = cast(dict[str, object], record["ref"])
        snapshot = cast(dict[str, object], record["snapshot"])
        sources[str(ref["stable_id"])] = str(snapshot["canonical_coordinate"])
    return SetupComposePlan(
        setup_id=str(resolved.frozen.document["stable_id"]),
        version=str(resolved.frozen.document["version"]),
        harness_id=resolved.manifest.harness_id,
        created_at=resolved.created_at,
        definition_digest=digest_bytes(ARTIFACT_DOMAIN, resolved.frozen.payload),
        plan_digest=resolved.plan_digest,
        members=[
            SetupComposeMember(
                stable_id=ref.stable_id,
                version=ref.version,
                source=sources[ref.stable_id],
                embedded=ref.stable_id in embedded_ids,
            )
            for ref in resolved.frozen.components
        ],
    )


def apply(
    connection: sqlite3.Connection,
    resolved: ResolvedComposition,
    *,
    expected_plan_digest: str,
    device_id: str,
    publisher_id: str,
    at: str,
) -> SetupComposeResult:
    if resolved.plan_digest != expected_plan_digest:
        raise CliFailure(
            "AI_STP_PLAN_STALE",
            "the setup composition changed after it was reviewed",
            details={"expected": expected_plan_digest, "found": resolved.plan_digest},
        )
    setup_id = str(resolved.frozen.document["stable_id"])
    version = str(resolved.frozen.document["version"])
    if versions.held(connection, setup_id, version) is not None:
        raise CliFailure(
            "AI_STP_CONFLICT", "that setup version already exists", details={"id": setup_id}
        )

    passports = [item.passport for item in resolved.catalog]
    raw_embedded = resolved.frozen.document.get("embedded", [])
    if isinstance(raw_embedded, list):
        passports.extend(
            cast(dict[str, JsonValue], item["passport"])
            for item in raw_embedded
            if isinstance(item, dict) and isinstance(item.get("passport"), dict)
        )
    passport = _setup_passport(
        resolved,
        publisher_id=publisher_id,
        at=at,
        member_passports=passports,
    )
    with transaction(connection):
        for item in resolved.catalog:
            artifact = content.put(connection, item.artifact, at=at)
            declared = cast(dict[str, object], item.passport["artifact"])
            if (
                artifact.digest != declared["digest"]
                or artifact.byte_length != declared["size_bytes"]
            ):
                raise CliFailure("AI_STP_CATALOG_INTEGRITY", "catalog component bytes changed")
            document = dict(item.passport)
            document.pop("revision_id", None)
            stored = revisions.commit(connection, document, device_id=device_id)
            versions.record(
                connection,
                stable_id=item.ref.stable_id,
                version=item.ref.version,
                passport_digest=item.ref.passport_digest,
                revision_id=stored.revision_id,
                at=at,
            )
        artifact = content.put(connection, resolved.frozen.payload, at=at)
        passport["artifact"] = {"digest": artifact.digest, "size_bytes": artifact.byte_length}
        committed = revisions.commit(connection, passport, device_id=device_id)
        passport_digest = cache.digest_of(
            cast(JsonValue, committed.envelope.model_dump(mode="json"))
        )
        versions.record(
            connection,
            stable_id=setup_id,
            version=version,
            passport_digest=passport_digest,
            revision_id=committed.revision_id,
            at=at,
        )
    return SetupComposeResult(
        setup_id=setup_id,
        version=version,
        created_at=at,
        passport_digest=passport_digest,
        definition_digest=digest_bytes(ARTIFACT_DOMAIN, resolved.frozen.payload),
        plan_digest=resolved.plan_digest,
        created=True,
    )


def _setup_passport(
    resolved: ResolvedComposition,
    *,
    publisher_id: str,
    at: str,
    member_passports: Sequence[Mapping[str, JsonValue]],
) -> dict[str, JsonValue]:
    refs = [
        {
            "stable_id": item.stable_id,
            "version": item.version,
            "passport_digest": item.passport_digest,
            **({} if item.variant_id is None else {"variant_id": item.variant_id}),
        }
        for item in resolved.frozen.components
    ]
    license_ids: set[str] = set()
    redistributable = True
    required_env: dict[str, str] = {}
    endpoints: set[str] = set()
    credentials = False
    authorization = "none"
    permissions: dict[str, set[str]] = {"filesystem": set(), "network": set(), "process": set()}
    runtime_requirements: set[str] = set()
    component_types: set[str] = set()
    member_presentations: list[dict[str, JsonValue]] = []
    embedded_ids = {
        str(cast(dict[str, object], item.get("ref", {})).get("stable_id") or "")
        for item in cast(list[dict[str, object]], resolved.frozen.document.get("embedded", []))
    }
    for member in member_passports:
        component_type = str(member.get("component_type") or "")
        if component_type:
            component_types.add(component_type)
        runtime_requirements.update(
            str(item) for item in cast(list[object], member.get("runtime_requirements", []))
        )
        stable_id = str(member.get("stable_id") or "")
        facts_raw = member.get("facts")
        facts = cast(dict[str, object], facts_raw) if isinstance(facts_raw, dict) else {}
        upstream_raw = facts.get("upstream_source")
        upstream = (
            cast(dict[str, object], upstream_raw).get("value")
            if isinstance(upstream_raw, dict)
            else None
        )
        member_presentations.append(
            {
                "stable_id": stable_id,
                "name": str(member.get("name") or stable_id),
                "version": str(member.get("version") or ""),
                "component_type": component_type,
                "embedded": stable_id in embedded_ids,
                "source_coordinate": str(upstream) if isinstance(upstream, str) else None,
            }
        )
        license_info = member.get("license")
        if isinstance(license_info, dict):
            license_ids.add(str(license_info.get("spdx_id") or "LicenseRef-Unknown"))
            redistributable = redistributable and bool(license_info.get("redistribution_allowed"))
        for requirement in cast(list[object], member.get("required_env", [])):
            if isinstance(requirement, dict):
                requirement_doc = cast(dict[str, object], requirement)
                required_env[str(requirement_doc.get("name") or "")] = str(
                    requirement_doc.get("purpose") or ""
                )
        endpoints.update(
            str(item) for item in cast(list[object], member.get("external_endpoints", []))
        )
        credentials = credentials or bool(member.get("requires_credentials"))
        if member.get("requires_authorization") != "none":
            authorization = str(member.get("requires_authorization"))
        raw_permissions = member.get("permissions")
        if isinstance(raw_permissions, dict):
            permission_doc = cast(dict[str, object], raw_permissions)
            for key in permissions:
                permissions[key].update(
                    str(item) for item in cast(list[object], permission_doc.get(key, []))
                )

    def fact(value: JsonValue) -> dict[str, JsonValue]:
        return {
            "value": value,
            "origin": "declared",
            "confirmation": "none",
            "observed_at": at,
        }

    projected_harnesses = [
        harness
        for harness in sorted(HARNESS_IDS)
        if all(rule_for(component_type, harness) is not None for component_type in component_types)
    ]
    body: dict[str, JsonValue] = {
        "schema_version": 1,
        "kind": "setup",
        "stable_id": str(resolved.frozen.document["stable_id"]),
        "owner_id": publisher_id,
        "created_at": at,
        "visibility": "public",
        "parent_revision_ids": [],
        "facts": {
            "harness_id": fact(resolved.manifest.harness_id),
            "members": fact(cast(JsonValue, refs)),
            "snapshot": fact(str(resolved.frozen.document["input_digest"])),
            "member_metadata_complete": fact(True),
            "component_presentations": fact(cast(JsonValue, member_presentations)),
            "harness_projections": fact(cast(JsonValue, projected_harnesses)),
        },
        "name": resolved.manifest.name,
        "description": resolved.manifest.description,
        "version": resolved.manifest.version,
        "tags": list(resolved.manifest.tags),
        "source": None,
        "artifact": {
            "digest": digest_bytes(ARTIFACT_DOMAIN, resolved.frozen.payload),
            "size_bytes": len(resolved.frozen.payload),
        },
        "harness_id": resolved.manifest.harness_id,
        "required_env": [
            {"name": name, "purpose": purpose}
            for name, purpose in sorted(required_env.items())
            if name
        ],
        "requires_credentials": credentials,
        "requires_authorization": authorization,
        "permissions": cast(JsonValue, {key: sorted(value) for key, value in permissions.items()}),
        "external_endpoints": cast(JsonValue, sorted(endpoints)),
        "license": {
            "spdx_id": " AND ".join(sorted(license_ids)) or "LicenseRef-Unknown",
            "redistribution_allowed": redistributable,
        },
        "compatibility_evidence_refs": [],
        "runtime_requirements": cast(JsonValue, sorted(runtime_requirements)),
        "purpose": "Install the exact mixed component composition.",
        "target_role": "local-project",
        "posture": None,
        "supported_tasks": [],
        "harness_ids": cast(JsonValue, projected_harnesses),
        "components": cast(JsonValue, refs),
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
        "artifact_format": resolved.frozen.format,
        "member_metadata_complete": True,
    }
    normalized = SetupVersionPassport.model_validate(
        {**body, "revision_id": "revision_" + "0" * 64}
    )
    return cast(dict[str, JsonValue], normalized.model_dump(mode="json", exclude={"revision_id"}))
