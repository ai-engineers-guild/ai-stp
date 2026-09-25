"""Durable inspect tasks share application.inspect with expert commands."""

from __future__ import annotations

import json
import os
import threading
import time
from contextlib import closing
from dataclasses import replace as evolve
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


def test_same_start_request_compares_the_stored_original_document() -> None:
    original = agent_tasks.payload_document(
        "switch", {"harness_id": "cursor", "project_root": "/tmp/project"}
    )
    subset = agent_tasks.payload_document("switch", {"harness_id": "cursor"})
    changed = agent_tasks.payload_document(
        "switch", {"harness_id": "cursor", "project_root": "/tmp/other"}
    )
    bare = agent_tasks.payload_document("switch", None)
    other_intent = agent_tasks.payload_document(
        "install", {"harness_id": "cursor", "project_root": "/tmp/project"}
    )
    assert agent_tasks.same_start_request(original, original) is True
    assert agent_tasks.same_start_request(original, subset) is False
    assert agent_tasks.same_start_request(original, changed) is False
    assert agent_tasks.same_start_request(original, bare) is False
    assert agent_tasks.same_start_request(original, other_intent) is False


def test_original_request_of_prefers_the_stored_identity_then_the_held_payload() -> None:
    at = moment()
    payload = agent_tasks.payload_document("inspect", {})
    row = StoredTask(
        task_id=new_id("task"),
        revision=1,
        intent="inspect",
        state="planned",
        goal_satisfied=False,
        idempotency_key="key",
        payload_json=payload,
        outcome_json=None,
        questions_json=agent_tasks.empty_list_json(),
        child_operation_ids_json=agent_tasks.empty_list_json(),
        created_at=at,
        updated_at=at,
    )
    assert agent_tasks.original_request_of(row) == payload
    stamped = evolve(row, original_request_json=agent_tasks.payload_document("inspect", {"x": 1}))
    assert agent_tasks.original_request_of(stamped) != payload


def test_insert_stamps_the_first_start_document_as_the_original() -> None:
    at = moment()
    payload = agent_tasks.payload_document("inspect", {})
    row = StoredTask(
        task_id=new_id("task"),
        revision=1,
        intent="inspect",
        state="planned",
        goal_satisfied=False,
        idempotency_key="insert-stamps-original-01",
        payload_json=payload,
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
        held = agent_tasks.by_id(connection, row.task_id)
    assert held is not None
    assert agent_tasks.original_request_of(held) == payload


def test_start_replays_the_original_request_after_an_answer_enriched_the_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_stp_cli.application import task as task_service
    from ai_stp_cli.application.install_task import DrainResult
    from ai_stp_contracts.machine_help import TaskQuestion

    key = "install-original-replay-01"
    started = task_command.start({"intent": "install", "idempotency-key": key})
    assert started.payload.state == "blocked"
    assert started.payload.questions[0].question_id == "harness-id"

    def drain(_facts: object, **_kwargs: object) -> DrainResult:
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="setup-ref",
                    prompt="Which exact setup should be installed?",
                    value_type="string",
                    choices=[],
                    why="test",
                    actor="human",
                ),
            )
        )

    monkeypatch.setattr(task_service, "drain_install", drain)
    answered = task_command.answer(
        {
            "task": started.payload.task_id,
            "revision": started.payload.revision,
            "question-id": "harness-id",
            "value": "cursor",
        }
    )
    assert answered.payload.task_id == started.payload.task_id
    replayed = task_command.start({"intent": "install", "idempotency-key": key})
    assert replayed.payload.task_id == started.payload.task_id


def test_start_rejects_a_subset_of_the_original_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_stp_cli.application import task as task_service
    from ai_stp_cli.application.install_task import DrainResult
    from ai_stp_contracts.machine_help import TaskQuestion

    def drain(_facts: object, **_kwargs: object) -> DrainResult:
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="setup-ref",
                    prompt="Which exact setup should be installed?",
                    value_type="string",
                    choices=[],
                    why="test",
                    actor="human",
                ),
            )
        )

    monkeypatch.setattr(task_service, "drain_install", drain)
    full = tmp_path / "full.json"
    full.write_text(
        json.dumps({"harness_id": "cursor", "project_root": str(tmp_path.resolve())}),
        encoding="utf-8",
    )
    subset = tmp_path / "subset.json"
    subset.write_text(json.dumps({"harness_id": "cursor"}), encoding="utf-8")
    key = "install-subset-replay-01"
    started = task_command.start({"intent": "install", "idempotency-key": key, "input": str(full)})
    assert started.payload.state == "blocked"
    with pytest.raises(CliFailure) as raised:
        task_command.start({"intent": "install", "idempotency-key": key, "input": str(subset)})
    assert raised.value.code == "AI_STP_CONFLICT"
    assert raised.value.details.get("task") == started.payload.task_id


