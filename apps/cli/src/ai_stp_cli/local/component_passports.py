"""Safe enrichment and publication-readiness checks for adopted components.

Adoption records only mechanically observed facts.  This module is the explicit
boundary where a person or agent may add declared metadata.  Updates are
content-addressed child revisions; a previously released revision is never
rewritten or repointed.
"""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from pydantic import ValidationError

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import components, content, journal, revisions
from ai_stp_cli.local.passports import moment
from ai_stp_contracts.authoring import AUTHORING_DRAFT_MARKER
from ai_stp_contracts.component_passport import ComponentPassportPatch
from ai_stp_foundation.canonical import JsonValue, from_json_bytes
from ai_stp_foundation.digests import digest_bytes
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_foundation.provider_surfaces import PROVIDER_SURFACES, provider_surface
from ai_stp_passports import ScopeAdaptation, build_projection, seal_adaptation
from ai_stp_passports.envelope import seal_envelope
from ai_stp_passports.versions import (
    ComponentAdaptation,
    ComponentType,
    ComponentVersionPassport,
    ProjectionKind,
    TargetScope,
)

MAX_PATCH_BYTES: Final[int] = 256 * 1024
_SECRET_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    {
        "api_key",
        "apikey",
        "access_token",
        "auth_token",
        "credential_value",
        "password",
        "private_key",
        "secret",
        "secret_value",
        "token",
    }
)


@dataclass(frozen=True)
class PublicationReadiness:
    stable_id: str
    revision_id: str
    ready: bool
    missing_fields: tuple[str, ...]
    invalid_fields: tuple[str, ...]


@dataclass(frozen=True)
class SuggestedFact:
    field: str
    value: JsonValue
    source_refs: tuple[str, ...]


@dataclass(frozen=True)
class Suggestions:
    stable_id: str
    revision_id: str
    facts: tuple[SuggestedFact, ...]
    unresolved_fields: tuple[str, ...]


@dataclass(frozen=True)
class QualityCheck:
    code: str
    passed: bool
    fields: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class QualityDimension:
    name: str
    checks: tuple[QualityCheck, ...]


@dataclass(frozen=True)
class QualityReport:
    stable_id: str
    revision_id: str
    component_type: ComponentType
    dimensions: tuple[QualityDimension, ...]


_SUGGESTIBLE_FIELDS: Final[frozenset[str]] = frozenset(ComponentPassportPatch.model_fields)
_PUBLICATION_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "name",
        "description",
        "tags",
        "source",
        "harness_id",
        "component_type",
        "projection_kind",
        "license",
        "entry_points",
        "runtime_requirements",
        "provides_capabilities",
        "requires_components",
        "requires_capabilities",
        "requires_credentials",
        "requires_authorization",
        "permissions",
    }
)
_ACTION_SURFACES: Final[dict[ComponentType, tuple[str, ...]]] = {
    "instruction": ("managed_paths", "entry_points"),
    "skill": ("managed_paths", "entry_points"),
    "mcp": ("native_ids", "entry_points"),
    "hook": ("native_ids", "managed_paths", "entry_points"),
    "command": ("native_ids", "managed_paths", "entry_points"),
    "agent": ("native_ids", "managed_paths", "entry_points"),
    "plugin": ("native_ids", "managed_paths", "entry_points"),
    "setting": ("native_ids", "managed_paths"),
}


def names_a_native_identifier(component_type: str) -> bool:
    """Whether this kind's contract has a native identifier at all.

    Read from `_ACTION_SURFACES` rather than restated: the set that decides
    which kinds carry `native_ids` is already written down once, and a second
    list would agree with it exactly until somebody edited one.
    """
    return "native_ids" in _ACTION_SURFACES.get(cast(ComponentType, component_type), ())


