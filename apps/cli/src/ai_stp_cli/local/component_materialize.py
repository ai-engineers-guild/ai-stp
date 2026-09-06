"""Materialize one target-harness adaptation from a pinned component version."""

from __future__ import annotations

import sqlite3
from typing import Final, Literal, cast

from pydantic import ValidationError

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, lifecycle, revisions, setup_recast, versions
from ai_stp_cli.local.database import transaction
from ai_stp_contracts.machine_help import (
    ComponentMaterializePlan,
    ComponentMaterializeResult,
    ComponentMaterializeTarget,
    SetupRecastMember,
)
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes, digest_canonical
from ai_stp_foundation.harnesses import HARNESS_ID_ORDER, HARNESS_IDS, HarnessId
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.provider_surfaces import TargetScope, provider_surface
from ai_stp_foundation.versioning import format_version, parse_version
from ai_stp_passports import adaptation_for, seal_envelope
from ai_stp_passports.envelope import verify_revision_id
from ai_stp_passports.versions import ComponentAdaptation, ComponentVersionPassport

PLAN_DOMAIN: Final[str] = "ai-stp:plan:v1"


def plan(
    connection: sqlite3.Connection,
    *,
    stable_id: str,
    version: str | None,
    source_harness: str,
    target_harness: str | tuple[str, ...],
    overlay_id: str,
    created_at: str,
    local_only: bool,
    all_missing: bool = False,
) -> ComponentMaterializePlan:
    """Preview one or more adaptations without writing."""
    passport, recorded = _held(connection, stable_id, version)
    source = _source_harness(passport, source_harness)
    requested = _requested_targets(passport, source, target_harness, all_missing)
    member = (recorded.stable_id, recorded.version, recorded.passport_digest)
    targets: list[ComponentMaterializeTarget] = []
    all_losses: list[str] = []
    all_filesystem: list[str] = []
    all_network: list[str] = []
    all_process: list[str] = []
    all_profiles: list[str] = []
    all_parts: list[JsonValue] = []
    for target in requested:
        classified = setup_recast.classify_member(connection, source, target, member)
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
        targets.append(
            ComponentMaterializeTarget(
                target_harness_id=target,
                disposition=classified.disposition,
                reason=classified.reason,
                projection_digest=projection_digest,
                semantic_losses=losses,
                filesystem_permissions=filesystem,
                network_permissions=network,
                process_permissions=process,
            )
        )
        all_losses.extend(losses)
        all_filesystem.extend(filesystem)
        all_network.extend(network)
        all_process.extend(process)
        all_profiles.extend(profiles)
        all_parts.extend(parts)
    overlay = overlay_id or (new_id("component") if local_only else recorded.stable_id)
    needs_version = any(item.disposition == "derive" for item in targets)
    if local_only:
        target_version = versions.FIRST_VERSION
    elif not needs_version:
        target_version = recorded.version
    else:
        major, minor = parse_version(recorded.version)
        target_version = format_version(major, minor + 1)
    primary = targets[0]
    if any(item.disposition == "blocked" for item in targets):
        summary_disposition: Literal["reuse", "derive", "blocked"] = "blocked"
        summary_reason = next(item.reason for item in targets if item.disposition == "blocked")
    elif needs_version:
        summary_disposition = "derive"
        summary_reason = "derive a native adaptation for every requested harness"
    else:
        summary_disposition = "reuse"
        summary_reason = "the pinned version already has every requested adaptation"
    losses = list(dict.fromkeys(all_losses))
    filesystem = list(dict.fromkeys(all_filesystem))
    network = list(dict.fromkeys(all_network))
    process = list(dict.fromkeys(all_process))
    projection_digest = digest_canonical(
        "ai-stp:plan:v1",
        cast(
            JsonValue,
            {
                "kind": "planned-projection-set",
                "targets": [
                    {"harness_id": item.target_harness_id, "digest": item.projection_digest}
                    for item in targets
                ],
                "parts": all_parts,
            },
        ),
    )
    profile_digest = digest_canonical(
        "ai-stp:plan:v1",
        cast(JsonValue, {"kind": "provider-profile-set", "digests": sorted(set(all_profiles))}),
    )
    body = cast(
        dict[str, JsonValue],
        {
            "stable_id": recorded.stable_id,
            "overlay_id": overlay,
            "source_version": recorded.version,
            "target_version": target_version,
            "source_harness_id": source,
            "target_harness_id": primary.target_harness_id,
            "source_passport_digest": recorded.passport_digest,
            "transform": {
                "transform_id": setup_recast.TRANSFORM_ID,
                "version": setup_recast.TRANSFORM_VERSION,
            },
            "provider_profile_digest": profile_digest,
            "projection_digest": projection_digest,
            "disposition": summary_disposition,
            "reason": summary_reason,
            "semantic_losses": losses,
            "filesystem_permissions": filesystem,
            "network_permissions": network,
            "process_permissions": process,
            "targets": [cast(JsonValue, item.model_dump(mode="json")) for item in targets],
            "local_only": local_only,
            "all_missing": all_missing,
            "created_at": created_at,
        },
    )
    return ComponentMaterializePlan(
        stable_id=recorded.stable_id,
        overlay_id=overlay,
        source_version=recorded.version,
        target_version=target_version,
        source_harness_id=source,
        target_harness_id=primary.target_harness_id,
        source_passport_digest=recorded.passport_digest,
        transform_id=setup_recast.TRANSFORM_ID,
        transform_version=setup_recast.TRANSFORM_VERSION,
        provider_profile_digest=profile_digest,
        projection_digest=projection_digest,
        disposition=summary_disposition,
        reason=summary_reason,
        semantic_losses=losses,
        filesystem_permissions=filesystem,
        network_permissions=network,
        process_permissions=process,
        targets=targets,
        local_only=local_only,
        complete=all(item.disposition != "blocked" for item in targets),
        created_at=created_at,
        plan_digest=digest_bytes(PLAN_DOMAIN, canonize(body)),
    )


