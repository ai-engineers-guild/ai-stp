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


def test_software_lifecycle_argv_is_in_the_provider_contract() -> None:
    """The flag names belong to the contract, not to a provider inventing them.

    A second copy in protocol_v3.py would be a second owner. The kit already
    names the operations; this is the argv the kit cannot express.
    """
    text = CONTRACT.read_text(encoding="utf-8")
    for token in (
        "--prefix",
        "--software-version",
        "--software-artifact",
        "software_artifacts",
        "byte_length",
        "entry_point",
    ):
        assert token in text, token


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

    # Closed, and required everywhere except the one name that may be absent.
    # `scoped_projection_profiles` must never join `required`: a provider built
    # before `ADR-0125` does not send it, and requiring it would refuse that
    # provider *whole* on every installed CLI. The global profile must likewise
    # stay free of `target_scope`, for the same reason and with the same blast
    # radius.
    required = set(cast(list[str], schema["required"]))
    assert required == set(properties) - protocol_v3.OPTIONAL_INFO_FIELDS
    assert "scoped_projection_profiles" not in required
    global_profile = cast(dict[str, object], properties["projection_profile"])
    assert "target_scope" not in cast(dict[str, object], global_profile["properties"])
    scoped = cast(dict[str, object], properties["scoped_projection_profiles"])
    scoped_item = cast(dict[str, object], scoped["items"])
    assert "target_scope" in cast(list[str], scoped_item["required"])


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


def _info_with(**overrides: object) -> dict[str, object]:
    """One valid `provider-info`, as a release shipped before `ADR-0125` sends it."""
    projection: dict[str, JsonValue] = {
        "profile_id": "antigravity/1",
        "component_kinds": ["skill"],
        "projection_kinds": ["native_files"],
        "native_namespaces": ["config/skills"],
        "bundle_formats": ["ai-stp-bundle/1"],
        "max_files": 2000,
        "max_bytes": 64 * 1024 * 1024,
    }
    info: dict[str, object] = {
        "protocol_version": 3,
        "provider_id": "nddev-antigravity",
        "harness_id": "antigravity",
        "provider_version": "0.0.6",
        "provider_build_digest": _digest("4"),
        "supported_commands": list(protocol_v3.CORE_COMMANDS),
        "supported_operations": sorted(item.value for item in protocol_v3.CORE_OPERATIONS),
        "supported_os": ["linux", "macos", "windows"],
        "supported_arch": ["arm64", "x86_64"],
        "permission_profiles": [],
        "projection_profile": {
            **projection,
            "digest": digest_canonical(protocol_v3.PROJECTION_DOMAIN, projection),
        },
    }
    return {**info, **overrides}


def _scoped(scope: str, *, bind_scope: bool = True) -> dict[str, JsonValue]:
    """One scoped entry. `bind_scope=False` omits the scope from its digest input."""
    body: dict[str, JsonValue] = {
        "profile_id": f"antigravity/{scope}",
        "component_kinds": ["command", "instruction"],
        "projection_kinds": ["native_files"],
        "native_namespaces": [".agents"],
        "bundle_formats": ["ai-stp-bundle/1"],
        "max_files": 2000,
        "max_bytes": 64 * 1024 * 1024,
    }
    digest_input = {**body, "target_scope": scope} if bind_scope else dict(body)
    return {
        **body,
        "target_scope": scope,
        "digest": digest_canonical(protocol_v3.PROJECTION_DOMAIN, digest_input),
    }


def test_a_release_shipped_before_the_second_scope_parses_unchanged() -> None:
    """The compatibility this whole shape exists to keep (`ADR-0125`).

    `provider-info` is compared on exact field equality, so a provider adding a
    field is refused *whole* — not its profile, the entire declaration, and with
    it fetch, conformance, plan, apply and status. An installed CLI cannot be
    taught tolerance afterwards, so the widening had to be a name that may be
    absent, and the existing profile had to keep its bytes and its digest.
    """
    parsed = protocol_v3.parse_capabilities(_info_with())
    assert parsed.scoped_projections == ()
    assert parsed.projection.scope == "global"


def test_a_second_scope_is_parsed_and_keeps_the_global_profile_untouched() -> None:
    parsed = protocol_v3.parse_capabilities(
        _info_with(scoped_projection_profiles=[_scoped("project")])
    )
    assert parsed.projection.scope == "global"
    assert (
        parsed.projection.digest == protocol_v3.parse_capabilities(_info_with()).projection.digest
    )
    assert [item.scope for item in parsed.scoped_projections] == ["project"]
    assert parsed.scoped_projections[0].native_namespaces == (".agents",)


def test_a_scoped_entry_binds_its_scope_into_its_own_identity() -> None:
    """Otherwise two profiles owning different targets could share a digest.

    The digest is what a plan pins and a status is verified against, so an
    identity blind to scope would let a provider answer for the wrong target
    while every comparison agreed.
    """
    with pytest.raises(ValueError, match="does not bind"):
        protocol_v3.parse_capabilities(
            _info_with(scoped_projection_profiles=[_scoped("project", bind_scope=False)])
        )


def test_the_global_scope_keeps_exactly_one_owner() -> None:
    entry = dict(_scoped("project"))
    entry["target_scope"] = "global"
    with pytest.raises(ValueError, match="declared by projection_profile"):
        protocol_v3.parse_capabilities(_info_with(scoped_projection_profiles=[entry]))


def test_two_entries_cannot_claim_the_same_scope() -> None:
    with pytest.raises(ValueError, match="distinct target scopes"):
        protocol_v3.parse_capabilities(
            _info_with(scoped_projection_profiles=[_scoped("project"), _scoped("project")])
        )


def test_the_widening_admits_exactly_one_new_name() -> None:
    """A closed set that grew by one is still closed."""
    with pytest.raises(ValueError, match="differ from the closed v3 schema"):
        protocol_v3.parse_capabilities(_info_with(something_else=[]))
    with pytest.raises(ValueError, match="unknown target scope"):
        protocol_v3.parse_capabilities(
            _info_with(scoped_projection_profiles=[{**_scoped("project"), "target_scope": "user"}])
        )
