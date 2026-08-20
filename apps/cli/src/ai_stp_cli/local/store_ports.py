"""Bounded read-only SX/APM adapters and explicit local registry import."""

from __future__ import annotations

import os
import shutil
import sqlite3
import stat
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, cast

import yaml

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import components
from ai_stp_cli.local.passports import moment
from ai_stp_cli.paths import redact_home
from ai_stp_contracts.store_ports import (
    APM_CONTRACT_URL,
    SX_CONTRACT_URL,
    StorePortDescriptor,
    StorePortDiscovery,
    StorePortImportedObject,
    StorePortImportPlan,
    StorePortImportResult,
    StorePortInspection,
    StorePortMapping,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_bytes, digest_canonical
from ai_stp_passports.versions import ComponentType

MAX_MANIFEST_BYTES: Final[int] = 4 * 1024 * 1024
MAX_RECORDS: Final[int] = 1000
MAX_UNKNOWN_FIELDS: Final[int] = 100
SX_SOURCE: Final[str] = SX_CONTRACT_URL.removeprefix("https://")
APM_SOURCE: Final[str] = APM_CONTRACT_URL.removeprefix("https://")
SX_TYPES: Final[dict[str, ComponentType]] = {
    "skill": "skill",
    "rule": "instruction",
    "agent": "agent",
    "command": "command",
    "mcp": "mcp",
    "mcp-remote": "mcp",
    "hook": "hook",
    "claude-code-plugin": "plugin",
    "app-plugin": "plugin",
}


@dataclass(frozen=True)
class Snapshot:
    descriptor: StorePortDescriptor
    document: dict[str, object]
    payload: bytes


def discover(root: Path) -> StorePortDiscovery:
    """Find supported manifests without running their CLIs or opening assets."""
    base = _root(root)
    stores: list[StorePortDescriptor] = []
    diagnostics: list[str] = []
    for adapter in ("sx", "apm"):
        try:
            stores.append(_snapshot(base, adapter).descriptor)
        except FileNotFoundError:
            continue
        except CliFailure as error:
            diagnostics.append(f"{adapter}: {error.message}")
    return StorePortDiscovery(root=redact_home(base), stores=stores, diagnostics=diagnostics)


def inspect(root: Path, adapter: str) -> StorePortInspection:
    snapshot = _snapshot(_root(root), adapter)
    if adapter == "sx":
        mappings, unknown, diagnostics = _inspect_sx(snapshot)
    else:
        mappings, unknown, diagnostics = _inspect_apm(snapshot)
    mappings = _bind_local_content(_root(root), mappings)
    if len(unknown) > MAX_UNKNOWN_FIELDS:
        diagnostics.append(
            f"unknown_fields truncated from {len(unknown)} to {MAX_UNKNOWN_FIELDS} entries"
        )
    return StorePortInspection(
        descriptor=snapshot.descriptor,
        mappings=mappings,
        unknown_fields=unknown[:MAX_UNKNOWN_FIELDS],
        diagnostics=diagnostics,
    )


def plan(root: Path, adapter: str) -> StorePortImportPlan:
    report = inspect(root, adapter)
    conflicts = _conflicts(report.mappings)
    body = _plan_body(report, conflicts)
    return StorePortImportPlan(
        plan_digest=digest_canonical("ai-stp:store-port-plan:v1", body),
        inspection=report,
        importable_count=sum(item.state == "component" for item in report.mappings),
        omitted_count=sum(item.state == "omitted" for item in report.mappings),
        conflicts=conflicts,
        trust_consequences=[
            "local_only",
            "author_verified_false",
            "component_verified_false",
            "external_store_unchanged",
            "harness_target_unchanged",
        ],
    )


def apply(
    connection: sqlite3.Connection,
    root: Path,
    adapter: str,
    expected_digest: str,
    *,
    device_id: str,
) -> StorePortImportResult:
    """Import exact local component bytes; never mutate the source or a target."""
    current = plan(root, adapter)
    if current.plan_digest != expected_digest:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the setup-store snapshot no longer matches the confirmed import plan",
            details={"expected": expected_digest, "found": current.plan_digest},
            next_actions=[f"registry port plan --adapter {adapter} --root <path> --json"],
        )
    if current.conflicts:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the setup-store import plan contains conflicting external identities",
            details={"conflicts": ", ".join(current.conflicts)},
        )
    results: list[StorePortImportedObject] = []
    for mapping in current.inspection.mappings:
        if (
            mapping.state != "component"
            or mapping.component_type is None
            or mapping.local_path is None
        ):
            continue
        import_key = digest_canonical(
            "ai-stp:store-port-plan:v1",
            {
                "adapter": adapter,
                "snapshot_digest": current.inspection.descriptor.snapshot_digest,
                "external_id": mapping.external_id,
            },
        )
        held = connection.execute(
            "SELECT stable_id, revision_id FROM store_port_import WHERE import_key = ?",
            (import_key,),
        ).fetchone()
        if held is not None:
            results.append(
                StorePortImportedObject(
                    external_id=mapping.external_id,
                    stable_id=str(held[0]),
                    revision_id=str(held[1]),
                    state="already_imported",
                )
            )
            continue
        path = _contained(_root(root), mapping.local_path)
        current_content = components.inspect_content(path)
        found_digest = digest_bytes("ai-stp:artifact:v1", current_content.payload)
        if found_digest != mapping.local_content_digest:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "a setup-store component changed after the import plan was confirmed",
                details={"external_id": mapping.external_id},
                next_actions=[f"registry port plan --adapter {adapter} --root <path> --json"],
            )
        candidate = _candidate(path, mapping, current.inspection.descriptor)
        stored = components.adopt(connection, candidate, device_id=device_id)
        connection.execute(
            "INSERT INTO store_port_import "
            "(import_key, adapter, snapshot_digest, external_id, stable_id, "
            "revision_id, imported_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                import_key,
                adapter,
                current.inspection.descriptor.snapshot_digest,
                mapping.external_id,
                stored.stable_id,
                stored.revision_id,
                moment(),
            ),
        )
        results.append(
            StorePortImportedObject(
                external_id=mapping.external_id,
                stable_id=stored.stable_id,
                revision_id=stored.revision_id,
                state="imported",
            )
        )
    return StorePortImportResult(plan_digest=current.plan_digest, imported=results)


