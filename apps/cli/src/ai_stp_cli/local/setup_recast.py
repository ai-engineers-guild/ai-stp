"""Recast one complete setup onto another harness (SPEC-062)."""

from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Final, Literal, cast

import tomlkit
from pydantic import ValidationError

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import (
    cache,
    composition,
    content,
    contribution,
    revisions,
    setup_versions,
    versions,
)
from ai_stp_cli.local.components import Rule
from ai_stp_cli.local.database import transaction
from ai_stp_contracts.machine_help import SetupRecastMember, SetupRecastPlan, SetupRecastResult
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes, digest_canonical
from ai_stp_foundation.harnesses import HARNESS_IDS, HarnessId
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.provider_surfaces import PROVIDER_SURFACES, provider_surface
from ai_stp_foundation.refs import SetupRef
from ai_stp_passports import (
    ComponentVersionPassport,
    SetupVersionPassport,
    adaptation_for,
    build_projection,
    seal_adaptation,
    seal_envelope,
)
from ai_stp_passports.versions import ComponentAdaptation, ScopeAdaptation, TargetScope

PLAN_DOMAIN: Final[str] = "ai-stp:plan:v1"
TRANSFORM_ID: Final[str] = "harness-native-rewrite"
TRANSFORM_VERSION: Final[str] = "1.1"
_NON_DERIVABLE: Final[frozenset[str]] = frozenset({"setting", "cli"})
_MCP_FILE_WRAPPERS: Final[tuple[str, ...]] = ("mcpServers", "mcp_servers", "mcp")
Disposition = Literal["reuse", "derive", "blocked"]


def plan(
    connection: sqlite3.Connection,
    *,
    source_id: str,
    source_version: str | None,
    target_harness: str,
    setup_id: str,
    created_at: str,
) -> SetupRecastPlan:
    """Preview one recast without writing."""
    source, members = _source_graph(connection, source_id, source_version)
    target = _target_harness(target_harness, source.harness_id)
    planned = tuple(_classify(connection, source.harness_id, target, item) for item in members)
    return _plan_view(source, target, setup_id, created_at, planned)


def apply(
    connection: sqlite3.Connection,
    *,
    source_id: str,
    source_version: str | None,
    target_harness: str,
    setup_id: str,
    created_at: str,
    expected_plan_digest: str,
    device_id: str,
    owner_id: str,
) -> SetupRecastResult:
    """Record the exact recast the caller reviewed."""
    source, members = _source_graph(connection, source_id, source_version)
    target = _target_harness(target_harness, source.harness_id)
    planned = tuple(_classify(connection, source.harness_id, target, item) for item in members)
    preview = _plan_view(source, target, setup_id, created_at, planned)
    if preview.plan_digest != expected_plan_digest:
        raise CliFailure(
            "AI_STP_PLAN_STALE",
            "the setup recast changed after it was reviewed",
            details={"expected": expected_plan_digest, "found": preview.plan_digest},
        )
    if not preview.complete:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the recast is not complete",
            details={
                "blocked": ",".join(
                    item.stable_id for item in preview.members if item.disposition == "blocked"
                )
            },
        )
    if versions.held(connection, setup_id, preview.version) is not None:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "that setup version already exists",
            details={"id": setup_id, "version": preview.version},
        )
    with transaction(connection):
        refs: list[setup_versions.MemberRef] = []
        for item, classified in zip(members, planned, strict=True):
            refs.append(
                _materialize_member(
                    connection,
                    source_harness=source.harness_id,
                    target=target,
                    member=item,
                    classified=classified,
                    device_id=device_id,
                    at=created_at,
                )
            )
        source_digest = cache.digest_of(cast(JsonValue, source.model_dump(mode="json")))
        passport = setup_versions.passport_content(
            connection,
            stable_id=setup_id,
            version=preview.version,
            owner_id=owner_id,
            project_id="",
            harness_id=target,
            snapshot=source_digest,
            members=tuple(refs),
            at=created_at,
            ported_from=cast(
                dict[str, JsonValue],
                SetupRef(
                    stable_id=source.stable_id,
                    version=source.version,
                    passport_digest=source_digest,
                ).model_dump(mode="json"),
            ),
            related_setup_ids=[source.stable_id],
            name=source.name,
            description=source.description,
        )
        stored = revisions.commit(connection, passport, device_id=device_id)
        passport_digest = cache.digest_of(cast(JsonValue, stored.envelope.model_dump(mode="json")))
        versions.record(
            connection,
            stable_id=setup_id,
            version=preview.version,
            passport_digest=passport_digest,
            revision_id=stored.revision_id,
            at=created_at,
        )
    return SetupRecastResult(
        setup_id=setup_id,
        version=preview.version,
        source_setup_id=source.stable_id,
        source_version=source.version,
        created_at=created_at,
        passport_digest=passport_digest,
        plan_digest=preview.plan_digest,
        created=True,
    )