def evaluate_quality(connection: sqlite3.Connection, stable_id: str) -> QualityReport:
    """Return deterministic authoring hints that never participate in trust."""
    current = _component_head(connection, stable_id)
    document = cast(dict[str, JsonValue], current.envelope.model_dump(mode="json"))
    raw_facts = cast(dict[str, JsonValue], document["facts"])
    values = {
        name: cast(dict[str, JsonValue], fact).get("value")
        for name, fact in raw_facts.items()
        if isinstance(fact, dict)
    }
    raw_type = values.get("component_type")
    if not isinstance(raw_type, str) or raw_type not in _ACTION_SURFACES:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the component passport has no supported component type for quality guidance",
        )
    component_type: ComponentType = raw_type
    source = _exact_source(values)
    license_info = values.get("license")
    readiness = validate_for_publication(connection, stable_id)
    surfaces = _ACTION_SURFACES[component_type]

    dimensions = (
        QualityDimension(
            "safety",
            (
                _hint(
                    "declared_permissions",
                    "permissions" in values,
                    ("permissions",),
                    "Declare the bounded filesystem, network, and process permissions.",
                ),
                _hint(
                    "declared_access_requirements",
                    "requires_credentials" in values and "requires_authorization" in values,
                    ("requires_credentials", "requires_authorization"),
                    "Declare credential and external authorization requirements explicitly.",
                ),
            ),
        ),
        QualityDimension(
            "clarity",
            (
                _hint("named_component", bool(values.get("name")), ("name",), "Add a name."),
                _hint(
                    "described_component",
                    bool(values.get("description")),
                    ("description",),
                    "Explain the component's purpose and operating boundary.",
                ),
            ),
        ),
        QualityDimension(
            "reusability",
            (
                _hint(
                    "exact_source",
                    isinstance(source, dict)
                    and bool(source.get("repository"))
                    and bool(source.get("commit"))
                    and bool(source.get("path")),
                    ("source",),
                    "Bind reusable content to an exact repository commit and subpath.",
                ),
                _hint(
                    "redistributable_license",
                    isinstance(license_info, dict)
                    and license_info.get("redistribution_allowed") is True,
                    ("license",),
                    "Declare a license that permits redistribution when reuse is intended.",
                ),
                _hint(
                    "harness_scope",
                    bool(values.get("harness_id")),
                    ("harness_id",),
                    "Name the harness whose native contract this component targets.",
                ),
            ),
        ),
        QualityDimension(
            "completeness",
            (
                _hint(
                    "publication_structure",
                    readiness.ready,
                    (*readiness.missing_fields, *readiness.invalid_fields),
                    "Resolve every structural publication-readiness field.",
                ),
            ),
        ),
        QualityDimension(
            "actionability",
            (
                _hint(
                    "declared_action_surface",
                    any(_nonempty(values.get(field)) for field in surfaces),
                    surfaces,
                    "Declare at least one type-appropriate entry point or native surface.",
                ),
            ),
        ),
    )
    return QualityReport(stable_id, current.revision_id, component_type, dimensions)


def _hint(code: str, passed: bool, fields: tuple[str, ...], message: str) -> QualityCheck:
    return QualityCheck(code, passed, fields, "No hint." if passed else message)


def _nonempty(value: JsonValue | None) -> bool:
    return (isinstance(value, str) and bool(value)) or (isinstance(value, list) and bool(value))


def _exact_source(values: dict[str, JsonValue]) -> dict[str, JsonValue] | None:
    source = values.get("source")
    if isinstance(source, dict):
        return cast(dict[str, JsonValue], source)
    repository = values.get("source_repository")
    revision = values.get("source_revision")
    subpath = values.get("source_subpath")
    if all(isinstance(item, str) and item for item in (repository, revision, subpath)):
        return {
            "repository": cast(str, repository),
            "commit": cast(str, revision),
            "path": cast(str, subpath),
        }
    return None


