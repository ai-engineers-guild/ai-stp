"""A queued observation keeps its signed policy; released signatures still verify."""

import json

import pytest
from pydantic import ValidationError

from ai_stp_contracts.heartbeat import InstallationHeartbeatRequest, heartbeat_signature_message

ORGANIZATION = "organization_01ARZ3NDEKTSV4RRFFQ69G5FAV"
PAYLOAD = {
    "schema_version": 1,
    "account_id": "account_01ARZ3NDEKTSV4RRFFQ69G5FAW",
    "device_id": "device_01ARZ3NDEKTSV4RRFFQ69G5FAX",
    "cli_version": "0.2.3",
    "capabilities": ["foreground-heartbeat"],
    "last_sync_at": None,
    "health_state": "partial",
    "checked_at": "2026-10-31T00:00:00.000Z",
    "signature": "A" * 86,
}


@pytest.mark.parametrize("fields", [{}, {"policy_version": None}])
def test_released_heartbeat_signature_bytes_are_unchanged(fields: dict[str, object]) -> None:
    request = InstallationHeartbeatRequest.model_validate({**PAYLOAD, **fields})
    old_payload = {key: value for key, value in PAYLOAD.items() if key != "signature"}
    expected = (
        b"ai-stp:installation-heartbeat:v1\n"
        + ORGANIZATION.encode("ascii")
        + b"\n"
        + json.dumps(old_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    assert heartbeat_signature_message(ORGANIZATION, request) == expected


def test_zero_policy_version_is_an_explicit_signed_observation() -> None:
    legacy = InstallationHeartbeatRequest.model_validate(PAYLOAD)
    bound = InstallationHeartbeatRequest.model_validate({**PAYLOAD, "policy_version": 0})
    assert heartbeat_signature_message(ORGANIZATION, legacy) != heartbeat_signature_message(
        ORGANIZATION, bound
    )
    assert b'"policy_version":0' in heartbeat_signature_message(ORGANIZATION, bound)


def test_native_foreground_liveness_has_the_same_signature_preimage() -> None:
    request = InstallationHeartbeatRequest.model_validate(
        {
            **PAYLOAD,
            "account_id": "account_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "device_id": "device_01ARZ3NDEKTSV4RRFFQ69G5FAW",
            "cli_version": "1.0.0",
            "capabilities": ["cli.foreground-liveness"],
            "health_state": "active",
            "checked_at": "2030-01-02T03:04:05.000Z",
            "policy_version": 7,
        }
    )
    assert heartbeat_signature_message("organization_01ARZ3NDEKTSV4RRFFQ69G5FAX", request) == (
        b"ai-stp:installation-heartbeat:v1\norganization_01ARZ3NDEKTSV4RRFFQ69G5FAX\n"
        b'{"account_id":"account_01ARZ3NDEKTSV4RRFFQ69G5FAV","capabilities":["cli.foreground-liveness"],'
        b'"checked_at":"2030-01-02T03:04:05.000Z","cli_version":"1.0.0",'
        b'"device_id":"device_01ARZ3NDEKTSV4RRFFQ69G5FAW","health_state":"active",'
        b'"last_sync_at":null,"policy_version":7,"schema_version":1}'
    )


def test_policy_change_cannot_preserve_a_previous_signature_message() -> None:
    original = InstallationHeartbeatRequest.model_validate({**PAYLOAD, "policy_version": 1})
    changed = InstallationHeartbeatRequest.model_validate({**PAYLOAD, "policy_version": 3})
    assert heartbeat_signature_message(ORGANIZATION, original) != heartbeat_signature_message(
        ORGANIZATION, changed
    )


@pytest.mark.parametrize("version", [-1, True, False, "0"])
def test_policy_versions_are_nonnegative_integer_observations(version: object) -> None:
    with pytest.raises(ValidationError):
        InstallationHeartbeatRequest.model_validate({**PAYLOAD, "policy_version": version})