def _snapshot(root: Path, adapter: str) -> Snapshot:
    if adapter not in {"sx", "apm"}:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            f"unknown setup-store adapter: {adapter}",
            details={"allowed": "sx, apm"},
        )
    relative = "sx.toml" if adapter == "sx" else "apm.lock.yaml"
    payload = _read_regular(root / relative)
    try:
        if adapter == "sx":
            document = cast(dict[str, object], tomllib.loads(payload.decode("utf-8")))
            version = document.get("schema_version", 1)
            if version != 2:
                raise CliFailure(
                    "AI_STP_SCHEMA_UNSUPPORTED",
                    "the SX manifest is not supported schema version 2",
                    details={"found": str(version), "supported": "2"},
                )
        else:
            parsed = yaml.load(payload.decode("utf-8"), Loader=_UniqueSafeLoader)
            if not isinstance(parsed, dict):
                raise ValueError("root is not an object")
            document = cast(dict[str, object], parsed)
            version = document.get("lockfile_version", "1")
            if str(version) not in {"1", "2"}:
                raise CliFailure(
                    "AI_STP_SCHEMA_UNSUPPORTED",
                    "the APM lock is not supported version 1 or 2",
                    details={"found": str(version), "supported": "1, 2"},
                )
    except CliFailure:
        raise
    except (UnicodeDecodeError, tomllib.TOMLDecodeError, yaml.YAMLError, ValueError) as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            f"the {adapter.upper()} manifest is not unambiguous UTF-8 data",
        ) from error
    return Snapshot(
        descriptor=StorePortDescriptor(
            adapter=adapter,  # pyright: ignore[reportArgumentType]
            contract_version=str(version),
            root=redact_home(root),
            manifest=relative,
            snapshot_digest=digest_bytes("ai-stp:artifact:v1", payload),
            cli_status="available" if shutil.which(adapter) else "absent",
        ),
        document=document,
        payload=payload,
    )


