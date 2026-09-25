"""Durable agent-task rows in the local registry (SPEC-080)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import replace as evolve
from typing import Literal, cast

from ai_stp_contracts.machine_help import (
    TaskInspectOutcome,
    TaskOutcome,
    TaskQuestion,
    TaskView,
)
from ai_stp_foundation.canonical import JsonValue, canonize


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
    harness_id: str = ""
    project_root: str = ""
    scope: str = ""
    account_id: str = ""
    precondition_digest: str = ""
    original_request_json: str = ""


_INSPECT = "inspect"


def input_facts(payload_json: str) -> dict[str, JsonValue]:
    body = json.loads(payload_json)
    if not isinstance(body, dict):
        return {}
    raw = cast(dict[object, object], body).get("input")
    if not isinstance(raw, dict):
        return {}
    items = cast(dict[object, object], raw)
    return {str(key): cast(JsonValue, item) for key, item in items.items()}


def binding_from_payload(intent: str, payload_json: str) -> tuple[str, str, str]:
    """Indexed overlap key: harness + project root + scope. Inspect is unbound."""
    if intent == _INSPECT:
        return "", "", ""
    facts = input_facts(payload_json)
    harness = str(facts.get("harness_id") or "")
    root = str(facts.get("project_root") or "")
    scope = "project" if root else "global"
    return harness, root, scope


def persist_binding(row: StoredTask) -> StoredTask:
    """Fill overlap columns from the canonical payload."""
    harness, root, scope = binding_from_payload(row.intent, row.payload_json)
    facts = input_facts(row.payload_json)
    account = str(facts.get("account_id") or "")
    digest = ""
    if harness:
        material = f"{harness}\0{root}\0{scope}".encode()
        digest = "sha256:" + hashlib.sha256(material).hexdigest()
    return evolve(
        row,
        harness_id=harness,
        project_root=root,
        scope=scope,
        account_id=account,
        precondition_digest=digest,
    )


def open_mutator(
    connection: sqlite3.Connection,
    harness_id: str,
    project_root: str,
    scope: str,
    *,
    excluding: str = "",
) -> StoredTask | None:
    """Another open mutating task on the same bound target, if any."""
    if not harness_id:
        return None
    row = connection.execute(
        """
        SELECT * FROM agent_task
        WHERE harness_id = ?
          AND project_root = ?
          AND scope = ?
          AND state IN ('planned', 'blocked', 'running')
          AND intent != 'inspect'
          AND task_id != ?
        LIMIT 1
        """,
        (harness_id, project_root, scope, excluding),
    ).fetchone()
    return None if row is None else _stored(row)


def payload_document(intent: str, facts: Mapping[str, JsonValue] | None = None) -> str:
    """Canonical start payload used for idempotency comparison."""
    body: dict[str, JsonValue] = {"intent": intent}
    if facts:
        body["input"] = dict(facts)
    return canonize(body).decode("utf-8")


def original_request_of(row: StoredTask) -> str:
    """The immutable first-start document recorded at insert.

    Rows written before the column existed carry an empty marker; their held
    payload is the best surviving evidence, so strict comparison against it is
    the conservative fallback rather than a guess at a merged request.
    """
    return row.original_request_json or row.payload_json


def same_start_request(original: str, incoming: str) -> bool:
    """True when incoming is exactly the recorded original start document.

    REQ-8007 keys idempotency on the caller's original `--input` document, not
    on facts a later drain merged into `payload_json`. Both documents are
    canonized by `payload_document`, so equality is canonical, not formatting.
    A request that drops material fields or an answer-enriched payload can
    never masquerade as the original.
    """
    return original == incoming


def by_id(connection: sqlite3.Connection, task_id: str) -> StoredTask | None:
    row = connection.execute("SELECT * FROM agent_task WHERE task_id = ?", (task_id,)).fetchone()
    return None if row is None else _stored(row)


def by_idempotency_key(connection: sqlite3.Connection, key: str) -> StoredTask | None:
    row = connection.execute(
        "SELECT * FROM agent_task WHERE idempotency_key = ?", (key,)
    ).fetchone()
    return None if row is None else _stored(row)


def unsettled(connection: sqlite3.Connection) -> tuple[StoredTask, ...]:
    """Open tasks a missing `--task` can uniquely resume."""
    rows = connection.execute(
        """
        SELECT * FROM agent_task
        WHERE state IN ('planned', 'blocked', 'running')
        ORDER BY updated_at, task_id
        """
    ).fetchall()
    return tuple(_stored(row) for row in rows)


def insert(connection: sqlite3.Connection, row: StoredTask) -> StoredTask:
    # The first write atomically freezes the caller's start document as the
    # idempotency identity. Enrichment later rewrites payload_json, never this.
    row = persist_binding(row)
    if not row.original_request_json:
        row = evolve(row, original_request_json=row.payload_json)
    connection.execute(
        """
        INSERT INTO agent_task (
            task_id, revision, intent, state, goal_satisfied, idempotency_key,
            payload_json, outcome_json, questions_json, child_operation_ids_json,
            created_at, updated_at,
            harness_id, project_root, scope, account_id, precondition_digest,
            original_request_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            row.harness_id,
            row.project_root,
            row.scope,
            row.account_id,
            row.precondition_digest,
            row.original_request_json,
        ),
    )
    return row


