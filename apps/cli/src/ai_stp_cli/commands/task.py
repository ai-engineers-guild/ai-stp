"""Durable agent-task lifecycle (SPEC-080)."""

from collections.abc import Mapping

from ai_stp_cli.answer import Answer
from ai_stp_cli.application import task as task_service
from ai_stp_contracts.machine_help import TaskIntentsCatalog, TaskListView, TaskView


def intents(parameters: Mapping[str, object]) -> Answer[TaskIntentsCatalog]:
    return task_service.intents(parameters)


def start(parameters: Mapping[str, object]) -> Answer[TaskView]:
    return task_service.start(parameters)


def answer(parameters: Mapping[str, object]) -> Answer[TaskView]:
    return task_service.answer_task(parameters)


def continue_(parameters: Mapping[str, object]) -> Answer[TaskView]:
    return task_service.continue_task(parameters)


def status(parameters: Mapping[str, object]) -> Answer[TaskView]:
    return task_service.status(parameters)


def cancel(parameters: Mapping[str, object]) -> Answer[TaskView]:
    return task_service.cancel(parameters)


def list_(parameters: Mapping[str, object]) -> Answer[TaskListView]:
    return task_service.list_pending(parameters)