def test_start_rejects_a_changed_original_input(tmp_path: Path) -> None:
    key = "install-changed-replay-01"
    first_doc = tmp_path / "first.json"
    first_doc.write_text(json.dumps({"harness_id": "cursor"}), encoding="utf-8")
    changed_doc = tmp_path / "changed.json"
    changed_doc.write_text(json.dumps({"harness_id": "codex"}), encoding="utf-8")
    started = task_command.start(
        {"intent": "install", "idempotency-key": key, "input": str(first_doc)}
    )
    with pytest.raises(CliFailure) as raised:
        task_command.start({"intent": "install", "idempotency-key": key, "input": str(changed_doc)})
    assert raised.value.code == "AI_STP_CONFLICT"
    assert raised.value.details.get("task") == started.payload.task_id


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


def test_concurrent_continue_on_one_revision_has_one_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two callers race the same blocked revision: exactly one drains.

    The loser joins the live executor's bounded wait instead of claiming a
    fresh revision beside it — and never enters a second drain.
    """
    from concurrent.futures import ThreadPoolExecutor

    from ai_stp_cli.application import task as task_service

    monkeypatch.setattr(task_service, "RUNNING_JOIN_SECONDS", 1.0)
    monkeypatch.setattr(task_service, "RUNNING_JOIN_POLL_SECONDS", 0.05)
    row = _planned_inspect("inspect-concurrent-01")
    entered, release, entries = _barrier_drain(monkeypatch)
    parameters = {"task": row.task_id, "revision": row.revision}
    won: list[Answer[TaskView]] = []
    lost: list[CliFailure] = []

    def work() -> None:
        try:
            won.append(task_command.continue_(parameters))
        except CliFailure as error:
            lost.append(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        racers = [pool.submit(work), pool.submit(work)]
        assert entered.wait(timeout=10)
        # While one executor drains, the other waits its bounded join.
        time.sleep(0.2)
        release.set()
        for racer in racers:
            racer.result(timeout=10)
    assert entries == [1]
    assert len(won) + len(lost) == 2
    assert all(error.code == "AI_STP_CONFLICT" for error in lost)
    assert all(item.payload.task_id == row.task_id for item in won)
    # One drain ran; the other caller joined it (settled or in-progress
    # view) or lost the stale-revision conflict — never a second drain.
    assert any(item.payload.state == "completed" for item in won)
    assert all(item.payload.state in {"planned", "running", "completed"} for item in won)


def _planned_inspect(key: str) -> StoredTask:
    """A minted inspect row: start would drain it, so tests insert it directly."""
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
    return row


def _barrier_drain(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[threading.Event, threading.Event, list[int]]:
    """Hold the inspect drain at a barrier and count how often it is entered."""
    from ai_stp_cli.application import task as task_service

    entered = threading.Event()
    release = threading.Event()
    entries: list[int] = []

    def held() -> object:
        entries.append(1)
        entered.set()
        assert release.wait(timeout=30)
        return inspect_doctor()

    monkeypatch.setattr(task_service, "doctor", held)
    return entered, release, entries


def test_continue_on_a_live_executor_joins_instead_of_draining(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The running revision is not permission for a second drain.

    Caller A holds the executor lease inside a barriered drain; caller B,
    armed only with the observed running revision, joins the bounded wait
    rather than entering a parallel drain.
    """
    from concurrent.futures import ThreadPoolExecutor

    from ai_stp_cli.application import task as task_service

    monkeypatch.setattr(task_service, "RUNNING_JOIN_SECONDS", 1.0)
    monkeypatch.setattr(task_service, "RUNNING_JOIN_POLL_SECONDS", 0.05)
    row = _planned_inspect("inspect-live-executor-01")
    entered, release, entries = _barrier_drain(monkeypatch)
    joined: list[Answer[TaskView]] = []

    with ThreadPoolExecutor(max_workers=2) as pool:
        executor = pool.submit(
            task_command.continue_, {"task": row.task_id, "revision": row.revision}
        )
        assert entered.wait(timeout=10)
        observed = task_command.status({"task": row.task_id})
        assert observed.payload.state == "running"
        assert observed.continuations[0].actor == "external"
        joined.append(
            pool.submit(
                task_command.continue_,
                {"task": row.task_id, "revision": observed.payload.revision},
            ).result(timeout=10)
        )
        # The second caller waited out its join bound without entering a drain.
        assert entries == [1]
        assert joined[0].payload.state == "running"
        assert joined[0].continuations[0].actor == "external"
        release.set()
        finished = executor.result(timeout=10)
    assert finished.payload.state == "completed"
    assert entries == [1]


