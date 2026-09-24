"""Durable inspect tasks share application.inspect with expert commands."""

from __future__ import annotations

import json
import time
from contextlib import closing
from io import StringIO
from pathlib import Path

import pytest

from ai_stp_cli import app
from ai_stp_cli.answer import Answer
from ai_stp_cli.application.inspect import doctor as inspect_doctor
from ai_stp_cli.application.inspect import orientation as inspect_orientation
from ai_stp_cli.application.outcome import operation_id_of
from ai_stp_cli.commands import doctor as doctor_command
from ai_stp_cli.commands import task as task_command
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import agent_tasks
from ai_stp_cli.local.agent_tasks import StoredTask
from ai_stp_cli.local.database import configured_path, open_registry, transaction
from ai_stp_cli.local.passports import moment
from ai_stp_cli.output import render_success
from ai_stp_contracts.machine_help import TaskView
from ai_stp_foundation.envelope import Continuation, continuation_argv
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
    assert first.payload.state == "completed"
    assert first.payload.goal_satisfied is True
    assert first.payload.revision == 3
    assert operation_id_of(first) is None
    assert first.continuations == ()
    assert first.payload.outcome is not None
    assert first.payload.outcome.kind == "inspect"


def test_same_start_payload_treats_drain_checkpoints_as_the_original_input() -> None:
    original = agent_tasks.payload_document(
        "switch", {"harness_id": "cursor", "project_root": "/tmp/project"}
    )
    checkpoint = agent_tasks.payload_document(
        "switch",
        {
            "harness_id": "cursor",
            "project_root": "/tmp/project",
            "preserved_setup_id": "setup_01TEST",
            "state": "verified",
        },
    )
    other = agent_tasks.payload_document(
        "switch", {"harness_id": "cursor", "project_root": "/tmp/other"}
    )
    bare = agent_tasks.payload_document("switch", None)
    assert agent_tasks.same_start_payload(original, original) is True
    assert agent_tasks.same_start_payload(checkpoint, original) is True
    assert agent_tasks.same_start_payload(checkpoint, other) is False
    assert agent_tasks.same_start_payload(checkpoint, bare) is False
    assert agent_tasks.same_start_payload(bare, original) is False


def test_start_drains_a_leftover_planned_row() -> None:
    key = "inspect-leftover-planned-01"
    at = moment()
    row = StoredTask(
        task_id=new_id("task"),
        revision=1,
        intent="inspect",
        state="planned",
        goal_satisfied=False,
        idempotency_key=key,
        payload_json=agent_tasks.payload_document("inspect", {}),
        outcome_json=None,
        questions_json=agent_tasks.empty_list_json(),
        child_operation_ids_json=agent_tasks.empty_list_json(),
        created_at=at,
        updated_at=at,
    )
    with (
        closing(open_registry(configured_path(), create=True)) as connection,
        transaction(connection),
    ):
        agent_tasks.insert(connection, row)
    started = task_command.start({"intent": "inspect", "idempotency-key": key})
    assert started.payload.task_id == row.task_id
    assert started.payload.state == "completed"
    assert started.payload.goal_satisfied is True
    assert started.continuations == ()