def suggest(connection: sqlite3.Connection, stable_id: str) -> Suggestions:
    """Extract bounded exact candidates without changing the component draft."""
    current = _component_head(connection, stable_id)
    document = cast(dict[str, JsonValue], current.envelope.model_dump(mode="json"))
    raw_facts = cast(dict[str, JsonValue], document["facts"])
    values = {
        name: cast(dict[str, JsonValue], fact).get("value")
        for name, fact in raw_facts.items()
        if isinstance(fact, dict)
    }
    candidates: dict[str, SuggestedFact] = {}

    repository = values.get("source_repository")
    revision = values.get("source_revision")
    subpath = values.get("source_subpath")
    if all(isinstance(item, str) and item for item in (repository, revision, subpath)):
        source: JsonValue = {
            "repository": cast(str, repository),
            "commit": cast(str, revision),
            "path": cast(str, subpath),
        }
        _add_candidate(candidates, "source", source, ("adopted:exact-source",))

    digest = values.get("content_digest")
    content_format = values.get("content_format")
    if isinstance(digest, str) and isinstance(content_format, str):
        payload = content.get(connection, digest)
        for item in components.expand(payload, content_format):
            declared = _manifest_component(item.path, item.content)
            for field, value in declared.items():
                _add_candidate(candidates, field, value, (f"artifact:{item.path}",))

    unresolved = tuple(
        sorted(
            field
            for field in _PUBLICATION_FIELDS
            if field not in candidates and not _confirmed_value(raw_facts.get(field))
        )
    )
    return Suggestions(
        stable_id=stable_id,
        revision_id=current.revision_id,
        facts=tuple(candidates[field] for field in sorted(candidates)),
        unresolved_fields=unresolved,
    )


def _manifest_component(path: str, payload: bytes) -> dict[str, JsonValue]:
    try:
        if path == "pyproject.toml":
            parsed = cast(dict[str, object], tomllib.loads(payload.decode("utf-8")))
            tool = parsed.get("tool")
            tools = cast(dict[str, object], tool) if isinstance(tool, dict) else {}
            namespace = tools.get("ai-stp")
            namespaces = cast(dict[str, object], namespace) if isinstance(namespace, dict) else {}
            raw: object = namespaces.get("component")
        elif path == "package.json":
            parsed_json: object = json.loads(payload)
            package = cast(dict[str, object], parsed_json) if isinstance(parsed_json, dict) else {}
            namespace = package.get("ai-stp")
            namespaces = cast(dict[str, object], namespace) if isinstance(namespace, dict) else {}
            raw = namespaces.get("component")
        else:
            return {}
    except (UnicodeDecodeError, ValueError, tomllib.TOMLDecodeError):
        return {}
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the component enrichment manifest section must be an object",
            details={"manifest": path},
        )
    document = cast(dict[str, object], raw)
    unknown = sorted(set(document) - _SUGGESTIBLE_FIELDS)
    if unknown:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the component enrichment manifest contains unknown fields",
            details={"manifest": path, "fields": ", ".join(unknown)},
        )
    return cast(dict[str, JsonValue], document)


def _add_candidate(
    candidates: dict[str, SuggestedFact], field: str, value: JsonValue, refs: tuple[str, ...]
) -> None:
    try:
        ComponentPassportPatch.model_validate({field: value})
    except ValidationError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a component enrichment manifest fact violates the passport schema",
            details={"field": field, "source": refs[0]},
        ) from error
    held = candidates.get(field)
    if held is not None and held.value != value:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "component enrichment manifests disagree",
            details={"field": field},
        )
    candidates[field] = SuggestedFact(
        field, value, refs if held is None else (*held.source_refs, *refs)
    )


def _confirmed_value(fact: JsonValue | None) -> bool:
    return isinstance(fact, dict) and fact.get("confirmation") == "user_confirmed"


def load_patch(path: Path) -> ComponentPassportPatch:
    """Read one bounded owner-selected JSON patch without following a symlink."""
    try:
        before = path.lstat()
    except OSError as error:
        raise CliFailure(
            "AI_STP_NOT_FOUND", "the component passport patch cannot be opened"
        ) from error
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_size > MAX_PATCH_BYTES
    ):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the component passport patch must be a bounded regular file",
            details={"limit_bytes": str(MAX_PATCH_BYTES)},
        )
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags)
        try:
            after = os.fstat(descriptor)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise CliFailure("AI_STP_CONFLICT", "the component passport patch changed")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                payload = stream.read(MAX_PATCH_BYTES + 1)
        finally:
            os.close(descriptor)
    except CliFailure:
        raise
    except OSError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR", "the component passport patch is not safely readable"
        ) from error
    if len(payload) > MAX_PATCH_BYTES:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the component passport patch exceeds its byte limit",
            details={"limit_bytes": str(MAX_PATCH_BYTES)},
        )
    try:
        raw = from_json_bytes(payload)
    except (TypeError, ValueError) as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR", "the component passport patch is not canonical JSON"
        ) from error
    if not isinstance(raw, dict):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR", "the component passport patch must be a JSON object"
        )
    secret_paths = _secret_paths(cast(dict[str, JsonValue], raw))
    if secret_paths:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "secret-bearing fields are forbidden in a component passport patch",
            details={"fields": ", ".join(secret_paths)},
        )
    try:
        patch = ComponentPassportPatch.model_validate(raw)
    except ValidationError as error:
        fields = sorted(
            {
                ".".join(str(part) for part in item["loc"])
                for item in error.errors(include_input=False)
            }
        )
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the component passport patch does not satisfy its closed schema",
            details={"fields": ", ".join(fields) or "document"},
        ) from error
    if not patch.model_fields_set:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "the component passport patch is empty")
    return patch


