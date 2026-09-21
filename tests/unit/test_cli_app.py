# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportIndexIssue=false, reportOperatorIssue=false, reportPrivateUsage=false
"""Dispatch: every way an invocation ends maps to a registered code and exit class."""

import io
import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Annotated, cast

import click
import pytest
from pydantic import BaseModel, Field, ValidationError

from ai_stp_cli import app
from ai_stp_cli.errors import invalid_parameters


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = app.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _envelope(out: str) -> dict[str, object]:
    assert out.count("\n") == 1, out
    return json.loads(out)


@pytest.mark.parametrize(
    "argv",
    [
        ["version"],
        ["doctor"],
        ["capabilities"],
        ["config", "show"],
        ["help", "--agent"],
    ],
)
def test_every_command_succeeds_in_both_modes(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(argv, capsys)
    assert code == 0
    assert out and not err

    code, out, err = _run([*argv, "--json"], capsys)
    assert code == 0
    assert not err
    assert _envelope(out)["ok"] is True


def test_the_flag_may_be_written_before_the_command(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _err = _run(["--json", "config", "show"], capsys)
    assert code == 0
    assert _envelope(out)["ok"] is True


@pytest.mark.parametrize("argv", [["schema", "--json"], ["schema", "bogus", "--json"]])
def test_a_schema_group_miss_lists_the_schema_verbs(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(argv, capsys)
    assert code == 2
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is False
    assert envelope["error"]["message"] == "the schema verbs are list and show"  # pyright: ignore[reportIndexIssue]
    assert envelope["continuations"][0]["argv"] == ["schema", "list", "--json"]  # pyright: ignore[reportIndexIssue]


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--json"], "no command given"),
        (["registry", "show", "--json"], "Missing option"),
        (["nope", "--json"], "No such command"),
        (["version", "--nosuch", "--json"], "No such option"),
        (["config", "--json"], "incomplete command group"),
        (["--help", "--json"], "usage text is not machine readable"),
    ],
)
def test_a_refused_invocation_is_a_validation_error_with_exit_class_two(
    argv: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(argv, capsys)
    assert code == 2
    if "--json" in argv:
        envelope = _envelope(out)
        assert envelope["ok"] is False
        assert envelope["error"]["code"] == "AI_STP_VALIDATION_ERROR"  # pyright: ignore[reportIndexIssue]
        assert message in envelope["error"]["message"]  # pyright: ignore[reportIndexIssue, reportOperatorIssue]
        assert not err
    else:
        assert message in err
        assert not out


@pytest.mark.parametrize(
    ("argv", "intent"),
    [
        (["install", "--json"], "install"),
        (["install", "--harness", "cursor", "--json"], "install"),
        (["install", "/tmp/project", "--json"], "install"),
        (["auth", "--json"], "account"),
        (["sync", "--json"], "account"),
        (["publication", "--json"], "publish"),
        (["setup", "preserve", "--json"], "switch"),
        (["setup", "restore", "--json"], "switch"),
        (["setup", "preserved", "--json"], "switch"),
        (["setup", "compose", "--json"], "change"),
        (["setup", "publish", "--json"], "publish"),
        (["initialize", "--json"], "initialize"),
        (["inspect", "--json"], "inspect"),
        (["change", "--json"], "change"),
        (["author", "--json"], "author"),
        (["switch", "--json"], "switch"),
        (["account", "--json"], "account"),
        (["publish", "--json"], "publish"),
    ],
)
def test_an_intent_group_without_a_leaf_starts_the_task_engine(
    argv: list[str], intent: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(argv, capsys)
    assert code == 2
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "AI_STP_VALIDATION_ERROR"  # pyright: ignore[reportIndexIssue]
    assert "task intent" in envelope["error"]["message"]  # pyright: ignore[reportIndexIssue, reportOperatorIssue]
    assert envelope["error"]["details"]["intent"] == intent  # pyright: ignore[reportIndexIssue]
    expected = f"task start --intent {intent} --idempotency-key {intent}-session-01 --json"
    assert envelope["next_actions"] == [expected]
    held = envelope["continuations"]
    assert isinstance(held, list) and held
    first = held[0]
    assert isinstance(first, dict)
    assert first["actor"] == "cli"
    assert first["argv"] == [
        "task",
        "start",
        "--intent",
        intent,
        "--idempotency-key",
        f"{intent}-session-01",
        "--json",
    ]
    assert "help --agent" not in out
    assert "install plan" not in out
    assert "compose plan" not in out
    assert "Usage:" not in out


@pytest.mark.parametrize(
    ("argv", "intent"),
    [
        (["task", "start", "--intent", "initialize", "--json"], "initialize"),
        (["task", "start", "--intent=install", "--json"], "install"),
        (["task", "start", "--intent", "inspect", "--json"], "inspect"),
    ],
)
def test_task_start_without_the_key_emits_the_start_argv(
    argv: list[str], intent: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(argv, capsys)
    assert code == 2
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is False
    assert envelope["error"]["message"] == "task start needs an idempotency key"  # pyright: ignore[reportIndexIssue]
    assert envelope["error"]["details"]["intent"] == intent  # pyright: ignore[reportIndexIssue]
    expected = f"task start --intent {intent} --idempotency-key {intent}-session-01 --json"
    assert envelope["next_actions"] == [expected]
    first = envelope["continuations"][0]
    assert isinstance(first, dict)
    assert first["actor"] == "cli"
    assert first["argv"] == [
        "task",
        "start",
        "--intent",
        intent,
        "--idempotency-key",
        f"{intent}-session-01",
        "--json",
    ]
    assert "help --agent" not in out
    assert first["argv"] != ["task", "intents", "--json"]


@pytest.mark.parametrize(
    "argv",
    [
        ["task", "start", "--json"],
        ["task", "start", "--idempotency-key", "initialize-session-01", "--json"],
        ["task", "start", "--intent", "--json"],
    ],
)
def test_task_start_without_an_intent_lists_intents(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(argv, capsys)
    assert code == 2
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is False
    assert envelope["error"]["message"] == "task start needs an intent"  # pyright: ignore[reportIndexIssue]
    assert envelope["next_actions"] == ["task intents --json"]
    first = envelope["continuations"][0]
    assert isinstance(first, dict)
    assert first["actor"] == "cli"
    assert first["argv"] == ["task", "intents", "--json"]
    assert "Missing option" not in out
    assert "help --agent" not in out
    assert "is not one of" not in out


@pytest.mark.parametrize(
    "argv",
    [
        ["task", "start", "--intent", "compose", "--json"],
        [
            "task",
            "start",
            "--intent",
            "compose",
            "--idempotency-key",
            "compose-session-01",
            "--json",
        ],
        ["task", "start", "--intent=recast", "--json"],
    ],
)
def test_task_start_with_an_unshipped_intent_lists_intents(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(argv, capsys)
    assert code == 2
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is False
    assert envelope["error"]["message"] == "the task intent is not supported"  # pyright: ignore[reportIndexIssue]
    assert envelope["next_actions"] == ["task intents --json"]
    first = envelope["continuations"][0]
    assert isinstance(first, dict)
    assert first["argv"] == ["task", "intents", "--json"]
    assert "compose" not in out
    assert "recast" not in out
    assert "is not one of" not in out
    assert "help --agent" not in out
    assert "help --path task" not in out


@pytest.mark.parametrize("verb", ["answer", "continue"])
def test_task_lifecycle_without_task_resumes_the_unique_blocked_question(
    verb: str, capsys: pytest.CaptureFixture[str]
) -> None:
    from ai_stp_cli.commands import task as task_command

    started = task_command.start(
        {"intent": "initialize", "idempotency-key": f"initialize-hint-{verb}-0001"}
    )
    assert started.payload.state == "blocked"
    code, out, err = _run(["task", verb, "--json"], capsys)
    assert code == 2
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is False
    assert envelope["error"]["message"] == "task answer needs the open question"  # pyright: ignore[reportIndexIssue]
    assert envelope["error"]["details"]["task"] == started.payload.task_id  # pyright: ignore[reportIndexIssue]
    first = envelope["continuations"][0]
    assert isinstance(first, dict)
    assert first["actor"] == "human"
    assert first["argv"][:4] == ["task", "answer", "--task", started.payload.task_id]
    assert "--question-id" in first["argv"]
    assert "harness-id" in first["argv"]
    assert "--value" not in first["argv"]
    assert first["argv"] != ["task", "intents", "--json"]
    assert "help --agent" not in out


@pytest.mark.parametrize("verb", ["answer", "continue"])
def test_task_lifecycle_without_task_lists_open_tasks_when_two_are_open(
    verb: str, capsys: pytest.CaptureFixture[str]
) -> None:
    from ai_stp_cli.commands import task as task_command

    task_command.start({"intent": "initialize", "idempotency-key": f"initialize-hint-{verb}-a-01"})
    task_command.start({"intent": "initialize", "idempotency-key": f"initialize-hint-{verb}-b-01"})
    code, out, err = _run(["task", verb, "--json"], capsys)
    assert code == 2
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is False
    assert envelope["next_actions"] == ["task list --json"]
    first = envelope["continuations"][0]
    assert isinstance(first, dict)
    assert first["argv"] == ["task", "list", "--json"]
    assert "needs the open question" not in out


@pytest.mark.parametrize("verb", ["answer", "continue"])
def test_task_lifecycle_without_revision_resumes_the_named_task(
    verb: str, capsys: pytest.CaptureFixture[str]
) -> None:
    from ai_stp_cli.commands import task as task_command

    started = task_command.start(
        {"intent": "initialize", "idempotency-key": f"initialize-rev-{verb}-0001"}
    )
    other = task_command.start(
        {"intent": "initialize", "idempotency-key": f"initialize-rev-{verb}-0002"}
    )
    assert started.payload.task_id != other.payload.task_id
    code, out, err = _run(["task", verb, "--task", started.payload.task_id, "--json"], capsys)
    assert code == 2
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is False
    assert envelope["error"]["message"] == "task answer needs the open question"  # pyright: ignore[reportIndexIssue]
    assert envelope["error"]["details"]["task"] == started.payload.task_id  # pyright: ignore[reportIndexIssue]
    first = envelope["continuations"][0]
    assert isinstance(first, dict)
    assert first["actor"] == "human"
    assert first["argv"][:6] == [
        "task",
        "answer",
        "--task",
        started.payload.task_id,
        "--revision",
        str(started.payload.revision),
    ]
    assert "--value" not in first["argv"]
    assert first["argv"] != ["task", "intents", "--json"]


@pytest.mark.parametrize(
    "argv",
    [
        ["task", "get", "--json"],
        ["task", "info", "--json"],
        ["task", "--json"],
    ],
)
def test_an_invented_task_verb_lists_intents_not_help_agent(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(argv, capsys)
    assert code == 2
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "AI_STP_VALIDATION_ERROR"  # pyright: ignore[reportIndexIssue]
    assert "start, answer, continue, status, cancel, and list" in envelope["error"]["message"]  # pyright: ignore[reportIndexIssue, reportOperatorIssue]
    assert envelope["next_actions"] == ["task intents --json"]
    held = envelope["continuations"]
    assert isinstance(held, list) and held
    first = held[0]
    assert isinstance(first, dict)
    assert first["actor"] == "cli"
    assert first["argv"] == ["task", "intents", "--json"]
    assert "help --agent" not in out


def test_an_empty_machine_invocation_lists_intents_not_help_agent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run(["--json"], capsys)
    assert code == 2
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is False
    assert envelope["error"]["message"] == "no command given"  # pyright: ignore[reportIndexIssue]
    assert envelope["next_actions"] == ["task intents --json"]
    held = envelope["continuations"]
    assert isinstance(held, list) and held
    first = held[0]
    assert isinstance(first, dict)
    assert first["actor"] == "cli"
    assert first["argv"] == ["task", "intents", "--json"]
    assert "help --agent" not in out


def test_machine_help_flag_lists_intents_not_usage(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run(["--help", "--json"], capsys)
    assert code == 2
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is False
    assert "usage text is not machine readable" in envelope["error"]["message"]  # pyright: ignore[reportIndexIssue, reportOperatorIssue]
    assert envelope["next_actions"] == ["task intents --json"]
    assert "help --agent" not in out


def test_click_usage_text_is_not_a_machine_error() -> None:
    assert app._is_click_usage("Missing command.")
    assert app._is_click_usage(
        "Usage: ai-stp component [OPTIONS] COMMAND [ARGS]...\n\n"
        "Commands:\n  adopt  Register one discovered component.\n"
        "Error: Missing command."
    )
    assert not app._is_click_usage("No such command 'nope'.")
    assert not app._is_click_usage("Missing option '--kind'.")


@pytest.mark.parametrize(
    ("argv", "intent"),
    [
        (["install", "plan", "--json"], "install"),
        (["install", "approve", "--json"], "install"),
        (["install", "apply", "--json"], "install"),
        (["auth", "login", "--json"], "account"),
        (["auth", "login", "--google", "--json"], "account"),
        (["auth", "login", "--provider", "gitlab", "--json"], "account"),
        (["auth", "login", "--provider=nope", "--json"], "account"),
        (["auth", "google", "login", "--json"], "account"),
        (["publication", "plan", "--json"], "publish"),
        (["publication", "confirm", "--json"], "publish"),
        (["setup", "compose", "apply", "--json"], "change"),
        (["setup", "preserve", "plan", "--json"], "switch"),
        (["setup", "restore", "plan", "--json"], "switch"),
        (["registry", "acquire", "--json"], "install"),
        (["setup", "compose", "plan", "--json"], "change"),
        (["select", "propose", "--json"], "install"),
        (["select", "confirm", "--json"], "install"),
        (["select", "bundle", "--json"], "install"),
        (["component", "adopt", "--json"], "author"),
        (["component", "discover", "--bogus", "--json"], "author"),
        (["component", "publish", "--json"], "publish"),
        (["setup", "import", "inspect", "--json"], "author"),
        (["setup", "import", "plan", "--json"], "author"),
        (["setup", "import", "register", "--json"], "author"),
        (["install", "transaction", "plan", "--json"], "install"),
        (["install", "transaction", "approve", "--json"], "install"),
        (["install", "transaction", "status", "--json"], "install"),
        (["install", "cancel", "--json"], "install"),
        (["install", "recover", "--json"], "install"),
        (["install", "resume", "--json"], "install"),
        (["registry", "search", "--json"], "install"),
        (["registry", "port", "import", "--json"], "install"),
        (["publication", "status", "--json"], "publish"),
        (["publication", "visibility", "plan", "--json"], "publish"),
        (["setup", "preserved", "show", "--json"], "switch"),
        (["setup", "preserve", "recover", "--json"], "switch"),
    ],
)
def test_a_covered_leaf_without_required_input_starts_the_task_engine(
    argv: list[str], intent: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(argv, capsys)
    assert code == 2
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "AI_STP_VALIDATION_ERROR"  # pyright: ignore[reportIndexIssue]
    assert "task intent" in envelope["error"]["message"]  # pyright: ignore[reportIndexIssue, reportOperatorIssue]
    assert envelope["error"]["details"]["intent"] == intent  # pyright: ignore[reportIndexIssue]
    expected = f"task start --intent {intent} --idempotency-key {intent}-session-01 --json"
    assert envelope["next_actions"] == [expected]
    first = envelope["continuations"][0]
    assert isinstance(first, dict)
    assert first["actor"] == "cli"
    assert first["argv"] == [
        "task",
        "start",
        "--intent",
        intent,
        "--idempotency-key",
        f"{intent}-session-01",
        "--json",
    ]
    assert "help --agent" not in out
    assert "install plan --proposal" not in out
    assert "auth login --provider" not in out


@pytest.mark.parametrize(
    ("argv", "intent", "forbidden"),
    [
        (
            ["install", "plan", "--setup", "setup_01JQZK7B8N4M6P2R9T5V0X3YC2", "--json"],
            "install",
            "install plan",
        ),
        (
            ["select", "confirm", "--proposal", "proposal_01JQZK7B8N4M6P2R9T5V0X3YC2", "--json"],
            "install",
            "select propose",
        ),
    ],
)
def test_an_everyday_leaf_with_flags_does_not_teach_an_expert_leaf(
    argv: list[str],
    intent: str,
    forbidden: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _code, out, err = _run(argv, capsys)
    assert err == ""
    envelope = _envelope(out)
    actions = envelope["next_actions"]
    assert isinstance(actions, list)
    joined = " ".join(str(item) for item in actions)
    assert forbidden not in joined
    expected = f"task start --intent {intent} --idempotency-key {intent}-session-01 --json"
    assert expected in actions
    first = envelope["continuations"][0]
    assert isinstance(first, dict)
    assert first["actor"] == "cli"
    assert first["argv"][3] == intent


def test_install_backup_still_names_the_expert_leaf(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run(
        ["install", "plan", "--action", "backup", "--json"],
        capsys,
    )
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is False
    assert "task start --intent install" not in out
    assert code == 2


def test_a_pending_everyday_success_carries_the_draining_intent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run(["component", "discover", "--json"], capsys)
    assert code == 0
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is True
    expected = "task start --intent author --idempotency-key author-session-01 --json"
    assert envelope["next_actions"][0] == expected
    first = envelope["continuations"][0]
    assert isinstance(first, dict)
    assert first["actor"] == "cli"
    assert first["argv"] == [
        "task",
        "start",
        "--intent",
        "author",
        "--idempotency-key",
        "author-session-01",
        "--json",
    ]


def test_config_init_success_carries_the_initialize_start(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run(["config", "init", "--json"], capsys)
    assert code == 0
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is True
    expected = "task start --intent initialize --idempotency-key initialize-session-01 --json"
    assert envelope["next_actions"][0] == expected
    first = envelope["continuations"][0]
    assert isinstance(first, dict)
    assert first["argv"] == [
        "task",
        "start",
        "--intent",
        "initialize",
        "--idempotency-key",
        "initialize-session-01",
        "--json",
    ]


@pytest.mark.parametrize(
    ("argv", "intent"),
    [
        (["install", "status", "--json"], "install"),
        (["setup", "preserved", "list", "--json"], "switch"),
    ],
)
def test_a_covered_read_success_carries_the_draining_intent(
    argv: list[str], intent: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(argv, capsys)
    assert code == 0
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is True
    expected = f"task start --intent {intent} --idempotency-key {intent}-session-01 --json"
    assert envelope["next_actions"][0] == expected
    first = envelope["continuations"][0]
    assert isinstance(first, dict)
    assert first["actor"] == "cli"
    assert first["argv"][3] == intent


def test_everyday_success_strips_forbidden_continuations_then_starts() -> None:
    from ai_stp_foundation.envelope import Continuation

    held = Continuation(
        kind="advance",
        path=["install", "apply"],
        argv=["install", "apply", "--json"],
        actor="cli",
    )
    continuations, actions = app._everyday_success_envelope(
        ("install", "plan"),
        "plan",
        [held],
        ["install apply --json"],
    )
    expected = "task start --intent install --idempotency-key install-session-01 --json"
    assert continuations[0].argv == [
        "task",
        "start",
        "--intent",
        "install",
        "--idempotency-key",
        "install-session-01",
        "--json",
    ]
    assert actions == [expected]
    assert "install apply" not in " ".join(actions)


def test_an_uncovered_path_keeps_bound_continuations() -> None:
    """`corporate assignment verify` names `install plan` as its remediation.

    Outside the everyday journeys there is no guided alternative the strip
    could route to, so dropping the leaf continuation would return an empty
    envelope for a perfectly executable next step.
    """
    from ai_stp_foundation.envelope import Continuation

    remediation = Continuation(
        kind="advance",
        path=["install", "plan"],
        arguments={"setup": "setup_x@1.0", "component": ["component_y@2.0"]},
    )
    continuations, actions = app._everyday_success_envelope(
        ("corporate", "assignment", "verify"),
        "read",
        [remediation],
        ["install plan --setup setup_x@1.0 --component component_y@2.0"],
    )
    assert continuations == [remediation]
    assert actions == ["install plan --setup setup_x@1.0 --component component_y@2.0"]


def test_terminal_apply_success_keeps_allowed_continuations() -> None:
    from ai_stp_foundation.envelope import Continuation

    recover = Continuation(
        kind="advance",
        path=["install", "recover"],
        argv=["install", "recover", "--json"],
        actor="cli",
    )
    forbidden = Continuation(
        kind="advance",
        path=["install", "plan"],
        argv=["install", "plan", "--json"],
        actor="cli",
    )
    continuations, actions = app._everyday_success_envelope(
        ("install", "apply"),
        "apply",
        [recover, forbidden],
        ["install recover --json", "install plan --json"],
    )
    assert [item.argv for item in continuations] == [["install", "recover", "--json"]]
    assert actions == ["install recover --json"]


def test_backup_install_plan_stays_expert_recovery(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run(["install", "plan", "--action", "backup", "--json"], capsys)
    assert code == 2
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is False
    assert envelope["next_actions"] != [  # pyright: ignore[reportIndexIssue]
        "task start --intent install --idempotency-key install-session-01 --json"
    ]
    assert "task start --intent install" not in out


def test_an_install_plan_that_already_names_a_proposal_still_starts_install(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run(["install", "plan", "--proposal", "proposal_x", "--json"], capsys)
    assert code != 0
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is False
    assert "this group is a task intent" not in str(envelope["error"]["message"])
    expected = "task start --intent install --idempotency-key install-session-01 --json"
    assert expected in envelope["next_actions"]
    assert "install plan --proposal" not in out
    first = envelope["continuations"][0]
    assert isinstance(first, dict)
    assert first["actor"] == "cli"
    assert first["argv"][3] == "install"


def test_an_expert_sync_leaf_is_not_redirected_to_account(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run(["sync", "preview", "--json"], capsys)
    assert code == 2
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is False
    assert envelope["next_actions"] != [  # pyright: ignore[reportIndexIssue]
        "task start --intent account --idempotency-key account-session-01 --json"
    ]
    assert "task start --intent account" not in out


@pytest.mark.parametrize(
    "argv",
    [
        ["component", "--json"],
        ["registry", "--json"],
        ["select", "--json"],
        ["setup", "--json"],
        ["config", "--json"],
    ],
)
def test_an_incomplete_group_does_not_list_expert_leaves(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(argv, capsys)
    assert code == 2
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "AI_STP_VALIDATION_ERROR"  # pyright: ignore[reportIndexIssue]
    assert envelope["error"]["message"] == "incomplete command group; list shipped intents"  # pyright: ignore[reportIndexIssue]
    assert envelope["next_actions"] == ["task intents --json"]
    held = envelope["continuations"]
    assert isinstance(held, list) and held
    first = held[0]
    assert isinstance(first, dict)
    assert first["actor"] == "cli"
    assert first["argv"] == ["task", "intents", "--json"]
    assert "help --agent" not in out
    assert "Usage:" not in out
    assert "Commands:" not in out
    assert "component adopt" not in out
    assert "compose plan" not in out
    assert "select propose" not in out


def test_help_with_an_unknown_path_lists_intents(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run(["help", "--path", "nope", "--json"], capsys)
    assert code == 2
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "AI_STP_NOT_FOUND"  # pyright: ignore[reportIndexIssue]
    assert envelope["error"]["message"] == "no command lives under that path"  # pyright: ignore[reportIndexIssue]
    assert envelope["next_actions"] == ["task intents --json"]
    first = envelope["continuations"][0]
    assert isinstance(first, dict)
    assert first["actor"] == "cli"
    assert first["argv"] == ["task", "intents", "--json"]
    assert "help --agent" not in out
    assert "capabilities --json" not in out


def test_unscoped_machine_help_points_at_task_intents(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run(["help", "--agent", "--json"], capsys)
    assert code == 0
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is True
    assert envelope["next_actions"] == ["task intents --json"]
    first = envelope["continuations"][0]
    assert isinstance(first, dict)
    assert first["actor"] == "cli"
    assert first["argv"] == ["task", "intents", "--json"]
    data = envelope["data"]
    assert isinstance(data, dict)
    assert "commands" in data


def test_scoped_install_help_starts_the_install_intent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run(["help", "--path", "install", "--json"], capsys)
    assert code == 0
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is True
    expected = "task start --intent install --idempotency-key install-session-01 --json"
    assert envelope["next_actions"] == [expected]
    first = envelope["continuations"][0]
    assert isinstance(first, dict)
    assert first["actor"] == "cli"
    assert first["argv"] == [
        "task",
        "start",
        "--intent",
        "install",
        "--idempotency-key",
        "install-session-01",
        "--json",
    ]
    assert "task intents --json" not in envelope["next_actions"]


@pytest.mark.parametrize(
    ("path", "intent"),
    [
        ("auth", "account"),
        ("publication", "publish"),
        ("sync", "account"),
        ("setup compose", "change"),
        ("setup publish", "publish"),
        ("setup preserve", "switch"),
        ("setup restore", "switch"),
        ("setup preserved", "switch"),
    ],
)
def test_scoped_help_of_a_drained_family_starts_that_intent(
    path: str, intent: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(["help", "--path", path, "--json"], capsys)
    assert code == 0
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is True
    expected = f"task start --intent {intent} --idempotency-key {intent}-session-01 --json"
    assert envelope["next_actions"] == [expected]


@pytest.mark.parametrize("path", ["component", "select", "setup", "registry", "config"])
def test_scoped_help_of_a_mixed_family_lists_intents(
    path: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(["help", "--path", path, "--json"], capsys)
    assert code == 0
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is True
    assert envelope["next_actions"] == ["task intents --json"]
    first = envelope["continuations"][0]
    assert isinstance(first, dict)
    assert first["argv"] == ["task", "intents", "--json"]


def test_scoped_inspect_help_has_no_intent_continuation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run(["help", "--path", "doctor", "--json"], capsys)
    assert code == 0
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is True
    assert envelope["next_actions"] == []
    assert envelope["continuations"] == []


def test_a_machine_failure_goes_to_stdout_so_one_stream_carries_the_outcome(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # A caller reading stdout must not have to merge stderr to learn what
    # happened. Only a crash before an envelope exists uses the error stream.
    code, out, err = _run(["nope", "--json"], capsys)
    assert code == 2
    assert json.loads(out)["ok"] is False
    assert err == ""


def test_target_readiness_rejects_environment_values_without_leaking_them(
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "this-must-never-appear"
    code, out, err = _run(
        [
            "target",
            "status",
            "--project",
            "project_test",
            "--harness",
            "claude-code",
            "--requires-env",
            f"OPENAI_API_KEY={secret}",
            "--json",
        ],
        capsys,
    )

    assert code == 2
    assert err == ""
    envelope = _envelope(out)
    assert envelope["error"]["code"] == "AI_STP_VALIDATION_ERROR"  # pyright: ignore[reportIndexIssue]
    assert secret not in out


def test_a_human_failure_goes_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _run(["nope"], capsys)
    assert code == 2
    assert out == ""
    assert err.startswith("AI_STP_VALIDATION_ERROR: ")


def test_human_help_is_click_s_own_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _err = _run(["--help"], capsys)
    assert code == 0
    assert "Usage: ai-stp" in out
    assert "--json" in out


def test_an_empty_human_invocation_opens_first_run_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run([], capsys)
    assert code == 0
    assert err == ""
    assert "Usage: ai-stp" in out
    assert "ai-stp task intents --json" in out


def test_auth_help_teaches_the_account_intent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run(["auth", "--help"], capsys)
    assert code == 0
    assert err == ""
    assert "ai-stp task start --intent account --idempotency-key account-session-01 --json" in out
    assert "ai-stp auth status" not in out
    assert "ai-stp auth login --provider google" not in out


@pytest.mark.parametrize(
    "argv",
    [
        ["auth", "login"],
        ["auth", "login", "--google"],
        ["auth", "login", "--provider", "gitlab"],
        ["auth", "google", "login"],
    ],
)
def test_common_auth_spelling_errors_start_the_account_intent(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(argv, capsys)
    assert code == 2
    assert out == ""
    assert "task intent" in err
    assert "auth login --provider" not in err
    assert "auth commands start with" not in err


def test_an_unexpected_exception_becomes_the_internal_class_and_leaks_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("/home/someone/.config/token=abc")

    monkeypatch.setattr(app, "build_group", explode)
    code, out, _err = _run(["version", "--json"], capsys)
    assert code == 70
    envelope = _envelope(out)
    assert envelope["error"]["code"] == "AI_STP_INTERNAL"  # pyright: ignore[reportIndexIssue]
    assert envelope["error"]["details"] == {"exception": "RuntimeError"}  # pyright: ignore[reportIndexIssue]
    assert "token" not in out


@pytest.mark.parametrize("error", [KeyboardInterrupt, click.Abort])
def test_an_interruption_is_the_shell_s_convention_and_not_an_internal_failure(
    error: type[BaseException], monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupt(*_args: object, **_kwargs: object) -> None:
        raise error

    monkeypatch.setattr(app, "build_group", interrupt)
    assert app.main(["version"]) == 130


def test_every_invocation_carries_its_own_request_id(capsys: pytest.CaptureFixture[str]) -> None:
    first = _envelope(_run(["version", "--json"], capsys)[1])["request_id"]
    second = _envelope(_run(["version", "--json"], capsys)[1])["request_id"]
    assert first != second


def test_the_console_entrypoint_exits_with_the_dispatch_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["ai-stp", "nope"])
    with pytest.raises(SystemExit) as raised:
        app.run()
    assert raised.value.code == 2


def test_a_valued_option_reaches_its_handler(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A declared parameter that is neither a flag nor required takes the branch
    # `_require_declared_flags` skips, and its value has to arrive intact.
    from ai_stp_cli.answer import Answer
    from ai_stp_cli.registry import COMMANDS, Command
    from ai_stp_contracts.machine_help import CommandParameter, VersionReport

    seen: dict[str, object] = {}

    def handler(parameters: Mapping[str, object]) -> Answer[VersionReport]:
        seen.update(parameters)
        return Answer(
            VersionReport(
                cli_version="9.9.9",
                python_version="3.12.0",
                contract_digest="sha256:" + "0" * 64,
            )
        )

    descriptor = COMMANDS[0].descriptor.model_copy(
        update={
            "path": ["probe"],
            "parameters": [
                CommandParameter(
                    name="thing",
                    kind="option",
                    value_type="string",
                    required=False,
                    repeatable=False,
                    summary="A declared value.",
                )
            ],
        }
    )
    # The handler is named rather than referenced, so the stub is installed
    # where the name resolves rather than passed in.
    from ai_stp_cli.commands import version as version_command

    monkeypatch.setattr(version_command, "run", handler)
    monkeypatch.setattr(app, "COMMANDS", (Command(descriptor, "version:run"),))

    code, out, _err = _run(["probe", "--thing", "value", "--json"], capsys)
    assert code == 0
    assert seen == {"thing": "value"}
    assert _envelope(out)["data"]["cli_version"] == "9.9.9"  # pyright: ignore[reportIndexIssue]


def test_a_hyphenated_option_reaches_its_handler_under_its_declared_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The declared name is the one the handler asks for, hyphens and all.

    Click derives its own key from the flag it parsed, so `--two-words` arrives
    as `two_words` while `registry.py` — the owner of the name, and the one
    machine help publishes — calls it `two-words`. A handler asking for the
    declared name would find nothing, and finding nothing is exactly what an
    omitted option looks like: the command would not fail, it would quietly do
    something else. This goes through real Click so that the assertion is about
    what Click does rather than about what we assume it does.
    """
    from ai_stp_cli.answer import Answer
    from ai_stp_cli.registry import COMMANDS, Command
    from ai_stp_contracts.machine_help import CommandParameter, VersionReport

    seen: dict[str, object] = {}

    def handler(parameters: Mapping[str, object]) -> Answer[VersionReport]:
        seen.update(parameters)
        return Answer(
            VersionReport(
                cli_version="9.9.9",
                python_version="3.12.0",
                contract_digest="sha256:" + "0" * 64,
            )
        )

    descriptor = COMMANDS[0].descriptor.model_copy(
        update={
            "path": ["probe"],
            "parameters": [
                CommandParameter(
                    name="two-words",
                    kind="option",
                    value_type="string",
                    required=False,
                    repeatable=False,
                    summary="A declared value whose name has a hyphen.",
                )
            ],
        }
    )
    # The handler is named rather than referenced, so the stub is installed
    # where the name resolves rather than passed in.
    from ai_stp_cli.commands import version as version_command

    monkeypatch.setattr(version_command, "run", handler)
    monkeypatch.setattr(app, "COMMANDS", (Command(descriptor, "version:run"),))

    code, _out, _err = _run(["probe", "--two-words", "value", "--json"], capsys)
    assert code == 0
    assert seen == {"two-words": "value"}


def test_a_required_hyphenated_boolean_is_checked_under_its_declared_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from ai_stp_cli.answer import Answer
    from ai_stp_cli.registry import COMMANDS, Command
    from ai_stp_contracts.machine_help import CommandParameter, VersionReport

    def handler(_parameters: Mapping[str, object]) -> Answer[VersionReport]:
        return Answer(
            VersionReport(
                cli_version="9.9.9",
                python_version="3.12.0",
                contract_digest="sha256:" + "0" * 64,
            )
        )

    descriptor = COMMANDS[0].descriptor.model_copy(
        update={
            "path": ["probe"],
            "parameters": [
                CommandParameter(
                    name="for-publication",
                    kind="option",
                    value_type="boolean",
                    required=True,
                    repeatable=False,
                    summary="Select one explicit validation profile.",
                )
            ],
        }
    )
    # The handler is named rather than referenced, so the stub is installed
    # where the name resolves rather than passed in.
    from ai_stp_cli.commands import version as version_command

    monkeypatch.setattr(version_command, "run", handler)
    monkeypatch.setattr(app, "COMMANDS", (Command(descriptor, "version:run"),))

    assert _run(["probe", "--for-publication", "--json"], capsys)[0] == 0
    code, out, _err = _run(["probe", "--json"], capsys)
    assert code == 2
    assert _envelope(out)["error"]["code"] == "AI_STP_VALIDATION_ERROR"  # pyright: ignore[reportIndexIssue]


def test_every_declared_option_arrives_under_the_name_it_was_declared_with() -> None:
    """Swept over the real registry, because one worked and ten did not.

    `--plan-digest` was read as `plan-digest` and delivered as `plan_digest`,
    which made an approved plan unreachable from the command line; one other
    option had the mismatch the other way round and happened to work. Neither
    is visible from reading a single command, so this asks all of them.
    """
    from ai_stp_cli.registry import COMMANDS

    for command in COMMANDS:
        parameters = command.descriptor.parameters
        # Keyed the way Click keys them, which the test above pins to reality.
        given = {item.name.replace("-", "_"): f"value of {item.name}" for item in parameters}
        arrived = app._as_declared(command, given)  # pyright: ignore[reportPrivateUsage]
        for item in parameters:
            assert arrived.get(item.name) == f"value of {item.name}", (
                f"{' '.join(command.descriptor.path)} --{item.name}"
            )


#: Declared parameters no handler reads, each for a stated reason. An entry here
#: is a claim; the test below is what keeps it honest.
UNREAD_BY_DESIGN: dict[str, str] = {
    "help --agent": "names the caller; the registry is the command's only answer either way",
    "component passport validate --for-publication": (
        "names the only profile the command has; accepted so an older spelling still parses"
    ),
}


def _handler_sources(handler: Callable[..., object]) -> str:
    """The handler's module and the `ai_stp_cli` modules it imports, as text."""
    import inspect
    import sys

    place = inspect.getsourcefile(handler)
    if place is None:
        return ""
    text = Path(place).read_text("utf-8")
    module = sys.modules.get(getattr(handler, "__module__", ""))
    for value in vars(module or object()).values():
        name = getattr(value, "__name__", "")
        if not name.startswith("ai_stp_cli"):
            continue
        nested = getattr(value, "__file__", None)
        if nested:
            text += Path(nested).read_text("utf-8")
    return text


def test_every_declared_option_is_read_by_the_handler_that_declares_it() -> None:
    """A declared option nobody reads does nothing, and says nothing about it.

    From the outside this is indistinguishable from the hyphen mismatch that
    made ten options dead: the command accepts the flag, exits zero and ignores
    it. `_as_declared` fixes how a name *arrives*; this asks whether anybody is
    there to receive it.

    Matched on the quoted name rather than on one access shape — handlers read
    through `parameters.get`, `parameters[...]` and a shared
    `_required(parameters, name)` helper, and a check that knew only the first
    would fail seven honest commands.

    Read across one level of delegation, not the handler's file alone. When the
    release-trust helpers moved out of `commands.install` so the harness program
    path could stop spawning providers it had not verified, three options that
    `install plan` genuinely reads went unread here — the reader had moved one
    import away. Following the `ai_stp_cli` modules a handler imports keeps the
    question "is anybody receiving this" answerable when the answer is a shared
    module, without naming that module and turning a mechanism into a list.
    """

    from ai_stp_cli.registry import COMMANDS

    unread: list[str] = []
    for command in COMMANDS:
        source = _handler_sources(command.handler)
        for parameter in command.descriptor.parameters:
            named = f'"{parameter.name}"' in source or f"'{parameter.name}'" in source
            if not named:
                unread.append(f"{' '.join(command.descriptor.path)} --{parameter.name}")

    assert sorted(unread) == sorted(UNREAD_BY_DESIGN), f"declared and unread: {sorted(unread)}"


def test_every_exemption_names_a_parameter_that_exists() -> None:
    """An exemption for a parameter nobody declares hides the next real one."""
    from ai_stp_cli.registry import COMMANDS

    declared = {
        f"{' '.join(command.descriptor.path)} --{parameter.name}"
        for command in COMMANDS
        for parameter in command.descriptor.parameters
    }
    assert set(UNREAD_BY_DESIGN) <= declared


def test_an_override_travels_from_the_command_line_into_the_report(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, _err = _run(
        [
            "config",
            "show",
            "--set",
            "search.result_limit=7",
            "--set",
            "sync.enabled=true",
            "--json",
        ],
        capsys,
    )
    assert code == 0
    data = cast(dict[str, list[dict[str, object]]], _envelope(out)["data"])
    values = {str(item["path"]): item for item in data["values"]}
    assert values["search.result_limit"]["value"] == 7
    assert values["search.result_limit"]["source"] == "command_argument"
    assert values["sync.enabled"]["value"] is True


def test_a_malformed_override_is_refused_rather_than_ignored(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, _err = _run(["config", "show", "--set", "search.result_limit", "--json"], capsys)
    assert code == 2
    assert "path=value" in _envelope(out)["error"]["message"]  # pyright: ignore[reportIndexIssue, reportOperatorIssue]


def test_a_missing_confirmation_is_a_decision_not_a_validation_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, _err = _run(["device", "reset", "--json"], capsys)
    assert code == 4
    envelope = _envelope(out)
    assert envelope["error"]["code"] == "AI_STP_USER_DECISION_REQUIRED"  # pyright: ignore[reportIndexIssue]
    assert envelope["next_actions"] == ["device reset --confirm --json"]


def test_a_fallback_warning_reaches_the_envelope_and_leaves_ok_true(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # A warning does not make the call unsuccessful, and it must not go to
    # stderr: machine mode promises one object on stdout and an empty stderr.
    code, out, err = _run(["device", "init", "--json"], capsys)
    assert code == 0
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is True
    assert envelope["warnings"] and "owner-only file" in envelope["warnings"][0]  # pyright: ignore[reportIndexIssue, reportOperatorIssue]


def test_a_warning_is_visible_in_human_mode_too(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _err = _run(["device", "init"], capsys)
    assert code == 0
    assert out.startswith("warning: ")


def test_a_refused_parameter_is_a_validation_error_not_an_internal_one() -> None:
    """A request model refusing a caller's value is bad input, not a fault.

    `registry search --query ""` answered `AI_STP_INTERNAL: unexpected internal
    failure` with an empty `next_actions`, because pydantic's `ValidationError`
    reached the generic handler. That tells an agent the CLI is broken when the
    truth is that `q` may not be empty.
    """

    class Request(BaseModel):
        q: Annotated[str, Field(min_length=1)]

    try:
        Request(q="")
    except ValidationError as error:
        failure = invalid_parameters(error)
    else:  # pragma: no cover - the model must refuse an empty value
        raise AssertionError("the model accepted an empty value")

    assert failure.code == "AI_STP_VALIDATION_ERROR"
    assert failure.details["fields"] == "q"
    assert failure.details["errors"] == [
        {
            "pointer": "#/q",
            "issue": "string_too_short",
            "detail": "String should have at least 1 character",
        }
    ]
    assert failure.next_actions == []


def test_a_refused_value_never_reaches_the_message_or_details() -> None:
    """`SPEC-011` REQ-1108: a caller's value may be the credential they mistyped."""
    secret = "sk-live-must-never-appear"

    class Request(BaseModel):
        token: Annotated[str, Field(max_length=4)]

    try:
        Request(token=secret)
    except ValidationError as error:
        failure = invalid_parameters(error)
    else:  # pragma: no cover - the model must refuse an over-long value
        raise AssertionError("the model accepted an over-long value")

    assert secret not in failure.message
    assert secret not in str(failure.details)
    assert failure.details["fields"] == "token"
    assert failure.details["errors"] == [
        {
            "pointer": "#/token",
            "issue": "string_too_long",
            "detail": "String should have at most 4 characters",
        }
    ]


def test_output_survives_a_stream_that_defaults_to_a_legacy_code_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Machine mode emits real characters, so the stream has to accept them.

    JSON is written with `ensure_ascii=False` on purpose: a passport carries the
    characters its author wrote rather than their escapes. On a host whose
    standard streams default to a legacy code page — Windows, before UTF-8 mode
    became the interpreter default — that write raises `UnicodeEncodeError` and
    the invocation dies inside its own success path, reporting an internal
    failure that says nothing about encoding.

    Measured rather than imagined: `toolchain profile` exited 70 with
    `details.exception = UnicodeEncodeError` on `windows-latest` while passing
    on Linux and macOS, which is what a cross-platform CI is for.
    """
    raw = io.BytesIO()
    legacy = io.TextIOWrapper(raw, encoding="cp1252", newline="")
    monkeypatch.setattr(sys, "stdout", legacy)

    code = app.main(["toolchain", "profile", "--json"])
    legacy.flush()

    assert code == 0
    written = raw.getvalue()
    assert written, "the command wrote nothing"
    # Decodes as UTF-8, which cp1252 output would not.
    envelope = json.loads(written.decode("utf-8"))
    assert envelope["ok"] is True


def test_a_damaged_registry_is_named_not_reported_as_an_internal_fault(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Corruption of the local store is the operator's state, not our bug.

    Measured: a registry file truncated mid-byte answered every read and write
    with `AI_STP_INTERNAL: unexpected internal failure` — no file named, no
    hint that local state (not the tool) is damaged, and `internal` telling an
    agent to retry the same dead end. sqlite reports this as its own error
    class; the answer must carry the registry path and read as state to
    reconcile.
    """
    from ai_stp_cli.local.database import configured_path

    place = configured_path()
    place.parent.mkdir(parents=True, exist_ok=True)
    place.write_bytes(b"this is not a database, and it is short")

    code = app.main(["component", "find", "--prefix", "component", "--json"])
    answer = json.loads(capsys.readouterr().out)

    assert answer["ok"] is False
    assert answer["error"]["code"] == "AI_STP_PRECONDITION_FAILED"
    assert "registry" in answer["error"]["details"]
    assert code == 4


@pytest.mark.parametrize(
    "argv",
    [
        ["auth", "login", "--provider=google", "--bogus", "--json"],
        ["auth", "login", "--provider", "google", "--bogus", "--json"],
    ],
)
def test_a_correct_provider_written_either_way_is_not_blamed_for_another_option(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """`--provider=google` is a provider, and the attached form is the common one.

    Looking for the literal token `--provider` found nothing in the attached
    spelling, so the answer was "auth login requires --provider" for a call that
    had supplied one. An agent following that edits the argument that was right
    and never sees `--bogus`.
    """
    code, out, _err = _run(argv, capsys)
    assert code == 2
    envelope = _envelope(out)
    error = cast(Mapping[str, object], envelope["error"])
    assert "--bogus" in str(error["message"])
    assert "requires --provider" not in str(error["message"])


@pytest.mark.parametrize(
    "argv",
    [
        ["help", "--agent", "--help", "--json"],
        ["--help", "--json"],
        ["version", "-h", "--json"],
    ],
)
def test_asking_for_usage_in_machine_mode_is_still_refused(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _err = _run(argv, capsys)
    assert code == 2
    error = cast(Mapping[str, object], _envelope(out)["error"])
    assert error["message"] == "usage text is not machine readable"


@pytest.mark.parametrize(
    "tail",
    [
        ["--arg", "--help"],
        ["--arg=--help"],
        ["--arg", "-h"],
        ["--arg", "run", "--arg", "--help"],
    ],
)
def test_a_forwarded_help_value_is_a_value_and_not_a_request_for_usage(
    tail: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """Asking an installed program to describe itself is the point of `invoke`.

    The refusal used to fire on any `--help` anywhere in argv, so the one call
    an agent makes to learn what a tool does was answered with "usage text is
    not machine readable" — about this CLI's usage, which nobody had asked for.
    """
    argv = [
        "component",
        "program",
        "invoke",
        "--id",
        "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        *tail,
        "--json",
    ]
    code, out, _err = _run(argv, capsys)
    _assert_not_about_usage(out)
    assert code != 0

    # The machine flag is accepted at every level, so the same call with it
    # written first must read the same way.
    code, out, _err = _run(["--json", *argv[:-1]], capsys)
    _assert_not_about_usage(out)
    assert code != 0


def _assert_not_about_usage(out: str) -> None:
    """It got as far as the registry, which is what "not intercepted" means."""
    error = cast(Mapping[str, object], _envelope(out)["error"])
    assert error["message"] != "usage text is not machine readable"


def test_everything_after_the_terminator_is_operand_text(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """After `--` there are no flags left, so there is no help request either.

    Click is the authority on what the tokens mean, and it calls this one an
    unexpected argument. Answering about usage instead would name a problem the
    caller does not have.
    """
    code, out, _err = _run(["version", "--json", "--", "--help"], capsys)
    assert code == 2
    error = cast(Mapping[str, object], _envelope(out)["error"])
    assert "--help" in str(error["message"])
    assert error["message"] != "usage text is not machine readable"
