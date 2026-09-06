"""Materialize one target-harness adaptation from a pinned component version."""

from __future__ import annotations

import sqlite3
from typing import Final, cast

from pydantic import ValidationError

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, lifecycle, revisions, setup_recast, versions
from ai_stp_cli.local.database import transaction
from ai_stp_contracts.machine_help import (
    ComponentMaterializePlan,
    ComponentMaterializeResult,
    SetupRecastMember,
)
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes, digest_canonical
from ai_stp_foundation.harnesses import HARNESS_ID_ORDER, HARNESS_IDS, HarnessId
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.provider_surfaces import TargetScope, provider_surface
from ai_stp_foundation.versioning import format_version, parse_version
from ai_stp_passports import adaptation_for, seal_envelope
from ai_stp_passports.versions import ComponentVersionPassport

PLAN_DOMAIN: Final[str] = "ai-stp:plan:v1"


def plan(
    connection: sqlite3.Connection,
    *,
    stable_id: str,
    version: str | None,
    source_harness: str,
    target_harness: str,
    overlay_id: str,
    created_at: str,
    local_only: bool,
) -> ComponentMaterializePlan:
    """Preview one adaptation without writing."""
    passport, recorded = _held(connection, stable_id, version)
    source = _source_harness(passport, source_harness)
    target = _target_harness(target_harness, source)
    member = (recorded.stable_id, recorded.version, recorded.passport_digest)
    classified = setup_recast.classify_member(connection, source, target, member)
    overlay = overlay_id or (new_id("component") if local_only else recorded.stable_id)
    if local_only:
        target_version = versions.FIRST_VERSION
    elif classified.disposition == "reuse":
        target_version = recorded.version
    else:
        major, minor = parse_version(recorded.version)
        target_version = format_version(major, minor + 1)
    losses, filesystem, network, process, profiles, parts = _bound_outputs(
        connection, passport, source, target, classified
    )
    projection_digest = digest_canonical(
        "ai-stp:plan:v1",
        cast(
            JsonValue,
            {
                "kind": "planned-projection",
                "disposition": classified.disposition,
                "parts": parts,
            },
        ),
    )
    profile_digest = digest_canonical(
        "ai-stp:plan:v1",
        cast(JsonValue, {"kind": "provider-profile-set", "digests": sorted(set(profiles))}),
    )
    body = cast(
        dict[str, JsonValue],
        {
            "stable_id": recorded.stable_id,
            "overlay_id": overlay,
            "source_version": recorded.version,
            "target_version": target_version,
            "source_harness_id": source,
            "target_harness_id": target,
            "source_passport_digest": recorded.passport_digest,
            "transform": {
                "transform_id": setup_recast.TRANSFORM_ID,
                "version": setup_recast.TRANSFORM_VERSION,
            },
            "provider_profile_digest": profile_digest,
            "projection_digest": projection_digest,
            "disposition": classified.disposition,
            "reason": classified.reason,
            "semantic_losses": losses,
            "filesystem_permissions": filesystem,
            "network_permissions": network,
            "process_permissions": process,
            "local_only": local_only,
            "created_at": created_at,
        },
    )
    return ComponentMaterializePlan(
        stable_id=recorded.stable_id,
        overlay_id=overlay,
        source_version=recorded.version,
        target_version=target_version,
        source_harness_id=source,
        target_harness_id=target,
        source_passport_digest=recorded.passport_digest,
        transform_id=setup_recast.TRANSFORM_ID,
        transform_version=setup_recast.TRANSFORM_VERSION,
        provider_profile_digest=profile_digest,
        projection_digest=projection_digest,
        disposition=classified.disposition,
        reason=classified.reason,
        semantic_losses=losses,
        filesystem_permissions=filesystem,
        network_permissions=network,
        process_permissions=process,
        local_only=local_only,
        complete=classified.disposition != "blocked",
        created_at=created_at,
        plan_digest=digest_bytes(PLAN_DOMAIN, canonize(body)),
    )