def _inspect_sx(snapshot: Snapshot) -> tuple[list[StorePortMapping], list[str], list[str]]:
    known = {
        "schema_version",
        "created_by",
        "assets",
        "teams",
        "bots",
        "collections",
        "org",
        "app-plugins",
    }
    unknown = [f"$.{key}" for key in sorted(set(snapshot.document) - known)]
    raw_assets = snapshot.document.get("assets", [])
    if not isinstance(raw_assets, list):
        raise _bounded("SX assets")
    assets = cast(list[object], raw_assets)
    if len(assets) > MAX_RECORDS:
        raise _bounded("SX assets")
    mappings: list[StorePortMapping] = []
    for index, raw in enumerate(assets):
        if not isinstance(raw, dict):
            mappings.append(_omitted(f"asset[{index}]", "invalid", "record is not an object"))
            continue
        item = cast(dict[str, object], raw)
        name, external_type = item.get("name"), item.get("type")
        version = item.get("version")
        identity = str(name) if isinstance(name, str) and name else f"asset[{index}]"
        component_type = SX_TYPES.get(str(external_type))
        source, local_path, source_digest = _sx_source(item)
        omissions: list[str] = []
        if component_type is None:
            omissions.append("external type has no canonical mapping")
        if local_path is None:
            omissions.append("source is not an available local snapshot path")
        mappings.append(
            StorePortMapping(
                external_id=identity,
                external_type=str(external_type or "unknown"),
                external_version=str(version) if version is not None else None,
                source_coordinate=source,
                source_digest=source_digest,
                state="component" if not omissions else "omitted",
                component_type=component_type,
                local_path=local_path,
                omissions=omissions,
                preserved_metadata={
                    "clients": ",".join(
                        str(value) for value in cast(list[object], item.get("clients", []))
                    )
                    if isinstance(item.get("clients", []), list)
                    else "invalid"
                },
            )
        )
        unknown.extend(
            f"$.assets[{index}].{key}"
            for key in sorted(
                set(item)
                - {
                    "name",
                    "version",
                    "type",
                    "clients",
                    "dependencies",
                    "source-http",
                    "source-path",
                    "source-git",
                    "scopes",
                }
            )
        )
    raw_collections = snapshot.document.get("collections", [])
    if isinstance(raw_collections, list):
        collections = cast(list[object], raw_collections)
        if len(collections) > MAX_RECORDS:
            raise _bounded("SX collections")
        for index, raw in enumerate(collections[:MAX_RECORDS]):
            item = cast(dict[str, object], raw) if isinstance(raw, dict) else {}
            name = str(item.get("name") or f"collection[{index}]")
            mappings.append(
                StorePortMapping(
                    external_id=f"collection:{name}",
                    external_type="collection",
                    source_coordinate=f"sx.toml#collection:{name}",
                    state="omitted",
                    omissions=[
                        "collection membership is reported but setup creation requires "
                        "exact imported component versions"
                    ],
                    preserved_metadata={
                        "assets": ",".join(
                            str(value) for value in cast(list[object], item.get("assets", []))
                        )
                        if isinstance(item.get("assets", []), list)
                        else "invalid"
                    },
                )
            )
    return mappings, unknown, []


def _inspect_apm(snapshot: Snapshot) -> tuple[list[StorePortMapping], list[str], list[str]]:
    known = {
        "lockfile_version",
        "generated_at",
        "apm_version",
        "dependencies",
        "local_deployed_files",
        "local_deployed_file_hashes",
        "local_package",
    }
    unknown = [f"$.{key}" for key in sorted(set(snapshot.document) - known)]
    raw_dependencies = snapshot.document.get("dependencies", [])
    records: list[dict[str, object]] = []
    if isinstance(raw_dependencies, list):
        records = [
            cast(dict[str, object], item)
            for item in cast(list[object], raw_dependencies)
            if isinstance(item, dict)
        ]
    elif isinstance(raw_dependencies, dict):
        records = [
            cast(dict[str, object], item)
            for item in cast(dict[object, object], raw_dependencies).values()
            if isinstance(item, dict)
        ]
    if len(records) > MAX_RECORDS:
        raise _bounded("APM dependencies")
    mappings: list[StorePortMapping] = []
    for index, item in enumerate(records):
        name = str(item.get("name") or item.get("repo_url") or f"dependency[{index}]")
        deployed = item.get("deployed_files", [])
        if not isinstance(deployed, list):
            mappings.append(
                _omitted(
                    name, str(item.get("package_type") or "package"), "deployed_files is not a list"
                )
            )
            continue
        boundaries: dict[tuple[str, str], list[str]] = {}
        for raw_path in cast(list[object], deployed):
            if not isinstance(raw_path, str):
                continue
            classified = _apm_boundary(raw_path)
            if classified is not None:
                component_type, boundary = classified
                boundaries.setdefault((component_type, boundary), []).append(raw_path)
        if not boundaries:
            mappings.append(
                _omitted(
                    name,
                    str(item.get("package_type") or "package"),
                    "no deployed path has a canonical component boundary",
                )
            )
        for (component_type, boundary), paths in sorted(boundaries.items()):
            digest = _apm_digest(item, paths)
            mappings.append(
                StorePortMapping(
                    external_id=f"{name}:{boundary}",
                    external_type=str(item.get("package_type") or "apm-package"),
                    external_version=str(item["version"])
                    if item.get("version") is not None
                    else None,
                    source_coordinate=str(
                        item.get("source_url") or item.get("repo_url") or f"apm.lock.yaml#{name}"
                    ),
                    source_digest=digest,
                    state="component",
                    component_type=cast(ComponentType, component_type),
                    local_path=boundary,
                    omissions=[],
                    preserved_metadata={"deployed_paths": ",".join(sorted(paths))},
                )
            )
        unknown.extend(
            f"$.dependencies[{index}].{key}"
            for key in sorted(
                set(item)
                - {
                    "repo_url",
                    "name",
                    "version",
                    "package_type",
                    "deployed_files",
                    "deployed_file_hashes",
                    "source",
                    "local_path",
                    "anchored_local_path",
                    "content_hash",
                    "source_url",
                    "source_digest",
                    "resolved_commit",
                    "resolved_ref",
                    "resolved_hash",
                    "resolved_url",
                    "declared_license",
                }
            )
        )
    return mappings, unknown, []


