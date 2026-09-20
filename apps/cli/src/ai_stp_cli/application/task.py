"""Durable agent tasks. Closed intents call named in-process services."""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import Final, NoReturn, cast

import yaml
from pydantic import ValidationError

from ai_stp_cli.answer import Answer
from ai_stp_cli.application.account import drain as drain_account
from ai_stp_cli.application.author import drain as drain_author
from ai_stp_cli.application.change import drain as drain_change
from ai_stp_cli.application.initialize import drain as drain_initialize
from ai_stp_cli.application.inspect import (
    INTENT_INPUT_MODELS,
    SHIPPED_INTENT_NAMES,
    doctor,
    intent_catalog,
    orientation,
)
from ai_stp_cli.application.install_task import drain as drain_install
from ai_stp_cli.application.publish import drain as drain_publish
from ai_stp_cli.application.switch import drain as drain_switch
from ai_stp_cli.errors import CliFailure, field_issues, internal_failure
from ai_stp_cli.local import agent_tasks
from ai_stp_cli.local.agent_tasks import StoredTask
from ai_stp_cli.local.database import configured_path, open_registry, transaction
from ai_stp_cli.local.passports import moment
from ai_stp_cli.yaml_documents import DuplicateKeyError, UniqueSafeLoader
from ai_stp_contracts.machine_help import (
    TaskInspectOutcome,
    TaskIntentsCatalog,
    TaskOutcome,
    TaskView,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.envelope import Continuation, continuation_command
from ai_stp_foundation.ids import is_valid_id, new_id
from ai_stp_foundation.schemas import schema_id

INSPECT_INTENT = "inspect"
INITIALIZE_INTENT = "initialize"
INSTALL_INTENT = "install"
CHANGE_INTENT = "change"
AUTHOR_INTENT = "author"
SWITCH_INTENT = "switch"
ACCOUNT_INTENT = "account"
PUBLISH_INTENT = "publish"
SUPPORTED_INTENTS = SHIPPED_INTENT_NAMES
SETTLED = frozenset({"completed", "failed", "cancelled"})
RUNNING_JOIN_SECONDS: Final[float] = 180.0
RUNNING_JOIN_POLL_SECONDS: Final[float] = 0.25
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._~-]{16,128}$")
_INPUT_LIMIT: Final[int] = 65_536
_TASK_NEXT_ACTIONS: Final[tuple[str, ...]] = (
    "install recover",
    "install resume",
    "task continue",
    "task start",
    "task answer",
    "task intents",
)


def intents(_parameters: Mapping[str, object]) -> Answer[TaskIntentsCatalog]:
    return Answer(intent_catalog())


def missing_answer_hint(task_id: str | None = None) -> CliFailure | None:
    """A blocked human question fills a missing `--task` or `--revision`."""
    try:
        with closing(open_registry(configured_path(), create=False)) as connection:
            if task_id:
                row = agent_tasks.by_id(connection, task_id)
                rows = () if row is None else (row,)
            else:
                rows = agent_tasks.unsettled(connection)
    except CliFailure:
        return None
    if len(rows) != 1:
        return None
    view = agent_tasks.view_of(rows[0])
    if view.state != "blocked" or not view.questions:
        return None
    if view.questions[0].actor != "human":
        return None
    held = _answer(view)
    if not held.continuations:
        return None
    continuation = held.continuations[0]
    return CliFailure(
        "AI_STP_VALIDATION_ERROR",
        "task answer needs the open question",
        details={"task": view.task_id},
        continuations=[continuation],
        next_actions=[continuation_command(continuation)],
    )


