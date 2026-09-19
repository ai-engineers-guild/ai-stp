"""Change intent: new setup identity from one member delta, then install."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from ai_stp_cli import identity
from ai_stp_cli.application import install as install_service
from ai_stp_cli.application.install_task import (
    ensure_local_context,
    harness_target,
    project_root_question,
    recommend_setup,
)
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import passports, setup_compose, setup_derive, versions
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_contracts.machine_help import TaskChangeOutcome, TaskQuestion
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.harnesses import HARNESS_IDS
from ai_stp_foundation.ids import is_valid_id
from ai_stp_foundation.refs import ComponentRef
from ai_stp_foundation.versioning import parse_version
from ai_stp_passports import SetupVersionPassport


@dataclass(frozen=True)
class DrainResult:
    outcome: TaskChangeOutcome | None = None
    questions: tuple[TaskQuestion, ...] = ()
    child_operation_ids: tuple[str, ...] = ()


DEFAULT_ACTION: Final[str] = "add"


def derive_setup(
    *,
    source: SetupVersionPassport,
    source_digest: str,
    action: str,
    component: ComponentRef,
    catalog: tuple[setup_compose.CatalogMaterial, ...],
) -> setup_derive.DerivedSetup:
    """Persist the derived identity. Tests may stub this."""
    current, _warning = identity.load_or_create()
    at = passports.moment()
    with closing(open_registry(configured_path(), create=True)) as connection:
        return setup_derive.record(
            connection,
            source=source,
            source_digest=source_digest,
            action=action,
            component=component,
            catalog=catalog,
            publisher_id=passports.owner().account_id,
            device_id=current.device_id,
            at=at,
        )


def drain(facts: Mapping[str, JsonValue]) -> DrainResult:
    """Advance change until a boundary. Never shells out to `ai-stp`."""
    harness = facts.get("harness_id")
    if not isinstance(harness, str) or harness not in HARNESS_IDS:
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="harness-id",
                    prompt="Which harness does this saved setup belong to?",
                    value_type="string",
                    choices=sorted(HARNESS_IDS),
                    why="Change derives one setup for one harness.",
                    actor="human",
                ),
            )
        )
    setup_id = facts.get("setup_id")
    setup_version = facts.get("setup_version")
    if not isinstance(setup_id, str) or not isinstance(setup_version, str):
        pin = recommend_setup(harness)
        if pin is None:
            return DrainResult(
                questions=(
                    TaskQuestion(
                        question_id="setup-ref",
                        prompt="Which saved setup should be changed? Answer as setup_id@X.Y.",
                        value_type="string",
                        choices=[],
                        why="Change derives from one pin. It will not quiz the catalog.",
                        actor="human",
                    ),
                )
            )
        setup_id = pin.setup_id
        setup_version = pin.setup_version
    setup_derive.require_setup_id(setup_id)
    try:
        parse_version(setup_version)
    except ValueError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "change input is not valid",
            details={"field": "setup_version"},
        ) from error
    action_raw = facts.get("action")
    action = DEFAULT_ACTION if action_raw is None else str(action_raw)
    if action not in setup_derive.ACTIONS:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "change action must be add or remove",
            details={"action": action},
        )
    component_id = facts.get("component_id")
    component_version = facts.get("component_version")
    if not isinstance(component_id, str) or not isinstance(component_version, str):
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="component-ref",
                    prompt=(
                        "Which exact component should be added or removed? "
                        "Answer as component_id@X.Y."
                    ),
                    value_type="string",
                    choices=[],
                    why="Change applies one member delta. It will not quiz the catalog.",
                    actor="human",
                ),
            )
        )
    setup_derive.require_component_id(component_id)
    try:
        parse_version(component_version)
    except ValueError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "change input is not valid",
            details={"field": "component_version"},
        ) from error
    question = project_root_question(
        facts.get("project_root"),
        prompt="Absolute project directory for the derived install?",
        why="Unsupported project-local must not silently become global.",
    )
    if question is not None:
        return DrainResult(questions=(question,))
    project_root = str(facts.get("project_root"))
    ensure_local_context(Path(project_root))
    source, source_digest, source_materials = _load_source(setup_id, setup_version)
    component, component_material = _load_component(component_id, component_version)
    catalog = _merge_catalog(source_materials, component_material)
    derived = derive_setup(
        source=source,
        source_digest=source_digest,
        action=action,
        component=component,
        catalog=catalog,
    )
    planned = install_service.plan(
        {
            "setup": f"{derived.setup_id}@{derived.setup_version}",
            "project": project_root,
            "harness": harness,
            "target": str(harness_target(harness)),
        }
    )
    approved = install_service.approve(
        {
            "operation": planned.payload.operation_id,
            "plan-digest": planned.payload.plan_digest,
        }
    )
    applied = install_service.apply({"operation": approved.payload.operation_id})
    view = applied.payload
    return DrainResult(
        outcome=TaskChangeOutcome(
            harness_id=harness,  # pyright: ignore[reportArgumentType]
            source_setup_id=derived.source_setup_id,
            source_setup_version=derived.source_setup_version,
            setup_id=derived.setup_id,
            setup_version=derived.setup_version,
            minted=derived.minted,
            operation_id=view.operation_id,
            state=view.state,
            verified=view.state == "verified",
        ),
        child_operation_ids=(view.operation_id,),
    )


def _load_source(
    setup_id: str, setup_version: str
) -> tuple[SetupVersionPassport, str, tuple[setup_compose.CatalogMaterial, ...]]:
    item = setup_derive.corpus_item("setup", setup_id, setup_version)
    current, _warning = identity.load_or_create()
    at = passports.moment()
    if item is not None and isinstance(item.passport, SetupVersionPassport):
        with closing(open_registry(configured_path(), create=True)) as connection:
            setup_derive.remember_corpus_setup(
                connection,
                setup_id,
                setup_version,
                device_id=current.device_id,
                at=at,
            )
        materials: list[setup_compose.CatalogMaterial] = []
        for member in item.passport.components:
            component = setup_derive.corpus_item("component", member.stable_id, member.version)
            if component is None:
                raise CliFailure(
                    "AI_STP_NOT_FOUND",
                    "a setup member is not in the first-party corpus",
                    details={"stable_id": member.stable_id},
                )
            materials.append(setup_derive.catalog_material(component, variant_id=member.variant_id))
        return item.passport, item.passport_digest, tuple(materials)
    _acquire_setup(setup_id, setup_version)
    with closing(open_registry(configured_path(), create=False)) as connection:
        recorded = versions.held(connection, setup_id, setup_version)
        if recorded is None:
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "the exact prepared SetupVersion is not held by this registry",
                details={"stable_id": setup_id, "version": setup_version},
            )
        from ai_stp_cli.local import revisions

        stored = revisions.get(connection, recorded.revision_id)
        if stored is None:
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "the exact prepared SetupVersion is not held by this registry",
                details={"stable_id": setup_id, "version": setup_version},
            )
        passport = SetupVersionPassport.model_validate(stored.envelope.model_dump(mode="json"))
        local_materials = tuple(
            _local_material(connection, member) for member in passport.components
        )
        return passport, recorded.passport_digest, local_materials


def _load_component(
    component_id: str, component_version: str
) -> tuple[ComponentRef, setup_compose.CatalogMaterial]:
    item = setup_derive.corpus_item("component", component_id, component_version)
    if item is not None:
        material = setup_derive.catalog_material(item)
        return material.ref, material
    local = _held_local_component(component_id, component_version)
    if local is not None:
        return local
    acquired = _acquire_component(component_id, component_version)
    return acquired.ref, acquired


def _held_local_component(
    component_id: str, component_version: str
) -> tuple[ComponentRef, setup_compose.CatalogMaterial] | None:
    """Owner-local component already in this registry. Do not hit the catalog."""
    with closing(open_registry(configured_path(), create=True)) as connection:
        recorded = versions.held(connection, component_id, component_version)
        if recorded is not None:
            member = ComponentRef(
                stable_id=recorded.stable_id,
                version=recorded.version,
                passport_digest=recorded.passport_digest,
            )
            material = _local_material(connection, member)
            return material.ref, material
        material = _embedded_local_component(connection, component_id, component_version)
        if material is None:
            return None
        return material.ref, material


def _embedded_local_component(
    connection: sqlite3.Connection, component_id: str, component_version: str
) -> setup_compose.CatalogMaterial | None:
    """Embedded member of a locally held setup. Author does not mint a catalog row."""
    from pydantic import ValidationError

    from ai_stp_cli.local import content, revisions
    from ai_stp_sources.definition import decode_embedded_artifact, try_parse_setup_definition
    from ai_stp_sources.errors import SourceError

    rows = connection.execute(
        "SELECT v.revision_id FROM entity e "
        "JOIN object_version v ON v.stable_id = e.stable_id WHERE e.kind = 'setup'"
    ).fetchall()
    for row in rows:
        stored = revisions.get(connection, str(row["revision_id"]))
        if stored is None:
            continue
        envelope = cast(dict[str, JsonValue], stored.envelope.model_dump(mode="json"))
        try:
            passport = SetupVersionPassport.model_validate(envelope)
        except ValidationError:
            continue
        member = next(
            (
                item
                for item in passport.components
                if item.stable_id == component_id and item.version == component_version
            ),
            None,
        )
        if member is None:
            continue
        artifact = envelope.get("artifact")
        if not isinstance(artifact, dict):
            continue
        digest = artifact.get("digest")
        if not isinstance(digest, str):
            continue
        try:
            definition = try_parse_setup_definition(content.get(connection, digest))
        except CliFailure:
            continue
        if definition is None:
            continue
        raw_embedded = definition.get("embedded")
        if not isinstance(raw_embedded, list):
            continue
        for item in raw_embedded:
            if not isinstance(item, dict):
                continue
            ref = item.get("ref")
            if not isinstance(ref, dict) or str(ref.get("stable_id") or "") != component_id:
                continue
            encoded = item.get("artifact_b64")
            raw_passport = item.get("passport")
            if not isinstance(encoded, str) or not isinstance(raw_passport, dict):
                continue
            try:
                packed = decode_embedded_artifact(encoded)
            except SourceError:
                continue
            return setup_compose.CatalogMaterial(
                member, cast(dict[str, JsonValue], raw_passport), packed
            )
    return None


def _merge_catalog(
    source_members: tuple[setup_compose.CatalogMaterial, ...],
    extra: setup_compose.CatalogMaterial,
) -> tuple[setup_compose.CatalogMaterial, ...]:
    by_id = {item.ref.stable_id: item for item in source_members}
    by_id[extra.ref.stable_id] = extra
    return tuple(by_id.values())


def _local_material(
    connection: sqlite3.Connection, member: ComponentRef
) -> setup_compose.CatalogMaterial:
    from ai_stp_cli.local import cache, content, revisions

    recorded = versions.held(connection, member.stable_id, member.version)
    if recorded is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "a setup member is not held by this registry",
            details={"stable_id": member.stable_id, "version": member.version},
        )
    stored = revisions.get(connection, recorded.revision_id)
    if stored is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "a setup member is not held by this registry",
            details={"stable_id": member.stable_id},
        )
    document = cast(dict[str, JsonValue], stored.envelope.model_dump(mode="json"))
    artifact = document.get("artifact")
    digest = str(artifact.get("digest") or "") if isinstance(artifact, dict) else ""
    payload: bytes | None = None
    path = cache.stored_version_artifact(digest) if digest else None
    if path is not None:
        payload = path.read_bytes()
    elif digest:
        try:
            payload = content.get(connection, digest)
        except CliFailure:
            payload = None
    if payload is None:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "the exact version artifact is not available in the verified cache",
            details={"stable_id": member.stable_id, "version": member.version},
        )
    return setup_compose.CatalogMaterial(member, document, payload)


def _acquire_setup(setup_id: str, setup_version: str) -> None:
    from ai_stp_cli.application import catalog as catalog_service

    if not is_valid_id(setup_id, "setup"):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "change input is not valid",
            details={"field": "setup_id"},
        )
    catalog_service.acquire({"id": setup_id, "version": setup_version})


def _acquire_component(component_id: str, component_version: str) -> setup_compose.CatalogMaterial:
    from ai_stp_cli.application import catalog as catalog_service
    from ai_stp_passports.versions import ComponentVersionPassport

    acquired = catalog_service.acquire_version(
        "component", component_id, component_version, offline=False, include_private=True
    )
    if not isinstance(acquired.passport, ComponentVersionPassport):
        raise CliFailure("AI_STP_CATALOG_INTEGRITY", "a component source is not a component")
    ref = ComponentRef(
        stable_id=acquired.passport.stable_id,
        version=acquired.passport.version,
        passport_digest=acquired.view.passport_digest,
    )
    return setup_compose.CatalogMaterial(ref, acquired.view.passport, acquired.artifact)