def _sx_source(item: dict[str, object]) -> tuple[str, str | None, str | None]:
    path_source = item.get("source-path")
    held_path = cast(dict[str, object], path_source) if isinstance(path_source, dict) else {}
    if isinstance(held_path.get("path"), str):
        value = str(held_path["path"])
        return value, value, None
    git = item.get("source-git")
    if isinstance(git, dict):
        held_git = cast(dict[str, object], git)
        url, ref = str(held_git.get("url") or ""), str(held_git.get("ref") or "")
        subpath = str(held_git.get("subdirectory") or "")
        return f"{url}@{ref}#{subpath}", None, f"git:{ref}" if ref else None
    http = item.get("source-http")
    if isinstance(http, dict):
        held_http = cast(dict[str, object], http)
        hashes = held_http.get("hashes")
        held_hashes = cast(dict[str, object], hashes) if isinstance(hashes, dict) else {}
        sha = held_hashes.get("sha256")
        return (
            str(held_http.get("url") or "source-http"),
            None,
            f"sha256:{sha}" if isinstance(sha, str) else None,
        )
    return "sx.toml#missing-source", None, None


def _bind_local_content(root: Path, mappings: list[StorePortMapping]) -> list[StorePortMapping]:
    bound: list[StorePortMapping] = []
    for item in mappings:
        if item.state != "component" or item.local_path is None:
            bound.append(item)
            continue
        try:
            path = _contained(root, item.local_path)
            payload = components.inspect_content(path).payload
        except CliFailure as error:
            bound.append(
                item.model_copy(
                    update={
                        "state": "omitted",
                        "local_content_digest": None,
                        "omissions": [*item.omissions, error.message],
                    }
                )
            )
            continue
        bound.append(
            item.model_copy(
                update={"local_content_digest": digest_bytes("ai-stp:artifact:v1", payload)}
            )
        )
    return bound


def _apm_boundary(value: str) -> tuple[str, str] | None:
    path = PurePosixPath(value.rstrip("/"))
    if value.startswith(("/", "~")) or "\\" in value or ".." in path.parts:
        return None
    parts = path.parts
    markers = {
        "skills": "skill",
        "agents": "agent",
        "prompts": "command",
        "commands": "command",
        "hooks": "hook",
        "plugins": "plugin",
        "instructions": "instruction",
        "rules": "instruction",
        "mcp": "mcp",
    }
    for index, part in enumerate(parts):
        if part in markers and index + 1 < len(parts):
            boundary = PurePosixPath(*parts[: index + 2]).as_posix()
            return markers[part], boundary
    return None


