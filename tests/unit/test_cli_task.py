"""Durable inspect tasks share application.inspect with expert commands."""

from __future__ import annotations

import json
from contextlib import closing
from io import StringIO

import pytest

from ai_stp_cli.answer import Answer
from ai_stp_cli.application.inspect import capabilities as inspect_capabilities
from ai_stp_cli.application.inspect import doctor as inspect_doctor
from ai_stp_cli.application.outcome import operation_id_of
from ai_stp_cli.commands import doctor as doctor_command
from ai_stp_cli.commands import task as task_command
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_cli.output import render_success
from ai_stp_contracts.machine_help import TaskView
from ai_stp_foundation.ids import new_id

KEY = "inspect-orientation-01"


def _start() -> Answer[TaskView]:
    return task_command.start({"intent": "inspect", "idempotency-key": KEY})


def test_inspect_task_start_is_idempotent_and_mints_task_ids() -> None:
    first = _start()
    second = _start()
    assert first.payload.task_id == second.payload.task_id
    assert first.payload.task_id.startswith("task_")
    assert first.payload.intent == "inspect"
    assert first.payload.state == "planned"
    assert first.payload.goal_satisfied is False
    assert first.payload.revision == 1
    assert operation_id_of(first) is None
    assert first.continuations[0].path == ["task", "continue"]
    assert first.continuations[0].arguments["task"] == first.payload.task_id
    assert first.continuations[0].arguments["revision"] == "1"


def test_inspect_continue_stores_the_same_reports_as_the_expert_adapters() -> None:
    started = _start()
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.state == "completed"
    assert continued.payload.goal_satisfied is True
    assert continued.payload.revision == 2
    assert continued.payload.outcome is not None
    assert continued.payload.outcome.doctor == inspect_doctor()
    assert continued.payload.outcome.capabilities == inspect_capabilities()
    assert continued.payload.outcome.doctor == doctor_command.run({}).payload
    assert operation_id_of(continued) is None


def test_inspect_continue_is_idempotent_once_completed() -> None:
    started = _start()
    first = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    again = task_command.continue_(
        {"task": first.payload.task_id, "revision": first.payload.revision}
    )
    assert again.payload.revision == first.payload.revision
    assert again.payload.state == "completed"


def test_stale_revision_is_a_conflict() -> None:
    started = _start()
    with pytest.raises(CliFailure) as raised:
        task_command.continue_({"task": started.payload.task_id, "revision": 99})
    assert raised.value.code == "AI_STP_CONFLICT"


def test_inspect_status_does_not_require_a_machine_global_task() -> None:
    started = _start()
    shown = task_command.status({"task": started.payload.task_id})
    assert shown.payload.task_id == started.payload.task_id
    with pytest.raises(CliFailure) as raised:
        task_command.status({"task": new_id("task")})
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_inspect_cancel_settles_a_planned_task() -> None:
    started = _start()
    cancelled = task_command.cancel(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert cancelled.payload.state == "cancelled"
    assert cancelled.payload.goal_satisfied is False
    with pytest.raises(CliFailure) as raised:
        task_command.continue_(
            {"task": cancelled.payload.task_id, "revision": cancelled.payload.revision}
        )
    assert raised.value.code == "AI_STP_CONFLICT"


def test_inspect_has_no_questions_to_answer() -> None:
    started = _start()
    with pytest.raises(CliFailure) as raised:
        task_command.answer(
            {
                "task": started.payload.task_id,
                "revision": started.payload.revision,
                "question-id": "anything",
                "value": "x",
            }
        )
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_conflicting_idempotency_payload_is_refused() -> None:
    started = _start()
    with closing(open_registry(configured_path())) as connection:
        connection.execute(
            "UPDATE agent_task SET payload_json = ? WHERE task_id = ?",
            ('{"intent":"other"}', started.payload.task_id),
        )
        connection.commit()
    with pytest.raises(CliFailure) as raised:
        _start()
    assert raised.value.code == "AI_STP_CONFLICT"


def test_completed_inspect_envelope_has_no_operation_receipt() -> None:
    started = _start()
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    stream = StringIO()
    render_success(
        continued.payload,
        machine=True,
        request_id=new_id("request"),
        operation_id=operation_id_of(continued),
        stream=stream,
    )
    body = json.loads(stream.getvalue())
    assert body["ok"] is True
    assert body["operation_id"] is None
    assert body["data"]["task_id"] == continued.payload.task_id
    assert body["data"]["task_id"].startswith("task_")
