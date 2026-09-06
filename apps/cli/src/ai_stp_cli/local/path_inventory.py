"""Passport-first inventory of one explicit root (`SPEC-005` REQ-534).

`component discover` without a path still lists global harness homes.
`inventory_root` never does. Canonical authoring markers are classified
before native detectors. Generated `projections/<harness>/` trees and setup
`components/` members are not independent sources. No stable id is minted.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path, PurePosixPath
from typing import Final, Literal, cast

from pydantic import ValidationError

from ai_stp_cli.local import components, discovery_continuation
from ai_stp_cli.paths import redact_home
from ai_stp_contracts.component_passport import ComponentPassportPatch
from ai_stp_contracts.machine_help import (
    NativeDiscoveryDiagnostic,
    PathInventory,
    PathInventoryObject,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_passports.versions import ComponentType

INVENTORY_DIGEST_DOMAIN: Final[str] = "ai-stp:path-inventory:v1"
MAX_INVENTORY_DIRECTORIES: Final[int] = 2000
MAX_PASSPORT_BYTES: Final[int] = components.MAX_COMPONENT_BYTES
EXCLUDED_NAMES: Final[frozenset[str]] = components.PORTABLE_SKILL_EXCLUDED_NAMES | {".git"}
SKIP_DESCEND: Final[frozenset[str]] = frozenset({"source", "projections"})

Kind = Literal["component", "setup"]
Relation = Literal["independent", "embedded_member", "generated_projection", "duplicate"]
Origin = Literal["passport", "native"]


def inventory_root(root: Path, cursor: str | None = None) -> PathInventory:
    """Classify every logical object under one named directory. Writes nothing."""
    place = root.expanduser()
    diagnostics: list[NativeDiscoveryDiagnostic] = []
    prior_covered: list[Path] = []
    stack: list[Path]
    skip_authoring = False
    native_cursor: str | None = None
    if cursor is not None:
        walk, frames, covered_rel = discovery_continuation.decode(cursor)
        if walk == "portable_skills":
            skip_authoring = True
            native_cursor = cursor
            stack = []
        elif walk == "path_inventory":
            stack = [discovery_continuation.join(place, relative) for relative, _depth in frames]
            prior_covered = [
                discovery_continuation.join(place, relative) for relative in covered_rel
            ]
        else:
            stack = [place]
    else:
        try:
            mode = place.lstat().st_mode
        except OSError:
            return _empty(place, diagnostics, complete=False, reason="the root could not be read")
        if stat.S_ISLNK(mode):
            return _empty(
                place,
                diagnostics,
                complete=True,
                code="invalid_record",
                reason="the explicit inventory root is a link and was not traversed",
            )
        if not stat.S_ISDIR(mode):
            return _empty(
                place,
                diagnostics,
                complete=True,
                code="invalid_record",
                reason="the explicit inventory root is not a directory",
            )
        owner = _generated_owner(place)
        if owner is not None:
            generated = _projection_object(place, owner, relative=".")
            return PathInventory(
                root=redact_home(place),
                complete=True,
                objects=[generated],
                diagnostics=[],
            )
        stack = [place]

    complete = True
    continuation: str | None = None
    trees: list[tuple[Path, Kind]] = []
    visited = 0
    remaining: list[Path] = []
    if not skip_authoring:
        while stack:
            directory = stack.pop()
            visited += 1
            if visited > MAX_INVENTORY_DIRECTORIES:
                complete = False
                remaining = [directory, *stack]
                diagnostics.append(
                    NativeDiscoveryDiagnostic(
                        code="bounded_limit",
                        source="path-inventory",
                        reason="the explicit inventory exceeded its bounded directory limit",
                    )
                )
                break
            kind, extra = _classify_directory(directory, place)
            if extra is not None:
                diagnostics.append(extra)
            if kind is not None:
                trees.append((directory, kind))
                if kind == "component":
                    continue
            try:
                entries = sorted(directory.iterdir(), key=lambda item: item.name, reverse=True)
            except OSError:
                diagnostics.append(
                    NativeDiscoveryDiagnostic(
                        code="unreadable",
                        source="path-inventory",
                        reason=(
                            "the directory at "
                            f"{discovery_continuation.relative_to(place, directory)} "
                            "could not be listed"
                        ),
                    )
                )
                complete = False
                continue
            for entry in entries:
                if entry.name in EXCLUDED_NAMES or entry.name in SKIP_DESCEND:
                    continue
                if not _plain_dir(entry):
                    continue
                stack.append(entry)

    setup_roots = [path for path, kind in trees if kind == "setup"] + list(prior_covered)
    objects: list[PathInventoryObject] = []
    covered: list[Path] = list(prior_covered)
    for directory, kind in trees:
        nested = kind == "component" and _under_setup(directory, setup_roots)
        relation: Relation = "embedded_member" if nested else "independent"
        origin: Origin = "passport"
        name, component_type, harness_id, passport_path = _identity(directory, kind)
        objects.append(
            _object(
                kind=kind,
                relation=relation,
                origin=origin,
                relative=_relative(place, directory),
                component_type=component_type,
                name=name,
                harness_id=harness_id,
                passport_path=passport_path,
            )
        )
        covered.append(directory)
        if kind == "component":
            objects.extend(_projections_of(directory, place, component_type, name, harness_id))

    if remaining:
        frames = [(discovery_continuation.relative_to(place, path), 0) for path in remaining]
        held = [discovery_continuation.relative_to(place, path) for path in covered]
        continuation = discovery_continuation.encode("path_inventory", frames, held)
        objects = _mark_duplicates(objects)
        objects.sort(key=lambda item: (item.relation, item.object_kind, item.relative_path))
        return PathInventory(
            root=redact_home(place),
            complete=False,
            continuation=continuation,
            objects=objects,
            diagnostics=diagnostics,
        )

    covered_roots = tuple(covered)
    native = components.discover_report(
        project=place, include_global=False, continuation=native_cursor
    )
    for item in native.diagnostics:
        diagnostics.append(
            NativeDiscoveryDiagnostic(
                code=item.code,  # pyright: ignore[reportArgumentType]
                source=item.source,
                reason=item.reason,
            )
        )
        if item.code in {"bounded_limit", "unreadable"}:
            complete = False
    if native.continuation:
        complete = False
        continuation = native.continuation
    for item in native.components:
        if _inside(item.absolute, covered_roots):
            continue
        try:
            relative = _relative(place, item.absolute)
        except ValueError:
            continue
        objects.append(
            _object(
                kind="component",
                relation="independent",
                origin="native",
                relative=relative,
                component_type=cast(ComponentType | None, item.component_type or None),
                name=item.absolute.name or None,
                harness_id=item.harness_id or None,
            )
        )

    objects = _mark_duplicates(objects)
    objects.sort(key=lambda item: (item.relation, item.object_kind, item.relative_path))
    return PathInventory(
        root=redact_home(place),
        complete=complete,
        continuation=continuation,
        objects=objects,
        diagnostics=diagnostics,
    )


def _empty(
    place: Path,
    diagnostics: list[NativeDiscoveryDiagnostic],
    *,
    complete: bool,
    code: Literal[
        "missing_manifest",
        "invalid_manifest",
        "unsupported_manifest",
        "invalid_record",
        "missing_source_entry",
        "bounded_limit",
    ] = "invalid_record",
    reason: str | None = None,
) -> PathInventory:
    held = list(diagnostics)
    if reason is not None:
        held.append(NativeDiscoveryDiagnostic(code=code, source="path-inventory", reason=reason))
    return PathInventory(
        root=redact_home(place),
        complete=complete,
        objects=[],
        diagnostics=held,
    )


def _classify_directory(
    directory: Path,
    root: Path,
) -> tuple[Kind | None, NativeDiscoveryDiagnostic | None]:
    setup_passport = directory / "setup-passport.json"
    component_passport = directory / "component-passport.json"
    template = directory / ".ai-stp-template.json"
    setup_json = directory / "setup.json"
    if _plain_file(setup_passport):
        if _json_object(setup_passport) is None:
            return None, _malformed(root, setup_passport, "setup")
        return "setup", None
    if _plain_file(component_passport):
        if _component_patch(component_passport) is None:
            extra = _malformed(root, component_passport, "component")
            if _plain_file(template):
                return "component", extra
            return None, extra
        return "component", None
    if _plain_file(template) and _plain_file(setup_json):
        return "setup", None
    if _plain_file(template):
        return "component", None
    return None, None


def _identity(
    directory: Path, kind: Kind
) -> tuple[str | None, ComponentType | None, str | None, str | None]:
    if kind == "setup":
        payload = _json_object(directory / "setup-passport.json") or _json_object(
            directory / "setup.json"
        )
        name = _string(payload, "name") if payload else None
        harness = _string(payload, "harness_id") if payload else None
        passport = "setup-passport.json" if _plain_file(directory / "setup-passport.json") else None
        return name, None, harness, passport
    patch = _component_patch(directory / "component-passport.json")
    if patch is not None:
        passport = "component-passport.json"
        return patch.name, patch.component_type, _harness(patch.harness_id), passport
    template = _json_object(directory / ".ai-stp-template.json")
    name = directory.name
    component_type = None
    harness = None
    if template is not None:
        raw_type = template.get("component_type")
        if isinstance(raw_type, str) and raw_type in components.COMPONENT_TYPES:
            component_type = cast(ComponentType, raw_type)
        harness = _string(template, "harness_variant")
        if harness == "portable":
            harness = None
    return name, component_type, harness, None


def _projections_of(
    directory: Path,
    root: Path,
    component_type: ComponentType | None,
    name: str | None,
    harness_id: str | None,
) -> list[PathInventoryObject]:
    projections = directory / "projections"
    if not _plain_dir(projections):
        return []
    parent = _relative(root, directory)
    found: list[PathInventoryObject] = []
    try:
        entries = sorted(projections.iterdir(), key=lambda item: item.name)
    except OSError:
        return []
    for entry in entries:
        if not _plain_dir(entry):
            continue
        found.append(
            _object(
                kind="component",
                relation="generated_projection",
                origin="passport",
                relative=_relative(root, entry),
                component_type=component_type,
                name=name,
                harness_id=entry.name,
                generated_from=parent,
            )
        )
    return found


def _projection_object(place: Path, owner: Path, *, relative: str) -> PathInventoryObject:
    name, component_type, _harness_id, _passport = _identity(owner, "component")
    return _object(
        kind="component",
        relation="generated_projection",
        origin="passport",
        relative=relative,
        component_type=component_type,
        name=name,
        harness_id=place.name,
        generated_from=None,
    )


def _object(
    *,
    kind: Kind,
    relation: Relation,
    origin: Origin,
    relative: str,
    component_type: ComponentType | None = None,
    name: str | None = None,
    harness_id: str | None = None,
    passport_path: str | None = None,
    generated_from: str | None = None,
) -> PathInventoryObject:
    object_id = digest_canonical(
        INVENTORY_DIGEST_DOMAIN,
        {
            "object_kind": kind,
            "relation": relation,
            "origin": origin,
            "relative_path": relative,
            "component_type": component_type,
            "name": name,
        },
    )
    return PathInventoryObject(
        object_kind=kind,
        relation=relation,
        origin=origin,
        object_id=object_id,
        relative_path=relative,
        component_type=component_type,
        name=name,
        harness_id=harness_id,
        passport_path=_join(relative, passport_path) if passport_path else None,
        generated_from=generated_from,
        stable_id=None,
    )


def _mark_duplicates(objects: list[PathInventoryObject]) -> list[PathInventoryObject]:
    seen: set[tuple[str, str | None, str | None]] = set()
    result: list[PathInventoryObject] = []
    for item in sorted(objects, key=lambda held: held.relative_path):
        if item.relation != "independent" or item.name is None:
            result.append(item)
            continue
        key = (item.object_kind, item.component_type, item.name)
        if key in seen:
            object_id = digest_canonical(
                INVENTORY_DIGEST_DOMAIN,
                {
                    "object_kind": item.object_kind,
                    "relation": "duplicate",
                    "origin": item.origin,
                    "relative_path": item.relative_path,
                    "component_type": item.component_type,
                    "name": item.name,
                },
            )
            result.append(item.model_copy(update={"relation": "duplicate", "object_id": object_id}))
            continue
        seen.add(key)
        result.append(item)
    return result


def _generated_owner(place: Path) -> Path | None:
    if not _plain_file(place / "GENERATED.md"):
        return None
    projections = place.parent
    if projections.name != "projections":
        return None
    owner = projections.parent
    has_passport = _plain_file(owner / "component-passport.json")
    has_template = _plain_file(owner / ".ai-stp-template.json")
    if has_passport or has_template:
        return owner
    return None


def _under_setup(directory: Path, setup_roots: list[Path]) -> bool:
    for setup in setup_roots:
        try:
            nested = (setup / "components").resolve(strict=False)
            directory.resolve(strict=False).relative_to(nested)
        except ValueError:
            continue
        return True
    return False


def _inside(path: Path, roots: tuple[Path, ...]) -> bool:
    held = path.resolve(strict=False)
    for root in roots:
        try:
            held.relative_to(root.resolve(strict=False))
        except ValueError:
            continue
        return True
    return False


def _relative(root: Path, path: Path) -> str:
    relative = path.resolve(strict=False).relative_to(root.resolve(strict=False))
    text = PurePosixPath(relative.as_posix()).as_posix()
    return "." if text == "." else text


def _join(root_relative: str, child: str) -> str:
    if root_relative == ".":
        return child
    return f"{root_relative}/{child}"


def _plain_dir(path: Path) -> bool:
    try:
        mode = path.lstat().st_mode
    except OSError:
        return False
    return stat.S_ISDIR(mode)


def _plain_file(path: Path) -> bool:
    try:
        mode = path.lstat().st_mode
    except OSError:
        return False
    return stat.S_ISREG(mode)


def _json_object(path: Path) -> dict[str, JsonValue] | None:
    raw = _read_bounded(path)
    if raw is None:
        return None
    try:
        document = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(document, dict):
        return None
    return cast(dict[str, JsonValue], document)


def _component_patch(path: Path) -> ComponentPassportPatch | None:
    document = _json_object(path)
    if document is None:
        return None
    try:
        return ComponentPassportPatch.model_validate(document)
    except ValidationError:
        return None


def _read_bounded(path: Path) -> bytes | None:
    if not _plain_file(path):
        return None
    try:
        size = path.lstat().st_size
    except OSError:
        return None
    if size > MAX_PASSPORT_BYTES:
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def _malformed(root: Path, path: Path, kind: str) -> NativeDiscoveryDiagnostic:
    try:
        relative = _relative(root, path)
    except ValueError:
        relative = path.name
    return NativeDiscoveryDiagnostic(
        code="invalid_manifest",
        source="path-inventory",
        reason=f"the {kind} passport at {relative} is not a valid {kind} passport",
    )


def _string(document: dict[str, JsonValue], key: str) -> str | None:
    value = document.get(key)
    if isinstance(value, str) and value:
        return value
    return None


def _harness(value: str | None) -> str | None:
    if value is None or value == "portable":
        return None
    return value
