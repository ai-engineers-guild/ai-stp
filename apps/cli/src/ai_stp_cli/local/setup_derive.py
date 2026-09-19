"""Derive a new setup identity from a saved setup plus one member delta."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, cast

from ulid import ULID

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import content, revisions, setup_compose, versions
from ai_stp_cli.local.database import transaction
from ai_stp_contracts.first_party import FirstPartyVersion
from ai_stp_contracts.first_party import versions as corpus_versions
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.ids import is_valid_id
from ai_stp_foundation.refs import ComponentRef
from ai_stp_passports import SetupVersionPassport
from ai_stp_passports.versions import ComponentVersionPassport

Action = Literal["add", "remove"]
DERIVED_VERSION = versions.FIRST_VERSION
ACTIONS: frozenset[str] = frozenset({"add", "remove"})


@dataclass(frozen=True)
class DerivedSetup:
    setup_id: str
    setup_version: str
    minted: bool
    source_setup_id: str
    source_setup_version: str


def derived_setup_id(
    publisher_id: str,
    source_id: str,
    source_version: str,
    action: str,
    component_id: str,
    component_version: str,
) -> str:
    """Stable identity for one owner and one exact member delta. Replays reuse it."""
    material = (
        f"{publisher_id}\0{source_id}\0{source_version}\0{action}\0"
        f"{component_id}\0{component_version}"
    ).encode()
    return f"setup_{ULID.from_bytes(hashlib.sha256(material).digest()[:16])}"


def next_members(
    members: Sequence[ComponentRef], action: str, component: ComponentRef
) -> tuple[tuple[ComponentRef, ...], bool]:
    """Return the next member set and whether it equals the source set."""
    if action not in ACTIONS:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "change action must be add or remove",
            details={"action": action},
        )
    current = tuple(members)
    if action == "remove":
        remaining = tuple(item for item in current if item.stable_id != component.stable_id)
        if remaining == current:
            return current, True
        if not remaining:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "a setup must keep at least one component",
            )
        return remaining, False
    existing = next((item for item in current if item.stable_id == component.stable_id), None)
    if existing == component:
        return current, True
    replaced = tuple(item for item in current if item.stable_id != component.stable_id)
    return (*replaced, component), False


def corpus_item(kind: str, stable_id: str, version: str) -> FirstPartyVersion | None:
    """Exact first-party object, or none. Does not touch the network."""
    return next(
        (
            item
            for item in corpus_versions()
            if item.kind == kind
            and item.passport.stable_id == stable_id
            and item.passport.version == version
        ),
        None,
    )


def catalog_material(
    item: FirstPartyVersion, *, variant_id: str | None = None
) -> setup_compose.CatalogMaterial:
    if not isinstance(item.passport, ComponentVersionPassport):
        raise CliFailure("AI_STP_VALIDATION_ERROR", "a setup component source is not a component")
    ref = ComponentRef(
        stable_id=item.passport.stable_id,
        version=item.passport.version,
        passport_digest=item.passport_digest,
        variant_id=variant_id,
    )
    return setup_compose.CatalogMaterial(
        ref,
        cast(dict[str, JsonValue], item.passport.model_dump(mode="json")),
        item.artifact,
    )


def remember_corpus(
    connection: sqlite3.Connection, item: FirstPartyVersion, *, device_id: str, at: str
) -> None:
    """Write one corpus object into the local registry without changing its identity."""
    if versions.held(connection, item.passport.stable_id, item.passport.version) is not None:
        return
    content.put(connection, item.artifact, at=at)
    document = cast(dict[str, JsonValue], json.loads(item.passport.model_dump_json()))
    document.pop("revision_id", None)
    stored = revisions.commit(connection, document, device_id=device_id)
    versions.record(
        connection,
        stable_id=item.passport.stable_id,
        version=item.passport.version,
        passport_digest=item.passport_digest,
        revision_id=stored.revision_id,
        at=at,
    )


def remember_corpus_setup(
    connection: sqlite3.Connection,
    setup_id: str,
    setup_version: str,
    *,
    device_id: str,
    at: str,
) -> SetupVersionPassport:
    """Materialize a first-party setup and its members under their published ids."""
    setup = corpus_item("setup", setup_id, setup_version)
    if setup is None or not isinstance(setup.passport, SetupVersionPassport):
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the exact prepared SetupVersion is not held by this registry",
            details={"stable_id": setup_id, "version": setup_version},
        )
    with transaction(connection):
        for member in setup.passport.components:
            component = corpus_item("component", member.stable_id, member.version)
            if component is None:
                raise CliFailure(
                    "AI_STP_NOT_FOUND",
                    "a setup member is not in the first-party corpus",
                    details={"stable_id": member.stable_id, "version": member.version},
                )
            remember_corpus(connection, component, device_id=device_id, at=at)
        remember_corpus(connection, setup, device_id=device_id, at=at)
    return setup.passport


def record(
    connection: sqlite3.Connection,
    *,
    source: SetupVersionPassport,
    source_digest: str,
    action: str,
    component: ComponentRef,
    catalog: Sequence[setup_compose.CatalogMaterial],
    publisher_id: str,
    device_id: str,
    at: str,
) -> DerivedSetup:
    """Persist a new setup identity, or reuse the source when the graph is unchanged."""
    members, unchanged = next_members(source.components, action, component)
    if unchanged:
        return DerivedSetup(
            setup_id=source.stable_id,
            setup_version=source.version,
            minted=False,
            source_setup_id=source.stable_id,
            source_setup_version=source.version,
        )
    setup_id = derived_setup_id(
        publisher_id,
        source.stable_id,
        source.version,
        action,
        component.stable_id,
        component.version,
    )
    held = versions.held(connection, setup_id, DERIVED_VERSION)
    if held is not None:
        versions.record_fork_origin(
            connection,
            stable_id=setup_id,
            source_stable_id=source.stable_id,
            source_version=source.version,
            source_digest=source_digest,
            at=at,
        )
        return DerivedSetup(
            setup_id=setup_id,
            setup_version=DERIVED_VERSION,
            minted=True,
            source_setup_id=source.stable_id,
            source_setup_version=source.version,
        )
    by_id = {item.ref.stable_id: item for item in catalog}
    missing = [item.stable_id for item in members if item.stable_id not in by_id]
    if missing:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "every derived member must be materialized before compose",
            details={"stable_id": missing[0]},
        )
    materials = tuple(by_id[item.stable_id] for item in members)
    lineage = tuple(dict.fromkeys((source.stable_id, *source.related_setup_ids)))
    tags = tuple(source.tags) if source.tags else ("derived",)
    manifest = setup_compose.ComposeManifest(
        name=_derived_name(source.name),
        description=(
            f"Derived from {source.stable_id}@{source.version} by {action} "
            f"{component.stable_id}@{component.version}."
        ),
        harness_id=source.harness_id,
        version=DERIVED_VERSION,
        tags=tags,
        components=tuple(
            setup_compose.ComposeComponent(source=_catalog_source(item.ref)) for item in materials
        ),
    )
    resolved = setup_compose.compose(
        manifest=manifest,
        setup_id=setup_id,
        publisher_id=publisher_id,
        created_at=at,
        snapshots=(),
        catalog=materials,
    )
    setup_compose.apply(
        connection,
        resolved,
        expected_plan_digest=resolved.plan_digest,
        device_id=device_id,
        publisher_id=publisher_id,
        at=at,
        related_setup_ids=lineage,
    )
    versions.record_fork_origin(
        connection,
        stable_id=setup_id,
        source_stable_id=source.stable_id,
        source_version=source.version,
        source_digest=source_digest,
        at=at,
    )
    return DerivedSetup(
        setup_id=setup_id,
        setup_version=DERIVED_VERSION,
        minted=True,
        source_setup_id=source.stable_id,
        source_setup_version=source.version,
    )


def _derived_name(name: str) -> str:
    suffix = " (changed)"
    if name.endswith(suffix):
        return name[:160]
    return (name + suffix)[:160]


def _catalog_source(ref: ComponentRef) -> dict[str, object]:
    source: dict[str, object] = {
        "kind": "catalog",
        "stable_id": ref.stable_id,
        "version": ref.version,
        "passport_digest": ref.passport_digest,
    }
    if ref.variant_id is not None:
        source["variant_id"] = ref.variant_id
    return source


def require_setup_id(value: str) -> None:
    if not is_valid_id(value, "setup"):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "change input is not valid",
            details={"field": "setup_id"},
        )


def require_component_id(value: str) -> None:
    if not is_valid_id(value, "component"):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "change input is not valid",
            details={"field": "component_id"},
        )