def update(
    connection: sqlite3.Connection,
    stable_id: str,
    expected_revision: str,
    patch: ComponentPassportPatch,
    *,
    device_id: str,
) -> revisions.StoredRevision:
    current = _component_head(connection, stable_id)
    if current.revision_id != expected_revision:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the component head changed after the patch was prepared",
            details={
                "expected_revision": expected_revision,
                "current_revision": current.revision_id,
            },
            next_actions=[f"component passport show --id {stable_id} --json"],
        )
    declared = cast(dict[str, JsonValue], patch.model_dump(mode="json", exclude_unset=True))
    current_document = cast(dict[str, JsonValue], current.envelope.model_dump(mode="json"))
    facts = dict(cast(dict[str, JsonValue], current_document["facts"]))
    unchanged = True
    for name, value in declared.items():
        held = facts.get(name)
        if (
            not isinstance(held, dict)
            or held.get("value") != value
            or held.get("confirmation") != "user_confirmed"
        ):
            unchanged = False
            break
    if unchanged:
        return current

    at = moment()
    for name, value in declared.items():
        facts[name] = {
            "value": value,
            "origin": "declared",
            "confirmation": "user_confirmed",
            "source_refs": [],
            "observed_at": None,
            "confirmed_at": at,
            "confidence": None,
        }
    document = {key: value for key, value in current_document.items() if key != "revision_id"}
    document.update(
        {"created_at": at, "parent_revision_ids": [current.revision_id], "facts": facts}
    )
    operation_id = journal.begin(connection, "component.passport.update", at)
    try:
        stored = revisions.commit(
            connection,
            document,
            device_id=device_id,
            operation_id=operation_id,
        )
    except BaseException as error:
        journal.settle(connection, operation_id, "failed", moment(), type(error).__name__)
        raise
    journal.settle(connection, operation_id, "verified", moment())
    return stored


def validate_for_publication(
    connection: sqlite3.Connection, stable_id: str
) -> PublicationReadiness:
    current = _component_head(connection, stable_id)
    document = cast(dict[str, JsonValue], current.envelope.model_dump(mode="json"))
    raw_facts = cast(dict[str, JsonValue], document["facts"])
    values: dict[str, JsonValue] = {
        name: cast(dict[str, JsonValue], fact).get("value")
        for name, fact in raw_facts.items()
        if isinstance(fact, dict)
    }
    source = values.get("source")
    if source is None and all(
        isinstance(values.get(name), str) and values.get(name)
        for name in ("source_repository", "source_revision", "source_subpath")
    ):
        source = {
            "repository": values["source_repository"],
            "commit": values["source_revision"],
            "path": values["source_subpath"],
        }
    required = (
        "name",
        "description",
        "tags",
        "source",
        "harness_id",
        "component_type",
        "projection_kind",
        "license",
        "content_digest",
        "byte_length",
        "scope",
        "source_path",
    )
    available = dict(values)
    available["source"] = source
    missing = tuple(sorted(name for name in required if available.get(name) is None))
    invalid: set[str] = set()
    if isinstance(source, dict):
        repository = source.get("repository")
        if not isinstance(repository, str) or not repository.startswith("https://github.com/"):
            invalid.add("source.repository")
    if not missing:
        harness_id = values.get("harness_id")
        scope = values.get("scope")
        if (harness_id, scope) not in PROVIDER_SURFACES:
            invalid.add("harness_id")
        if scope not in {"global", "user_root", "project"}:
            invalid.add("scope")
        try:
            payload = content.get(connection, cast(str, values["content_digest"]))
            expanded = components.expand(payload, cast(str, values.get("content_format") or ""))
            if not expanded:
                invalid.add("artifact")
        except (CliFailure, ValueError):
            invalid.add("artifact")
    return PublicationReadiness(
        stable_id=stable_id,
        revision_id=current.revision_id,
        ready=not missing and not invalid,
        missing_fields=missing,
        invalid_fields=tuple(sorted(invalid)),
    )