def start(parameters: Mapping[str, object]) -> Answer[TaskView]:
    intent = str(parameters.get("intent") or "")
    if intent not in SUPPORTED_INTENTS:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the task intent is not supported",
            details={"intent": intent, "supported": ",".join(SUPPORTED_INTENTS)},
            continuations=[
                Continuation(
                    kind="inspect",
                    path=["task", "intents"],
                    argv=["task", "intents", "--json"],
                    actor="cli",
                )
            ],
            next_actions=["task intents --json"],
        )
    key = str(parameters.get("idempotency-key") or "")
    if _IDEMPOTENCY_KEY.fullmatch(key) is None:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "the idempotency key is not a valid key")
    facts = _input_document(parameters)
    model = INTENT_INPUT_MODELS[intent]
    try:
        model.model_validate(facts)
    except ValidationError as error:
        schema_urn = schema_id(f"cli-task-input-{intent}")
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the task input is not valid",
            details={
                "intent": intent,
                "fields": _field_names(error),
                "errors": field_issues(error),
                "schema": schema_urn,
            },
            continuations=[
                Continuation(
                    kind="inspect",
                    path=["schema", "show"],
                    arguments={"id": schema_urn},
                    actor="cli",
                )
            ],
        ) from error
    payload = agent_tasks.payload_document(intent, facts)
    at = moment()
    minted: StoredTask | None = None
    join: StoredTask | None = None
    raced: StoredTask | None = None
    try:
        with (
            closing(open_registry(configured_path(), create=True)) as connection,
            transaction(connection),
        ):
            held = agent_tasks.by_idempotency_key(connection, key)
            if held is not None:
                if not agent_tasks.same_start_payload(held.payload_json, payload):
                    raise CliFailure(
                        "AI_STP_CONFLICT",
                        "the idempotency key already names a different input",
                        details={"task": held.task_id},
                    )
                if held.state == "running":
                    join = held
                elif held.state != "planned":
                    return _answer(agent_tasks.view_of(held))
                else:
                    minted = held
            else:
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
                _refuse_overlap(connection, row)
                try:
                    agent_tasks.insert(connection, row)
                except sqlite3.IntegrityError:
                    raced = row
                    raise
                minted = row
    except sqlite3.IntegrityError:
        if raced is None:
            raise
        return _replay_after_insert_race(key, payload, raced)
    if join is not None:
        return _join_running(join)
    assert minted is not None
    return _advance_or_join(minted)


def _replay_after_insert_race(key: str, payload: str, candidate: StoredTask) -> Answer[TaskView]:
    """Same-key insert lost the unique index. Join that row; different keys stay overlap."""
    with closing(open_registry(configured_path(), create=False)) as connection:
        occupied = agent_tasks.by_idempotency_key(connection, key)
        if occupied is None:
            bound = agent_tasks.persist_binding(candidate)
            rival = agent_tasks.open_mutator(
                connection,
                bound.harness_id,
                bound.project_root,
                bound.scope,
                excluding=bound.task_id,
            )
            raise CliFailure(
                "AI_STP_CONFLICT",
                "another mutating task already holds this target",
                details={"task": (rival.task_id if rival is not None else bound.task_id)},
            )
    if not agent_tasks.same_start_payload(occupied.payload_json, payload):
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the idempotency key already names a different input",
            details={"task": occupied.task_id},
        )
    if occupied.state == "running":
        return _join_running(occupied)
    if occupied.state == "planned":
        return _advance_or_join(occupied)
    return _answer(agent_tasks.view_of(occupied))


def _advance_or_join(row: StoredTask) -> Answer[TaskView]:
    """Drain this row, or join it when another start already claimed the revision."""
    try:
        return _advance_minted(row)
    except CliFailure as error:
        if (
            error.code != "AI_STP_CONFLICT"
            or error.details.get("task") != row.task_id
            or "expected" not in error.details
        ):
            raise
        with closing(open_registry(configured_path(), create=False)) as connection:
            current = _held(connection, row.task_id)
        if current.state == "running":
            return _join_running(current)
        return _answer(agent_tasks.view_of(current))


def _join_running(row: StoredTask) -> Answer[TaskView]:
    """Wait for an in-flight drain. Do not return running with empty continuations."""
    deadline = time.monotonic() + RUNNING_JOIN_SECONDS
    current = row
    while True:
        with closing(open_registry(configured_path(), create=False)) as connection:
            current = _held(connection, row.task_id)
        if current.state != "running":
            return _answer(agent_tasks.view_of(current))
        if time.monotonic() >= deadline:
            break
        time.sleep(RUNNING_JOIN_POLL_SECONDS)
    try:
        return continue_task({"task": current.task_id, "revision": current.revision})
    except CliFailure as error:
        if error.code == "AI_STP_CONFLICT":
            with closing(open_registry(configured_path(), create=False)) as connection:
                current = _held(connection, row.task_id)
            if current.state != "running":
                return _answer(agent_tasks.view_of(current))
        raise