def _target_harness(target: str, source: str) -> HarnessId:
    for harness in HARNESS_IDS:
        if harness != target:
            continue
        if harness == source:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "recast requires a different target harness",
                details={"harness_id": source},
            )
        return harness
    raise CliFailure("AI_STP_VALIDATION_ERROR", "the target harness is unknown")


def _source_graph(
    connection: sqlite3.Connection, source_id: str, source_version: str | None
) -> tuple[SetupVersionPassport, tuple[tuple[str, str, str], ...]]:
    recorded = _held_setup(connection, source_id, source_version)
    stored = revisions.get(connection, recorded.revision_id)
    if stored is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the recorded setup revision is missing",
            details={"id": source_id, "version": recorded.version},
        )
    try:
        passport = SetupVersionPassport.model_validate(stored.envelope.model_dump(mode="json"))
    except ValidationError as error:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the recorded setup is not an immutable version passport",
            details={"id": source_id},
        ) from error
    members = tuple(
        (item.stable_id, item.version, item.passport_digest) for item in passport.components
    )
    if not members:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the source setup has no components to recast",
            details={"id": source_id},
        )
    return passport, members


def _classify(
    connection: sqlite3.Connection,
    source_harness: HarnessId,
    target: HarnessId,
    member: tuple[str, str, str],
) -> SetupRecastMember:
    passport = _component_passport(connection, member)
    try:
        adaptation_for(passport, target)
    except ValueError:
        reason = _blocked_reason(passport, source_harness, target)
        if (
            reason is None
            and _preview_projection(connection, passport, source_harness, target) is None
        ):
            reason = "the recorded projection cannot be mapped without losing files or modes"
        if reason is None:
            return SetupRecastMember(
                stable_id=member[0],
                source_version=member[1],
                target_version=versions.next_minor(connection, member[0]),
                component_type=passport.component_type,
                disposition="derive",
                reason="derive a native adaptation for the target harness",
            )
        return SetupRecastMember(
            stable_id=member[0],
            source_version=member[1],
            target_version=member[1],
            component_type=passport.component_type,
            disposition="blocked",
            reason=reason,
        )
    return SetupRecastMember(
        stable_id=member[0],
        source_version=member[1],
        target_version=member[1],
        component_type=passport.component_type,
        disposition="reuse",
        reason="the pinned version already has the target adaptation",
    )


def _blocked_reason(
    passport: ComponentVersionPassport, source_harness: HarnessId, target: HarnessId
) -> str | None:
    if passport.component_type in _NON_DERIVABLE:
        return "settings and cli components do not derive across harnesses"
    try:
        source_adaptation = adaptation_for(passport, source_harness)
    except ValueError:
        return "the source setup pin has no adaptation for its own harness"
    source_scope = source_adaptation.scope_adaptations[0].scope
    source_rule = composition.rule_for(
        passport.component_type, source_harness, scope=source_scope
    ) or composition.rule_for(passport.component_type, source_harness)
    rule = composition.rule_for(
        passport.component_type, target, scope=source_scope
    ) or composition.rule_for(passport.component_type, target)
    if rule is None:
        return "the target harness has no native surface for this kind"
    if (source_rule is not None and source_rule.projection_kind == "package") or (
        rule.projection_kind == "package"
    ):
        return "an MCP plugin package cannot be derived automatically"
    if rule.declared_key and passport.component_type != "mcp":
        return "a host-file contribution cannot be derived automatically"
    if source_rule is not None and source_rule.declared_key and passport.component_type != "mcp":
        return "a host-file contribution cannot be derived automatically"
    return None


