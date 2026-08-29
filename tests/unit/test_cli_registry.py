"""The registry is the only declaration: parser, machine help and capabilities agree."""

import click
import pytest

from ai_stp_cli import app, registry
from ai_stp_cli.commands import machine_help
from ai_stp_cli.registry import (
    COMMANDS,
    command_paths,
    descriptors,
    reserved_option_names,
)
from ai_stp_contracts.machine_help import CommandParameter
from ai_stp_foundation.errors import ERROR_CODES
from ai_stp_foundation.harnesses import HARNESS_IDS


def _leaf(root: click.Group, path: list[str]) -> click.Command:
    node: click.Command = root
    for step in path:
        assert isinstance(node, click.Group), path
        found = node.commands.get(step)
        assert found is not None, path
        node = found
    return node


def _option_names(command: click.Command) -> set[str]:
    return {
        name.removeprefix("--")
        for parameter in command.params
        for name in parameter.opts
        if name.startswith("--")
    }


def test_every_declared_command_is_reachable_with_exactly_its_declared_flags() -> None:
    # The claim `ADR-0057` rests on is that parser and machine help cannot
    # drift because there is one declaration. That is only true if the parser
    # really is built from it, so this walks the built group rather than
    # trusting the construction.
    root = app.build_group()
    for command in COMMANDS:
        leaf = _leaf(root, list(command.descriptor.path))
        declared = {parameter.name for parameter in command.descriptor.parameters}
        assert _option_names(leaf) == declared | {"json"}, command.name


def test_the_parser_contains_nothing_the_registry_did_not_declare() -> None:
    # The other direction: a command added to the parser alone would be
    # invisible to `help --agent`, and the agent is told the registry is
    # complete.
    root = app.build_group()
    reachable: set[str] = set()

    def walk(node: click.Command, prefix: list[str]) -> None:
        if isinstance(node, click.Group):
            for name, child in node.commands.items():
                walk(child, [*prefix, name])
            return
        reachable.add(" ".join(prefix))

    walk(root, [])
    assert reachable == set(command_paths())


def test_machine_help_and_capabilities_report_the_same_commands() -> None:
    help_paths = {" ".join(descriptor.path) for descriptor in descriptors()}
    reported = machine_help.capabilities({}).payload.command_paths
    assert help_paths == set(reported) == set(command_paths())


def test_machine_help_publishes_the_canonical_error_dispositions() -> None:
    published = machine_help.registry({}).payload.error_codes
    assert [item.code for item in published] == sorted(ERROR_CODES)
    for item in published:
        canonical = ERROR_CODES[item.code]
        assert item.exit_class == canonical.exit_class
        assert item.handling == canonical.handling
        assert item.description == canonical.description

    # Exit class 4 is deliberately not one agent action: only the named
    # user-decision code asks, while stale/concurrent state is reconciled.
    by_code = {item.code: item.handling for item in published}
    assert by_code["AI_STP_USER_DECISION_REQUIRED"] == "ask_user"
    assert by_code["AI_STP_CONFLICT"] == "reconcile_state"


def test_command_paths_are_unique_and_ordered() -> None:
    names = [command.name for command in COMMANDS]
    assert len(set(names)) == len(names)
    assert command_paths() == sorted(names)
    assert [descriptor.path for descriptor in descriptors()] == [
        descriptor.path
        for descriptor in sorted(descriptors(), key=lambda item: " ".join(item.path))
    ]


def test_no_command_redeclares_a_global_option() -> None:
    # `--json` belongs to every command. A command declaring it again would put
    # the same flag in machine help twice and let the two summaries diverge.
    reserved = reserved_option_names()
    for command in COMMANDS:
        assert not reserved & {parameter.name for parameter in command.descriptor.parameters}


def test_integration_scenarios_are_machine_described_without_parsing_prose() -> None:
    scenarios: list[tuple[str, set[str], dict[str, set[str]]]] = [
        ("registry search", {"kind"}, {"kind": {"component", "setup"}}),
        ("component discover", set(), {}),
        ("component adopt", {"path"}, {}),
        ("target status", {"project", "harness"}, {"harness": set(HARNESS_IDS)}),
        ("target diff", {"project", "harness"}, {"harness": set(HARNESS_IDS)}),
        ("target rollback", {"project", "harness"}, {"harness": set(HARNESS_IDS)}),
    ]
    for path, required, closed in scenarios:
        descriptor = next(item for item in descriptors() if " ".join(item.path) == path)
        parameters = {item.name: item for item in descriptor.parameters}

        assert descriptor.result_schema is not None
        assert {name for name, item in parameters.items() if item.required} == required
        for name, choices in closed.items():
            assert set(parameters[name].choices) == choices


def test_update_plan_cross_parameter_rules_are_structured() -> None:
    descriptor = next(item for item in descriptors() if item.path == ["install", "plan"])

    assert next(item for item in descriptor.parameters if item.name == "action").choices == [
        "install",
        "update",
        "backup",
        "remove",
        "rollback",
    ]
    assert [item.model_dump(mode="json") for item in descriptor.parameter_rules] == [
        {
            "kind": "exactly_one",
            "parameters": ["proposal", "setup"],
            "when_parameter": "",
            "when_values": [],
        },
        {
            "kind": "required_when",
            "parameters": ["project"],
            "when_parameter": "setup",
            "when_values": ["present"],
        },
        {
            "kind": "required_when",
            "parameters": ["target"],
            "when_parameter": "protocol-version",
            "when_values": ["2", "3"],
        },
    ]


