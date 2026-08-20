"""Mixed-version envelope compatibility: strict producers, tolerant readers,
a wire schema that requires declared fields and tolerates additive extensions."""

import json
from pathlib import Path
from typing import cast

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from ai_stp_foundation import (
    CliError,
    ErrorEnvelope,
    ErrorEnvelopeReader,
    SuccessEnvelope,
    SuccessEnvelopeReader,
    new_id,
)

SCHEMAS_DIR = Path(__file__).parents[2] / "schemas" / "v1"


def _schema_accepts(name: str, instance: object) -> bool:
    schema = cast(dict[str, object], json.loads((SCHEMAS_DIR / f"{name}.schema.json").read_text()))
    validator = Draft202012Validator(schema)
    # jsonschema types its instance parameter with a private alias that plain
    # ``object`` cannot satisfy under strict mode; the runtime accepts any JSON.
    result = validator.is_valid(instance)  # pyright: ignore[reportUnknownMemberType, reportArgumentType]
    return bool(result)


def test_new_producer_old_reader_tolerates_unknown_optional_field() -> None:
    wire = SuccessEnvelope(request_id=new_id("request")).model_dump()
    wire["future_optional"] = {"anything": 1}
    parsed = SuccessEnvelopeReader.model_validate(wire)
    assert parsed.ok is True
    assert not hasattr(parsed, "future_optional")
    assert _schema_accepts("cli-envelope-success", wire)


def test_strict_producer_still_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        SuccessEnvelope.model_validate({"request_id": new_id("request"), "future_optional": 1})


def test_wire_requires_every_declared_field() -> None:
    full = SuccessEnvelope(request_id=new_id("request")).model_dump()
    assert _schema_accepts("cli-envelope-success", full)
    without_warnings = {key: value for key, value in full.items() if key != "warnings"}
    assert not _schema_accepts("cli-envelope-success", without_warnings)


def test_error_reader_tolerates_additive_error_details() -> None:
    wire = ErrorEnvelope(
        request_id=new_id("request"),
        error=CliError(code="AI_STP_VALIDATION_ERROR", message="safe", retryable=False),
    ).model_dump()
    cast(dict[str, object], wire["error"])["future_hint"] = "ignored"
    parsed = ErrorEnvelopeReader.model_validate(wire)
    assert parsed.error.code == "AI_STP_VALIDATION_ERROR"
    assert _schema_accepts("cli-envelope-error", wire)


def test_old_producer_new_reader_round_trip() -> None:
    wire = ErrorEnvelope(
        request_id=new_id("request"),
        error=CliError(code="AI_STP_CONFLICT", message="safe", retryable=True),
    ).model_dump()
    parsed = ErrorEnvelopeReader.model_validate(wire)
    assert parsed.ok is False
    assert _schema_accepts("cli-envelope-error", wire)