def _advance_minted(row: StoredTask) -> Answer[TaskView]:
    """Drain a minted row so start returns questions, not a no-op continue."""
    try:
        return continue_task({"task": row.task_id, "revision": row.revision})
    except CliFailure as error:
        if "task" not in error.details:
            error.details["task"] = row.task_id
        raise
    except Exception as error:
        failure = internal_failure(error)
        failure.details["task"] = row.task_id
        raise failure from error


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
    claimed = _commit_if_current(row, agent_tasks.claim(row, at=moment()))
    try:
        return _drain(claimed)
    except CliFailure:
        raise
    except Exception as error:
        failure = internal_failure(error)
        failure.details["task"] = claimed.task_id
        raise _attach_running_continue(failure, claimed.task_id) from error


def answer_task(parameters: Mapping[str, object]) -> Answer[TaskView]:
    row = _load_for_write(parameters)
    if row.state in SETTLED:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the task is already settled",
            details={"task": row.task_id, "state": row.state},
        )
    view = agent_tasks.view_of(row)
    if not view.questions:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "this task has no open questions",
            details={"task": row.task_id},
        )
    question = view.questions[0]
    incoming = _input_document(parameters)
    question_id = str(parameters.get("question-id") or incoming.get("question-id") or "")
    value = str(parameters.get("value") or incoming.get("value") or "")
    if question_id != question.question_id or not value:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the answer does not match the open question",
            details={"task": row.task_id, "question": question.question_id},
        )
    merged = dict(_facts_of(row))
    if question.question_id == "harness-id":
        merged["harness_id"] = value
    elif question.question_id == "setup-ref":
        setup_id, separator, version = value.rpartition("@")
        if not separator or not setup_id or not version:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "the answer does not match the open question",
                details={"task": row.task_id, "question": question.question_id},
            )
        merged["setup_id"] = setup_id
        merged["setup_version"] = version
    elif question.question_id == "component-ref":
        component_id, separator, version = value.rpartition("@")
        if not separator or not component_id or not version:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "the answer does not match the open question",
                details={"task": row.task_id, "question": question.question_id},
            )
        merged["component_id"] = component_id
        merged["component_version"] = version
    elif question.question_id == "project-root":
        merged["project_root"] = value
    else:
        merged[question.question_id.replace("-", "_")] = value
    holding = StoredTask(
        task_id=row.task_id,
        revision=row.revision,
        intent=row.intent,
        state=row.state,
        goal_satisfied=row.goal_satisfied,
        idempotency_key=row.idempotency_key,
        payload_json=agent_tasks.payload_document(row.intent, merged),
        outcome_json=row.outcome_json,
        questions_json=agent_tasks.empty_list_json(),
        child_operation_ids_json=row.child_operation_ids_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
    claimed = _commit_if_current(row, agent_tasks.claim(holding, at=moment()))
    return _drain(claimed)


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


def _facts_of(row: StoredTask) -> dict[str, JsonValue]:
    body = _as_object(json.loads(row.payload_json))
    return _as_object(body.get("input"))


def _failed_drain(
    row: StoredTask,
    error: CliFailure,
    *,
    at: str,
    child_operation_ids: tuple[str, ...] | None = None,
) -> None:
    if "task" not in error.details:
        error.details["task"] = row.task_id
    error.details["state"] = "failed"
    error.next_actions = [
        action
        for action in error.next_actions
        if any(token in action for token in _TASK_NEXT_ACTIONS)
    ]
    _commit_if_current(row, agent_tasks.failed(row, at=at, child_operation_ids=child_operation_ids))


def _children_of(row: StoredTask) -> tuple[str, ...]:
    parsed: object = json.loads(row.child_operation_ids_json)
    if not isinstance(parsed, list):
        return ()
    items = cast(list[object], parsed)
    return tuple(str(item) for item in items)


def _as_object(value: object) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        return {}
    items = cast(dict[object, object], value)
    return {str(key): cast(JsonValue, item) for key, item in items.items()}


def _field_names(error: ValidationError) -> str:
    """Comma-joined field names — the house `details.fields` convention.

    `details.errors` next to it carries the structured form (pointer, issue,
    detail); this member stays a plain string because every other refusal in
    the CLI spells `fields` that way and a sync reader consumes it as one.
    """
    return ", ".join(
        sorted({".".join(str(part) for part in item["loc"]) for item in error.errors()} - {""})
    )


def _unique_pairs(pairs: list[tuple[object, object]]) -> dict[object, object]:
    """`object_pairs_hook` that refuses duplicate keys the way the YAML loader does.

    `json.loads` alone is last-wins, so without this hook `{"a": 1, "a": 2}` and
    the YAML spelling would disagree about which value the validator saw.
    """
    result: dict[object, object] = {}
    for key, value in pairs:
        if key in result:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "the task input repeats a key",
            )
        result[key] = value
    return result


