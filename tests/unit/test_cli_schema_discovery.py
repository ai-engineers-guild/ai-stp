"""`schema` resolves every URN the CLI emits, and task inputs report fields."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_stp_cli.application.inspect import INTENT_INPUT_MODELS, SHIPPED_INTENT_NAMES
from ai_stp_cli.application.task import _input_document  # pyright: ignore[reportPrivateUsage]
from ai_stp_cli.commands import machine_help
from ai_stp_cli.commands import task as task_command
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.registry import command_paths
from ai_stp_contracts.machine_help import TaskView
from ai_stp_contracts.schemas import EXPORTED_MODELS
from ai_stp_foundation.harnesses import HARNESS_IDS
from ai_stp_foundation.schemas import schema_id

KEY = "schema-discovery-01"


def test_every_declared_intent_names_an_input_model() -> None:
    assert tuple(INTENT_INPUT_MODELS) == SHIPPED_INTENT_NAMES


def test_schema_index_lists_every_exported_id() -> None:
    index = machine_help.schema_list({}).payload
    assert [entry.name for entry in index.schemas] == sorted(EXPORTED_MODELS)
    assert {entry.urn for entry in index.schemas} == {schema_id(name) for name in EXPORTED_MODELS}


@pytest.mark.parametrize(
    "identifier",
    [
        "cli-task",
        "urn:ai-stp:schema:v1:cli-task",
        "cli-task.schema.json",
    ],
)
def test_schema_show_accepts_name_urn_and_file_name(identifier: str) -> None:
    document = machine_help.schema_show({"id": identifier}).payload
    assert document.name == "cli-task"
    assert document.urn == "urn:ai-stp:schema:v1:cli-task"
    assert document.document == TaskView.model_json_schema()


def test_schema_show_resolves_the_urn_task_intents_emits() -> None:
    catalog = task_command.intents({}).payload
    for intent in catalog.intents:
        document = machine_help.schema_show({"id": intent.input_schema}).payload
        assert document.document == INTENT_INPUT_MODELS[intent.name].model_json_schema()


def test_schema_show_unknown_id_is_a_typed_refusal() -> None:
    with pytest.raises(CliFailure) as raised:
        machine_help.schema_show({"id": "cli-no-such-schema"})
    failure = raised.value
    assert failure.code == "AI_STP_NOT_FOUND"
    assert failure.details["id"] == "cli-no-such-schema"
    assert failure.continuations[0].argv == ["schema", "list", "--json"]


def test_task_intents_describe_input_fields() -> None:
    catalog = task_command.intents({}).payload
    by_name = {intent.name: intent for intent in catalog.intents}

    install = {field.name: field for field in by_name["install"].input_fields}
    assert install["harness_id"].choices == sorted(HARNESS_IDS)
    assert install["harness_id"].required is False
    assert install["project_root"].value_type == "string"
    assert install["project_root"].choices == []

    account = {field.name: field for field in by_name["account"].input_fields}
    assert account["action"].choices == ["login", "logout", "sync"]
    assert account["provider"].choices == ["github", "google"]

    assert by_name["inspect"].input_fields == []
    for intent in catalog.intents:
        assert "schema_version" not in {field.name for field in intent.input_fields}


def test_invalid_task_input_names_the_fields_and_the_schema(tmp_path: Path) -> None:
    place = tmp_path / "input.json"
    place.write_text('{"harness_id": "not-a-harness", "bogus": 1}', encoding="utf-8")
    with pytest.raises(CliFailure) as raised:
        task_command.start({"intent": "install", "idempotency-key": KEY, "input": str(place)})
    failure = raised.value
    assert failure.code == "AI_STP_VALIDATION_ERROR"
    assert failure.details["schema"] == "urn:ai-stp:schema:v1:cli-task-input-install"
    assert "bogus:extra_forbidden" in failure.details["fields"]
    assert "harness_id:" in failure.details["fields"]
    continuation = failure.continuations[0]
    assert continuation.actor == "cli"
    assert continuation.arguments == {"id": "urn:ai-stp:schema:v1:cli-task-input-install"}
    # `argv` is bound from the registry when the envelope is built; assert the
    # emitted form, not the pre-binding placeholder.
    from ai_stp_cli.application.continuations import bind_continuation

    assert bind_continuation(continuation).argv == [
        "schema",
        "show",
        "--id",
        "urn:ai-stp:schema:v1:cli-task-input-install",
        "--json",
    ]


def test_yaml_input_document_parses(tmp_path: Path) -> None:
    place = tmp_path / "input.yaml"
    place.write_text("harness_id: claude-code\nproject_root: /tmp/proj\n", encoding="utf-8")
    assert _input_document({"input": str(place)}) == {
        "harness_id": "claude-code",
        "project_root": "/tmp/proj",
    }


def test_yaml_duplicate_keys_are_refused(tmp_path: Path) -> None:
    place = tmp_path / "input.yaml"
    place.write_text("harness_id: claude-code\nharness_id: cursor\n", encoding="utf-8")
    with pytest.raises(CliFailure) as raised:
        _input_document({"input": str(place)})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    assert raised.value.message == "the task input repeats a key"


def test_json_duplicate_keys_are_refused(tmp_path: Path) -> None:
    # `json.loads` alone is last-wins; the contract refuses the ambiguity.
    place = tmp_path / "input.json"
    place.write_text('{"harness_id": "claude-code", "harness_id": "cursor"}', encoding="utf-8")
    with pytest.raises(CliFailure) as raised:
        _input_document({"input": str(place)})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    assert raised.value.message == "the task input repeats a key"


def test_non_object_input_is_refused_in_either_spelling(tmp_path: Path) -> None:
    place = tmp_path / "input.yaml"
    place.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(CliFailure) as raised:
        _input_document({"input": str(place)})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_help_find_filters_by_text_within_scope() -> None:
    found = machine_help.registry({"find": "sync"}).payload
    assert found.commands
    for command in found.commands:
        haystack = " ".join(command.path).lower() + " " + command.summary.lower()
        assert "sync" in haystack

    scoped = machine_help.registry({"path": "setup", "find": "import"}).payload
    assert scoped.commands
    for command in scoped.commands:
        assert command.path[0] == "setup"

    with pytest.raises(CliFailure) as raised:
        machine_help.registry({"find": "zzz-no-such-command"})
    assert raised.value.code == "AI_STP_NOT_FOUND"
    assert raised.value.continuations[0].argv == ["task", "intents", "--json"]


def test_schema_commands_are_reachable_and_inspect_class() -> None:
    from ai_stp_cli.application.inventory import classify

    paths = set(command_paths())
    assert "schema list" in paths
    assert "schema show" in paths
    assert classify(("schema", "list")) == "inspect"
    assert classify(("schema", "show")) == "inspect"