def _apm_digest(item: dict[str, object], paths: list[str]) -> str | None:
    hashes = item.get("deployed_file_hashes")
    if isinstance(hashes, dict):
        held_hashes = cast(dict[str, object], hashes)
        values = [str(held_hashes[path]) for path in sorted(paths) if path in held_hashes]
        if values:
            return digest_bytes("ai-stp:artifact:v1", "\n".join(values).encode())
    for key in ("content_hash", "source_digest", "resolved_hash"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value if ":" in value else f"sha256:{value}"
    return None


def _candidate(
    path: Path, mapping: StorePortMapping, descriptor: StorePortDescriptor
) -> components.Found:
    source_path = redact_home(path)
    provenance = components.Provenance(
        kind="package",
        state="imported",
        package_name=mapping.external_id,
        package_version=mapping.external_version,
        digest=mapping.source_digest,
        subpath=mapping.local_path,
        evidence=(descriptor.manifest,),
    )
    candidate_id = digest_canonical(
        "ai-stp:native-discovery:v1",
        {
            "adapter": descriptor.adapter,
            "snapshot": descriptor.snapshot_digest,
            "external_id": mapping.external_id,
            "path": source_path,
        },
    )
    return components.Found(
        component_type=str(mapping.component_type),
        native_role=None,
        harness_id="",
        scope=components.SCOPE_PROJECT,
        candidate_id=candidate_id,
        layout_source=SX_SOURCE if descriptor.adapter == "sx" else APM_SOURCE,
        provenance=provenance,
        source_path=source_path,
        absolute=path,
        byte_length=None,
        holds_secret=False,
        reason="declared by an inspected local setup-store snapshot",
        entry_points=(),
        transport_capabilities=(),
        evidence_refs=(descriptor.manifest,),
    )


def _plan_body(report: StorePortInspection, conflicts: list[str]) -> JsonValue:
    return cast(
        JsonValue,
        {
            "inspection": report.model_dump(mode="json"),
            "conflicts": conflicts,
            "effects": ["local_registry_write"],
            "non_effects": ["external_store_write", "harness_target_write"],
        },
    )


def _conflicts(mappings: list[StorePortMapping]) -> list[str]:
    identities: dict[str, StorePortMapping] = {}
    conflicts: list[str] = []
    for item in mappings:
        previous = identities.get(item.external_id)
        if previous is not None:
            conflicts.append(item.external_id)
        identities[item.external_id] = item
    return sorted(set(conflicts))


def _root(path: Path) -> Path:
    named = path.expanduser()
    try:
        if stat.S_ISLNK(named.lstat().st_mode):
            raise CliFailure("AI_STP_VALIDATION_ERROR", "a setup-store root cannot be a link")
    except FileNotFoundError:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR", "an existing non-home store root is required"
        ) from None
    expanded = named.resolve()
    if expanded == Path.home().resolve() or not expanded.is_dir():
        raise CliFailure("AI_STP_VALIDATION_ERROR", "an existing non-home store root is required")
    return expanded


def _contained(root: Path, relative: str) -> Path:
    value = PurePosixPath(relative.rstrip("/"))
    if relative.startswith(("/", "~")) or "\\" in relative or ".." in value.parts:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED", "a setup-store path escapes its declared root"
        )
    unresolved = root.joinpath(*value.parts)
    cursor = root
    for part in value.parts:
        cursor /= part
        try:
            if stat.S_ISLNK(cursor.lstat().st_mode):
                raise CliFailure(
                    "AI_STP_PRECONDITION_FAILED",
                    "a setup-store component path cannot traverse a link",
                    details={"path": relative},
                )
        except FileNotFoundError:
            break
    candidate = unresolved.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED", "a setup-store path escapes its declared root"
        ) from error
    if not candidate.exists():
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "a declared setup-store component is unavailable",
            details={"path": relative},
        )
    return candidate


def _read_regular(path: Path) -> bytes:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > MAX_MANIFEST_BYTES
        ):
            raise _bounded(path.name)
        chunks: list[bytes] = []
        remaining = MAX_MANIFEST_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            len(payload) > MAX_MANIFEST_BYTES
            or len(payload) != after.st_size
            or before.st_ino != after.st_ino
            or before.st_dev != after.st_dev
            or before.st_mtime_ns != after.st_mtime_ns
        ):
            raise _bounded(path.name)
        return payload
    finally:
        if descriptor is not None:
            os.close(descriptor)


class _UniqueSafeLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader: yaml.Loader, node: yaml.Node, deep: bool = False) -> object:
    pairs = cast(
        list[tuple[object, object]],
        loader.construct_pairs(node, deep=deep),  # pyright: ignore[reportUnknownMemberType]
    )
    result: dict[object, object] = {}
    for key, value in pairs:
        if key in result:
            raise yaml.constructor.ConstructorError(
                None, None, f"duplicate key: {key}", node.start_mark
            )
        result[key] = value
    return result


_UniqueSafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def _omitted(identity: str, external_type: str, reason: str) -> StorePortMapping:
    return StorePortMapping(
        external_id=identity,
        external_type=external_type,
        source_coordinate="manifest record",
        state="omitted",
        omissions=[reason],
        preserved_metadata={},
    )


def _bounded(subject: str) -> CliFailure:
    return CliFailure(
        "AI_STP_VALIDATION_ERROR", f"{subject} exceeds the bounded setup-store port limit"
    )