def test_read_commands_never_ask_for_confirmation() -> None:
    # `#72` ships only observing commands, and a `read` that demanded a decision
    # would teach the Skill a rule that does not exist.
    for command in COMMANDS:
        if command.descriptor.mutability == "read":
            assert command.descriptor.confirmation == "none", command.name


def test_state_changing_commands_are_not_published_as_reads() -> None:
    mutability = {command.name: command.descriptor.mutability for command in COMMANDS}

    assert mutability["toolchain install"] == "apply"
    assert mutability["toolchain remove"] == "destructive"
    assert mutability["select propose"] == "plan"
    assert mutability["select cancel"] == "apply"


def test_next_actions_only_name_commands_that_exist() -> None:
    known = set(command_paths())
    for command in COMMANDS:
        for suggestion in command.descriptor.next_actions:
            # Suggestions carry flags; the command is the leading path.
            head = " ".join(word for word in suggestion.split() if not word.startswith("--"))
            assert head in known, f"{command.name} -> {suggestion}"


def test_a_command_path_deeper_than_the_contract_allows_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `CommandPath` allows four segments; a fifth has to fail loudly, because a
    # silently dropped command would be in machine help and not in the parser.
    deep = COMMANDS[0].descriptor.model_copy(update={"path": ["a", "b", "c", "d", "e"]})
    monkeypatch.setattr(app, "COMMANDS", (COMMANDS[0].__class__(deep, COMMANDS[0].handler_ref),))
    with pytest.raises(Exception, match="deeper than the contract allows"):
        app.build_group()


@pytest.mark.parametrize(
    ("value_type", "expected"),
    [("string", click.STRING), ("integer", click.INT)],
)
def test_value_typed_options_reach_click_with_their_declared_type(
    value_type: str, expected: click.ParamType[object], monkeypatch: pytest.MonkeyPatch
) -> None:
    # No shipped command declares a valued option yet, but the mapping is part
    # of the registry contract; leaving it unexercised means the command that
    # introduces one discovers the behaviour instead of relying on it.
    original = COMMANDS[0]
    descriptor = original.descriptor.model_copy(
        update={
            "path": ["probe"],
            "parameters": [
                CommandParameter(
                    name="thing",
                    kind="option",
                    value_type=value_type,  # pyright: ignore[reportArgumentType]
                    required=True,
                    repeatable=False,
                    summary="A declared value.",
                )
            ],
        }
    )
    monkeypatch.setattr(app, "COMMANDS", (type(original)(descriptor, original.handler_ref),))

    option = next(
        parameter
        for parameter in _leaf(app.build_group(), ["probe"]).params
        if "--thing" in parameter.opts
    )
    assert option.type is expected
    assert option.required


def test_the_harness_set_is_derived_from_its_own_type() -> None:
    # `capabilities` publishes this set, so a second literal list restating it
    # would be a machine boundary that can drift from the type it claims.
    from typing import get_args

    from ai_stp_foundation.harnesses import HARNESS_IDS, HarnessId, is_supported_harness

    assert frozenset(get_args(HarnessId.__value__)) == HARNESS_IDS
    assert is_supported_harness("claude-code")
    assert not is_supported_harness("undefined")


def test_a_command_and_a_group_cannot_claim_the_same_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `version` and `version show` cannot both exist: one name would have to be
    # both a leaf and a group, and the parser would silently keep whichever it
    # built second while machine help advertised both.
    original = COMMANDS[0]
    leaf = original.descriptor.model_copy(update={"path": ["clash"], "parameters": []})
    nested = original.descriptor.model_copy(update={"path": ["clash", "deeper"], "parameters": []})
    monkeypatch.setattr(
        app,
        "COMMANDS",
        (
            type(original)(leaf, original.handler_ref),
            type(original)(nested, original.handler_ref),
        ),
    )
    with pytest.raises(Exception, match="claim the same name"):
        app.build_group()


def test_every_declared_handler_resolves() -> None:
    """A named handler is a string until something resolves it.

    The registry imported thirty command modules at load so that
    `handler=version.run` could be a reference, and every invocation paid for
    all of them: measured 2026-08-29, `import ai_stp_cli.registry` cost 0.818s
    against 0.461s for the descriptors alone, on a 1.0s `ai-stp version`.

    Naming the handler defers that to dispatch and moves the cost onto the
    command actually typed. What it also does is turn a typo from an import
    error at startup into a failure at dispatch, on one command, possibly the
    one nobody runs. This test is the exchange: every declaration resolves here
    instead.
    """
    unresolved: list[str] = []
    for command in registry.COMMANDS:
        try:
            handler = command.handler
        except (ImportError, AttributeError) as error:
            unresolved.append(f"{command.name} -> {command.handler_ref}: {error}")
            continue
        if not callable(handler):
            unresolved.append(f"{command.name} -> {command.handler_ref}: not callable")

    assert not unresolved, unresolved
    assert len(registry.COMMANDS) == len(registry.DECLARATIONS)


def test_dispatching_one_command_does_not_import_every_command_module() -> None:
    """The property the change was made for, asserted rather than assumed.

    Without this, the handlers could quietly become eager again — a single
    module-level `from ai_stp_cli.commands import x` restores the old cost and
    nothing else in the suite would notice.
    """
    import subprocess
    import sys

    probe = (
        "import ai_stp_cli.registry, sys;"
        "loaded = {name for name in sys.modules if name.startswith('ai_stp_cli.commands.')};"
        "print(len(loaded))"
    )
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    # A handful arrive through other module-level imports; thirty would mean the
    # registry is eager again.
    assert int(result.stdout.strip()) < 10, result.stdout
