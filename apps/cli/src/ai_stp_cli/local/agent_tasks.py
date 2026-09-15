"""Durable agent-task rows in the local registry (SPEC-080)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from ai_stp_contracts.machine_help import TaskInspectOutcome, TaskQuestion, TaskView
from ai_stp_foundation.canonical import canonize


@dataclass(frozen=True)
class StoredTask:
    task_id: str
    revision: int
    intent: str
    state: str
    goal_satisfied: bool
    idempotency_key: str
    payload_json: str
    outcome_json: str | None
    questions_json: str
    child_operation_ids_json: str
    created_at: str
    updated_at: str


def payload_document(intent: str) -> str:
    """Canonical start payload used for idempotency comparison."""
    return canonize({"intent": intent}).decode("utf-8")


def by_id(connection: sqlite3.Connection, task_id: str) -> StoredTask | None:
    row = connection.execute("SELECT * FROM agent_task WHERE task_id = ?", (task_id,)).fetchone()
    return None if row is None else _stored(row)


def by_idempotency_key(connection: sqlite3.Connection, key: str) -> StoredTask | None:
    row = connection.execute(
        "SELECT * FROM agent_task WHERE idempotency_key = ?", (key,)
    ).fetchone()
    return None if row is None else _stored(row)


def insert(connection: sqlite3.Connection, row: StoredTask) -> StoredTask:
    connection.execute(
        """
        INSERT INTO agent_task (
            task_id, revision, intent, state, goal_satisfied, idempotency_key,
            payload_json, outcome_json, questions_json, child_operation_ids_json,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row.task_id,
            row.revision,
            row.intent,
            row.state,
            int(row.goal_satisfied),
            row.idempotency_key,
            row.payload_json,
            row.outcome_json,
            row.questions_json,
            row.child_operation_ids_json,
            row.created_at,
            row.updated_at,
        ),
    )
    return row


def replace(connection: sqlite3.Connection, row: StoredTask) -> StoredTask:
    connection.execute(
        """
        UPDATE agent_task SET
            revision = ?,
            state = ?,
            goal_satisfied = ?,
            outcome_json = ?,
            questions_json = ?,
            child_operation_ids_json = ?,
            updated_at = ?
        WHERE task_id = ?
        """,
        (
            row.revision,
            row.state,
            int(row.goal_satisfied),
            row.outcome_json,
            row.questions_json,
            row.child_operation_ids_json,
            row.updated_at,
            row.task_id,
        ),
    )
    return row


def view_of(row: StoredTask) -> TaskView:
    questions_raw = json.loads(row.questions_json)
    children_raw = json.loads(row.child_operation_ids_json)
    outcome = (
        None
        if row.outcome_json is None
        else TaskInspectOutcome.model_validate_json(row.outcome_json)
    )
    return TaskView(
        task_id=row.task_id,
        revision=row.revision,
        intent=row.intent,  # pyright: ignore[reportArgumentType]
        state=row.state,  # pyright: ignore[reportArgumentType]
        goal_satisfied=row.goal_satisfied,
        questions=[TaskQuestion.model_validate(item) for item in questions_raw],
        outcome=outcome,
        child_operation_ids=[str(item) for item in children_raw],
    )


def with_outcome(row: StoredTask, outcome: TaskInspectOutcome, *, at: str) -> StoredTask:
    return StoredTask(
        task_id=row.task_id,
        revision=row.revision + 1,
        intent=row.intent,
        state="completed",
        goal_satisfied=True,
        idempotency_key=row.idempotency_key,
        payload_json=row.payload_json,
        outcome_json=outcome.model_dump_json(),
        questions_json=row.questions_json,
        child_operation_ids_json=row.child_operation_ids_json,
        created_at=row.created_at,
        updated_at=at,
    )


def cancelled(row: StoredTask, *, at: str) -> StoredTask:
    return StoredTask(
        task_id=row.task_id,
        revision=row.revision + 1,
        intent=row.intent,
        state="cancelled",
        goal_satisfied=False,
        idempotency_key=row.idempotency_key,
        payload_json=row.payload_json,
        outcome_json=row.outcome_json,
        questions_json=row.questions_json,
        child_operation_ids_json=row.child_operation_ids_json,
        created_at=row.created_at,
        updated_at=at,
    )


def empty_list_json() -> str:
    return canonize([]).decode("utf-8")


def _stored(row: sqlite3.Row) -> StoredTask:
    return StoredTask(
        task_id=str(row["task_id"]),
        revision=int(row["revision"]),
        intent=str(row["intent"]),
        state=str(row["state"]),
        goal_satisfied=bool(row["goal_satisfied"]),
        idempotency_key=str(row["idempotency_key"]),
        payload_json=str(row["payload_json"]),
        outcome_json=None if row["outcome_json"] is None else str(row["outcome_json"]),
        questions_json=str(row["questions_json"]),
        child_operation_ids_json=str(row["child_operation_ids_json"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