def _input_document(parameters: Mapping[str, object]) -> dict[str, JsonValue]:
    raw = parameters.get("input")
    if raw is None or raw == "":
        return {}
    locator = str(raw)
    if locator == "-":
        body = sys.stdin.read(_INPUT_LIMIT + 1)
    else:
        path = Path(locator)
        try:
            body = path.read_text(encoding="utf-8")
        except OSError as error:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "the task input file could not be read",
                details={"input": locator, "reason": type(error).__name__},
            ) from error
    if len(body) > _INPUT_LIMIT:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the task input is larger than the allowed bound",
            details={"limit": str(_INPUT_LIMIT)},
        )
    parsed: object = None
    try:
        parsed = json.loads(body, object_pairs_hook=_unique_pairs)
    except CliFailure:
        raise
    except json.JSONDecodeError:
        # JSON is a YAML subset, so a document that is not JSON is tried once
        # more as YAML — the same model validates either spelling.
        try:
            parsed = yaml.load(body, Loader=UniqueSafeLoader)
        except DuplicateKeyError as error:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "the task input repeats a key",
            ) from error
        except (yaml.YAMLError, RecursionError) as error:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "the task input is not a JSON or YAML object",
            ) from error
    except RecursionError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the task input is not a JSON or YAML object",
        ) from error
    if not isinstance(parsed, dict):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the task input is not a JSON or YAML object",
        )
    return cast(dict[str, JsonValue], parsed)