def test_a_dead_executors_running_row_is_recovered_by_the_next_continue() -> None:
    """A `running` row whose lease is free names a dead owner, not a rival."""
    row = _planned_inspect("inspect-dead-executor-01")
    claimed = agent_tasks.claim(row, at=moment())
    with (
        closing(open_registry(configured_path(), create=True)) as connection,
        transaction(connection),
    ):
        agent_tasks.replace(connection, claimed)

    status = task_command.status({"task": row.task_id})
    assert status.payload.state == "running"
    # No live executor holds the lease: continuing is the safe recovery.
    assert status.continuations[0].actor == "cli"

    recovered = task_command.continue_({"task": row.task_id, "revision": claimed.revision})
    assert recovered.payload.state == "completed"
    assert recovered.payload.goal_satisfied is True


@pytest.mark.skipif(os.name != "posix", reason="flock release on death is POSIX-verified")
def test_the_lease_dies_with_the_executor_process() -> None:
    """Two real processes: the OS releases the lock when the holder is killed."""
    import signal
    import subprocess
    import sys

    from ai_stp_cli.local import executor_lease

    task_id = new_id("task")
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import fcntl, os, sys, time\n"
                "path = sys.argv[1]\n"
                "fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)\n"
                "fcntl.flock(fd, fcntl.LOCK_EX)\n"
                "open(path + '.held', 'w').close()\n"
                "time.sleep(60)\n"
            ),
            str(executor_lease._path(task_id)),  # pyright: ignore[reportPrivateUsage]
        ]
    )
    try:
        deadline = time.monotonic() + 10
        while not executor_lease.held(task_id):
            assert time.monotonic() < deadline, "the holder never took the lease"
            time.sleep(0.05)
    finally:
        holder.send_signal(signal.SIGKILL)
        holder.wait(timeout=10)
    deadline = time.monotonic() + 10
    while executor_lease.held(task_id):
        assert time.monotonic() < deadline, "the OS never released the lease"
        time.sleep(0.05)


