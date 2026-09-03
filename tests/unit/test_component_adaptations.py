"""Exact per-harness component adaptation manifests (ADR-0143)."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from ai_stp_foundation.canonical import JsonValue
from ai_stp_passports import ComponentAdaptation, seal_adaptation

_DIGEST_A = "sha256:" + "a" * 64
_DIGEST_B = "sha256:" + "b" * 64
_DIGEST_C = "sha256:" + "c" * 64
_DIGEST_D = "sha256:" + "d" * 64


def _manifest() -> dict[str, JsonValue]:
    return {
        "harness_id": "cursor",
        "implementation_mode": "derived",
        "source_artifact": {"digest": _DIGEST_A, "size_bytes": 120},
        "transform": {
            "transform_id": "cursor-agent-projection",
            "version": "1.0",
            "digest": _DIGEST_B,
        },
        "logical_component_type": "agent",
        "scope_adaptations": [
            {
                "scope": "project",
                "projection_format": "ai-stp-adaptation-projection/1",
                "projection_artifact": {"digest": _DIGEST_C, "size_bytes": 240},
                "provider_component_kind": "agent",
                "projection_kind": "native_files",
                "required_surface": {
                    "profile_id": "cursor/native-files/project/1",
                    "profile_digest": _DIGEST_D,
                    "bundle_format": "ai-stp-bundle/1",
                },
                "permissions": {"filesystem": ["project"], "network": [], "process": []},
                "members": [
                    {
                        "path": ".cursor/agents/reviewer.md",
                        "object_type": "file",
                        "mode": 0o644,
                        "native_ids": ["reviewer"],
                        "content_format": "commonmark_v1",
                        "parser_id": None,
                        "ownership": "whole",
                        "ownership_key": None,
                        "write_semantics": "replace",
                        "withdrawal_semantics": "remove_path",
                    }
                ],
                "supported_harness_versions": [">=2026.08"],
                "supported_os": ["linux", "macos", "windows"],
                "supported_arch": ["x86_64", "arm64"],
                "technical_support": "supported",
                "technical_support_reason": None,
                "semantic_losses": [],
            }
        ],
    }


def test_adaptation_identity_is_deterministic_and_covers_every_scope_fact() -> None:
    first = seal_adaptation(_manifest())
    second = seal_adaptation(_manifest())
    changed = _manifest()
    scope = changed["scope_adaptations"]
    assert isinstance(scope, list)
    assert isinstance(scope[0], dict)
    scope[0]["projection_artifact"] = {"digest": _DIGEST_B, "size_bytes": 240}

    assert first == second
    assert first.adaptation_id.startswith("adaptation_")
    assert seal_adaptation(changed).adaptation_id != first.adaptation_id


def test_adaptation_refuses_an_id_for_different_manifest_bytes() -> None:
    sealed = seal_adaptation(_manifest()).model_dump(mode="json")
    scopes = sealed["scope_adaptations"]
    assert isinstance(scopes, list)
    assert isinstance(scopes[0], dict)
    scopes[0]["supported_harness_versions"] = [">=2026.08", "<2027.00"]

    with pytest.raises(ValidationError, match="adaptation_id does not match"):
        ComponentAdaptation.model_validate(sealed)


def test_scope_facts_cannot_be_borrowed_from_another_scope() -> None:
    manifest = _manifest()
    scopes = manifest["scope_adaptations"]
    assert isinstance(scopes, list)
    assert isinstance(scopes[0], dict)
    scopes.append(deepcopy(scopes[0]))

    with pytest.raises(ValidationError, match="duplicate scopes"):
        seal_adaptation(manifest)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("ownership_key", None, "ownership_key and parser_id"),
        ("parser_id", None, "ownership_key and parser_id"),
        ("write_semantics", "replace", "must use merge"),
        ("withdrawal_semantics", "remove_path", "preserve unowned"),
    ],
)
def test_shared_file_contribution_requires_complete_preservation_semantics(
    field: str, value: JsonValue, message: str
) -> None:
    manifest = _manifest()
    scopes = manifest["scope_adaptations"]
    assert isinstance(scopes, list)
    assert isinstance(scopes[0], dict)
    members = scopes[0]["members"]
    assert isinstance(members, list)
    assert isinstance(members[0], dict)
    members[0].update(
        {
            "content_format": "toml_v1",
            "parser_id": "tomlkit/0.15",
            "ownership": "contribution",
            "ownership_key": "mcp_servers.postgres",
            "write_semantics": "merge",
            "withdrawal_semantics": "preserve_unowned",
            field: value,
        }
    )

    with pytest.raises(ValidationError, match=message):
        seal_adaptation(manifest)


def test_native_and_derived_transform_rules_are_closed() -> None:
    missing = _manifest()
    missing["transform"] = None
    with pytest.raises(ValidationError, match="derived adaptation requires"):
        seal_adaptation(missing)

    native = _manifest()
    native["implementation_mode"] = "native"
    with pytest.raises(ValidationError, match="native adaptation has no transform"):
        seal_adaptation(native)


@pytest.mark.parametrize(
    "path",
    ["", "/absolute", "../escape", "nested/../escape", "windows\\path", "control\npath"],
)
def test_projected_member_path_is_rejected_by_wire_or_semantic_validation(path: str) -> None:
    manifest = _manifest()
    scopes = manifest["scope_adaptations"]
    assert isinstance(scopes, list)
    assert isinstance(scopes[0], dict)
    members = scopes[0]["members"]
    assert isinstance(members, list)
    assert isinstance(members[0], dict)
    members[0]["path"] = path

    with pytest.raises(ValidationError):
        seal_adaptation(manifest)


def test_projected_members_reject_duplicate_native_ids_and_zero_artifact() -> None:
    duplicate = _manifest()
    scopes = duplicate["scope_adaptations"]
    assert isinstance(scopes, list)
    assert isinstance(scopes[0], dict)
    members = scopes[0]["members"]
    assert isinstance(members, list)
    assert isinstance(members[0], dict)
    members[0]["native_ids"] = ["reviewer", "reviewer"]
    with pytest.raises(ValidationError, match="native_ids must not contain duplicates"):
        seal_adaptation(duplicate)

    empty = _manifest()
    empty_scopes = empty["scope_adaptations"]
    assert isinstance(empty_scopes, list)
    assert isinstance(empty_scopes[0], dict)
    empty_scopes[0]["projection_artifact"] = {"digest": _DIGEST_C, "size_bytes": 0}
    with pytest.raises(ValidationError, match="zero artifact bytes"):
        seal_adaptation(empty)