def _materialize_member(
    connection: sqlite3.Connection,
    *,
    source_harness: HarnessId,
    target: HarnessId,
    member: tuple[str, str, str],
    classified: SetupRecastMember,
    device_id: str,
    at: str,
) -> setup_versions.MemberRef:
    passport = _component_passport(connection, member)
    if classified.disposition == "reuse":
        return setup_versions.MemberRef(member[0], member[1], member[2])
    derived = _derive_adaptation(connection, passport, source_harness, target, at=at)
    if derived is None:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the recast member can no longer be derived",
            details={"stable_id": member[0]},
        )
    body = cast(dict[str, JsonValue], passport.model_dump(mode="json", exclude={"revision_id"}))
    body["version"] = classified.target_version
    body["created_at"] = at
    body["adaptations"] = [
        *[cast(JsonValue, item.model_dump(mode="json")) for item in passport.adaptations],
        cast(JsonValue, derived.model_dump(mode="json")),
    ]
    sealed = seal_envelope(body)
    stored = revisions.commit(
        connection,
        cast(dict[str, JsonValue], sealed.model_dump(mode="json", exclude={"revision_id"})),
        device_id=device_id,
    )
    digest = cache.digest_of(cast(JsonValue, stored.envelope.model_dump(mode="json")))
    versions.record(
        connection,
        stable_id=member[0],
        version=classified.target_version,
        passport_digest=digest,
        revision_id=stored.revision_id,
        at=at,
    )
    return setup_versions.MemberRef(member[0], classified.target_version, digest)


def _preview_projection(
    connection: sqlite3.Connection,
    passport: ComponentVersionPassport,
    source_harness: HarnessId,
    target: HarnessId,
) -> tuple[ScopeAdaptation, Rule, dict[str, bytes], dict[str, int]] | None:
    """Read and map the recorded files and modes without creating registry state."""
    if _blocked_reason(passport, source_harness, target) is not None:
        return None
    source_scope = adaptation_for(passport, source_harness).scope_adaptations[0]
    rule = composition.rule_for(
        passport.component_type, target, scope=source_scope.scope
    ) or composition.rule_for(passport.component_type, target)
    if rule is None or (target, rule.target_scope) not in PROVIDER_SURFACES:
        return None
    payload = content.get(connection, source_scope.projection_artifact.digest)
    files = _projection_files(source_scope, payload)
    source_modes = {
        member.path: member.mode for member in source_scope.members if member.object_type == "file"
    }
    if passport.component_type == "mcp":
        remapped = _derive_mcp_files(files, source_harness, source_scope.scope, rule)
        # MCP conversion is one document to one document, not a package transform.
        modes = (
            {rule.relative: next(iter(source_modes.values()))} if len(source_modes) == 1 else None
        )
    else:
        remapped = _remap_files(
            files, passport.component_type, source_harness, source_scope.scope, rule
        )
        modes = _remap_files(
            source_modes, passport.component_type, source_harness, source_scope.scope, rule
        )
    if not remapped or modes is None or remapped.keys() != modes.keys():
        return None
    return source_scope, rule, remapped, modes


