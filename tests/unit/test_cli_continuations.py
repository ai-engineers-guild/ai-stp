"""Emitted continuations bind argv from the registry, not from guesses.

UX-02: `continuation_argv` cannot tell a valued option from a flag, so an
empty string collapsed into a bare flag and an explicit `False` disappeared.
The binder in `application.continuations` derives argv from the same
`CommandParameter` declarations the Click parser enforces — these tests
parse the emitted argv with the real parser rather than asserting strings.
"""

import click

from ai_stp_cli.app import build_group
from ai_stp_cli.application.continuations import bind_continuation
from ai_stp_foundation.envelope import Continuation, continuation_argv

_GROUP = build_group()


def _command(path: list[str]) -> click.Command:
    command: click.Command = _GROUP
    for name in path:
        assert isinstance(command, click.Group)
        command = command.commands[name]
    return command


def _parse(item: Continuation) -> dict[str, object]:
    """Parse the bound argv with the real command, without invoking it."""
    bound = bind_continuation(item)
    argv = bound.argv[len(item.path) :]
    context = _command(item.path).make_context("continuation", argv)
    return dict(context.params)


def test_an_empty_string_value_survives_binding() -> None:
    """`--input ''` must reach the parser as an empty string, not a bare flag."""
    item = Continuation(
        kind="advance",
        path=["task", "start"],
        arguments={"intent": "author", "idempotency-key": "k1", "input": ""},
    )
    assert bind_continuation(item).argv == [
        "task",
        "start",
        "--intent",
        "author",
        "--idempotency-key",
        "k1",
        "--input",
        "",
        "--json",
    ]
    # The declaration-free derivation collapsed the value into `--input`.
    assert continuation_argv(item) == [
        "task",
        "start",
        "--intent",
        "author",
        "--idempotency-key",
        "k1",
        "--input",
        "--json",
    ]
    assert _parse(item)["input"] == ""


def test_an_explicit_false_on_a_valued_option_is_not_dropped() -> None:
    item = Continuation(
        kind="advance",
        path=["task", "start"],
        arguments={"intent": "author", "idempotency-key": "k1", "input": False},
    )
    assert _parse(item)["input"] == "false"


def test_integer_arguments_reach_the_parser_as_integers() -> None:
    item = Continuation(
        kind="advance",
        path=["task", "continue"],
        arguments={"task": "task_01J0000000000000000000000A", "revision": 3},
    )
    parsed = _parse(item)
    assert parsed["task"] == "task_01J0000000000000000000000A"
    assert parsed["revision"] == 3


def test_repeatable_options_emit_one_flag_per_value() -> None:
    item = Continuation(
        kind="advance",
        path=["config", "set"],
        arguments={"set": ["sync.enabled=true", "catalog.url=https://x"]},
    )
    bound = bind_continuation(item)
    assert bound.argv == [
        "config",
        "set",
        "--set",
        "sync.enabled=true",
        "--set",
        "catalog.url=https://x",
        "--json",
    ]
    assert _parse(item)["set"] == ("sync.enabled=true", "catalog.url=https://x")


def test_boolean_options_emit_a_flag_only_for_true() -> None:
    held = Continuation(
        kind="advance",
        path=["auth", "complete"],
        arguments={"wait": True},
    )
    assert bind_continuation(held).argv == ["auth", "complete", "--wait", "--json"]
    assert _parse(held)["wait"] is True

    declined = Continuation(
        kind="advance",
        path=["auth", "complete"],
        arguments={"wait": False},
    )
    assert bind_continuation(declined).argv == ["auth", "complete", "--json"]
    assert _parse(declined)["wait"] is False


def test_an_empty_string_on_a_declared_flag_is_the_flag_sentinel() -> None:
    """Producers emitted `"confirm": ""` to mean flag-present; a declared
    boolean cannot hold a valued empty string, so it binds to `--confirm`
    while a string parameter keeps `""` as data (the test above)."""
    item = Continuation(
        kind="advance",
        path=["harness", "remove"],
        arguments={"harness": "codex", "prefix": "/p", "target": "/t", "confirm": ""},
    )
    assert bind_continuation(item).argv == [
        "harness",
        "remove",
        "--harness",
        "codex",
        "--prefix",
        "/p",
        "--target",
        "/t",
        "--confirm",
        "--json",
    ]
    assert _parse(item)["confirm"] is True


def test_dash_prefixed_values_use_the_equals_form() -> None:
    item = Continuation(
        kind="advance",
        path=["task", "start"],
        arguments={"intent": "author", "idempotency-key": "k1", "input": "-n"},
    )
    bound = bind_continuation(item)
    assert "--input=-n" in bound.argv
    assert _parse(item)["input"] == "-n"


def test_spaces_quotes_and_unicode_stay_one_token() -> None:
    for text in ("/tmp/My Project/x", 'say "hi"', "héllo wörld", "a;b|c"):
        item = Continuation(
            kind="advance",
            path=["task", "start"],
            arguments={"intent": "author", "idempotency-key": "k1", "input": text},
        )
        assert _parse(item)["input"] == text


def test_a_hand_filled_argv_that_matches_is_kept() -> None:
    item = Continuation(
        kind="advance",
        path=["task", "continue"],
        arguments={"task": "task_01J0000000000000000000000A", "revision": 7},
        argv=[
            "task",
            "continue",
            "--task",
            "task_01J0000000000000000000000A",
            "--revision",
            "7",
            "--json",
        ],
    )
    assert bind_continuation(item) is item


def test_an_undeclared_argument_keeps_the_foundation_derivation() -> None:
    """A producer bug must not break the envelope carrying the continuation."""
    item = Continuation(
        kind="advance",
        path=["task", "continue"],
        arguments={"task": "task_01J0000000000000000000000A", "nope": "x"},
    )
    assert bind_continuation(item).argv == continuation_argv(item)


def test_an_unknown_path_keeps_the_foundation_derivation() -> None:
    item = Continuation(kind="advance", path=["not", "a", "command"], arguments={"x": "1"})
    assert bind_continuation(item).argv == continuation_argv(item)


def test_missing_arguments_still_render_the_help_fallback() -> None:
    item = Continuation(kind="blocked", path=["task", "start"], missing=["intent"])
    assert bind_continuation(item).argv == ["help", "--path", "task start", "--json"]
