"""Protocol v3 negotiates native capability without changing frozen v1/v2."""

from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from ai_stp_cli.provider import protocol, protocol_v2, protocol_v3
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical

CONTRACT = Path("docs/contracts/provider-protocol.md")
ADR = Path("docs/adr/ADR-0061-capability-negotiated-provider-protocol-v3.md")
REMOVE = object()
PROFILE_CASES: tuple[tuple[str, object], ...] = (
    ("profile_id", ""),
    ("component_kinds", frozenset[protocol_v3.ComponentKind]()),
    ("native_namespaces", ("same", "same")),
    ("bundle_formats", ("ai-stp-bundle/1", "ai-stp-bundle/1")),
    ("max_files", 0),
)
CAPABILITY_CASES: tuple[tuple[str, object], ...] = (
    ("provider_id", ""),
    ("provider_build_digest", "main"),
    ("commands", frozenset[str]()),
    ("supported_os", ()),
    ("supported_arch", ("x86_64", "x86_64")),
    ("permission_profiles", ("safe", "safe")),
    ("commands", frozenset({*protocol_v3.CORE_COMMANDS, "launch"})),
)
WIRE_CASES: tuple[tuple[str, str, object, str], ...] = (
    ("root", "protocol_version", 2, "protocol version differs"),
    ("root", "supported_os", "linux", "must be a string array"),
    ("root", "supported_os", [""], "must be a string array"),
    ("root", "supported_os", ["linux", "linux"], "must be unique"),
    ("root", "projection_profile", [], "must be an object"),
    ("profile", "max_bytes", REMOVE, "projection fields differ"),
    ("profile", "component_kinds", [], "must be a non-empty string array"),
    ("profile", "component_kinds", ["instruction", "instruction"], "must be unique"),
    ("profile", "component_kinds", ["memory"], "unknown closed vocabulary"),
    ("profile", "max_files", True, "limits must be integers"),
    ("profile", "profile_id", 7, "identity is invalid"),
    ("root", "provider_id", "", "identity fields are invalid"),
)


def _digest(character: str) -> str:
    return "sha256:" + character * 64


def _profile(
    *kinds: protocol_v3.ComponentKind,
) -> protocol_v3.ProjectionProfile:
    return protocol_v3.ProjectionProfile(
        profile_id="claude-code/1",
        digest=_digest("1"),
        component_kinds=frozenset(kinds),
        projection_kinds=frozenset({protocol_v3.ProjectionKind.PLUGIN}),
        native_namespaces=("claude.plugin",),
        bundle_formats=("ai-stp-bundle/1",),
        max_files=2000,
        max_bytes=16 * 1024 * 1024,
    )


def _capabilities(
    operations: frozenset[protocol_v3.Operation],
) -> protocol_v3.ProviderCapabilities:
    return protocol_v3.ProviderCapabilities(
        provider_id="nddev-claude-app",
        harness_id="claude-code",
        provider_version="1.0.0",
        provider_build_digest=_digest("2"),
        commands=frozenset(protocol_v3.CORE_COMMANDS),
        operations=operations,
        supported_os=("linux", "macos"),
        supported_arch=("x86_64", "arm64"),
        permission_profiles=(),
        projection=_profile(
            protocol_v3.ComponentKind.INSTRUCTION,
            protocol_v3.ComponentKind.PLUGIN,
            protocol_v3.ComponentKind.SETTING,
        ),
    )


def test_v1_and_v2_remain_frozen() -> None:
    assert protocol.VERSION == 1
    assert protocol_v2.VERSION == 2
    assert protocol_v2.COMMANDS == protocol.COMMANDS
    assert len(protocol.COMMANDS) == 12
    assert protocol_v3.VERSION == 3
    assert protocol_v3.COMMANDS != protocol.COMMANDS


def test_v3_has_one_planned_mutation_path() -> None:
    assert {
        "provider-info",
        "validate-bundle",
        "plan-operation",
        "status",
    } == protocol_v3.READ_COMMANDS
    assert {"apply-operation", "recover-operation"} == protocol_v3.APPLY_COMMANDS
    assert set(protocol_v3.CORE_COMMANDS) == {
        *protocol_v3.READ_COMMANDS,
        *protocol_v3.APPLY_COMMANDS,
    }
    assert protocol_v3.OPTIONAL_COMMANDS == ("launch",)