def _derive_adaptation(
    connection: sqlite3.Connection,
    passport: ComponentVersionPassport,
    source_harness: HarnessId,
    target: HarnessId,
    *,
    at: str,
) -> ComponentAdaptation | None:
    preview = _preview_projection(connection, passport, source_harness, target)
    if preview is None:
        return None
    source_scope, rule, remapped, modes = preview
    contributing = bool(rule.declared_key)
    scope_name = cast(TargetScope, rule.target_scope)
    members: list[JsonValue] = []
    for path, payload in sorted(remapped.items()):
        stored = content.put(connection, payload, at=at)
        members.append(
            _projection_member(
                path,
                stored.digest,
                stored.byte_length,
                rule if contributing else None,
                mode=modes[path],
            )
        )
    surface = provider_surface(target, scope_name)
    provider_kind = rule.provider_kind or passport.component_type
    scope_document: dict[str, JsonValue] = {
        "scope": scope_name,
        "projection_format": "ai-stp-adaptation-projection/1",
        "projection_artifact": {"digest": "sha256:" + "0" * 64, "size_bytes": 1},
        "provider_component_kind": provider_kind,
        "projection_kind": rule.projection_kind,
        "required_surface": {
            "profile_id": surface.profile_id,
            "profile_digest": surface.profile_digest,
            "bundle_format": surface.bundle_format,
        },
        "permissions": passport.permissions.model_dump(mode="json"),
        "members": members,
        "supported_harness_versions": [],
        "supported_os": [],
        "supported_arch": [],
        "technical_support": "experimental",
        "technical_support_reason": "derived recast adaptation pending assessment",
        "semantic_losses": [],
    }
    provisional = ScopeAdaptation.model_validate(scope_document)
    projection = build_projection(provisional, remapped)
    stored_projection = content.put(connection, projection, at=at)
    scope_document["projection_artifact"] = {
        "digest": stored_projection.digest,
        "size_bytes": stored_projection.byte_length,
    }
    transform_body: dict[str, JsonValue] = {
        "transform_id": TRANSFORM_ID,
        "version": TRANSFORM_VERSION,
        "source_harness": source_harness,
        "target_harness": target,
        "component_type": passport.component_type,
        "target_path": rule.relative,
    }
    return seal_adaptation(
        {
            "harness_id": target,
            "implementation_mode": "derived",
            "source_artifact": {
                "digest": source_scope.projection_artifact.digest,
                "size_bytes": source_scope.projection_artifact.size_bytes,
            },
            "transform": {
                "transform_id": TRANSFORM_ID,
                "version": TRANSFORM_VERSION,
                "digest": digest_canonical("ai-stp:component-adaptation:v1", transform_body),
            },
            "logical_component_type": passport.component_type,
            "scope_adaptations": [scope_document],
        }
    )


def _projection_member(
    path: str, digest: str, byte_length: int, contributing: Rule | None, *, mode: int
) -> dict[str, JsonValue]:
    key = contributing.declared_key if contributing is not None else ""
    suffix = PurePosixPath(path).suffix.casefold()
    parser = "toml/1" if suffix == ".toml" else "json/1" if key else None
    return {
        "path": path,
        "object_type": "file",
        "mode": mode,
        "content_artifact": {"digest": digest, "size_bytes": byte_length},
        "native_ids": [],
        "content_format": "application/octet-stream",
        "parser_id": parser,
        "ownership": "contribution" if key else "whole",
        "ownership_key": key or None,
        "write_semantics": "merge" if key else "replace",
        "withdrawal_semantics": "preserve_unowned" if key else "remove_path",
    }


def _derive_mcp_files(
    files: Mapping[str, bytes],
    source_harness: HarnessId,
    source_scope: str,
    target: Rule,
) -> dict[str, bytes] | None:
    source_rule = composition.rule_for("mcp", source_harness, scope=source_scope) or (
        composition.rule_for("mcp", source_harness)
    )
    servers = _logical_mcp_servers(files, source_rule)
    encoded = _encode_mcp(servers, target) if servers is not None else None
    if encoded is None:
        return None
    return {target.relative: encoded}


def _logical_mcp_servers(
    files: Mapping[str, bytes], source_rule: Rule | None
) -> dict[str, JsonValue] | None:
    if len(files) != 1:
        return None
    path, payload = next(iter(files.items()))
    host = source_rule.relative if source_rule is not None else path
    if source_rule is not None and source_rule.declared_key:
        parsed = contribution.parse_value(host=host, content=payload)
        return parsed if isinstance(parsed, dict) else None
    return _unwrap_mcp(_parse_mcp_document(host, payload))


def _parse_mcp_document(host: str, payload: bytes) -> JsonValue | None:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return None
    suffix = PurePosixPath(host).suffix.casefold()
    try:
        if suffix == ".toml":
            return cast("JsonValue", tomlkit.parse(text).unwrap())
        return cast("JsonValue", json.loads(text))
    except ValueError:
        return None


def _unwrap_mcp(document: JsonValue | None) -> dict[str, JsonValue] | None:
    if not isinstance(document, dict):
        return None
    for key in _MCP_FILE_WRAPPERS:
        held = document.get(key)
        if isinstance(held, dict):
            return cast("dict[str, JsonValue]", held)
    if document and all(isinstance(value, dict) for value in document.values()):
        return cast("dict[str, JsonValue]", document)
    return None