def _drain(row: StoredTask) -> Answer[TaskView]:
    at = moment()
    if row.intent == INSPECT_INTENT:
        outcome: TaskOutcome = TaskInspectOutcome(doctor=doctor(), orientation=orientation())
        updated = _commit_if_current(row, agent_tasks.with_outcome(row, outcome, at=at))
        return _answer(agent_tasks.view_of(updated))
    if row.intent == INITIALIZE_INTENT:
        facts = _facts_of(row)
        try:
            result = drain_initialize(facts)
        except CliFailure as error:
            _failed_drain(row, error, at=at)
            raise
        if result.outcome is not None:
            updated = _commit_if_current(row, agent_tasks.with_outcome(row, result.outcome, at=at))
            return _answer(agent_tasks.view_of(updated))
        updated = _commit_if_current(row, agent_tasks.with_questions(row, result.questions, at=at))
        return _answer(agent_tasks.view_of(updated))
    if row.intent == INSTALL_INTENT:
        facts = _facts_of(row)

        def persist_operation(operation_id: str) -> None:
            nonlocal row
            if operation_id in _children_of(row):
                return
            row = _commit_if_current(
                row, agent_tasks.with_children(row, (operation_id,), at=moment())
            )

        try:
            result = drain_install(
                facts,
                held_operation_ids=_children_of(row),
                persist_operation=persist_operation,
            )
        except CliFailure as error:
            held = (error.operation_id,) if error.operation_id else _children_of(row)
            children = held if held != _children_of(row) else None
            _failed_drain(row, error, at=at, child_operation_ids=children)
            raise
        if result.outcome is not None:
            updated = _commit_if_current(
                row,
                agent_tasks.with_outcome(
                    row,
                    result.outcome,
                    at=at,
                    goal_satisfied=result.outcome.verified,
                    child_operation_ids=result.child_operation_ids,
                ),
            )
            return _answer(agent_tasks.view_of(updated))
        updated = _commit_if_current(row, agent_tasks.with_questions(row, result.questions, at=at))
        return _answer(agent_tasks.view_of(updated))
    if row.intent == CHANGE_INTENT:
        facts = _facts_of(row)
        try:
            result = drain_change(facts)
        except CliFailure as error:
            _failed_drain(row, error, at=at)
            raise
        if result.outcome is not None:
            updated = _commit_if_current(
                row,
                agent_tasks.with_outcome(
                    row,
                    result.outcome,
                    at=at,
                    goal_satisfied=result.outcome.verified,
                    child_operation_ids=result.child_operation_ids,
                ),
            )
            return _answer(agent_tasks.view_of(updated))
        updated = _commit_if_current(row, agent_tasks.with_questions(row, result.questions, at=at))
        return _answer(agent_tasks.view_of(updated))
    if row.intent == AUTHOR_INTENT:
        facts = _facts_of(row)
        try:
            result = drain_author(facts)
        except CliFailure as error:
            _failed_drain(row, error, at=at)
            raise
        if result.outcome is not None:
            updated = _commit_if_current(
                row,
                agent_tasks.with_outcome(
                    row,
                    result.outcome,
                    at=at,
                    goal_satisfied=True,
                    child_operation_ids=result.child_operation_ids,
                ),
            )
            return _answer(agent_tasks.view_of(updated))
        updated = _commit_if_current(row, agent_tasks.with_questions(row, result.questions, at=at))
        return _answer(agent_tasks.view_of(updated))
    if row.intent == SWITCH_INTENT:
        facts = _facts_of(row)
        try:
            result = drain_switch(facts)
        except CliFailure as error:
            _failed_drain(row, error, at=at)
            raise
        if result.outcome is not None:
            updated = _commit_if_current(
                row,
                agent_tasks.with_outcome(
                    row,
                    result.outcome,
                    at=at,
                    goal_satisfied=True,
                    child_operation_ids=result.child_operation_ids,
                ),
            )
            return _answer(agent_tasks.view_of(updated))
        updated = _commit_if_current(
            row,
            agent_tasks.with_questions(
                row,
                result.questions,
                at=at,
                facts=result.facts,
                child_operation_ids=result.child_operation_ids or None,
            ),
        )
        return _answer(agent_tasks.view_of(updated))
    if row.intent == ACCOUNT_INTENT:
        facts = _facts_of(row)
        try:
            result = drain_account(facts)
        except CliFailure as error:
            _failed_drain(row, error, at=at)
            raise
        if result.outcome is not None:
            updated = _commit_if_current(
                row,
                agent_tasks.with_outcome(
                    row,
                    result.outcome,
                    at=at,
                    goal_satisfied=True,
                    child_operation_ids=result.child_operation_ids,
                ),
            )
            return _answer(agent_tasks.view_of(updated))
        updated = _commit_if_current(
            row,
            agent_tasks.with_questions(
                row,
                result.questions,
                at=at,
                facts=result.facts,
                child_operation_ids=result.child_operation_ids or None,
            ),
        )
        return _answer(agent_tasks.view_of(updated))
    if row.intent == PUBLISH_INTENT:
        facts = _facts_of(row)
        try:
            result = drain_publish(facts)
        except CliFailure as error:
            _failed_drain(row, error, at=at)
            raise
        if result.outcome is not None:
            updated = _commit_if_current(
                row,
                agent_tasks.with_outcome(
                    row,
                    result.outcome,
                    at=at,
                    goal_satisfied=result.outcome.readable,
                    child_operation_ids=result.child_operation_ids,
                ),
            )
            return _answer(agent_tasks.view_of(updated))
        updated = _commit_if_current(
            row,
            agent_tasks.with_questions(
                row,
                result.questions,
                at=at,
                facts=result.facts,
                child_operation_ids=result.child_operation_ids or None,
            ),
        )
        return _answer(agent_tasks.view_of(updated))
    error = CliFailure(
        "AI_STP_VALIDATION_ERROR",
        "the task intent is not supported",
        details={"intent": row.intent},
    )
    _failed_drain(row, error, at=at)
    raise error


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
        _refuse_overlap(connection, updated)
        try:
            agent_tasks.replace(connection, updated)
        except sqlite3.IntegrityError as error:
            _overlap_conflict(connection, updated, error)
    return updated