def declared_values(document: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """The `value` of every fact in a stored draft, by name.

    A draft carries `{name: {value, origin, confirmation, observed_at}}`; the
    readers that only need what was declared read this map. Shared by the two
    reports and the evaluator so that "what a draft says" is answered once.
    """
    raw = document.get("facts")
    values: dict[str, JsonValue] = {}
    if isinstance(raw, dict):
        for name, fact in cast(dict[str, JsonValue], raw).items():
            values[name] = (
                cast(dict[str, JsonValue], fact).get("value") if isinstance(fact, dict) else fact
            )
    return values


def names_of(value: JsonValue | None) -> tuple[str, ...]:
    """Strings out of a declared list that may hold names or `{name: ...}` objects."""
    if not isinstance(value, list):
        return ()
    found: list[str] = []
    for item in cast(list[JsonValue], value):
        if isinstance(item, str) and item:
            found.append(item)
        elif isinstance(item, dict):
            name = cast(dict[str, JsonValue], item).get("name")
            if isinstance(name, str) and name:
                found.append(name)
    return tuple(found)


def version_passport(
    connection: sqlite3.Connection, stable_id: str, version: str
) -> ComponentVersionPassport:
    """Materialize the exact released revision as a public version passport."""
    from ai_stp_cli.local import versions
    from ai_stp_passports.envelope import derive_revision_id

    recorded = versions.held(connection, stable_id, version)
    if recorded is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "that component has no such released local version",
            details={"id": stable_id, "version": version},
            next_actions=[f"component version list --id {stable_id} --json"],
        )
    stored = revisions.get(connection, recorded.revision_id)
    if stored is None or stored.envelope.kind != "component":
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the released component revision is unavailable",
            details={"id": stable_id, "version": version},
        )
    document = cast(dict[str, JsonValue], stored.envelope.model_dump(mode="json"))
    # Catalog acquisition stores the complete immutable snapshot. Keep that
    # shape intact; only adopted local drafts need reconstruction from facts.
    try:
        complete = ComponentVersionPassport.model_validate(document)
    except ValidationError:
        complete = None
    if complete is not None and complete.version == version:
        sealed = cast(dict[str, JsonValue], complete.model_dump(mode="json"))
        sealed["revision_id"] = derive_revision_id(sealed)
        return ComponentVersionPassport.model_validate(sealed)

    raise CliFailure(
        "AI_STP_VALIDATION_ERROR",
        "the released component revision is not an immutable version snapshot",
        details={"id": stable_id, "version": version, "fields": "adaptations"},
        next_actions=[f"component version release --id {stable_id} --json"],
    )


