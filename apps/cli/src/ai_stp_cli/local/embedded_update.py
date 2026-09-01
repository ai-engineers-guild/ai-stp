# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
"""Explicit embedded-component update: plan does not select; apply creates a version.

REQ-5712: a newer upstream snapshot never changes a frozen setup until the
caller confirms an exact plan. REQ-5716: the target is an exact component id,
never a display name.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping, Sequence
from typing import Final, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, content, revisions, selection, versions
from ai_stp_cli.local.catalog_replacement import (
    CatalogMatchInput,
    suggest_embedded_catalog_replacement,
)
from ai_stp_cli.local.database import transaction
from ai_stp_contracts.machine_help import SetupUpdatePlan, SetupUpdateResult
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_bytes, digest_canonical
from ai_stp_foundation.ids import is_valid_id
from ai_stp_foundation.refs import ComponentRef
from ai_stp_foundation.versioning import format_version, parse_version
from ai_stp_sources.definition import (
    EmbeddedDraft,
    FrozenDefinition,
    decode_embedded_artifact,
    encode_component_ref,
    freeze_setup_definition,
    unpack_component_tree,
    validate_setup_definition,
)
from ai_stp_sources.models import SourceIntent, SourceSnapshot
from ai_stp_sources.resolve import resolve_source

PLAN_DOMAIN: Final[str] = "ai-stp:plan:v1"
Resolver = Callable[[SourceIntent], SourceSnapshot]


def plan(
    connection: sqlite3.Connection,
    *,
    setup_id: str,
    version: str,
    component_id: str,
    snapshot: SourceSnapshot,
    project_id: str,
    harness_id: str,
    at: str,
    catalog: Sequence[CatalogMatchInput] = (),
) -> SetupUpdatePlan:
    """Preview one exact replacement. Does not write a version or change selection."""
    _require_component_id(component_id)
    frozen, from_version, selected = _freeze_replacement(
        connection,
        setup_id=setup_id,
        version=version,
        component_id=component_id,
        snapshot=snapshot,
        project_id=project_id,
        harness_id=harness_id,
        at=at,
    )
    to_version = str(frozen.document["version"])
    digest = _plan_digest(
        setup_id=setup_id,
        from_version=from_version,
        to_version=to_version,
        component_id=component_id,
        snapshot=snapshot,
        definition_digest=digest_bytes("ai-stp:artifact:v1", frozen.payload),
        selected_stable_id=selected[0] if selected else "",
        selected_version=selected[1] if selected else "",
    )
    suggestion = suggest_embedded_catalog_replacement(snapshot, catalog)
    return SetupUpdatePlan(
        setup_id=setup_id,
        from_version=from_version,
        to_version=to_version,
        component_id=component_id,
        snapshot_coordinate=snapshot.canonical_coordinate,
        snapshot_identity=snapshot.exact_identity,
        plan_digest=digest,
        selected_stable_id=selected[0] if selected else "",
        selected_version=selected[1] if selected else "",
        suggested_catalog_stable_id="" if suggestion is None else suggestion.catalog_stable_id,
        suggested_catalog_version="" if suggestion is None else suggestion.catalog_version,
        suggested_catalog_dismissible=suggestion is not None,
    )


def apply(
    connection: sqlite3.Connection,
    *,
    setup_id: str,
    version: str,
    component_id: str,
    snapshot: SourceSnapshot,
    project_id: str,
    harness_id: str,
    expected_plan_digest: str,
    device_id: str,
    at: str,
    confirm: bool,
) -> SetupUpdateResult:
    """Create one new immutable setup version and pin it only after confirmation."""
    if confirm is not True:
        raise CliFailure(
            "AI_STP_USER_DECISION_REQUIRED",
            "setup update apply requires explicit confirmation",
            next_actions=["setup update plan --id <id> --version <X.Y> --json"],
        )
    _require_component_id(component_id)
    frozen, from_version, selected = _freeze_replacement(
        connection,
        setup_id=setup_id,
        version=version,
        component_id=component_id,
        snapshot=snapshot,
        project_id=project_id,
        harness_id=harness_id,
        at=at,
    )
    to_version = str(frozen.document["version"])
    digest = _plan_digest(
        setup_id=setup_id,
        from_version=from_version,
        to_version=to_version,
        component_id=component_id,
        snapshot=snapshot,
        definition_digest=digest_bytes("ai-stp:artifact:v1", frozen.payload),
        selected_stable_id=selected[0] if selected else "",
        selected_version=selected[1] if selected else "",
    )
    if digest != expected_plan_digest:
        raise CliFailure(
            "AI_STP_PLAN_STALE",
            "the update plan digest changed before apply",
            details={"expected": expected_plan_digest, "found": digest},
            next_actions=["setup update plan --id <id> --version <X.Y> --json"],
        )
    current = selection.selected(connection, project_id=project_id, harness_id=harness_id)
    if (selected or ()) != (current or ()):
        raise CliFailure(
            "AI_STP_PLAN_STALE",
            "the selected setup changed before the update was confirmed",
            next_actions=["setup update plan --id <id> --version <X.Y> --json"],
        )

    recorded = versions.held(connection, setup_id, version)
    if recorded is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the setup version points to a missing passport",
            details={"stable_id": setup_id, "version": version},
        )
    stored = revisions.get(connection, recorded.revision_id)
    if stored is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the setup version points to a missing passport",
            details={"stable_id": setup_id, "version": version},
        )
    passport = cast(dict[str, JsonValue], stored.envelope.model_dump(mode="json"))
    passport.pop("revision_id", None)
    artifact = content.put(connection, frozen.payload, at=at)
    refs = [encode_component_ref(item) for item in frozen.components]
    passport["version"] = to_version
    passport["created_at"] = at
    passport["parent_revision_ids"] = []
    passport["artifact"] = {"digest": artifact.digest, "size_bytes": artifact.byte_length}
    passport["artifact_format"] = frozen.format
    passport["components"] = cast(JsonValue, refs)
    facts = passport.get("facts")
    if isinstance(facts, dict):
        members = facts.get("members")
        if isinstance(members, dict):
            members["value"] = cast(JsonValue, refs)

    with transaction(connection):
        committed = revisions.commit(connection, passport, device_id=device_id)
        versions.record(
            connection,
            stable_id=setup_id,
            version=to_version,
            passport_digest=cache.digest_of(
                cast(JsonValue, committed.envelope.model_dump(mode="json"))
            ),
            revision_id=committed.revision_id,
            at=at,
        )
        if selected is not None and selected[0] == setup_id and selected[1] == from_version:
            connection.execute(
                """
                UPDATE selected_version
                SET version = ?, state = ?, selected_at = ?
                WHERE project_id = ? AND harness_id = ?
                """,
                (
                    to_version,
                    selection.PENDING_INSTALL,
                    at,
                    project_id,
                    harness_id,
                ),
            )

    pinned = selection.selected(connection, project_id=project_id, harness_id=harness_id)
    return SetupUpdateResult(
        setup_id=setup_id,
        from_version=from_version,
        to_version=to_version,
        created=True,
        selected_stable_id="" if pinned is None else pinned[0],
        selected_version="" if pinned is None else pinned[1],
        plan_digest=digest,
    )


def parse_source(source: str, *, commit: str | None, subpath: str | None) -> SourceIntent:
    """Turn one exact CLI source string into a SourceIntent."""
    from ai_stp_sources.models import GitIntent, PackageIntent, PathIntent

    value = source.strip()
    if value.startswith("path:"):
        relative = value.removeprefix("path:")
        if not relative or relative.startswith("/") or "\\" in relative:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "an exact update snapshot is required",
                next_actions=["setup update plan --id <id> --version <X.Y> --json"],
            )
        return PathIntent(relative_path=relative)
    if value.startswith("package:"):
        rest = value.removeprefix("package:")
        ecosystem, sep, remainder = rest.partition(":")
        name, at, version = remainder.rpartition("@")
        if not sep or not at or not name or not version:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "an exact update snapshot is required",
                next_actions=["setup update plan --id <id> --version <X.Y> --json"],
            )
        return PackageIntent(
            ecosystem=ecosystem,  # pyright: ignore[reportArgumentType]
            name=name,
            version=version,
        )
    if not commit:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "an exact update snapshot is required",
            next_actions=["setup update plan --id <id> --version <X.Y> --json"],
        )
    repository = (
        value
        if value.startswith("https://github.com/")
        else f"https://github.com/{value.removeprefix('gh:')}"
    )
    return GitIntent(
        repository_url=repository,
        tracked_ref=commit,
        subpath=subpath or ".",
    )


def default_resolve(intent: SourceIntent, *, root: str | None = None) -> SourceSnapshot:
    """Resolve through the shared source adapters. Tests inject a stub instead."""
    import asyncio
    from pathlib import Path

    return asyncio.run(resolve_source(intent, local_root=None if root is None else Path(root)))


def _require_component_id(component_id: str) -> None:
    if not is_valid_id(component_id, "component"):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the update requires an exact component identifier, not a name",
            details={"given": component_id},
            next_actions=["setup update plan --id <id> --component-id <component_…> --json"],
        )


def _freeze_replacement(
    connection: sqlite3.Connection,
    *,
    setup_id: str,
    version: str,
    component_id: str,
    snapshot: SourceSnapshot,
    project_id: str,
    harness_id: str,
    at: str,
) -> tuple[FrozenDefinition, str, tuple[str, str, str] | None]:
    recorded = versions.held(connection, setup_id, version)
    if recorded is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the setup version points to a missing passport",
            details={"stable_id": setup_id, "version": version},
        )
    stored = revisions.get(connection, recorded.revision_id)
    if stored is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the setup version points to a missing passport",
            details={"stable_id": setup_id, "version": version},
        )
    passport = stored.envelope.model_dump(mode="json")
    artifact = passport.get("artifact")
    if not isinstance(artifact, dict) or not isinstance(artifact.get("digest"), str):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this setup version has no embedded component to update",
            details={"stable_id": setup_id, "version": version},
        )
    definition = validate_setup_definition(content.get(connection, str(artifact["digest"])))
    raw_embedded = definition.get("embedded")
    if not isinstance(raw_embedded, list) or not raw_embedded:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this setup version has no embedded component to update",
            details={"stable_id": setup_id, "version": version},
        )
    drafts: list[EmbeddedDraft] = []
    replaced = False
    for item in raw_embedded:
        if not isinstance(item, dict):
            continue
        draft = _draft_from_record(item)
        ref = item.get("ref")
        if isinstance(ref, dict) and str(ref.get("stable_id") or "") == component_id:
            drafts.append(
                EmbeddedDraft(
                    snapshot=snapshot,
                    component_type=draft.component_type,
                    name=draft.name,
                    description=draft.description,
                    license_spdx=draft.license_spdx,
                    harness_id=draft.harness_id,
                    redistribution_allowed=draft.redistribution_allowed,
                    version=_next_component_version(draft.version),
                    tags=draft.tags,
                    stable_id=component_id,
                    managed_paths=draft.managed_paths,
                    requires_components=draft.requires_components,
                    permissions=draft.permissions,
                    required_env=draft.required_env,
                    conflicts=draft.conflicts,
                    upstream_project=draft.upstream_project,
                    upstream_maintainers=draft.upstream_maintainers,
                    projection_kind=draft.projection_kind,
                )
            )
            replaced = True
        else:
            drafts.append(draft)
    if not replaced:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the named embedded component is not in this setup",
            details={"component_id": component_id},
            next_actions=["setup update plan --id <id> --version <X.Y> --json"],
        )

    catalog_members = _catalog_members(
        definition, frozenset(item.stable_id or "" for item in drafts)
    )
    publisher = str(passport.get("owner_id") or "")
    next_version = versions.next_minor(connection, setup_id)
    frozen = freeze_setup_definition(
        setup_id=setup_id,
        version=next_version,
        harness_id=str(passport.get("harness_id") or harness_id),
        input_digest=digest_canonical(
            PLAN_DOMAIN,
            {
                "setup_id": setup_id,
                "from_version": version,
                "component_id": component_id,
                "coordinate": snapshot.canonical_coordinate,
                "identity": snapshot.exact_identity,
            },
        ),
        publisher_id=publisher,
        created_at=at,
        catalog_members=catalog_members,
        embedded_members=tuple(drafts),
        catalog_ids=frozenset(item.stable_id for item in catalog_members),
    )
    selected = selection.selected(connection, project_id=project_id, harness_id=harness_id)
    return frozen, version, selected


def _next_component_version(current: str) -> str:
    major, minor = parse_version(current)
    return format_version(major, minor + 1)


def _draft_from_record(record: Mapping[str, object]) -> EmbeddedDraft:
    ref = record.get("ref")
    passport = record.get("passport")
    snapshot_doc = record.get("snapshot")
    if (
        not isinstance(ref, dict)
        or not isinstance(passport, dict)
        or not isinstance(snapshot_doc, dict)
    ):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "an embedded component record is not complete",
        )
    files = unpack_component_tree(decode_embedded_artifact(str(record.get("artifact_b64") or "")))
    snapshot = SourceSnapshot.model_validate({**snapshot_doc, "files": files})
    license_info = passport.get("license")
    spdx = "LicenseRef-Unknown"
    allowed = False
    if isinstance(license_info, dict):
        spdx = str(license_info.get("spdx_id") or spdx)
        allowed = bool(license_info.get("redistribution_allowed"))
    managed = passport.get("managed_paths")
    paths = tuple(str(item) for item in managed) if isinstance(managed, list) else ()
    tags = passport.get("tags")
    return EmbeddedDraft(
        snapshot=snapshot,
        component_type=str(passport.get("component_type") or "skill"),  # pyright: ignore[reportArgumentType]
        name=str(passport.get("name") or "embedded"),
        description=str(passport.get("description") or "Embedded component."),
        license_spdx=spdx,
        harness_id=str(passport.get("harness_id") or "claude-code"),
        redistribution_allowed=allowed,
        version=str(passport.get("version") or "1.0"),
        tags=tuple(str(item) for item in tags) if isinstance(tags, list) else ("embedded",),
        stable_id=str(ref.get("stable_id") or ""),
        managed_paths=paths,
    )


def _catalog_members(
    definition: Mapping[str, JsonValue], embedded_ids: frozenset[str]
) -> tuple[ComponentRef, ...]:
    raw = definition.get("components")
    if not isinstance(raw, list):
        return ()
    members: list[ComponentRef] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        stable_id = str(item.get("stable_id") or "")
        if not stable_id or stable_id in embedded_ids:
            continue
        members.append(
            ComponentRef(
                stable_id=stable_id,
                version=str(item.get("version") or "1.0"),
                passport_digest=str(item.get("passport_digest") or ""),
            )
        )
    return tuple(members)


def _plan_digest(
    *,
    setup_id: str,
    from_version: str,
    to_version: str,
    component_id: str,
    snapshot: SourceSnapshot,
    definition_digest: str,
    selected_stable_id: str,
    selected_version: str,
) -> str:
    return digest_canonical(
        PLAN_DOMAIN,
        {
            "setup_id": setup_id,
            "from_version": from_version,
            "to_version": to_version,
            "component_id": component_id,
            "coordinate": snapshot.canonical_coordinate,
            "identity": snapshot.exact_identity,
            "definition_digest": definition_digest,
            "selected_stable_id": selected_stable_id,
            "selected_version": selected_version,
        },
    )
