"""Machine envelope: literal ok, stable error codes, closed field sets."""

import pytest
from pydantic import ValidationError

from ai_stp_foundation import (
    CliError,
    Continuation,
    ContinuationReader,
    ErrorEnvelope,
    SuccessEnvelope,
    bound_continuation,
    continuation_argv,
    continuation_command,
    new_id,
)


def test_an_old_continuation_without_argv_still_derives_tokens() -> None:
    parsed = ContinuationReader.model_validate(
        {
            "kind": "advance",
            "path": ["install", "status"],
            "arguments": {"operation": "operation_01J0000000000000000000000A"},
        }
    )
    assert parsed.argv == []
    assert continuation_argv(parsed)[-1] == "--json"
    assert parsed.actor == "cli"


def test_success_envelope_defaults() -> None:
    envelope = SuccessEnvelope(request_id=new_id("request"))
    assert envelope.ok is True
    assert envelope.schema_version == 1
    assert envelope.operation_id is None
    assert envelope.data == {}
    assert envelope.warnings == []
    assert envelope.next_actions == []
    assert envelope.continuations == []


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


def test_a_complete_continuation_is_runnable_argv() -> None:
    item = Continuation(
        kind="advance",
        path=["harness", "remove"],
        arguments={"harness": "codex", "prefix": "/p", "target": "/t", "confirm": ""},
    )
    assert (
        continuation_command(item)
        == "harness remove --harness codex --prefix /p --target /t --confirm --json"
    )


def test_an_incomplete_continuation_points_at_scoped_help() -> None:
    item = Continuation(
        kind="advance",
        path=["attestation", "sign"],
        arguments={"confirm": ""},
        missing=["component-root"],
    )
    assert continuation_command(item) == "help --path attestation --json"
    assert continuation_argv(item) == ["help", "--path", "attestation", "--json"]


def test_explicit_argv_is_kept_when_missing_is_non_empty() -> None:
    item = Continuation(
        kind="blocked",
        path=["task", "answer"],
        arguments={"task": "task_01J0000000000000000000000A", "revision": 3},
        missing=["value"],
        argv=[
            "task",
            "answer",
            "--task",
            "task_01J0000000000000000000000A",
            "--revision",
            "3",
            "--question-id",
            "harness-id",
            "--json",
        ],
        actor="human",
    )
    assert continuation_argv(item) == item.argv
    assert "help" not in continuation_argv(item)
    assert "..." not in continuation_command(item)
    bound = bound_continuation(item)
    assert bound.argv == item.argv


def test_argv_is_the_execution_form_and_display_is_quoted() -> None:
    item = Continuation(
        kind="advance",
        path=["task", "start"],
        arguments={"intent": "inspect", "idempotency-key": "k" * 16, "input": "/tmp/my file.json"},
    )
    tokens = continuation_argv(item)
    assert tokens[tokens.index("--input") + 1] == "/tmp/my file.json"
    assert "'/tmp/my file.json'" in continuation_command(item)
    bound = bound_continuation(item)
    assert bound.argv == continuation_argv(item)
    assert bound.actor == "cli"


def test_dash_prefixed_values_use_equals_form() -> None:
    item = Continuation(
        kind="advance",
        path=["task", "start"],
        arguments={"intent": "inspect", "idempotency-key": "k" * 16, "input": "-facts.json"},
    )
    assert "--input=-facts.json" in continuation_argv(item)


def test_integer_argument_values_are_json_numbers() -> None:
    item = Continuation(
        kind="advance",
        path=["task", "continue"],
        arguments={"task": "task_01J0000000000000000000000A", "revision": 2},
    )
    dumped = item.model_dump(mode="json")
    assert dumped["arguments"]["revision"] == 2
    assert continuation_argv(item)[continuation_argv(item).index("--revision") + 1] == "2"