def test_setup_lifecycle_is_mandatory_but_software_and_launch_are_optional() -> None:
    capabilities = _capabilities(protocol_v3.CORE_OPERATIONS)
    for operation in protocol_v3.CORE_OPERATIONS:
        capabilities.require(operation)
    for operation in protocol_v3.OPTIONAL_OPERATIONS:
        with pytest.raises(protocol_v3.UnsupportedOperation) as failure:
            capabilities.require(operation)
        assert failure.value.reason is protocol_v3.UnsupportedReason.OPERATION


def test_provider_cannot_omit_a_core_setup_operation() -> None:
    with pytest.raises(ValueError, match="missing mandatory setup operations: remove"):
        _capabilities(protocol_v3.CORE_OPERATIONS - {protocol_v3.Operation.REMOVE})


def test_operations_are_closed_and_unique() -> None:
    assert protocol_v3.normalize_operations(["install", "remove", "backup", "restore", "replace"])
    with pytest.raises(ValueError, match="not a valid Operation"):
        protocol_v3.normalize_operations(["install-everything"])
    with pytest.raises(ValueError, match="must be unique"):
        protocol_v3.normalize_operations(["install", "install"])


def test_projection_profile_fails_closed_before_plan() -> None:
    profile = _profile(protocol_v3.ComponentKind.INSTRUCTION)
    protocol_v3.validate_profile_for_components(profile, ["instruction"])
    with pytest.raises(ValueError, match="unsupported_component_kind: mcp"):
        protocol_v3.validate_profile_for_components(profile, ["instruction", "mcp"])
    with pytest.raises(ValueError, match="not a valid ComponentKind"):
        protocol_v3.validate_profile_for_components(profile, ["memory"])
    protocol_v3.validate_profile_for_projections(profile, ["plugin"])
    with pytest.raises(ValueError, match="unsupported_native_surface: package"):
        protocol_v3.validate_profile_for_projections(profile, ["package"])
    with pytest.raises(ValueError, match="not a valid ProjectionKind"):
        protocol_v3.validate_profile_for_projections(profile, ["archive"])


def test_profile_and_build_identities_are_content_addressed() -> None:
    with pytest.raises(ValueError, match="projection profile digest"):
        protocol_v3.ProjectionProfile(
            profile_id="broken",
            digest="main",
            component_kinds=frozenset({protocol_v3.ComponentKind.SETTING}),
            projection_kinds=frozenset({protocol_v3.ProjectionKind.NATIVE_FILES}),
            native_namespaces=("settings",),
            bundle_formats=("ai-stp-bundle/1",),
            max_files=1,
            max_bytes=1,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    PROFILE_CASES,
)
def test_projection_profile_rejects_every_ambiguous_or_unbounded_identity(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValueError):
        replace(
            _profile(protocol_v3.ComponentKind.INSTRUCTION),
            **{field: value},  # pyright: ignore[reportArgumentType]
        )


@pytest.mark.parametrize(
    ("field", "value"),
    CAPABILITY_CASES,
)
def test_provider_capabilities_reject_incomplete_or_ambiguous_declarations(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValueError):
        replace(
            _capabilities(protocol_v3.CORE_OPERATIONS),
            **{field: value},  # pyright: ignore[reportArgumentType]
        )


def test_software_download_does_not_widen_apply() -> None:
    software = {
        policy.phase: policy.requirement
        for policy in protocol_v3.OPERATION_NETWORK[protocol_v3.Operation.SOFTWARE_INSTALL]
    }
    launch = {
        policy.phase: policy.requirement
        for policy in protocol_v3.OPERATION_NETWORK[protocol_v3.Operation.LAUNCH]
    }
    assert software[protocol_v3.OperationPhase.DOWNLOAD] is (
        protocol_v3.NetworkRequirement.ARTIFACT_DOWNLOAD
    )
    assert software[protocol_v3.OperationPhase.APPLY] is protocol_v3.NetworkRequirement.NONE
    assert launch[protocol_v3.OperationPhase.EXECUTE] is (
        protocol_v3.NetworkRequirement.RUNTIME_EXTERNAL
    )


def test_provider_state_provenance_is_complete_and_non_secret() -> None:
    required = set(protocol_v3.PROVENANCE_FIELDS)
    assert {
        "setup_version_passport_digest",
        "setup_definition_digest",
        "component_refs",
        "bundle_digest",
        "artifact_digest",
        "provider_plan_digest",
        "native_ownership",
        "backup_ref",
        "previous_verified_identity",
    } <= required
    assert not {field for field in required if "secret" in field or "token" in field}