def test_cancel_before_effects_settles_immediately() -> None:
    """No children, no outcome, no live executor: nothing could have happened."""
    started = task_command.start(
        {"intent": "initialize", "idempotency-key": "inspect-cancel-prefx-01"}
    )
    assert started.payload.state == "blocked"
    cancelled = task_command.cancel(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert cancelled.payload.state == "cancelled"


def test_cancel_during_a_live_drain_settles_at_the_drain_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A live executor cannot be terminalized by the cancel call itself.

    The request is recorded; the drain's own commit honors it, and the
    outcome it produced stays attached so `cancelled` is never 'nothing
    happened'.
    """
    from concurrent.futures import ThreadPoolExecutor

    row = _planned_inspect("inspect-cancel-live-01")
    entered, release, _entries = _barrier_drain(monkeypatch)
    with ThreadPoolExecutor(max_workers=1) as pool:
        executor = pool.submit(
            task_command.continue_, {"task": row.task_id, "revision": row.revision}
        )
        assert entered.wait(timeout=10)
        observed = task_command.status({"task": row.task_id})
        requested = task_command.cancel(
            {"task": row.task_id, "revision": observed.payload.revision}
        )
        # The task is still running: cancellation is a request, not a verdict.
        assert requested.payload.state == "running"
        release.set()
        finished = executor.result(timeout=10)
    assert finished.payload.state == "cancelled"
    assert finished.payload.goal_satisfied is True
    assert finished.payload.outcome is not None
    assert finished.payload.outcome.kind == "inspect"
    with pytest.raises(CliFailure) as raised:
        task_command.continue_({"task": row.task_id, "revision": finished.payload.revision})
    assert raised.value.code == "AI_STP_CONFLICT"


def test_cancel_of_a_dead_executor_recovers_then_settles() -> None:
    """Cancellation of an abandoned running row keeps the resumable path:
    a later continue reconciles the drain and then settles cancelled."""
    row = _planned_inspect("inspect-cancel-dead-01")
    claimed = agent_tasks.claim(row, at=moment())
    held = agent_tasks.with_children(claimed, ("operation_testchild01",), at=moment())
    with (
        closing(open_registry(configured_path(), create=True)) as connection,
        transaction(connection),
    ):
        agent_tasks.replace(connection, held)

    requested = task_command.cancel({"task": row.task_id, "revision": held.revision})
    # Not terminal: the recorded child may already have had an effect.
    assert requested.payload.state == "running"
    assert requested.payload.child_operation_ids == ["operation_testchild01"]
    # A free lease marks the row as recoverable, not as settled.
    assert requested.continuations[0].actor == "cli"

    settled = task_command.continue_({"task": row.task_id, "revision": requested.payload.revision})
    assert settled.payload.state == "cancelled"
    assert settled.payload.child_operation_ids == ["operation_testchild01"]
    assert settled.payload.outcome is not None


def test_cancel_requested_twice_is_one_request() -> None:
    row = _planned_inspect("inspect-cancel-twice-01")
    claimed = agent_tasks.claim(row, at=moment())
    with (
        closing(open_registry(configured_path(), create=True)) as connection,
        transaction(connection),
    ):
        agent_tasks.replace(connection, claimed)
    first = task_command.cancel({"task": row.task_id, "revision": claimed.revision})
    second = task_command.cancel({"task": row.task_id, "revision": first.payload.revision})
    assert second.payload.state == "running"


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


@pytest.mark.parametrize("key", ["init-1790264096", "x" * 129, "private value!", "é" * 16])
def test_invalid_task_key_explains_constraints_without_echoing_input(key: str) -> None:
    from ai_stp_contracts.http import IDEMPOTENCY_KEY_PATTERN

    existed = configured_path().exists()
    with pytest.raises(CliFailure) as raised:
        task_command.start({"intent": "inspect", "idempotency-key": key})
    error = raised.value
    assert error.code == "AI_STP_VALIDATION_ERROR"
    assert error.details == {"field": "idempotency-key", "pattern": IDEMPOTENCY_KEY_PATTERN}
    assert key not in error.message
    assert key not in json.dumps(error.details)
    assert continuation_argv(error.continuations[0]) == ["help", "--path", "task start", "--json"]
    assert configured_path().exists() == existed


@pytest.mark.parametrize("key", ["a" * 16, "z" * 128, "valid.key_01~-task"])
def test_task_key_boundary_values_keep_idempotent_start(key: str) -> None:
    parameters = {"intent": "inspect", "idempotency-key": key}
    first = task_command.start(parameters)
    repeated = task_command.start(parameters)
    assert first.payload.task_id == repeated.payload.task_id
    assert first.payload.goal_satisfied is True
    assert first.payload.revision == repeated.payload.revision


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
    key = next(item for item in start.descriptor.parameters if item.name == "idempotency-key")
    assert "16 to 128 ASCII" in key.summary
    assert "same request" in key.summary
    intent = next(item for item in start.descriptor.parameters if item.name == "intent")
    assert tuple(intent.choices) == SHIPPED_INTENT_NAMES
    by_name = {item.name: item.when for item in catalog.payload.intents}
    assert "provider-too-old" in by_name["initialize"]
    assert "do not start account" in by_name["initialize"]
    assert "provider-too-old" in by_name["account"]
    assert "Login never uploads" in by_name["account"]


@pytest.mark.parametrize("case", ["inline-json", "missing-file", "invalid-utf8"])
def test_unreadable_task_input_explains_file_or_stdin_without_echoing_values(
    case: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    locator = str(tmp_path / "missing.json")
    if case == "inline-json":
        locator = '{"private_value":"do-not-echo-this-input"}'
    elif case == "invalid-utf8":
        place = tmp_path / "invalid.json"
        place.write_bytes(b"\xff\xfe")
        locator = str(place)
    code = app.main(
        [
            "task",
            "start",
            "--intent",
            "install",
            "--idempotency-key",
            "unreadable-task-input-01",
            "--input",
            locator,
            "--json",
        ]
    )
    output = capsys.readouterr().out
    body = json.loads(output)
    assert code == 2
    assert body["error"]["code"] == "AI_STP_VALIDATION_ERROR"
    assert "JSON/YAML file path or '-' for stdin" in body["error"]["message"]
    assert body["error"]["details"]["field"] == "input"
    assert "do-not-echo-this-input" not in output
    assert body["continuations"][0]["argv"] == ["help", "--path", "task start", "--json"]
    assert task_command.list_({}).payload.tasks == []


def test_conflicting_idempotency_payload_is_refused() -> None:
    started = _start()
    with closing(open_registry(configured_path())) as connection:
        connection.execute(
            "UPDATE agent_task SET original_request_json = ? WHERE task_id = ?",
            ('{"intent":"other"}', started.payload.task_id),
        )
        connection.commit()
    with pytest.raises(CliFailure) as raised:
        _start()
    assert raised.value.code == "AI_STP_CONFLICT"


def test_mutable_payload_is_not_the_idempotency_identity() -> None:
    """A changed held payload cannot forge or break the recorded original."""
    started = _start()
    with closing(open_registry(configured_path())) as connection:
        connection.execute(
            "UPDATE agent_task SET payload_json = ? WHERE task_id = ?",
            ('{"intent":"inspect","input":{"merged":1}}', started.payload.task_id),
        )
        connection.commit()
    replayed = _start()
    assert replayed.payload.task_id == started.payload.task_id


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
