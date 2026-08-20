"""Author attestation: exact binding, closed fields, signed-payload boundary."""

import pytest
from pydantic import ValidationError

from ai_stp_assurance import AuthorAttestation, attestation_digest, attestation_payload
from ai_stp_foundation import digest_canonical, is_digest, new_id

SIGNATURE = "A" * 86 + "=="


def _record(**overrides: object) -> AuthorAttestation:
    data: dict[str, object] = {
        "object_digest": digest_canonical("ai-stp:artifact:v1", {"bytes": 1}),
        "subject": {
            "stable_id": new_id("component"),
            "version": "1.0",
            "passport_digest": digest_canonical("ai-stp:passport:v1", {"p": 1}),
        },
        "check_id": "mcp-remote-handshake",
        "policy_version": "1.0",
        "tool_versions": {"scanner": "2.1.0"},
        "harness_id": "claude-code",
        "harness_version": "3.5.0",
        "provider_version": "1.2",
        "test_case_ids": ["handshake-basic"],
        "result": "passed",
        "account_id": new_id("account"),
        "device_id": new_id("device"),
        "attested_at": "2026-08-05T10:00:00.000Z",
        "signature": SIGNATURE,
    }
    data.update(overrides)
    return AuthorAttestation.model_validate(data)


def test_record_binds_every_coordinate() -> None:
    record = _record()
    assert record.result == "passed"
    assert record.test_case_ids


def test_signature_is_excluded_from_the_signed_payload() -> None:
    record = _record()
    payload = attestation_payload(record)
    assert isinstance(payload, dict)
    assert "signature" not in payload
    digest = attestation_digest(record)
    assert is_digest(digest)
    resigned = record.model_copy(update={"signature": "B" * 86 + "=="})
    assert attestation_digest(resigned) == digest


def test_content_change_changes_the_digest() -> None:
    assert attestation_digest(_record()) != attestation_digest(_record(result="failed"))


def test_unknown_fields_fail_closed() -> None:
    with pytest.raises(ValidationError):
        _record(api_token="secret-value")


def test_empty_test_cases_and_bad_signature_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _record(test_case_ids=[])
    with pytest.raises(ValidationError):
        _record(signature="short")