def materialize_version_passport(
    connection: sqlite3.Connection,
    stable_id: str,
    version: str,
    *,
    device_id: str,
    at: str,
) -> tuple[ComponentVersionPassport, str]:
    """Freeze a draft into one immutable adaptation snapshot and native CAS artifact."""
    current = _component_head(connection, stable_id)
    document = cast(dict[str, JsonValue], current.envelope.model_dump(mode="json"))
    values = declared_values(document)
    required = ("name", "description", "tags", "harness_id", "component_type", "projection_kind")
    missing = [name for name in required if values.get(name) is None]
    if missing:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the component draft is not ready to release",
            details={"fields": ", ".join(missing)},
        )
    if AUTHORING_DRAFT_MARKER in str(values.get("description") or ""):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "replace every TODO(ai-stp-scaffold) marker before release",
            details={"fields": "description"},
        )
    harness_id = cast(HarnessId, values["harness_id"])
    component_type = cast(ComponentType, values["component_type"])
    permissions = values.get("permissions") or {"filesystem": [], "network": [], "process": []}
    frozen: list[ComponentAdaptation] = _freeze_adaptations(
        connection, values, component_type, at=at
    )
    adaptations: list[JsonValue] = [
        cast(JsonValue, item.model_dump(mode="json")) for item in frozen
    ]
    stored_artifact = frozen[0].scope_adaptations[0].projection_artifact
    body: dict[str, JsonValue] = {
        "schema_version": 1,
        "kind": "component",
        "stable_id": stable_id,
        "owner_id": document["owner_id"],
        "created_at": document["created_at"],
        "visibility": "public",
        "parent_revision_ids": [],
        "facts": document.get("facts") or {},
        "name": values["name"],
        "description": values["description"],
        "version": version,
        "tags": values["tags"],
        "source": _exact_source(values),
        "artifact": {"digest": stored_artifact.digest, "size_bytes": stored_artifact.size_bytes},
        "required_env": values.get("required_env") or [],
        "requires_credentials": values.get("requires_credentials") or False,
        "requires_authorization": values.get("requires_authorization") or "none",
        "permissions": permissions,
        "external_endpoints": values.get("external_endpoints") or [],
        "license": values.get("license"),
        "compatibility_evidence_refs": values.get("compatibility_evidence_refs") or [],
        "component_type": component_type,
        "origin_harness_id": harness_id,
        "adaptations": adaptations,
        "provides_capabilities": values.get("provides_capabilities") or [],
        "requires_components": values.get("requires_components") or [],
        "requires_capabilities": values.get("requires_capabilities") or [],
        "conflicts": values.get("conflicts") or {},
        "artifact_format": "ai-stp-adaptation-projection/1",
        "runtime_requirements": values.get("runtime_requirements") or [],
    }
    normalized = ComponentVersionPassport.model_validate(
        seal_envelope(body).model_dump(mode="json")
    ).model_dump(mode="json")
    normalized.pop("revision_id", None)
    snapshot = revisions.store_snapshot(
        connection, cast(dict[str, JsonValue], normalized), device_id=device_id
    )
    passport = ComponentVersionPassport.model_validate(snapshot.envelope.model_dump(mode="json"))
    return passport, snapshot.revision_id


def _freeze_adaptations(
    connection: sqlite3.Connection,
    values: dict[str, JsonValue],
    component_type: ComponentType,
    *,
    at: str,
) -> list[ComponentAdaptation]:
    """One adaptation per declared harness source; one when the draft is singular."""
    raw = values.get("adaptation_contents")
    sources: list[dict[str, JsonValue]] = []
    if isinstance(raw, list) and len(raw) >= 2:
        for item in raw:
            if not isinstance(item, dict):
                raise CliFailure(
                    "AI_STP_VALIDATION_ERROR",
                    "each adaptation source must be an object",
                )
            sources.append(cast(dict[str, JsonValue], item))
    else:
        sources = [
            {
                "harness_id": values["harness_id"],
                "content_digest": values.get("content_digest") or "",
                "content_format": values.get("content_format") or "",
                "managed_paths": values.get("managed_paths") or [],
                "scope": values.get("scope") or "",
                "projection_kind": values.get("projection_kind") or "",
                "declared_key": values.get("declared_key") or "",
                "source_locator": values.get("source_locator") or "",
                "native_ids": values.get("native_ids") or [],
            }
        ]
    harnesses = [str(item.get("harness_id") or "") for item in sources]
    if len(harnesses) != len(set(harnesses)):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "component adaptations must not repeat a harness",
        )
    frozen: list[ComponentAdaptation] = []
    for item in sources:
        frozen.append(_freeze_one_adaptation(connection, values, component_type, item, at=at))
    return frozen