def apply(
    connection: sqlite3.Connection,
    *,
    stable_id: str,
    version: str | None,
    source_harness: str,
    target_harness: str | tuple[str, ...],
    overlay_id: str,
    created_at: str,
    local_only: bool,
    expected_plan_digest: str,
    device_id: str,
    owner_id: str,
    all_missing: bool = False,
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
        all_missing=all_missing,
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
    with transaction(connection):
        if local_only:
            result = _apply_local(
                connection,
                passport=passport,
                recorded=recorded,
                source=source,
                preview=preview,
                created_at=created_at,
                device_id=device_id,
                owner_id=owner_id,
            )
        else:
            result = _apply_owned(
                connection,
                recorded=recorded,
                source=source,
                preview=preview,
                created_at=created_at,
                device_id=device_id,
            )
    harnesses: list[HarnessId] = [item.target_harness_id for item in preview.targets]
    return ComponentMaterializeResult(
        stable_id=result[0],
        version=result[1],
        source_stable_id=recorded.stable_id,
        source_version=recorded.version,
        target_harness_id=harnesses[0],
        target_harness_ids=harnesses,
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
    preview: ComponentMaterializePlan,
    created_at: str,
    device_id: str,
) -> tuple[str, str, str, bool]:
    if all(item.disposition == "reuse" for item in preview.targets):
        return recorded.stable_id, recorded.version, recorded.passport_digest, False
    existing = versions.held(connection, recorded.stable_id, preview.target_version)
    # A coordinate already being occupied is not proof of an identical retry.
    # Reconstruct the intended passport and compare it before reusing that version.
    passport, _current = _held(connection, recorded.stable_id, recorded.version)
    added = _derived_adaptations(connection, passport, source, preview, created_at)
    replaced = {item.harness_id for item in added}
    kept = [item for item in passport.adaptations if item.harness_id not in replaced]
    digest = _record_version(
        connection,
        passport=passport,
        stable_id=recorded.stable_id,
        version=preview.target_version,
        adaptations=(*kept, *added),
        created_at=created_at,
        device_id=device_id,
    )
    return recorded.stable_id, preview.target_version, digest, existing is None


def _apply_local(
    connection: sqlite3.Connection,
    *,
    passport: ComponentVersionPassport,
    recorded: versions.Recorded,
    source: HarnessId,
    preview: ComponentMaterializePlan,
    created_at: str,
    device_id: str,
    owner_id: str,
) -> tuple[str, str, str, bool]:
    overlay_id = preview.overlay_id
    existing = versions.held(connection, overlay_id, versions.FIRST_VERSION)
    if existing is not None:
        origin = connection.execute(
            "SELECT source_stable_id, source_version, source_digest FROM fork_origin "
            "WHERE stable_id = ?",
            (overlay_id,),
        ).fetchone()
        if (
            origin is None
            or tuple(origin) != (recorded.stable_id, recorded.version, recorded.passport_digest)
            or not lifecycle.version_is_overlay(connection, overlay_id, existing.version)
        ):
            raise CliFailure(
                "AI_STP_CONFLICT",
                "the overlay identity already belongs to a different origin",
                details={"stable_id": overlay_id},
            )
    added = _derived_adaptations(connection, passport, source, preview, created_at)
    replaced = {item.harness_id for item in added}
    kept = [item for item in passport.adaptations if item.harness_id not in replaced]
    if existing is None:
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
    digest = _record_version(
        connection,
        passport=passport,
        stable_id=overlay_id,
        version=versions.FIRST_VERSION,
        adaptations=(*kept, *added),
        created_at=created_at,
        device_id=device_id,
        owner_id=owner_id,
        visibility="private",
    )
    if existing is not None:
        return overlay_id, existing.version, digest, False
    stored = versions.held(connection, overlay_id, versions.FIRST_VERSION)
    if stored is None:  # pragma: no cover - recorded above
        raise CliFailure("AI_STP_INTERNAL", "the overlay version vanished after being written")
    lifecycle.record_overlay(
        connection,
        revision_id=stored.revision_id,
        source_kind="generated",
        source_ref=recorded.passport_digest,
        base_digest=recorded.passport_digest,
        at=created_at,
    )
    return overlay_id, versions.FIRST_VERSION, digest, True


def _derived_adaptations(
    connection: sqlite3.Connection,
    passport: ComponentVersionPassport,
    source: HarnessId,
    preview: ComponentMaterializePlan,
    created_at: str,
) -> tuple[ComponentAdaptation, ...]:
    added: list[ComponentAdaptation] = []
    for item in preview.targets:
        if item.disposition == "reuse":
            added.append(adaptation_for(passport, item.target_harness_id))
            continue
        derived = setup_recast.derive_adaptation(
            connection, passport, source, item.target_harness_id, at=created_at
        )
        if derived is None:
            raise CliFailure(
                "AI_STP_CONFLICT",
                "the component can no longer be derived for that harness",
                details={
                    "stable_id": passport.stable_id,
                    "harness_id": item.target_harness_id,
                },
            )
        added.append(derived)
    return tuple(added)


def _record_version(
    connection: sqlite3.Connection,
    *,
    passport: ComponentVersionPassport,
    stable_id: str,
    version: str,
    adaptations: tuple[ComponentAdaptation, ...],
    created_at: str,
    device_id: str,
    owner_id: str | None = None,
    visibility: str | None = None,
) -> str:
    body = cast(dict[str, JsonValue], passport.model_dump(mode="json", exclude={"revision_id"}))
    body["stable_id"] = stable_id
    body["version"] = version
    body["created_at"] = created_at
    if owner_id is not None:
        body["owner_id"] = owner_id
    if visibility is not None:
        body["visibility"] = visibility
    body["adaptations"] = [cast(JsonValue, item.model_dump(mode="json")) for item in adaptations]
    sealed = seal_envelope(body)
    expected = cache.digest_of(cast(JsonValue, sealed.model_dump(mode="json")))
    existing = versions.held(connection, stable_id, version)
    if existing is not None:
        held = revisions.get(connection, existing.revision_id)
        if (
            existing.passport_digest != expected
            or held is None
            or held.revision_id != sealed.revision_id
            or cache.digest_of(cast(JsonValue, held.envelope.model_dump(mode="json"))) != expected
        ):
            raise CliFailure(
                "AI_STP_CONFLICT",
                "that component version already stands for different materialized content",
                details={"stable_id": stable_id, "version": version},
            )
        return expected
    stored = revisions.commit(
        connection,
        cast(dict[str, JsonValue], sealed.model_dump(mode="json", exclude={"revision_id"})),
        device_id=device_id,
    )
    digest = cache.digest_of(cast(JsonValue, stored.envelope.model_dump(mode="json")))
    versions.record(
        connection,
        stable_id=stable_id,
        version=version,
        passport_digest=digest,
        revision_id=stored.revision_id,
        at=created_at,
    )
    return digest


def _requested_targets(
    passport: ComponentVersionPassport,
    source: HarnessId,
    named: str | tuple[str, ...],
    all_missing: bool,
) -> tuple[HarnessId, ...]:
    held = {item.harness_id for item in passport.adaptations}
    names = _string_tuple(named)
    if all_missing:
        if names:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "all-missing cannot be combined with an explicit target harness",
            )
        missing = tuple(
            harness for harness in HARNESS_ID_ORDER if harness != source and harness not in held
        )
        if not missing:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "the version already names an adaptation for every other harness",
            )
        return cast(tuple[HarnessId, ...], missing)
    if not names:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "the target harness is required")
    resolved: list[HarnessId] = []
    seen: set[HarnessId] = set()
    for item in names:
        target = _target_harness(item, source)
        if target in seen:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "a target harness was named more than once",
                details={"harness_id": target},
            )
        seen.add(target)
        resolved.append(target)
    return tuple(resolved)


def _string_tuple(value: str | tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    return tuple(item for item in value if item)


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
    if (
        passport.stable_id != recorded.stable_id
        or passport.version != recorded.version
        or not verify_revision_id(passport)
        or cache.digest_of(cast(JsonValue, passport.model_dump(mode="json")))
        != recorded.passport_digest
    ):
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the recorded component no longer matches its exact passport identity",
            details={"id": stable_id, "version": recorded.version},
        )
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
