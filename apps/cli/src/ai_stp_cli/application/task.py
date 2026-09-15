"""Durable agent tasks. Closed intents call named in-process services."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping
from contextlib import closing

from ai_stp_cli.answer import Answer
from ai_stp_cli.application.inspect import capabilities, doctor
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import agent_tasks
from ai_stp_cli.local.agent_tasks import StoredTask
from ai_stp_cli.local.database import configured_path, open_registry, transaction
from ai_stp_cli.local.passports import moment
from ai_stp_contracts.machine_help import TaskInspectOutcome, TaskView
from ai_stp_foundation.envelope import Continuation
from ai_stp_foundation.ids import is_valid_id, new_id

INSPECT_INTENT = "inspect"
SUPPORTED_INTENTS = (INSPECT_INTENT,)
SETTLED = frozenset({"completed", "failed", "cancelled"})
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._~-]{16,128}$")


def start(parameters: Mapping[str, object]) -> Answer[TaskView]:
    intent = str(parameters.get("intent") or "")
    if intent not in SUPPORTED_INTENTS:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the task intent is not supported",
            details={"intent": intent, "supported": ",".join(SUPPORTED_INTENTS)},
            next_actions=["help --path task --json"],
        )
    key = str(parameters.get("idempotency-key") or "")
    if _IDEMPOTENCY_KEY.fullmatch(key) is None:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "the idempotency key is not a valid key")
    payload = agent_tasks.payload_document(intent)
    at = moment()
    with (
        closing(open_registry(configured_path(), create=True)) as connection,
        transaction(connection),
    ):
        held = agent_tasks.by_idempotency_key(connection, key)
        if held is not None:
            if held.payload_json != payload:
                raise CliFailure(
                    "AI_STP_CONFLICT",
                    "the idempotency key already names a different intent",
                    details={"task": held.task_id},
                )
            return _answer(agent_tasks.view_of(held))
        row = StoredTask(
            task_id=new_id("task"),
            revision=1,
            intent=intent,
            state="planned",
            goal_satisfied=False,
            idempotency_key=key,
            payload_json=payload,
            outcome_json=None,
            questions_json=agent_tasks.empty_list_json(),
            child_operation_ids_json=agent_tasks.empty_list_json(),
            created_at=at,
            updated_at=at,
        )
        agent_tasks.insert(connection, row)
    return _answer(agent_tasks.view_of(row))


def continue_task(parameters: Mapping[str, object]) -> Answer[TaskView]:
    row = _load_for_write(parameters)
    if row.state == "completed":
        return _answer(agent_tasks.view_of(row))
    if row.state in SETTLED:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the task is already settled",
            details={"task": row.task_id, "state": row.state},
        )
    if row.intent != INSPECT_INTENT:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the task intent is not supported",
            details={"intent": row.intent},
        )
    outcome = TaskInspectOutcome(doctor=doctor(), capabilities=capabilities())
    updated = _commit_if_current(row, agent_tasks.with_outcome(row, outcome, at=moment()))
    return _answer(agent_tasks.view_of(updated))


def answer_task(parameters: Mapping[str, object]) -> Answer[TaskView]:
    row = _load_for_write(parameters)
    if row.state in SETTLED:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the task is already settled",
            details={"task": row.task_id, "state": row.state},
        )
    raise CliFailure(
        "AI_STP_VALIDATION_ERROR",
        "this task has no open questions",
        details={"task": row.task_id},
    )


def status(parameters: Mapping[str, object]) -> Answer[TaskView]:
    task_id = _task_id(parameters)
    with closing(open_registry(configured_path(), create=False)) as connection:
        row = agent_tasks.by_id(connection, task_id)
    if row is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the task is not held by this registry",
            details={"task": task_id},
        )
    return _answer(agent_tasks.view_of(row))


def cancel(parameters: Mapping[str, object]) -> Answer[TaskView]:
    row = _load_for_write(parameters)
    if row.state in SETTLED:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the task is already settled",
            details={"task": row.task_id, "state": row.state},
        )
    updated = _commit_if_current(row, agent_tasks.cancelled(row, at=moment()))
    return _answer(agent_tasks.view_of(updated))


def _load_for_write(parameters: Mapping[str, object]) -> StoredTask:
    task_id = _task_id(parameters)
    expected = _revision(parameters)
    with closing(open_registry(configured_path(), create=False)) as connection:
        row = agent_tasks.by_id(connection, task_id)
    if row is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the task is not held by this registry",
            details={"task": task_id},
        )
    if row.revision != expected:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the task revision does not match",
            details={"task": task_id, "expected": str(expected), "found": str(row.revision)},
        )
    return row


def _commit_if_current(expected: StoredTask, updated: StoredTask) -> StoredTask:
    with (
        closing(open_registry(configured_path(), create=False)) as connection,
        transaction(connection),
    ):
        current = _held(connection, expected.task_id)
        if current.revision != expected.revision:
            raise CliFailure(
                "AI_STP_CONFLICT",
                "the task revision does not match",
                details={
                    "task": expected.task_id,
                    "expected": str(expected.revision),
                    "found": str(current.revision),
                },
            )
        agent_tasks.replace(connection, updated)
    return updated


def _held(connection: sqlite3.Connection, task_id: str) -> StoredTask:
    row = agent_tasks.by_id(connection, task_id)
    if row is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the task is not held by this registry",
            details={"task": task_id},
        )
    return row


def _task_id(parameters: Mapping[str, object]) -> str:
    value = str(parameters.get("task") or "")
    if not is_valid_id(value, "task"):
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the task is not held by this registry",
            details={"task": value},
        )
    return value


def _revision(parameters: Mapping[str, object]) -> int:
    raw = parameters.get("revision")
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise CliFailure("AI_STP_VALIDATION_ERROR", "the task revision does not match")
    if raw < 1:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "the task revision does not match")
    return raw


def _answer(view: TaskView) -> Answer[TaskView]:
    if view.state == "planned":
        return Answer(
            view,
            continuations=(
                Continuation(
                    kind="advance",
                    path=["task", "continue"],
                    arguments={"task": view.task_id, "revision": str(view.revision)},
                ),
            ),
        )
    if view.state == "blocked":
        return Answer(
            view,
            continuations=(
                Continuation(
                    kind="blocked",
                    path=["task", "answer"],
                    arguments={"task": view.task_id, "revision": str(view.revision)},
                    missing=["question-id", "value"],
                ),
            ),
        )
    return Answer(view)