def test_start_joins_a_leftover_running_row(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_stp_cli.application import task as task_service

    monkeypatch.setattr(task_service, "RUNNING_JOIN_SECONDS", 0.0)
    key = "inspect-leftover-running-01"
    at = moment()
    row = StoredTask(
        task_id=new_id("task"),
        revision=2,
        intent="inspect",
        state="running",
        goal_satisfied=False,
        idempotency_key=key,
        payload_json=agent_tasks.payload_document("inspect", {}),
        outcome_json=None,
        questions_json=agent_tasks.empty_list_json(),
        child_operation_ids_json=agent_tasks.empty_list_json(),
        created_at=at,
        updated_at=at,
    )
    with (
        closing(open_registry(configured_path(), create=True)) as connection,
        transaction(connection),
    ):
        agent_tasks.insert(connection, row)
    started = task_command.start({"intent": "inspect", "idempotency-key": key})
    assert started.payload.task_id == row.task_id
    assert started.payload.state == "completed"
    assert started.payload.goal_satisfied is True
    assert started.continuations == ()


def test_concurrent_inspect_start_joins_the_same_key() -> None:
    from concurrent.futures import ThreadPoolExecutor

    # Race the task key after schema preparation. Concurrent first opens have
    # their own registry regression; migrations are not part of this wait.
    with closing(open_registry(configured_path(), create=True)):
        pass
    key = "inspect-concurrent-start-01"
    parameters = {"intent": "inspect", "idempotency-key": key}
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(lambda: task_command.start(parameters))
        second = pool.submit(lambda: task_command.start(parameters))
        results = [first.result(timeout=10), second.result(timeout=10)]
    assert results[0].payload.task_id == results[1].payload.task_id
    assert {item.payload.state for item in results} == {"completed"}
    assert all(item.continuations == () for item in results)


def test_inspect_continue_stores_the_same_reports_as_the_expert_adapters() -> None:
    started = _start()
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert started.payload.state == "completed"
    assert continued.payload.state == "completed"
    assert continued.payload.goal_satisfied is True
    assert continued.payload.revision == started.payload.revision
    assert continued.payload.outcome is not None
    assert continued.payload.outcome.kind == "inspect"
    assert continued.payload.outcome.doctor == inspect_doctor()
    assert continued.payload.outcome.orientation == inspect_orientation()
    assert "command_paths" not in continued.payload.outcome.orientation.model_dump()
    assert continued.payload.outcome.doctor == doctor_command.run({}).payload
    assert continued.continuations == ()


def test_inspect_protocol_uses_emitted_argv(capsys: pytest.CaptureFixture[str]) -> None:
    code = app.main(
        [
            "task",
            "start",
            "--intent",
            "inspect",
            "--idempotency-key",
            "inspect-protocol-argv-01",
            "--json",
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    body = json.loads(captured.out)
    assert body["ok"] is True
    assert body["data"]["state"] == "completed"
    assert body["data"]["goal_satisfied"] is True
    assert body["continuations"] == []
    assert body["data"]["outcome"]["kind"] == "inspect"
    assert "command_paths" not in body["data"]["outcome"]["orientation"]


def test_intents_catalog_drives_inspect_without_typed_flags() -> None:
    catalog = task_command.intents({})
    names = [item.name for item in catalog.payload.intents]
    assert names[0] == "inspect"
    started = task_command.start({"intent": names[0], "idempotency-key": "inspect-from-intents-01"})
    assert started.payload.state == "completed"
    assert started.continuations == ()
    assert started.payload.outcome is not None
    assert started.payload.outcome.kind == "inspect"


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


def test_concurrent_continue_on_one_revision_has_one_winner() -> None:
    from concurrent.futures import ThreadPoolExecutor

    started = task_command.start(
        {"intent": "initialize", "idempotency-key": "inspect-concurrent-01"}
    )
    assert started.payload.state == "blocked"
    parameters = {"task": started.payload.task_id, "revision": started.payload.revision}
    won: list[Answer[TaskView]] = []
    lost: list[CliFailure] = []

    def work() -> None:
        try:
            won.append(task_command.continue_(parameters))
        except CliFailure as error:
            lost.append(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(work), pool.submit(work)]
        for future in futures:
            future.result()
    assert len(won) == 1
    assert won[0].payload.state == "blocked"
    assert won[0].payload.questions[0].question_id == "harness-id"
    assert len(lost) == 1
    assert lost[0].code == "AI_STP_CONFLICT"


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
    started = task_command.start(
        {"intent": "initialize", "idempotency-key": "initialize-cancel-0001"}
    )
    assert started.payload.state == "blocked"
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
    assert raised.value.code == "AI_STP_CONFLICT"


def test_unshipped_intent_names_are_refused() -> None:
    with pytest.raises(CliFailure) as raised:
        task_command.start({"intent": "compose", "idempotency-key": KEY})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    assert raised.value.next_actions == ["task intents --json"]
    assert raised.value.continuations[0].argv == ["task", "intents", "--json"]
    assert raised.value.continuations[0].actor == "cli"


def test_inspect_input_facts_are_refused(tmp_path: Path) -> None:
    place = tmp_path / "input.json"
    place.write_text('{"harness_id":"cursor"}', encoding="utf-8")
    with pytest.raises(CliFailure) as raised:
        task_command.start({"intent": "inspect", "idempotency-key": KEY, "input": str(place)})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_task_intents_lists_shipped_intents_only() -> None:
    from ai_stp_cli.application.inspect import SHIPPED_INTENT_NAMES
    from ai_stp_cli.registry import COMMANDS

    catalog = task_command.intents({})
    assert [item.name for item in catalog.payload.intents] == list(SHIPPED_INTENT_NAMES)
    assert catalog.payload.intents[0].input_schema.endswith("cli-task-input-inspect")
    assert catalog.payload.intents[1].input_schema.endswith("cli-task-input-initialize")
    assert catalog.payload.intents[2].input_schema.endswith("cli-task-input-install")
    assert catalog.payload.intents[3].input_schema.endswith("cli-task-input-change")
    assert catalog.payload.intents[4].input_schema.endswith("cli-task-input-author")
    assert catalog.payload.intents[5].input_schema.endswith("cli-task-input-switch")
    assert catalog.payload.intents[6].input_schema.endswith("cli-task-input-account")
    assert catalog.payload.intents[7].input_schema.endswith("cli-task-input-publish")
    start = next(item for item in COMMANDS if item.name == "task start")
    intent = next(item for item in start.descriptor.parameters if item.name == "intent")
    assert tuple(intent.choices) == SHIPPED_INTENT_NAMES
    by_name = {item.name: item.when for item in catalog.payload.intents}
    assert "provider-too-old" in by_name["initialize"]
    assert "do not start account" in by_name["initialize"]
    assert "provider-too-old" in by_name["account"]
    assert "Login never uploads" in by_name["account"]


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


def test_continuation_argv_round_trips_spaces_and_dash_prefixed_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    place = tmp_path / "my input.json"
    place.write_text("{}", encoding="utf-8")
    dashed = tmp_path / "-facts.json"
    dashed.write_text("{}", encoding="utf-8")
    spaced = Continuation(
        kind="advance",
        path=["task", "start"],
        arguments={
            "intent": "inspect",
            "idempotency-key": "inspect-key-00001",
            "input": str(place),
        },
    )
    code = app.main(continuation_argv(spaced))
    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["ok"] is True
    monkeypatch.chdir(tmp_path)
    prefixed = Continuation(
        kind="advance",
        path=["task", "start"],
        arguments={
            "intent": "inspect",
            "idempotency-key": "inspect-key-00002",
            "input": "-facts.json",
        },
    )
    tokens = continuation_argv(prefixed)
    assert "--input=-facts.json" in tokens
    code = app.main(tokens)
    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["ok"] is True


def test_task_outcome_refuses_an_unknown_kind() -> None:
    from pydantic import ValidationError

    from ai_stp_cli.local.agent_tasks import parse_outcome
    from ai_stp_contracts.machine_help import TaskInspectOutcome

    with pytest.raises(ValidationError) as raised:
        TaskInspectOutcome.model_validate({"kind": "install"})
    assert any(error["loc"] == ("kind",) for error in raised.value.errors())
    with pytest.raises(ValueError, match="unsupported task outcome kind"):
        parse_outcome('{"kind": "compose"}')


def test_two_inspect_tasks_may_run_together() -> None:
    first = task_command.start({"intent": "inspect", "idempotency-key": "inspect-overlap-a-0001"})
    second = task_command.start({"intent": "inspect", "idempotency-key": "inspect-overlap-b-0001"})
    assert first.payload.task_id != second.payload.task_id
    left = task_command.continue_(
        {"task": first.payload.task_id, "revision": first.payload.revision}
    )
    right = task_command.continue_(
        {"task": second.payload.task_id, "revision": second.payload.revision}
    )
    assert left.payload.state == "completed"
    assert right.payload.state == "completed"


def test_second_mutating_start_on_the_same_target_conflicts(tmp_path: Path) -> None:
    facts = tmp_path / "facts.json"
    facts.write_text(json.dumps({"harness_id": "cursor"}), encoding="utf-8")
    first = task_command.start(
        {
            "intent": "initialize",
            "idempotency-key": "overlap-mut-a-0000001",
            "input": str(facts),
        }
    )
    with pytest.raises(CliFailure) as caught:
        task_command.start(
            {
                "intent": "initialize",
                "idempotency-key": "overlap-mut-b-0000001",
                "input": str(facts),
            }
        )
    assert caught.value.code == "AI_STP_CONFLICT"
    assert caught.value.details["task"] == first.payload.task_id


def test_different_project_roots_do_not_conflict(tmp_path: Path) -> None:
    first_facts = tmp_path / "a.json"
    second_facts = tmp_path / "b.json"
    first_facts.write_text(
        json.dumps({"harness_id": "cursor", "project_root": "left"}),
        encoding="utf-8",
    )
    second_facts.write_text(
        json.dumps({"harness_id": "cursor", "project_root": "right"}),
        encoding="utf-8",
    )
    first = task_command.start(
        {
            "intent": "install",
            "idempotency-key": "overlap-root-a-0000001",
            "input": str(first_facts),
        }
    )
    second = task_command.start(
        {
            "intent": "install",
            "idempotency-key": "overlap-root-b-0000001",
            "input": str(second_facts),
        }
    )
    assert first.payload.state == "blocked"
    assert second.payload.state == "blocked"
    assert first.payload.task_id != second.payload.task_id


def test_answering_the_same_harness_on_a_second_task_conflicts() -> None:
    first = task_command.start({"intent": "initialize", "idempotency-key": "overlap-ans-a-0000001"})
    second = task_command.start(
        {"intent": "initialize", "idempotency-key": "overlap-ans-b-0000001"}
    )
    blocked = task_command.continue_(
        {"task": first.payload.task_id, "revision": first.payload.revision}
    )
    other = task_command.continue_(
        {"task": second.payload.task_id, "revision": second.payload.revision}
    )
    task_command.answer(
        {
            "task": blocked.payload.task_id,
            "revision": blocked.payload.revision,
            "question-id": "harness-id",
            "value": "cursor",
        }
    )
    with pytest.raises(CliFailure) as caught:
        task_command.answer(
            {
                "task": other.payload.task_id,
                "revision": other.payload.revision,
                "question-id": "harness-id",
                "value": "cursor",
            }
        )
    assert caught.value.code == "AI_STP_CONFLICT"
    assert caught.value.details["task"] == first.payload.task_id


def test_task_answer_without_task_resumes_the_unique_blocked_question() -> None:
    from ai_stp_cli.application.task import missing_answer_hint

    started = task_command.start(
        {"intent": "initialize", "idempotency-key": "initialize-hint-svc-01"}
    )
    assert started.payload.state == "blocked"
    hinted = missing_answer_hint()
    assert hinted is not None
    assert hinted.message == "task answer needs the open question"
    assert hinted.details["task"] == started.payload.task_id
    assert hinted.continuations[0].argv[:4] == [
        "task",
        "answer",
        "--task",
        started.payload.task_id,
    ]
    assert hinted.continuations[0].actor == "human"
    assert "--value" not in hinted.continuations[0].argv


def test_task_answer_without_task_lists_open_tasks_when_two_are_open() -> None:
    from ai_stp_cli.application.task import missing_answer_hint

    task_command.start({"intent": "initialize", "idempotency-key": "initialize-hint-x-0001"})
    task_command.start({"intent": "initialize", "idempotency-key": "initialize-hint-y-0001"})
    hinted = missing_answer_hint()
    assert hinted is not None
    assert hinted.continuations[0].argv == ["task", "list", "--json"]
    assert hinted.continuations[0].actor == "cli"


def test_task_list_returns_only_unsettled_tasks_newest_first() -> None:
    task_command.start({"intent": "inspect", "idempotency-key": "inspect-list-0000001"})
    time.sleep(0.01)
    held = task_command.start({"intent": "initialize", "idempotency-key": "initialize-list-a-0001"})

    listed = task_command.list_({})
    assert [entry.task_id for entry in listed.payload.tasks] == [held.payload.task_id]
    entry = listed.payload.tasks[0]
    assert entry.intent == "initialize"
    assert entry.state == "blocked"
    assert entry.open_question_ids
    assert entry.revision == held.payload.revision


def test_task_list_on_a_fresh_registry_is_empty() -> None:
    assert task_command.list_({}).payload.tasks == []


def test_task_list_reports_an_unreadable_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    def refused(_path: Path, *, create: bool = True) -> object:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "the task input is not valid")

    monkeypatch.setattr("ai_stp_cli.application.task.open_registry", refused)
    with pytest.raises(CliFailure) as raised:
        task_command.list_({})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_task_list_orders_by_updated_at_descending() -> None:
    first = task_command.start(
        {"intent": "initialize", "idempotency-key": "initialize-list-ord-01"}
    )
    time.sleep(0.01)
    second = task_command.start(
        {"intent": "initialize", "idempotency-key": "initialize-list-ord-02"}
    )
    listed = task_command.list_({})
    ids = [entry.task_id for entry in listed.payload.tasks]
    assert ids.index(second.payload.task_id) < ids.index(first.payload.task_id)


def test_task_answer_without_revision_resumes_the_named_task() -> None:
    from ai_stp_cli.application.task import missing_answer_hint

    started = task_command.start(
        {"intent": "initialize", "idempotency-key": "initialize-hint-rev-01"}
    )
    other = task_command.start(
        {"intent": "initialize", "idempotency-key": "initialize-hint-rev-02"}
    )
    ambiguous = missing_answer_hint()
    assert ambiguous is not None
    assert ambiguous.continuations[0].argv == ["task", "list", "--json"]
    hinted = missing_answer_hint(task_id=started.payload.task_id)
    assert hinted is not None
    assert hinted.details["task"] == started.payload.task_id
    assert hinted.details["task"] != other.payload.task_id
    assert "--revision" in hinted.continuations[0].argv
    assert str(started.payload.revision) in hinted.continuations[0].argv
