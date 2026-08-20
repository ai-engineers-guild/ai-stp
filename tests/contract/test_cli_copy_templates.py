"""Every canonical copy template must be a command the CLI actually accepts.

`SPEC-037` `REQ-3706` requires exact commands from one canonical source. Before
this gate existed, all five templates rendered something the parser refuses:
`registry show` was written without its required `--kind` and `--id`, `@{version}`
was a syntax the CLI never parsed, and `component sync`, `setup sync` and `login`
were not commands at all. A copy button handed the user a guaranteed failure.

The oracle is the parser, not a second list. Comparing templates against a
hand-written table of command names is how the previous drift survived: both
tables agreed with each other and neither agreed with the registry.

Only parsing is exercised. These commands reach the network or the local
registry, so what is asserted is that the invocation is well-formed — that the
verb exists, the options are declared, and the values satisfy their choices.
"""

import re
from pathlib import Path

import pytest

from ai_stp_cli.registry import COMMANDS
from ai_stp_contracts.cli_copy import (
    COMPONENT_NEXT_STEP,
    DISTRIBUTION,
    INSTALL_CLI,
    LOGIN,
    REGISTRY_SHOW,
    REGISTRY_VERSION,
    SETUP_NEXT_STEP,
    login,
    owner_component_next_step,
    owner_setup_next_step,
    registry_show,
    registry_version,
    select_impact,
)

SAMPLE_COMPONENT = "component_01KZWSHE3V0T8KVJYFEKWJV63Y"
SAMPLE_SETUP = "setup_01KZWSHE3V0T8KVJYFEKWJV63Z"

RENDERED: tuple[str, ...] = (
    registry_show("component", SAMPLE_COMPONENT),
    registry_show("setup", SAMPLE_SETUP),
    registry_version("component", SAMPLE_COMPONENT, "1.0"),
    registry_version("setup", SAMPLE_SETUP, "2.13"),
    select_impact(SAMPLE_SETUP, "1.0"),
    owner_component_next_step(),
    owner_setup_next_step(),
    login("google"),
    login("github"),
)


def _declared() -> dict[str, set[str]]:
    """Command name to the option names it declares."""
    return {
        command.name: {parameter.name for parameter in command.descriptor.parameters}
        for command in COMMANDS
    }


@pytest.mark.parametrize("rendered", RENDERED)
def test_a_copy_template_names_a_command_that_exists(rendered: str) -> None:
    program, *argv = rendered.split(" ")
    assert program == "ai-stp", rendered

    words = [item for item in argv if not item.startswith("--")]
    options = {item.removeprefix("--") for item in argv if item.startswith("--")}

    declared = _declared()
    # The longest leading run of words that names a command; the rest are values.
    name = next(
        (
            candidate
            for length in range(len(words), 0, -1)
            if (candidate := " ".join(words[:length])) in declared
        ),
        None,
    )
    assert name is not None, f"no command is named by {rendered!r}"
    unknown = options - declared[name]
    assert not unknown, f"{rendered!r} passes options {name} does not declare: {sorted(unknown)}"


@pytest.mark.parametrize("rendered", RENDERED)
def test_a_copy_template_supplies_every_required_option(rendered: str) -> None:
    _program, *argv = rendered.split(" ")
    words = [item for item in argv if not item.startswith("--")]
    options = {item.removeprefix("--") for item in argv if item.startswith("--")}

    for command in COMMANDS:
        if command.name != " ".join(words[: len(command.name.split(" "))]):
            continue
        required = {
            parameter.name for parameter in command.descriptor.parameters if parameter.required
        }
        assert not required - options, (
            f"{rendered!r} omits required options: {sorted(required - options)}"
        )
        return


def test_a_copy_template_carries_no_path_or_secret() -> None:
    # `cli-copy-templates.md`: paths and tokens are never substituted into a UI
    # command. A rendered template is copied verbatim by a browser, so anything
    # machine-specific in it is both wrong elsewhere and a disclosure here.
    for rendered in RENDERED:
        assert "/" not in rendered, rendered
        assert "\\" not in rendered, rendered
        assert "~" not in rendered, rendered


def test_the_landing_installs_the_distribution_this_project_publishes() -> None:
    # `ai-stp` is the console script; `ai-stp-cli` is the wheel. Installing the
    # script name fetches something this project does not publish.
    assert DISTRIBUTION == "ai-stp-cli"
    assert INSTALL_CLI == "uv tool install " + DISTRIBUTION


_WEB_COPY = Path("apps/web/src/lib/generated/cli-copy.ts")


def _web_source() -> str:
    return _WEB_COPY.read_text(encoding="utf-8")


def _web_constant(name: str) -> str:
    """A plain exported string constant, with `${DISTRIBUTION}` resolved."""
    source = _web_source()
    match = re.search(rf'export const {name} =\s*[`"]([^`"]+)[`"](?: as const)?;', source)
    assert match is not None, f"{_WEB_COPY} exports no {name}"
    value = match.group(1)
    if "${DISTRIBUTION}" in value:
        distribution = re.search(r'export const DISTRIBUTION = "([^"]+)";', source)
        assert distribution is not None, f"{_WEB_COPY} exports no DISTRIBUTION"
        value = value.replace("${DISTRIBUTION}", distribution.group(1))
    return value


def _web_template(function: str) -> str:
    """Read the generated constant used by a copy function."""
    return _web_constant(
        {"registryShow": "REGISTRY_SHOW", "registryVersion": "REGISTRY_VERSION", "login": "LOGIN"}[
            function
        ]
    )


def test_the_web_copy_module_says_exactly_what_the_owner_says() -> None:
    """The lockstep is a test, not a request in a comment.

    The generated web module follows this module, and `SPEC-037` `REQ-3706`
    requires the UI to take command templates from one canonical source. Before
    this test, nothing compared them, and every one of the five
    commands had drifted into something the CLI refuses: `registry show` without
    `--kind`, `ai-stp login`, two `sync` verbs that are not registered commands,
    and an install line naming the console script instead of the distribution.

    Comparing rendered strings rather than files, because the two languages are
    allowed to spell a template differently — what they are not allowed to do is
    render a different command.
    """
    assert _web_constant("DISTRIBUTION") == DISTRIBUTION
    assert _web_constant("INSTALL_CLI") == INSTALL_CLI
    assert _web_constant("COMPONENT_NEXT_STEP") == COMPONENT_NEXT_STEP
    assert _web_constant("SETUP_NEXT_STEP") == SETUP_NEXT_STEP
    assert _web_template("registryShow") == REGISTRY_SHOW
    assert _web_template("registryVersion") == REGISTRY_VERSION
    assert _web_template("login") == LOGIN


def test_every_command_the_web_publishes_is_a_registered_command() -> None:
    """A published command that the CLI does not declare cannot be run.

    This is the half a string comparison cannot catch: both sides could agree on
    a command that does not exist. The registry is the only authority on which
    ones do, and the machine projection publishes these to agents that will not
    read a help page first.
    """
    registered = {command.name for command in COMMANDS}
    published = (
        _web_template("registryShow"),
        _web_template("registryVersion"),
        _web_template("login"),
        _web_constant("COMPONENT_NEXT_STEP"),
        _web_constant("SETUP_NEXT_STEP"),
    )
    for rendered in published:
        words = rendered.removeprefix("ai-stp ").split(" ")
        # The command name is the leading words before the first option.
        name = " ".join(word for word in words if not word.startswith("-") and "{" not in word)
        while name and name not in registered:
            name = " ".join(name.split(" ")[:-1])
        assert name in registered, f"web publishes {rendered!r}, which is not a registered command"
