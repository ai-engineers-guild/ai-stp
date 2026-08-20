"""Machine envelope: literal ok, stable error codes, closed field sets."""

import pytest
from pydantic import ValidationError

from ai_stp_foundation import CliError, ErrorEnvelope, SuccessEnvelope, new_id


def test_success_envelope_defaults() -> None:
    envelope = SuccessEnvelope(request_id=new_id("request"))
    assert envelope.ok is True
    assert envelope.schema_version == 1
    assert envelope.operation_id is None
    assert envelope.data == {}


def test_error_envelope_carries_typed_error_and_operation() -> None:
    envelope = ErrorEnvelope(
        request_id=new_id("request"),
        operation_id=new_id("operation"),
        error=CliError(code="AI_STP_VALIDATION_ERROR", message="safe", retryable=False),
    )
    assert envelope.ok is False
    assert envelope.error.code == "AI_STP_VALIDATION_ERROR"


@pytest.mark.parametrize("bad_code", ["VALIDATION", "ai_stp_x", "AI_STP_", "AI_STP_x y"])
def test_unstable_error_codes_are_rejected(bad_code: str) -> None:
    with pytest.raises(ValidationError):
        CliError(code=bad_code, message="safe", retryable=False)


def test_ok_literals_cannot_be_flipped() -> None:
    with pytest.raises(ValidationError):
        SuccessEnvelope.model_validate({"request_id": new_id("request"), "ok": False})


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        SuccessEnvelope.model_validate({"request_id": new_id("request"), "extra": 1})
