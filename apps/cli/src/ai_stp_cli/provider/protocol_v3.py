"""Capability-negotiated provider protocol v3 (`ADR-0061`).

Versions one and two stay frozen.  V3 replaces a mandatory product lifecycle
surface with a small wire-command core and a closed set of operations.  The
consumer learns the operations and native projection profile before planning;
it never probes unsupported behavior by attempting a mutation.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final, cast

from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical

VERSION: Final[int] = 3
PLAN_DOMAIN: Final[str] = "ai-stp:provider-plan:v3"
PROJECTION_DOMAIN: Final[str] = "ai-stp:provider-projection:v3"
INFO_FIELDS: Final[tuple[str, ...]] = (
    "protocol_version",
    "provider_id",
    "harness_id",
    "provider_version",
    "provider_build_digest",
    "supported_commands",
    "supported_operations",
    "supported_os",
    "supported_arch",
    "permission_profiles",
    "projection_profile",
)

CORE_COMMANDS: Final[tuple[str, ...]] = (
    "provider-info",
    "validate-bundle",
    "plan-operation",
    "apply-operation",
    "recover-operation",
    "status",
)
OPTIONAL_COMMANDS: Final[tuple[str, ...]] = ("launch",)
COMMANDS: Final[tuple[str, ...]] = (*CORE_COMMANDS, *OPTIONAL_COMMANDS)

READ_COMMANDS: Final[frozenset[str]] = frozenset(
    {"provider-info", "validate-bundle", "plan-operation", "status"}
)
APPLY_COMMANDS: Final[frozenset[str]] = frozenset({"apply-operation", "recover-operation"})


class Operation(StrEnum):
    """An operation selected before a pure provider plan is requested."""

    INSTALL = "install"
    REPLACE = "replace"
    BACKUP = "backup"
    RESTORE = "restore"
    REMOVE = "remove"
    SOFTWARE_INSTALL = "software_install"
    SOFTWARE_UPDATE = "software_update"
    SOFTWARE_REMOVE = "software_remove"
    LAUNCH = "launch"


CORE_OPERATIONS: Final[frozenset[Operation]] = frozenset(
    {
        Operation.INSTALL,
        Operation.REPLACE,
        Operation.BACKUP,
        Operation.RESTORE,
        Operation.REMOVE,
    }
)
OPTIONAL_OPERATIONS: Final[frozenset[Operation]] = frozenset(Operation) - CORE_OPERATIONS


class ComponentKind(StrEnum):
    INSTRUCTION = "instruction"
    SKILL = "skill"
    MCP = "mcp"
    HOOK = "hook"
    COMMAND = "command"
    AGENT = "agent"
    PLUGIN = "plugin"
    SETTING = "setting"


class ProjectionKind(StrEnum):
    MARKETPLACE = "marketplace"
    PLUGIN = "plugin"
    NATIVE_FILES = "native_files"
    PACKAGE = "package"


class UnsupportedReason(StrEnum):
    """Stable, non-secret refusal reasons emitted before mutation."""

    OPERATION = "unsupported_operation"
    COMPONENT = "unsupported_component_kind"
    NATIVE_SURFACE = "unsupported_native_surface"
    BUNDLE_FORMAT = "unsupported_bundle_format"
    PROTOCOL_VERSION = "unsupported_protocol_version"
    PROJECTION_PROFILE = "projection_profile_mismatch"
    PLATFORM = "unsupported_platform"
    ARCHITECTURE = "unsupported_architecture"


PROVENANCE_FIELDS: Final[tuple[str, ...]] = (
    "state_schema",
    "protocol_version",
    "provider_id",
    "provider_version",
    "provider_build_digest",
    "provider_release_digest",
    "harness_id",
    "canonical_target",
    "target_identity_digest",
    "setup_stable_id",
    "setup_version",
    "setup_version_passport_digest",
    "setup_definition_digest",
    "component_refs",
    "bundle_format",
    "bundle_digest",
    "artifact_digest",
    "projection_profile_digest",
    "provider_plan_digest",
    "operation_id",
    "target_precondition_digest",
    "native_ownership",
    "backup_ref",
    "previous_verified_identity",
    "drift_state",
)

BUNDLE_REJECTIONS: Final[frozenset[str]] = frozenset(
    {
        "unsupported_protocol_version",
        "unsupported_bundle_format",
        "unsupported_component_kind",
        "unsupported_native_surface",
        "path_escapes_target",
        "path_not_relative",
        "path_duplicate",
        "link_not_allowed",
        "special_file_not_allowed",
        "limit_exceeded",
        "digest_mismatch",
    }
)


@dataclass(frozen=True)
class ProjectionProfile:
    """Exact public-provider input used by the compiler and provider validator."""

    profile_id: str
    digest: str
    component_kinds: frozenset[ComponentKind]
    projection_kinds: frozenset[ProjectionKind]
    native_namespaces: tuple[str, ...]
    bundle_formats: tuple[str, ...]
    max_files: int
    max_bytes: int

    def __post_init__(self) -> None:
        if not self.profile_id:
            raise ValueError("projection profile id is required")
        if not _is_sha256(self.digest):
            raise ValueError("projection profile digest must be canonical sha256")
        if not self.component_kinds or not self.projection_kinds:
            raise ValueError("projection profile capabilities cannot be empty")
        if not self.native_namespaces or len(set(self.native_namespaces)) != len(
            self.native_namespaces
        ):
            raise ValueError("native namespaces must be non-empty and unique")
        if not self.bundle_formats or len(set(self.bundle_formats)) != len(self.bundle_formats):
            raise ValueError("bundle formats must be non-empty and unique")
        if self.max_files <= 0 or self.max_bytes <= 0:
            raise ValueError("projection profile limits must be positive")


@dataclass(frozen=True)
class ProviderCapabilities:
    """Validated provider-info capability declaration for one exact release."""

    provider_id: str
    harness_id: str
    provider_version: str
    provider_build_digest: str
    commands: frozenset[str]
    operations: frozenset[Operation]
    supported_os: tuple[str, ...]
    supported_arch: tuple[str, ...]
    permission_profiles: tuple[str, ...]
    projection: ProjectionProfile

    def __post_init__(self) -> None:
        if not self.provider_id or not self.harness_id or not self.provider_version:
            raise ValueError("provider identity fields are required")
        if not _is_sha256(self.provider_build_digest):
            raise ValueError("provider build digest must be canonical sha256")
        if not set(CORE_COMMANDS) <= self.commands or not self.commands <= set(COMMANDS):
            raise ValueError("provider commands do not satisfy the closed v3 command core")
        missing = CORE_OPERATIONS - self.operations
        if missing:
            names = ", ".join(sorted(operation.value for operation in missing))
            raise ValueError(f"provider is missing mandatory setup operations: {names}")
        if not self.supported_os or len(set(self.supported_os)) != len(self.supported_os):
            raise ValueError("supported operating systems must be non-empty and unique")
        if not self.supported_arch or len(set(self.supported_arch)) != len(self.supported_arch):
            raise ValueError("supported architectures must be non-empty and unique")
        if len(set(self.permission_profiles)) != len(self.permission_profiles):
            raise ValueError("permission profiles must be unique")
        if ("launch" in self.commands) != (Operation.LAUNCH in self.operations):
            raise ValueError("launch command and operation capability must agree")

    def require(self, operation: Operation) -> None:
        """Refuse an unsupported operation before plan or provider mutation."""
        if operation not in self.operations:
            raise UnsupportedOperation(operation)


class UnsupportedOperation(ValueError):
    reason: Final[UnsupportedReason] = UnsupportedReason.OPERATION

    def __init__(self, operation: Operation) -> None:
        self.operation = operation
        super().__init__(f"provider does not support operation {operation.value!r}")


class NetworkRequirement(StrEnum):
    NONE = "none"
    ARTIFACT_DOWNLOAD = "artifact_download"
    RUNTIME_EXTERNAL = "runtime_external"


class OperationPhase(StrEnum):
    PLAN = "plan"
    DOWNLOAD = "download"
    APPLY = "apply"
    EXECUTE = "execute"


@dataclass(frozen=True)
class PhasePolicy:
    phase: OperationPhase
    requirement: NetworkRequirement


_LOCAL_PLAN_APPLY: Final[tuple[PhasePolicy, ...]] = (
    PhasePolicy(OperationPhase.PLAN, NetworkRequirement.NONE),
    PhasePolicy(OperationPhase.APPLY, NetworkRequirement.NONE),
)
_DOWNLOAD_PLAN_APPLY: Final[tuple[PhasePolicy, ...]] = (
    PhasePolicy(OperationPhase.PLAN, NetworkRequirement.NONE),
    PhasePolicy(OperationPhase.DOWNLOAD, NetworkRequirement.ARTIFACT_DOWNLOAD),
    PhasePolicy(OperationPhase.APPLY, NetworkRequirement.NONE),
)

OPERATION_NETWORK: Final[Mapping[Operation, tuple[PhasePolicy, ...]]] = MappingProxyType(
    {
        Operation.INSTALL: _LOCAL_PLAN_APPLY,
        Operation.REPLACE: _LOCAL_PLAN_APPLY,
        Operation.BACKUP: _LOCAL_PLAN_APPLY,
        Operation.RESTORE: _LOCAL_PLAN_APPLY,
        Operation.REMOVE: _LOCAL_PLAN_APPLY,
        Operation.SOFTWARE_INSTALL: _DOWNLOAD_PLAN_APPLY,
        Operation.SOFTWARE_UPDATE: _DOWNLOAD_PLAN_APPLY,
        Operation.SOFTWARE_REMOVE: _LOCAL_PLAN_APPLY,
        Operation.LAUNCH: (
            PhasePolicy(OperationPhase.EXECUTE, NetworkRequirement.RUNTIME_EXTERNAL),
        ),
    }
)


def _is_sha256(value: str) -> bool:
    if not value.startswith("sha256:") or len(value) != 71:
        return False
    return all(character in "0123456789abcdef" for character in value[7:])


def normalize_operations(values: Iterable[str]) -> frozenset[Operation]:
    """Parse a closed provider declaration; unknown names never pass through."""
    operations = tuple(Operation(value) for value in values)
    if len(operations) != len(set(operations)):
        raise ValueError("provider operations must be unique")
    return frozenset(operations)


def parse_capabilities(value: Mapping[str, object]) -> ProviderCapabilities:
    """Parse one closed provider-info object without trusting schema prose."""
    required = frozenset(INFO_FIELDS)
    if frozenset(value) != required:
        raise ValueError("provider-info fields differ from the closed v3 schema")
    if value.get("protocol_version") != VERSION:
        raise ValueError("provider-info protocol version differs")

    def strings(name: str, *, nonempty: bool = True) -> tuple[str, ...]:
        raw = value.get(name)
        if not isinstance(raw, list):
            raise ValueError(f"provider-info {name} must be a string array")
        values = cast(list[object], raw)
        if any(not isinstance(item, str) or (nonempty and not item) for item in values):
            raise ValueError(f"provider-info {name} must be a string array")
        held = cast(tuple[str, ...], tuple(values))
        if len(held) != len(set(held)):
            raise ValueError(f"provider-info {name} must be unique")
        return held

    untyped_profile = value.get("projection_profile")
    if not isinstance(untyped_profile, dict):
        raise ValueError("provider-info projection_profile must be an object")
    raw_profile = cast(dict[str, object], untyped_profile)
    profile_fields = {
        "profile_id",
        "digest",
        "component_kinds",
        "projection_kinds",
        "native_namespaces",
        "bundle_formats",
        "max_files",
        "max_bytes",
    }
    if set(raw_profile) != profile_fields:
        raise ValueError("provider projection fields differ from the closed v3 schema")

    def profile_strings(name: str) -> tuple[str, ...]:
        raw = raw_profile.get(name)
        if not isinstance(raw, list):
            raise ValueError(f"provider projection {name} must be a non-empty string array")
        values = cast(list[object], raw)
        if not values or any(not isinstance(item, str) or not item for item in values):
            raise ValueError(f"provider projection {name} must be a non-empty string array")
        held = cast(tuple[str, ...], tuple(values))
        if len(held) != len(set(held)):
            raise ValueError(f"provider projection {name} must be unique")
        return held

    component_names = profile_strings("component_kinds")
    projection_names = profile_strings("projection_kinds")
    try:
        components = frozenset(ComponentKind(name) for name in component_names)
        projections = frozenset(ProjectionKind(name) for name in projection_names)
    except ValueError as error:
        raise ValueError(
            "provider projection contains an unknown closed vocabulary value"
        ) from error
    max_files = raw_profile.get("max_files")
    max_bytes = raw_profile.get("max_bytes")
    if (
        isinstance(max_files, bool)
        or not isinstance(max_files, int)
        or isinstance(max_bytes, bool)
        or not isinstance(max_bytes, int)
    ):
        raise ValueError("provider projection limits must be integers")
    profile_id = raw_profile.get("profile_id")
    profile_digest = raw_profile.get("digest")
    if not isinstance(profile_id, str) or not isinstance(profile_digest, str):
        raise ValueError("provider projection identity is invalid")
    digest_input: dict[str, JsonValue] = {
        "profile_id": profile_id,
        "component_kinds": list(component_names),
        "projection_kinds": list(projection_names),
        "native_namespaces": list(profile_strings("native_namespaces")),
        "bundle_formats": list(profile_strings("bundle_formats")),
        "max_files": max_files,
        "max_bytes": max_bytes,
    }
    if digest_canonical(PROJECTION_DOMAIN, digest_input) != profile_digest:
        raise ValueError("provider projection digest does not bind its exact declaration")
    profile = ProjectionProfile(
        profile_id=profile_id,
        digest=profile_digest,
        component_kinds=components,
        projection_kinds=projections,
        native_namespaces=profile_strings("native_namespaces"),
        bundle_formats=profile_strings("bundle_formats"),
        max_files=max_files,
        max_bytes=max_bytes,
    )
    commands = frozenset(strings("supported_commands"))
    operations = normalize_operations(strings("supported_operations"))
    provider_id = value.get("provider_id")
    harness_id = value.get("harness_id")
    provider_version = value.get("provider_version")
    provider_build_digest = value.get("provider_build_digest")
    if not all(
        isinstance(item, str) and item
        for item in (provider_id, harness_id, provider_version, provider_build_digest)
    ):
        raise ValueError("provider identity fields are invalid")
    return ProviderCapabilities(
        provider_id=provider_id,  # type: ignore[arg-type]
        harness_id=harness_id,  # type: ignore[arg-type]
        provider_version=provider_version,  # type: ignore[arg-type]
        provider_build_digest=provider_build_digest,  # type: ignore[arg-type]
        commands=commands,
        operations=operations,
        supported_os=strings("supported_os"),
        supported_arch=strings("supported_arch"),
        permission_profiles=strings("permission_profiles", nonempty=True),
        projection=profile,
    )


def validate_profile_for_components(
    profile: ProjectionProfile,
    component_kinds: Iterable[str],
) -> None:
    """Reject unsupported component kinds before a provider plan is requested."""
    requested = frozenset(ComponentKind(value) for value in component_kinds)
    unsupported = requested - profile.component_kinds
    if unsupported:
        names = ", ".join(sorted(kind.value for kind in unsupported))
        raise ValueError(f"{UnsupportedReason.COMPONENT.value}: {names}")


def validate_profile_for_projections(
    profile: ProjectionProfile,
    projection_kinds: Iterable[str],
) -> None:
    """Reject native package families the exact provider did not declare."""
    requested = frozenset(ProjectionKind(value) for value in projection_kinds)
    unsupported = requested - profile.projection_kinds
    if unsupported:
        names = ", ".join(sorted(kind.value for kind in unsupported))
        raise ValueError(f"{UnsupportedReason.NATIVE_SURFACE.value}: {names}")


def _closed_string_enum(values: Sequence[StrEnum]) -> dict[str, object]:
    return {"type": "string", "enum": [value.value for value in values]}


def _build_wire_schema() -> dict[str, object]:
    """Machine-owned closed schema for the v3 provider-info payload."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://nddev.asia/schemas/provider-protocol/v3/provider-info.json",
        "type": "object",
        "properties": {
            "protocol_version": {"const": VERSION},
            "provider_id": {"type": "string", "minLength": 1},
            "harness_id": {"type": "string", "minLength": 1},
            "provider_version": {"type": "string", "minLength": 1},
            "provider_build_digest": {
                "type": "string",
                "pattern": "^sha256:[0-9a-f]{64}$",
            },
            "supported_commands": {
                "type": "array",
                "items": {"type": "string", "enum": list(COMMANDS)},
                "minItems": len(CORE_COMMANDS),
                "maxItems": len(COMMANDS),
                "uniqueItems": True,
            },
            "supported_operations": {
                "type": "array",
                "items": _closed_string_enum(tuple(Operation)),
                "minItems": len(CORE_OPERATIONS),
                "uniqueItems": True,
            },
            "supported_os": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "minItems": 1,
                "uniqueItems": True,
            },
            "supported_arch": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "minItems": 1,
                "uniqueItems": True,
            },
            "permission_profiles": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "uniqueItems": True,
            },
            "projection_profile": {
                "type": "object",
                "properties": {
                    "profile_id": {"type": "string", "minLength": 1},
                    "digest": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
                    "component_kinds": {
                        "type": "array",
                        "items": _closed_string_enum(tuple(ComponentKind)),
                        "minItems": 1,
                        "uniqueItems": True,
                    },
                    "projection_kinds": {
                        "type": "array",
                        "items": _closed_string_enum(tuple(ProjectionKind)),
                        "minItems": 1,
                        "uniqueItems": True,
                    },
                    "native_namespaces": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                        "minItems": 1,
                        "uniqueItems": True,
                    },
                    "bundle_formats": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                        "minItems": 1,
                        "uniqueItems": True,
                    },
                    "max_files": {"type": "integer", "minimum": 1},
                    "max_bytes": {"type": "integer", "minimum": 1},
                },
                "required": [
                    "profile_id",
                    "digest",
                    "component_kinds",
                    "projection_kinds",
                    "native_namespaces",
                    "bundle_formats",
                    "max_files",
                    "max_bytes",
                ],
                "additionalProperties": False,
            },
        },
        "required": list(INFO_FIELDS),
        "additionalProperties": False,
    }


WIRE_SCHEMA: Final[dict[str, object]] = _build_wire_schema()