def _encode_mcp(servers: Mapping[str, JsonValue], target: Rule) -> bytes | None:
    if target.shape != "file":
        return None
    body: dict[str, JsonValue] = dict(servers)
    suffix = PurePosixPath(target.relative).suffix.casefold()
    if not target.declared_key:
        wrapper = "mcp_servers" if suffix == ".toml" else "mcpServers"
        body = {wrapper: body}
    if suffix == ".toml":
        return tomlkit.dumps(body).encode("utf-8")
    if suffix == ".json":
        return (json.dumps(body, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return None


def _projection_files(scope: ScopeAdaptation, payload: bytes) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(payload), mode="r") as archive:
        for member in scope.members:
            if member.object_type != "file":
                continue
            files[member.path] = archive.read(member.path)
    return files


def _remap_files[T](
    files: Mapping[str, T],
    component_type: str,
    source_harness: HarnessId,
    source_scope: str,
    target: Rule,
) -> dict[str, T] | None:
    """Map a complete declared subtree without flattening or overwriting members.

    The same mapping is used for bytes and modes. A path outside the source
    surface is not a basename alias: guessing one can silently replace another
    file or detach a script from its package-relative resources.
    """
    if target.declared_key or not files:
        return None
    if target.shape == "file":
        if len(files) != 1:
            return None
        return {target.relative: next(iter(files.values()))}
    if target.shape != "directory":
        return None
    source_rule = composition.rule_for(component_type, source_harness, scope=source_scope)
    if source_rule is None or source_rule.shape != "directory":
        return None
    prefix = source_rule.relative.rstrip("/") + "/"
    remapped: dict[str, T] = {}
    seen: set[str] = set()
    root = target.relative.rstrip("/")
    for path, payload in files.items():
        if not path.startswith(prefix) or path == prefix:
            return None
        destination = f"{root}/{path[len(prefix):]}"
        folded = destination.casefold()
        if folded in seen:
            return None
        seen.add(folded)
        remapped[destination] = payload
    return remapped


def _component_passport(
    connection: sqlite3.Connection, member: tuple[str, str, str]
) -> ComponentVersionPassport:
    recorded = versions.held(connection, member[0], member[1])
    if recorded is None or recorded.passport_digest != member[2]:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "a recast member is not in the local registry",
            details={"stable_id": member[0], "version": member[1]},
        )
    stored = revisions.get(connection, recorded.revision_id)
    if stored is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "a recast member revision is missing",
            details={"stable_id": member[0]},
        )
    try:
        return ComponentVersionPassport.model_validate(stored.envelope.model_dump(mode="json"))
    except ValidationError as error:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "a recast member is not an immutable component version",
            details={"stable_id": member[0]},
        ) from error


def _held_setup(
    connection: sqlite3.Connection, setup_id: str, version: str | None
) -> versions.Recorded:
    if version:
        recorded = versions.held(connection, setup_id, version)
        if recorded is None:
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "that setup version is not in the local registry",
                details={"id": setup_id, "version": version},
            )
        return recorded
    held = versions.line(connection, setup_id)
    if not held:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "that setup is not in the local registry",
            details={"id": setup_id},
        )
    return held[-1]


def _plan_view(
    source: SetupVersionPassport,
    target: HarnessId,
    setup_id: str,
    created_at: str,
    members: tuple[SetupRecastMember, ...],
) -> SetupRecastPlan:
    if not setup_id:
        setup_id = new_id("setup")
    body: dict[str, JsonValue] = {
        "source_setup_id": source.stable_id,
        "source_version": source.version,
        "source_harness_id": source.harness_id,
        "target_harness_id": target,
        "setup_id": setup_id,
        "version": versions.FIRST_VERSION,
        "created_at": created_at,
        "transform": {"transform_id": TRANSFORM_ID, "version": TRANSFORM_VERSION},
        "members": [cast(JsonValue, item.model_dump(mode="json")) for item in members],
    }
    return SetupRecastPlan(
        setup_id=setup_id,
        version=versions.FIRST_VERSION,
        source_setup_id=source.stable_id,
        source_version=source.version,
        source_harness_id=source.harness_id,
        target_harness_id=target,
        created_at=created_at,
        complete=all(item.disposition != "blocked" for item in members),
        plan_digest=digest_bytes(PLAN_DOMAIN, canonize(body)),
        members=list(members),
    )