def _refuse_overlap(connection: sqlite3.Connection, row: StoredTask) -> None:
    bound = agent_tasks.persist_binding(row)
    if bound.intent == INSPECT_INTENT or not bound.harness_id:
        return
    held = agent_tasks.open_mutator(
        connection,
        bound.harness_id,
        bound.project_root,
        bound.scope,
        excluding=bound.task_id,
    )
    if held is None:
        return
    raise CliFailure(
        "AI_STP_CONFLICT",
        "another mutating task already holds this target",
        details={"task": held.task_id, "harness_id": bound.harness_id},
    )


def _overlap_conflict(
    connection: sqlite3.Connection, row: StoredTask, error: sqlite3.IntegrityError
) -> NoReturn:
    bound = agent_tasks.persist_binding(row)
    held = agent_tasks.open_mutator(
        connection,
        bound.harness_id,
        bound.project_root,
        bound.scope,
        excluding=bound.task_id,
    )
    raise CliFailure(
        "AI_STP_CONFLICT",
        "another mutating task already holds this target",
        details={"task": (held.task_id if held is not None else bound.task_id)},
    ) from error


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


def _attach_running_continue(failure: CliFailure, task_id: str) -> CliFailure:
    """A killed drain stays running. Emit continue argv so a weak model can resume."""
    with closing(open_registry(configured_path(), create=False)) as connection:
        current = agent_tasks.by_id(connection, task_id)
    if current is None or current.state != "running":
        return failure
    view = agent_tasks.view_of(current)
    held = Continuation(
        kind="advance",
        path=["task", "continue"],
        arguments={"task": view.task_id, "revision": view.revision},
        argv=[
            "task",
            "continue",
            "--task",
            view.task_id,
            "--revision",
            str(view.revision),
            "--json",
        ],
        actor="cli",
    )
    failure.continuations = [held]
    failure.next_actions = [continuation_command(held)]
    return failure


def _answer(view: TaskView) -> Answer[TaskView]:
    if view.state == "planned":
        return Answer(
            view,
            continuations=(
                Continuation(
                    kind="advance",
                    path=["task", "continue"],
                    arguments={"task": view.task_id, "revision": view.revision},
                    argv=[
                        "task",
                        "continue",
                        "--task",
                        view.task_id,
                        "--revision",
                        str(view.revision),
                        "--json",
                    ],
                    actor="cli",
                ),
            ),
        )
    if view.state == "blocked":
        actor = view.questions[0].actor if view.questions else "human"
        if actor == "external":
            return Answer(
                view,
                continuations=(
                    Continuation(
                        kind="blocked",
                        path=["task", "continue"],
                        arguments={"task": view.task_id, "revision": view.revision},
                        argv=[
                            "task",
                            "continue",
                            "--task",
                            view.task_id,
                            "--revision",
                            str(view.revision),
                            "--json",
                        ],
                        actor="external",
                    ),
                ),
            )
        question = view.questions[0] if view.questions else None
        arguments: dict[str, JsonValue] = {"task": view.task_id, "revision": view.revision}
        argv = [
            "task",
            "answer",
            "--task",
            view.task_id,
            "--revision",
            str(view.revision),
        ]
        missing = ["question-id", "value"]
        if question is not None:
            arguments["question-id"] = question.question_id
            argv.extend(["--question-id", question.question_id])
            missing = ["value"]
        argv.append("--json")
        return Answer(
            view,
            continuations=(
                Continuation(
                    kind="blocked",
                    path=["task", "answer"],
                    arguments=arguments,
                    missing=missing,
                    argv=argv,
                    actor="human",
                ),
            ),
        )
    return Answer(view)