def apply(
    connection: sqlite3.Connection,
    *,
    stable_id: str,
    version: str | None,
    source_harness: str,
    target_harness: str,
    overlay_id: str,
    created_at: str,
    local_only: bool,
    expected_plan_digest: str,
    device_id: str,
    owner_id: str,
) -> ComponentMaterializeResult:
    """Record the exact still-current materialize plan."""
    preview = plan(
        connection,
        stable_id=stable_id,
        version=version,
        source_harness=source_harness,
        target_harness=target_harness,
        overlay_id=overlay_id,
        created_at=created_at,
        local_only=local_only,
    )
    if preview.plan_digest != expected_plan_digest:
        raise CliFailure(
            "AI_STP_PLAN_STALE",
            "the component materialize changed after it was reviewed",
            details={"expected": expected_plan_digest, "found": preview.plan_digest},
        )
    if not preview.complete:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the component cannot be materialized for that harness",
            details={"reason": preview.reason},
        )
    passport, recorded = _held(connection, stable_id, version)
    source = preview.source_harness_id
    target = preview.target_harness_id
    member = (recorded.stable_id, recorded.version, recorded.passport_digest)
    classified = setup_recast.classify_member(connection, source, target, member)
    bound = classified.model_copy(update={"target_version": preview.target_version})
    with transaction(connection):
        if local_only:
            result = _apply_local(
                connection,
                passport=passport,
                recorded=recorded,
                source=source,
                target=target,
                classified=bound,
                overlay_id=preview.overlay_id,
                created_at=created_at,
                device_id=device_id,
                owner_id=owner_id,
            )
        else:
            result = _apply_owned(
                connection,
                recorded=recorded,
                source=source,
                target=target,
                classified=bound,
                created_at=created_at,
                device_id=device_id,
            )
    return ComponentMaterializeResult(
        stable_id=result[0],
        version=result[1],
        source_stable_id=recorded.stable_id,
        source_version=recorded.version,
        target_harness_id=target,
        created_at=created_at,
        passport_digest=result[2],
        plan_digest=preview.plan_digest,
        local_only=local_only,
        created=result[3],
    )


def _apply_owned(
    connection: sqlite3.Connection,
    *,
    recorded: versions.Recorded,
    source: HarnessId,
    target: HarnessId,
    classified: SetupRecastMember,
    created_at: str,
    device_id: str,
) -> tuple[str, str, str, bool]:
    member = (recorded.stable_id, recorded.version, recorded.passport_digest)
    if classified.disposition == "reuse":
        return recorded.stable_id, recorded.version, recorded.passport_digest, False
    existing = versions.held(connection, recorded.stable_id, classified.target_version)
    if existing is not None:
        return existing.stable_id, existing.version, existing.passport_digest, False
    ref = setup_recast.materialize_member(
        connection,
        source_harness=source,
        target=target,
        member=member,
        classified=classified,
        device_id=device_id,
        at=created_at,
    )
    return ref.stable_id, ref.version, ref.passport_digest, True