def replace(connection: sqlite3.Connection, row: StoredTask) -> StoredTask:
    row = persist_binding(row)
    connection.execute(
        """
        UPDATE agent_task SET
            revision = ?,
            state = ?,
            goal_satisfied = ?,
            payload_json = ?,
            outcome_json = ?,
            questions_json = ?,
            child_operation_ids_json = ?,
            updated_at = ?,
            harness_id = ?,
            project_root = ?,
            scope = ?,
            account_id = ?,
            precondition_digest = ?,
            original_request_json = ?
        WHERE task_id = ?
        """,
        (
            row.revision,
            row.state,
            int(row.goal_satisfied),
            row.payload_json,
            row.outcome_json,
            row.questions_json,
            row.child_operation_ids_json,
            row.updated_at,
            row.harness_id,
            row.project_root,
            row.scope,
            row.account_id,
            row.precondition_digest,
            row.original_request_json,
            row.task_id,
        ),
    )
    return row


def view_of(row: StoredTask) -> TaskView:
    questions_raw = json.loads(row.questions_json)
    children_raw = json.loads(row.child_operation_ids_json)
    outcome = None if row.outcome_json is None else parse_outcome(row.outcome_json)
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


def parse_outcome(raw: str) -> TaskOutcome:
    """Dispatch on `kind` so a later intent cannot parse as inspect."""
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("task outcome is not an object")
    body = cast(dict[str, JsonValue], payload)
    kind = body.get("kind", "inspect")
    if kind == "inspect":
        return TaskInspectOutcome.model_validate(body)
    if kind == "initialize":
        from ai_stp_contracts.machine_help import TaskInitializeOutcome

        return TaskInitializeOutcome.model_validate(body)
    if kind == "install":
        from ai_stp_contracts.machine_help import TaskInstallOutcome

        return TaskInstallOutcome.model_validate(body)
    if kind == "change":
        from ai_stp_contracts.machine_help import TaskChangeOutcome

        return TaskChangeOutcome.model_validate(body)
    if kind == "author":
        from ai_stp_contracts.machine_help import TaskAuthorOutcome

        return TaskAuthorOutcome.model_validate(body)
    if kind == "switch":
        from ai_stp_contracts.machine_help import TaskSwitchOutcome

        return TaskSwitchOutcome.model_validate(body)
    if kind == "account":
        from ai_stp_contracts.machine_help import TaskAccountOutcome

        return TaskAccountOutcome.model_validate(body)
    if kind == "publish":
        from ai_stp_contracts.machine_help import TaskPublishOutcome

        return TaskPublishOutcome.model_validate(body)
    raise ValueError(f"unsupported task outcome kind: {kind}")


def with_outcome(
    row: StoredTask,
    outcome: TaskOutcome,
    *,
    at: str,
    goal_satisfied: bool = True,
    state: Literal["planned", "blocked", "completed"] = "completed",
    questions: tuple[TaskQuestion, ...] = (),
    child_operation_ids: tuple[str, ...] | None = None,
) -> StoredTask:
    children = (
        canonize(list(child_operation_ids)).decode("utf-8")
        if child_operation_ids is not None
        else row.child_operation_ids_json
    )
    return evolve(
        row,
        revision=row.revision + 1,
        state=state,
        goal_satisfied=goal_satisfied,
        outcome_json=outcome.model_dump_json(),
        questions_json=canonize([item.model_dump(mode="json") for item in questions]).decode(
            "utf-8"
        ),
        child_operation_ids_json=children,
        updated_at=at,
    )


def with_questions(
    row: StoredTask,
    questions: tuple[TaskQuestion, ...],
    *,
    at: str,
    facts: Mapping[str, JsonValue] | None = None,
    child_operation_ids: tuple[str, ...] | None = None,
) -> StoredTask:
    payload = payload_document(row.intent, facts) if facts is not None else row.payload_json
    children = (
        canonize(list(child_operation_ids)).decode("utf-8")
        if child_operation_ids is not None
        else row.child_operation_ids_json
    )
    return evolve(
        row,
        revision=row.revision + 1,
        state="blocked",
        goal_satisfied=False,
        payload_json=payload,
        questions_json=canonize([item.model_dump(mode="json") for item in questions]).decode(
            "utf-8"
        ),
        child_operation_ids_json=children,
        updated_at=at,
    )


def claim(row: StoredTask, *, at: str) -> StoredTask:
    """Occupy this revision before effects. Concurrent continue then conflicts."""
    return evolve(row, revision=row.revision + 1, state="running", updated_at=at)


def with_children(row: StoredTask, child_operation_ids: tuple[str, ...], *, at: str) -> StoredTask:
    """Record a child operation before apply so a killed continue can resume."""
    return evolve(
        row,
        revision=row.revision + 1,
        child_operation_ids_json=canonize(list(child_operation_ids)).decode("utf-8"),
        updated_at=at,
    )


def failed(
    row: StoredTask, *, at: str, child_operation_ids: tuple[str, ...] | None = None
) -> StoredTask:
    children = (
        canonize(list(child_operation_ids)).decode("utf-8")
        if child_operation_ids is not None
        else row.child_operation_ids_json
    )
    return evolve(
        row,
        revision=row.revision + 1,
        state="failed",
        goal_satisfied=False,
        child_operation_ids_json=children,
        updated_at=at,
    )


def cancelled(row: StoredTask, *, at: str) -> StoredTask:
    return evolve(
        row,
        revision=row.revision + 1,
        state="cancelled",
        goal_satisfied=False,
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
        harness_id=str(row["harness_id"] or ""),
        project_root=str(row["project_root"] or ""),
        scope=str(row["scope"] or ""),
        account_id=str(row["account_id"] or ""),
        precondition_digest=str(row["precondition_digest"] or ""),
        original_request_json=str(row["original_request_json"] or ""),
    )
