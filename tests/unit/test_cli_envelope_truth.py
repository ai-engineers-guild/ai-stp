"""Envelope `ok` is reserved for a completed request (SPEC-011 REQ-1132)."""

from __future__ import annotations

import json
from io import StringIO

import pytest
from pydantic import BaseModel

from ai_stp_cli.answer import Answer
from ai_stp_cli.application.inspect import capabilities as inspect_capabilities
from ai_stp_cli.application.install_transaction import (
    _complete,  # pyright: ignore[reportPrivateUsage]
)
from ai_stp_cli.application.outcome import envelope_actions, operation_id_of
from ai_stp_cli.commands import machine_help
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.output import render_failure, render_success
from ai_stp_contracts.machine_help import MultiRootChildView, MultiRootTransactionView
from ai_stp_foundation.envelope import Continuation, bound_continuation
from ai_stp_foundation.ids import new_id

DIGEST = "sha256:" + "ab" * 32


class _Payload(BaseModel):
    operation_id: str | None = None


def _children() -> list[MultiRootChildView]:
    first = new_id("operation")
    second = new_id("operation")
    return [
        MultiRootChildView(
            scope="global",
            operation_id=first,
            target_id="target",
            plan_digest=DIGEST,
            state="verified",
            harness_id="claude-code",
            setup_stable_id="setup_01J0000000000000000000000A",
            setup_version="1.0",
        ),
        MultiRootChildView(
            scope="project",
            operation_id=second,
            target_id="target",
            plan_digest=DIGEST,
            state="verified",
            harness_id="claude-code",
            setup_stable_id="setup_01J0000000000000000000000A",
            setup_version="1.0",
        ),
    ]


def _transaction(state: str) -> MultiRootTransactionView:
    transaction_id = new_id("operation")
    return MultiRootTransactionView(
        transaction_id=transaction_id,
        transaction_digest=DIGEST,
        setup_stable_id="setup_01J0000000000000000000000A",
        setup_version="1.0",
        harness_id="claude-code",
        state=state,  # type: ignore[arg-type]
        approved=True,
        children=_children(),
        next_actions=(
            [
                "install transaction recover "
                f"--transaction {transaction_id} --provider <executable> --json"
            ]
            if state == "recovery_required"
            else []
        ),
    )


def test_capabilities_are_served_from_application_inspect() -> None:
    assert machine_help.capabilities({}).payload == inspect_capabilities()


def test_doctor_is_served_from_application_inspect() -> None:
    from ai_stp_cli.application.inspect import doctor as inspect_doctor
    from ai_stp_cli.commands import doctor as doctor_command

    assert doctor_command.run({}).payload == inspect_doctor()


def test_envelope_actions_are_handler_continuations_only() -> None:
    held = Continuation(
        kind="advance",
        path=["install", "status"],
        arguments={"operation": "operation_01J0000000000000000000000A"},
    )
    continuations, actions = envelope_actions(Answer(_Payload(), continuations=(held,)))
    assert continuations == [bound_continuation(held)]
    assert actions == ["install status --operation operation_01J0000000000000000000000A --json"]
    empty, empty_actions = envelope_actions(Answer(_Payload()))
    assert empty == []
    assert empty_actions == []


def test_operation_id_prefers_the_answer_then_a_payload_operation() -> None:
    minted = new_id("operation")
    assert operation_id_of(Answer(_Payload(), operation_id=minted)) == minted
    assert operation_id_of(Answer(_Payload(operation_id=minted))) == minted
    assert operation_id_of(Answer(_Payload())) is None
    assert (
        operation_id_of(Answer(_Payload(operation_id="setup_01J0000000000000000000000A"))) is None
    )


def test_verified_transaction_keeps_success_and_the_operation_receipt() -> None:
    view = _transaction("verified")
    answer = _complete(view)
    assert answer.payload.state == "verified"
    assert answer.operation_id == view.transaction_id
    assert answer.operation_id is not None
    assert answer.operation_id.startswith("operation_")


def test_cancelled_transaction_is_success_with_no_native_effect() -> None:
    view = _transaction("cancelled")
    answer = _complete(view)
    assert answer.payload.state == "cancelled"
    assert answer.operation_id == view.transaction_id


def test_rolled_back_transaction_is_compensated_failure() -> None:
    view = _transaction("rolled_back")
    with pytest.raises(CliFailure) as raised:
        _complete(view)
    assert raised.value.code == "AI_STP_COMPENSATED"
    assert raised.value.exit_code == 4
    assert raised.value.operation_id == view.transaction_id
    assert raised.value.details["state"] == "rolled_back"
    assert raised.value.continuations == []


def test_recovery_required_transaction_is_partial_failure() -> None:
    view = _transaction("recovery_required")
    with pytest.raises(CliFailure) as raised:
        _complete(view)
    assert raised.value.code == "AI_STP_PARTIAL_OPERATION"
    assert raised.value.exit_code == 6
    assert raised.value.operation_id == view.transaction_id
    assert raised.value.continuations[0].missing == ["provider"]


def test_machine_envelopes_forward_operation_id() -> None:
    minted = new_id("operation")
    request = new_id("request")
    success = StringIO()
    render_success(
        _Payload(),
        machine=True,
        request_id=request,
        operation_id=minted,
        stream=success,
    )
    assert json.loads(success.getvalue())["operation_id"] == minted
    failure = StringIO()
    exit_code = render_failure(
        CliFailure(
            "AI_STP_COMPENSATED",
            "the requested install did not complete; compensation finished",
            operation_id=minted,
        ),
        machine=True,
        request_id=request,
        stream=failure,
    )
    body = json.loads(failure.getvalue())
    assert exit_code == 4
    assert body["ok"] is False
    assert body["operation_id"] == minted
    assert body["error"]["code"] == "AI_STP_COMPENSATED"