def _freeze_one_adaptation(
    connection: sqlite3.Connection,
    values: dict[str, JsonValue],
    component_type: ComponentType,
    source: Mapping[str, JsonValue],
    *,
    at: str,
) -> ComponentAdaptation:
    harness_id = cast(HarnessId, str(source.get("harness_id") or values["harness_id"]))
    projection_kind = cast(
        ProjectionKind, str(source.get("projection_kind") or values["projection_kind"])
    )
    scope_name = cast(TargetScope, str(source.get("scope") or values.get("scope") or ""))
    if (harness_id, scope_name) not in PROVIDER_SURFACES:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the component draft has no supported explicit harness scope",
        )
    source_digest = str(source.get("content_digest") or "")
    source_format = str(source.get("content_format") or "")
    managed_paths = names_of(source.get("managed_paths"))
    declared_key = str(source.get("declared_key") or "")
    source_locator = str(source.get("source_locator") or "")
    source_payload = content.get(connection, source_digest)
    expanded = components.expand(source_payload, source_format)
    if (
        not expanded
        or (declared_key and len(expanded) != 1)
        or (not declared_key and len(managed_paths) != 1)
    ):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the component source projection is empty",
            details={
                "managed_paths": ", ".join(managed_paths),
                "source_members": str(len(expanded)),
                "declared_key": declared_key,
            },
        )
    projection_root = source_locator.split("#", 1)[0] if declared_key else managed_paths[0]
    projected: dict[str, bytes] = {}
    modes: dict[str, int] = {}
    for member in expanded:
        path = (
            projection_root if not member.path else f"{projection_root.rstrip('/')}/{member.path}"
        )
        projected[path] = member.content
        modes[path] = member.mode
    native_ids = names_of(source.get("native_ids") or values.get("native_ids"))
    members: list[JsonValue] = [
        {
            "path": path,
            "object_type": "file",
            "mode": modes[path],
            "content_artifact": {
                "digest": digest_bytes("ai-stp:artifact:v1", payload),
                "size_bytes": len(payload),
            },
            "native_ids": list(native_ids),
            "content_format": "application/octet-stream",
            "parser_id": "toml/1" if declared_key else None,
            "ownership": "contribution" if declared_key else "whole",
            "ownership_key": declared_key or None,
            "write_semantics": "merge" if declared_key else "replace",
            "withdrawal_semantics": "preserve_unowned" if declared_key else "remove_path",
        }
        for path, payload in sorted(projected.items())
    ]
    surface = provider_surface(harness_id, scope_name)
    permissions = values.get("permissions") or {"filesystem": [], "network": [], "process": []}
    scope_document: dict[str, JsonValue] = {
        "scope": scope_name,
        "projection_format": "ai-stp-adaptation-projection/1",
        "projection_artifact": {"digest": "sha256:" + "0" * 64, "size_bytes": 1},
        "provider_component_kind": component_type,
        "projection_kind": projection_kind,
        "required_surface": {
            "profile_id": surface.profile_id,
            "profile_digest": surface.profile_digest,
            "bundle_format": surface.bundle_format,
        },
        "permissions": permissions,
        "members": members,
        "supported_harness_versions": values.get("supported_harness_versions") or [],
        "supported_os": values.get("supported_os") or [],
        "supported_arch": values.get("supported_arch") or [],
        "technical_support": "experimental",
        "technical_support_reason": "locally authored component pending assessment",
        "semantic_losses": [],
    }
    provisional = ScopeAdaptation.model_validate(scope_document)
    projection = build_projection(provisional, projected)
    stored_artifact = content.put(connection, projection, at=at)
    scope_document["projection_artifact"] = {
        "digest": stored_artifact.digest,
        "size_bytes": stored_artifact.byte_length,
    }
    return seal_adaptation(
        {
            "harness_id": harness_id,
            "implementation_mode": "native",
            "source_artifact": None,
            "transform": None,
            "logical_component_type": component_type,
            "scope_adaptations": [scope_document],
        }
    )


def _component_head(connection: sqlite3.Connection, stable_id: str) -> revisions.StoredRevision:
    stored = revisions.head(connection, stable_id)
    if stored is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "that component has no local passport",
            details={"id": stable_id},
            next_actions=["component discover --json"],
        )
    if stored.envelope.kind != "component":
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "that identifier does not name a component passport",
            details={"id": stable_id, "kind": stored.envelope.kind},
        )
    return stored


def _secret_paths(value: JsonValue, path: tuple[str, ...] = ()) -> tuple[str, ...]:
    found: list[str] = []
    if isinstance(value, dict):
        for name, nested in value.items():
            held = str(name)
            current = (*path, held)
            normalized = held.lower().replace("-", "_")
            if normalized in _SECRET_FIELD_NAMES:
                found.append(".".join(current))
            else:
                found.extend(_secret_paths(cast(JsonValue, nested), current))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            found.extend(_secret_paths(nested, (*path, str(index))))
    return tuple(sorted(found))