def _apply_local(
    connection: sqlite3.Connection,
    *,
    passport: ComponentVersionPassport,
    recorded: versions.Recorded,
    source: HarnessId,
    target: HarnessId,
    classified: SetupRecastMember,
    overlay_id: str,
    created_at: str,
    device_id: str,
    owner_id: str,
) -> tuple[str, str, str, bool]:
    existing = versions.held(connection, overlay_id, versions.FIRST_VERSION)
    if existing is not None:
        return overlay_id, existing.version, existing.passport_digest, False
    derived = None
    if classified.disposition != "reuse":
        derived = setup_recast.derive_adaptation(
            connection, passport, source, target, at=created_at
        )
        if derived is None:
            raise CliFailure(
                "AI_STP_CONFLICT",
                "the component can no longer be derived for that harness",
                details={"stable_id": recorded.stable_id},
            )
    connection.execute(
        "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, ?, ?)",
        (overlay_id, "component", created_at),
    )
    connection.execute(
        """
        INSERT INTO fork_origin
            (stable_id, source_stable_id, source_version, source_digest, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            overlay_id,
            recorded.stable_id,
            recorded.version,
            recorded.passport_digest,
            created_at,
        ),
    )
    body = cast(dict[str, JsonValue], passport.model_dump(mode="json", exclude={"revision_id"}))
    body["stable_id"] = overlay_id
    body["version"] = versions.FIRST_VERSION
    body["created_at"] = created_at
    body["owner_id"] = owner_id
    body["visibility"] = "private"
    kept = [item for item in passport.adaptations if item.harness_id != target]
    held = derived if derived is not None else adaptation_for(passport, target)
    body["adaptations"] = [
        *[cast(JsonValue, item.model_dump(mode="json")) for item in kept],
        cast(JsonValue, held.model_dump(mode="json")),
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
        stable_id=overlay_id,
        version=versions.FIRST_VERSION,
        passport_digest=digest,
        revision_id=stored.revision_id,
        at=created_at,
    )
    lifecycle.record_overlay(
        connection,
        revision_id=stored.revision_id,
        source_kind="generated",
        source_ref=recorded.passport_digest,
        base_digest=recorded.passport_digest,
        at=created_at,
    )
    return overlay_id, versions.FIRST_VERSION, digest, True


def _bound_outputs(
    connection: sqlite3.Connection,
    passport: ComponentVersionPassport,
    source: HarnessId,
    target: HarnessId,
    classified: SetupRecastMember,
) -> tuple[list[str], list[str], list[str], list[str], list[str], list[JsonValue]]:
    losses: list[str] = []
    filesystem: list[str] = []
    network: list[str] = []
    process: list[str] = []
    profiles: list[str] = []
    parts: list[JsonValue] = []
    if classified.disposition == "reuse":
        existing = adaptation_for(passport, target)
        for scope in existing.scope_adaptations:
            filesystem.extend(scope.permissions.filesystem)
            network.extend(scope.permissions.network)
            process.extend(scope.permissions.process)
            losses.extend(scope.semantic_losses)
            profiles.append(scope.required_surface.profile_digest)
            parts.append(scope.projection_artifact.digest)
        return _unique(losses, filesystem, network, process, profiles, parts)
    if classified.disposition == "blocked":
        parts.append(classified.reason)
        return _unique(losses, filesystem, network, process, profiles, parts)
    preview = setup_recast.preview_projection(connection, passport, source, target)
    if preview is None:
        parts.append(classified.reason)
        return _unique(losses, filesystem, network, process, profiles, parts)
    for item in preview:
        filesystem.extend(item.source.permissions.filesystem)
        network.extend(item.source.permissions.network)
        process.extend(item.source.permissions.process)
        losses.extend(item.losses)
        surface = provider_surface(target, cast("TargetScope", item.rule.target_scope))
        profiles.append(surface.profile_digest)
        for path, payload in sorted(item.files.items()):
            parts.append(
                {
                    "path": path,
                    "digest": digest_bytes("ai-stp:artifact:v1", payload),
                    "mode": item.modes[path],
                }
            )
    return _unique(losses, filesystem, network, process, profiles, parts)


def _unique(
    losses: list[str],
    filesystem: list[str],
    network: list[str],
    process: list[str],
    profiles: list[str],
    parts: list[JsonValue],
) -> tuple[list[str], list[str], list[str], list[str], list[str], list[JsonValue]]:
    return (
        list(dict.fromkeys(losses)),
        list(dict.fromkeys(filesystem)),
        list(dict.fromkeys(network)),
        list(dict.fromkeys(process)),
        profiles,
        parts,
    )


def _held(
    connection: sqlite3.Connection, stable_id: str, version: str | None
) -> tuple[ComponentVersionPassport, versions.Recorded]:
    if version:
        recorded = versions.held(connection, stable_id, version)
        if recorded is None:
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "that component version is not in the local registry",
                details={"id": stable_id, "version": version},
            )
    else:
        held = versions.line(connection, stable_id)
        if not held:
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "that component is not in the local registry",
                details={"id": stable_id},
            )
        recorded = held[-1]
    stored = revisions.get(connection, recorded.revision_id)
    if stored is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the recorded component revision is missing",
            details={"id": stable_id},
        )
    try:
        passport = ComponentVersionPassport.model_validate(stored.envelope.model_dump(mode="json"))
    except ValidationError as error:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the recorded component is not an immutable version passport",
            details={"id": stable_id},
        ) from error
    return passport, recorded


def _source_harness(passport: ComponentVersionPassport, named: str) -> HarnessId:
    available: tuple[HarnessId, ...] = tuple(
        harness
        for harness in HARNESS_ID_ORDER
        if any(item.harness_id == harness for item in passport.adaptations)
    )
    if named:
        for harness in available:
            if harness == named:
                return harness
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the source harness is not an adaptation of this version",
            details={"harness_id": named},
        )
    if len(available) == 1:
        return available[0]
    raise CliFailure(
        "AI_STP_VALIDATION_ERROR",
        "a source harness is required when the version names more than one adaptation",
        details={"harnesses": ",".join(available)},
    )


def _target_harness(target: str, source: str) -> HarnessId:
    for harness in HARNESS_IDS:
        if harness != target:
            continue
        if harness == source:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "materialize requires a different target harness",
                details={"harness_id": source},
            )
        return harness
    raise CliFailure("AI_STP_VALIDATION_ERROR", "the target harness is unknown")
