"""`status` takes a scope only from a provider that says it does.

Measured on 0.0.54: `plan-operation` digests the target's owned paths at the
requested scope while `status` has no scope and digests the home view, so a
workspace plan bound only an empty target — the install passed and the removal
was refused on `expected_target_digest`. The fix is a request field, and a
request field is the provider's move first: the consumer accepts the name in
`provider-info` one release before any provider declares it, and sends the flag
only to one that has (`ADR-0125`, mirrored as `plan_request_fields` was).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_stp_cli.local.bundle import BUNDLE_FORMAT
from ai_stp_cli.provider import operation_v3, protocol_v3
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical

pytestmark = pytest.mark.cli


def _info(**extra: object) -> dict[str, object]:
    profile: dict[str, JsonValue] = {
        "profile_id": "codex/native-files/1",
        "component_kinds": ["instruction"],
        "projection_kinds": ["native_files"],
        "native_namespaces": ["AGENTS.md"],
        "bundle_formats": [BUNDLE_FORMAT],
        "max_files": 100,
        "max_bytes": 1_000_000,
    }
    profile["digest"] = digest_canonical(protocol_v3.PROJECTION_DOMAIN, profile)
    document: dict[str, object] = {
        "protocol_version": protocol_v3.VERSION,
        "provider_id": "codex-setup-system",
        "harness_id": "codex",
        "provider_version": "0.0.55",
        "provider_build_digest": "sha256:" + "b" * 64,
        "supported_commands": sorted(protocol_v3.CORE_COMMANDS),
        "supported_operations": sorted(item.value for item in protocol_v3.CORE_OPERATIONS),
        "supported_os": ["linux"],
        "supported_arch": ["x86_64"],
        "permission_profiles": ["default"],
        "projection_profile": profile,
    }
    document.update(extra)
    return document


def test_a_provider_declaring_nothing_for_status_still_parses() -> None:
    capabilities = protocol_v3.parse_capabilities(_info())
    assert capabilities.status_request_fields == frozenset()


def test_the_declared_status_field_reaches_the_capabilities() -> None:
    capabilities = protocol_v3.parse_capabilities(_info(status_request_fields=["target_scope"]))
    assert capabilities.status_request_fields == frozenset({"target_scope"})


def test_a_status_field_this_build_cannot_send_is_refused_whole() -> None:
    with pytest.raises(ValueError, match="status_request_fields names"):
        protocol_v3.parse_capabilities(_info(status_request_fields=["moon_phase"]))


def test_the_flag_is_sent_only_for_a_workspace_and_only_when_declared() -> None:
    silent = protocol_v3.parse_capabilities(_info())
    declared = protocol_v3.parse_capabilities(_info(status_request_fields=["target_scope"]))
    assert operation_v3.status_arguments(silent, "project") == ()
    assert operation_v3.status_arguments(declared, "global") == ()
    assert operation_v3.status_arguments(declared, "project") == ("--target-scope", "project")


def test_the_kit_schema_names_the_status_field_with_its_closed_vocabulary() -> None:
    kit = Path(__file__).parents[2] / "provider-kit" / "v3" / "provider-info.schema.json"
    schema = json.loads(kit.read_text(encoding="utf-8"))
    assert schema["properties"]["status_request_fields"]["items"]["enum"] == ["target_scope"]