def test_wire_schema_is_closed_and_requires_core_commands() -> None:
    schema = protocol_v3.WIRE_SCHEMA
    assert schema["additionalProperties"] is False
    properties = cast(dict[str, object], schema["properties"])
    commands = properties["supported_commands"]
    assert isinstance(commands, dict)
    command_schema = cast(dict[str, object], commands)
    assert command_schema["items"] == {
        "type": "string",
        "enum": list(protocol_v3.COMMANDS),
    }
    assert command_schema["minItems"] == len(protocol_v3.CORE_COMMANDS)
    assert set(cast(list[str], schema["required"])) == set(properties)


def test_provider_info_parser_binds_the_exact_projection_and_capabilities() -> None:
    projection: dict[str, JsonValue] = {
        "profile_id": "claude-code/1",
        "component_kinds": ["instruction", "skill"],
        "projection_kinds": ["native_files"],
        "native_namespaces": ["CLAUDE.md", "skills"],
        "bundle_formats": ["ai-stp-bundle/1"],
        "max_files": 2000,
        "max_bytes": 64 * 1024 * 1024,
    }
    info: dict[str, object] = {
        "protocol_version": 3,
        "provider_id": "nddev-claude-app",
        "harness_id": "claude-code",
        "provider_version": "0.2.0",
        "provider_build_digest": _digest("3"),
        "supported_commands": list(protocol_v3.CORE_COMMANDS),
        "supported_operations": sorted(item.value for item in protocol_v3.CORE_OPERATIONS),
        "supported_os": ["linux", "macos"],
        "supported_arch": ["arm64", "x86_64"],
        "permission_profiles": [],
        "projection_profile": {
            **projection,
            "digest": digest_canonical(protocol_v3.PROJECTION_DOMAIN, projection),
        },
    }
    parsed = protocol_v3.parse_capabilities(info)
    assert parsed.harness_id == "claude-code"
    assert parsed.commands == frozenset(protocol_v3.CORE_COMMANDS)
    assert parsed.operations == protocol_v3.CORE_OPERATIONS

    changed = dict(info)
    changed_profile = dict(cast(dict[str, object], info["projection_profile"]))
    changed_profile["native_namespaces"] = ["changed"]
    changed["projection_profile"] = changed_profile
    with pytest.raises(ValueError, match="does not bind"):
        protocol_v3.parse_capabilities(changed)


@pytest.mark.parametrize(
    ("surface", "field", "replacement", "message"),
    WIRE_CASES,
)
def test_provider_info_parser_fails_closed_for_malformed_wire_fields(
    surface: str,
    field: str,
    replacement: object,
    message: str,
) -> None:
    projection: dict[str, JsonValue] = {
        "profile_id": "claude-code/test",
        "component_kinds": ["instruction"],
        "projection_kinds": ["native_files"],
        "native_namespaces": ["CLAUDE.md"],
        "bundle_formats": ["ai-stp-bundle/1"],
        "max_files": 10,
        "max_bytes": 1024,
    }
    value: dict[str, object] = {
        "protocol_version": 3,
        "provider_id": "nddev-claude-app",
        "harness_id": "claude-code",
        "provider_version": "3.0.0",
        "provider_build_digest": _digest("3"),
        "supported_commands": list(protocol_v3.CORE_COMMANDS),
        "supported_operations": sorted(item.value for item in protocol_v3.CORE_OPERATIONS),
        "supported_os": ["linux"],
        "supported_arch": ["x86_64"],
        "permission_profiles": [],
        "projection_profile": {
            **projection,
            "digest": digest_canonical(protocol_v3.PROJECTION_DOMAIN, projection),
        },
    }
    changed = value if surface == "root" else cast(dict[str, object], value["projection_profile"])
    if replacement is REMOVE:
        changed.pop(field)
    else:
        changed[field] = replacement

    with pytest.raises(ValueError, match=message):
        protocol_v3.parse_capabilities(value)


def test_contract_and_adr_name_v3_without_redefining_old_versions() -> None:
    contract = CONTRACT.read_text(encoding="utf-8")
    adr = ADR.read_text(encoding="utf-8")
    assert "Protocol v1 и v2 остаются без изменений" in adr
    assert "protocol v3" in contract.lower()
