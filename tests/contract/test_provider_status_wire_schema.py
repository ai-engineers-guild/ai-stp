"""The provider-kit owns the complete protocol-v3 status response shape."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import cast

import pytest
from jsonschema import Draft202012Validator, ValidationError
from release_scripts import provider_kit

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider import protocol_v3
from ai_stp_cli.provider import status as provider_status
from ai_stp_foundation.canonical import JsonValue

DIGEST = "sha256:" + "a" * 64
OTHER_DIGEST = "sha256:" + "b" * 64


def _always(*, state: str, provider_state: dict[str, object]) -> dict[str, object]:
    return {
        "backups": [],
        "canonical_target": "/tmp/provider-status-target",
        "cleanup_state": "none",
        "harness_id": "codex",
        "journal": None,
        "protocol_version": 3,
        "provider_id": "codex-setup-system",
        "provider_state": provider_state,
        "shadowed_by": [],
        "state": state,
        "target_digest": DIGEST,
        "target_identity_digest": DIGEST,
    }


def _managed() -> dict[str, object]:
    answer = _always(
        state="managed",
        provider_state={
            "present": True,
            "readable": True,
            "setup_stable_id": "setup_01M00000000000000000000000",
            "setup_version": "1.0",
            "operation_id": "operation_status_contract",
            "backup_ref": "slot-000000000002",
            "recorded_identity": DIGEST,
            "drift_state": "clean",
        },
    )
    answer.update(
        {
            "state_schema": 4,
            "provider_version": "0.0.47",
            "provider_build_digest": DIGEST,
            "provider_release_digest": DIGEST,
            "setup_stable_id": "setup_01M00000000000000000000000",
            "setup_version": "1.0",
            "setup_version_passport_digest": DIGEST,
            "setup_definition_digest": DIGEST,
            "component_refs": ["component_01M00000000000000000000000"],
            "bundle_format": "ai-stp-bundle/1",
            "bundle_digest": DIGEST,
            "artifact_digest": DIGEST,
            "projection_profile_digest": DIGEST,
            "provider_plan_digest": DIGEST,
            "operation_id": "operation_status_contract",
            "target_precondition_digest": OTHER_DIGEST,
            "native_ownership": ["AGENTS.md", "config.toml"],
            "written_paths": ["AGENTS.md", "config.toml"],
            "backup_ref": "slot-000000000002",
            "previous_verified_identity": OTHER_DIGEST,
            "drift_state": "clean",
            "backups": [
                {
                    "backup_ref": "slot-000000000001",
                    "operation": "replace",
                    "setup_id": None,
                    "held": True,
                    "hold_reason": "baseline-control",
                }
            ],
        }
    )
    return answer


def _validator() -> Draft202012Validator:
    schema = protocol_v3.STATUS_WIRE_SCHEMA
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _validate(answer: dict[str, object]) -> None:
    _validator().validate(answer)  # pyright: ignore[reportUnknownMemberType]


def test_missing_unmanaged_and_clean_managed_answers_validate() -> None:
    missing = _always(state="missing", provider_state={"present": False})
    unmanaged = _always(state="unmanaged", provider_state={"present": False})
    unmanaged["shadowed_by"] = [
        {
            "name": "opencode.jsonc",
            "over": "opencode.json",
            "effect": "the product reads this candidate last",
        }
    ]
    for answer in (missing, unmanaged, _managed()):
        _validate(answer)


def test_runtime_enforces_the_same_closed_schema() -> None:
    managed = _managed()
    assert provider_status.require_wire(cast(dict[str, JsonValue], managed))["state"] == "managed"

    malformed = deepcopy(managed)
    del malformed["cleanup_state"]
    with pytest.raises(CliFailure) as raised:
        provider_status.require_wire(cast(dict[str, JsonValue], malformed))
    assert raised.value.code == "AI_STP_SCHEMA_UNSUPPORTED"
    assert raised.value.details["field"] == "$"
    assert raised.value.next_actions == [
        # The old pointer named `toolchain install` with a flag it does not
        # take; a schema mismatch means the provider is behind or foreign,
        # and the way out is a released one.
        "provider fetch --harness <id> --json",
        "provider conformance --harness <id> --executable <path> --json",
    ]


def test_clean_state_requires_every_flat_provenance_field() -> None:
    answer = _managed()
    del answer[protocol_v3.STATUS_VERIFIED_FIELDS[-1]]
    with pytest.raises(ValidationError):
        _validate(answer)


def test_drifted_state_carries_only_the_nested_record_and_always_fields() -> None:
    answer = _managed()
    state = cast(dict[str, object], answer["provider_state"])
    state["drift_state"] = "local_drift"
    for field in protocol_v3.STATUS_VERIFIED_FIELDS:
        answer.pop(field)
    _validate(answer)


def test_the_schema_is_closed_and_a_hold_reason_matches_the_hold() -> None:
    answer = _managed()
    answer["invented_status_key"] = True
    with pytest.raises(ValidationError):
        _validate(answer)

    held_without_reason = _managed()
    backup = cast(list[dict[str, object]], held_without_reason["backups"])[0]
    backup["hold_reason"] = None
    with pytest.raises(ValidationError):
        _validate(held_without_reason)


def test_kit_schema_and_cases_are_derived_from_the_runtime_contract() -> None:
    rendered = provider_kit.render()
    assert rendered["status-response.schema.json"]
    cases = cast(dict[str, object], json.loads(rendered["conformance-cases.json"]))
    status = cast(dict[str, object], cases["status_response"])
    assert status["required_fields"] == list(protocol_v3.STATUS_ALWAYS_FIELDS)
    assert status["verified_fields"] == list(protocol_v3.STATUS_VERIFIED_FIELDS)

    properties = cast(dict[str, object], protocol_v3.STATUS_WIRE_SCHEMA["properties"])
    assert set(properties) == set(protocol_v3.STATUS_ALWAYS_FIELDS) | set(
        protocol_v3.STATUS_VERIFIED_FIELDS
    )


def test_always_and_verified_sets_do_not_overlap() -> None:
    assert not set(protocol_v3.STATUS_ALWAYS_FIELDS) & set(protocol_v3.STATUS_VERIFIED_FIELDS)
    assert len(protocol_v3.STATUS_ALWAYS_FIELDS) == 12
    assert len(protocol_v3.STATUS_VERIFIED_FIELDS) == 21


def test_a_foreign_state_schema_has_its_own_closed_shape() -> None:
    answer = _always(
        state="unmanaged",
        provider_state={
            "present": True,
            "readable": False,
            "found_schema": 99,
            "detail": "a schema this provider does not write",
        },
    )
    _validate(answer)

    changed = deepcopy(answer)
    cast(dict[str, object], changed["provider_state"])["recorded_identity"] = DIGEST
    with pytest.raises(ValidationError):
        _validate(changed)
