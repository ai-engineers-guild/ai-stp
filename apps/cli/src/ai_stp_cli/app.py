"""The parser, built from the registry, and the entrypoint (issue #72).

`ADR-0057` keeps Click a thin application layer: it parses arguments and calls a
use case, and it decides nothing about the envelope, the error codes or the exit
status. This module is where that boundary is enforced.

The parser is **constructed from the registry** rather than written beside it.
`#72` requires machine help to come from the actual command registry, and the
canonical Skill is told not to guess flags — both hold only if a command has one
declaration. Two hand-written lists would agree on the day they were written.

Nothing Click does reaches the public contract. Click's own usage text, its exit
status and its help output are all library behaviour; in machine mode each is
replaced by an envelope carrying a registered `AI_STP_*` code. That is why the
group runs with `standalone_mode=False`: Click raises instead of printing and
exiting, and this module decides what the caller actually sees.
"""

import io
import sys
from collections.abc import Mapping, Sequence
from typing import Any, Final

import click
from pydantic import ValidationError

from ai_stp_cli.errors import (
    CliFailure,
    internal_failure,
    invalid_parameters,
    unknown_command,
)
from ai_stp_cli.output import (
    JSON_FLAG,
    new_request_id,
    render_failure,
    render_success,
    wants_machine_mode,
)
from ai_stp_cli.registry import COMMANDS, Command
from ai_stp_contracts.machine_help import CommandParameter

PROGRAM_NAME: Final[str] = "ai-stp"

#: Click prints its own help and exits. That is right for a person and wrong for
#: a machine caller, who asked for exactly one JSON object — so in machine mode
#: the request is answered with a typed error naming the command that does
#: produce a machine-readable registry.
_HELP_FLAGS: Final[frozenset[str]] = frozenset({"--help", "-h"})

#: The Python name Click derives from `--json`.
_JSON_PARAMETER: Final[str] = JSON_FLAG.removeprefix("--")

#: `CommandPath` in the published contract allows at most four segments, so the
#: parser refuses a deeper one rather than dropping it while machine help still
#: advertises it.
MAXIMUM_PATH_DEPTH: Final[int] = 4


def _json_option() -> click.Option:
    """`--json`, accepted at every level so its position never matters.

    Which mode was requested is decided by `wants_machine_mode` reading argv,
    not by this option: an invocation that fails to parse never reaches a
    callback, and that is exactly when a machine caller most needs its envelope.
    The option exists so the flag parses wherever it is written and so it shows
    up in the human help.
    """
    return click.Option(
        [JSON_FLAG],
        is_flag=True,
        default=False,
        help="Emit exactly one JSON envelope on stdout and nothing else.",
    )


def _option_for(parameter: CommandParameter) -> click.Option:
    """One declared parameter, as Click sees it."""
    if parameter.value_type == "boolean":
        # A required flag is unusual and deliberate: `help` exists only to
        # produce the machine registry, so an absent `--agent` is a mistake
        # worth naming rather than a default worth guessing. Click cannot model
        # "required flag", so it is declared optional here and enforced in
        # `_require_declared_flags`, which can raise a registered error code
        # instead of Click's usage text.
        return click.Option(
            [f"--{parameter.name}"], is_flag=True, default=False, help=parameter.summary
        )
    if parameter.choices:
        click_type: click.ParamType[Any] = click.Choice(parameter.choices, case_sensitive=True)
    else:
        click_type = click.INT if parameter.value_type == "integer" else click.STRING
    return click.Option(
        [f"--{parameter.name}"],
        type=click_type,
        required=parameter.required,
        multiple=parameter.repeatable,
        help=parameter.summary,
    )


def _callback_for(command: Command) -> Any:
    def _invoke(**parameters: object) -> None:
        context = click.get_current_context()
        state: Mapping[str, object] = context.find_root().obj or {}
        parameters.pop(_JSON_PARAMETER, None)
        declared = _as_declared(command, parameters)
        _require_declared_flags(command, declared)
        answer = command.handler(declared)
        render_success(
            answer.payload,
            machine=bool(state.get("machine")),
            request_id=str(state.get("request_id") or new_request_id()),
            next_actions=list(command.descriptor.next_actions),
            warnings=list(answer.warnings),
        )

    return _invoke


def _as_declared(command: Command, parameters: Mapping[str, object]) -> Mapping[str, object]:
    """Key the handler's mapping by the names the descriptor declares.

    Click derives its own key from the flag it parsed, so `--plan-digest`
    arrives as `plan_digest`, while `registry.py` — the single owner of the
    name, and the one machine help publishes — calls it `plan-digest`. A
    handler asking for the declared name would find nothing, and finding
    nothing is indistinguishable from the user leaving the option out: the
    command would not fail, it would quietly do something else.

    Translated once, here, so that a hyphen stays a detail of the declaration
    rather than something every handler has to know about its own options.
    """
    renamed = {
        parameter.name.replace("-", "_"): parameter.name
        for parameter in command.descriptor.parameters
    }
    return {renamed.get(name, name): value for name, value in parameters.items()}


def _require_declared_flags(command: Command, parameters: Mapping[str, object]) -> None:
    """Enforce a required boolean, which Click models as a flag that defaults off.

    A confirmation flag is **not** enforced here. Its absence is not a malformed
    command — it is a decision the user has not made — so it carries
    `AI_STP_USER_DECISION_REQUIRED` and exit class 4 rather than a validation
    error and exit class 2. An agent reads those differently: one says "ask the
    user", the other says "you called it wrong". The use case that knows what is
    being confirmed raises it.
    """
    if command.descriptor.confirmation == "explicit_flag":
        return
    for declared in command.descriptor.parameters:
        if declared.value_type != "boolean" or not declared.required:
            continue
        # `_as_declared` already restored the canonical registry spelling, so a
        # hyphenated flag is keyed by that exact name here.
        if not parameters.get(declared.name):
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                f"{command.name} requires --{declared.name}",
                details={"command": command.name},
                next_actions=[f"{command.name} --{declared.name} {JSON_FLAG}"],
            )


def _click_command(command: Command) -> click.Command:
    params: list[click.Parameter] = [
        _option_for(parameter) for parameter in command.descriptor.parameters
    ]
    params.append(_json_option())
    return click.Command(
        name=command.descriptor.path[-1],
        params=params,
        callback=_callback_for(command),
        help=command.descriptor.summary,
    )


def _ignore_root_options(**_parameters: object) -> None:
    """The root group parses `--json` and acts on nothing else."""


def _group(name: str, help_text: str, *, epilog: str | None = None) -> click.Group:
    """An intermediate group.

    It takes `--json` like everything else, so the flag parses wherever it is
    written. Without that, `ai-stp config --json` reports an unknown option
    instead of the missing subcommand it actually is.
    """
    return click.Group(
        name=name,
        params=[_json_option()],
        callback=_ignore_root_options,
        help=help_text,
        epilog=epilog,
    )


def _group_content(path: tuple[str, ...]) -> tuple[str, str | None]:
    if path == ("auth",):
        return (
            "Sign in, inspect or remove the optional cloud session.",
            "\b\nExamples:\n"
            "  ai-stp auth login --provider google\n"
            "  ai-stp auth login --provider github\n"
            "  ai-stp auth complete\n"
            "  ai-stp auth status",
        )
    return f"Commands for {' '.join(path)}.", None


def build_group() -> click.Group:
    """Assemble the whole parser from the registry.

    The walk is recursive over the declared path. `ADR-0057` originally bounded
    it at two levels, on the grounds that a deeper path was untested code
    guarding an unreachable case, and named "the registry needs a deeper path"
    as its revision condition. `passport developer init` met it.

    The bound that remains is the contract's own: `CommandPath` allows at most
    four segments, so a deeper declaration is refused rather than silently
    dropped from the parser while staying visible in machine help.
    """
    root = _group(
        PROGRAM_NAME,
        "Manage AI harness setups through a strict machine contract.",
        epilog=("First run:\n  ai-stp doctor --json\n  ai-stp help --agent --json"),
    )

    for command in sorted(COMMANDS, key=lambda item: item.name):
        path = command.descriptor.path
        if len(path) > MAXIMUM_PATH_DEPTH:
            raise CliFailure(
                "AI_STP_INTERNAL",
                f"command path is deeper than the contract allows: {command.name}",
                details={"depth": str(len(path)), "maximum": str(MAXIMUM_PATH_DEPTH)},
            )
        parent = root
        for index, step in enumerate(path[:-1]):
            existing = parent.commands.get(step)
            if existing is None:
                group_path = tuple(path[: index + 1])
                help_text, epilog = _group_content(group_path)
                child = _group(step, help_text, epilog=epilog)
                parent.add_command(child)
                parent = child
                continue
            if not isinstance(existing, click.Group):
                raise CliFailure(
                    "AI_STP_INTERNAL",
                    f"a command and a group claim the same name: {step}",
                    details={"command": command.name},
                )
            parent = existing
        parent.add_command(_click_command(command))
    return root


def _dispatch(argv: list[str], machine: bool, request_id: str) -> int:
    if machine and _HELP_FLAGS.intersection(argv):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "usage text is not machine readable",
            next_actions=[f"help --agent {JSON_FLAG}"],
        )
    if not [item for item in argv if item != JSON_FLAG] and not machine:
        argv = ["--help"]
    elif not [item for item in argv if item != JSON_FLAG]:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "no command given",
            next_actions=[f"help --agent {JSON_FLAG}"],
        )

    # With `standalone_mode=False` Click returns the status it would otherwise
    # have exited with instead of calling `sys.exit`, and returns the callback's
    # own value when nothing asked to exit. `--help` is the path that produces
    # a status; the handlers return nothing.
    outcome = build_group().main(
        args=argv,
        prog_name=PROGRAM_NAME,
        standalone_mode=False,
        obj={"machine": machine, "request_id": request_id},
    )
    return outcome if isinstance(outcome, int) else 0


def _use_utf8_streams() -> None:
    """Make this CLI's own output encodable wherever it runs.

    Machine mode writes JSON with `ensure_ascii=False` on purpose: a passport
    carries the characters its author wrote rather than their escapes. On a host
    whose standard streams default to a legacy code page — Windows, before UTF-8
    mode became the interpreter default — writing one of those characters raises
    `UnicodeEncodeError`, and the invocation dies inside its own success path
    with an internal failure that says nothing about encoding.

    Measured rather than anticipated: `toolchain profile` exited 70 with
    `AI_STP_INTERNAL` and `details.exception = UnicodeEncodeError` on
    `windows-latest`, while the same command passed on Linux and macOS.

    A stream that is not a text wrapper is left alone. Tests substitute their own
    objects, and reconfiguring something a caller supplied would be this
    function reaching outside what it owns.
    """
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper) and (stream.encoding or "").lower() not in {
            "utf-8",
            "utf8",
        }:
            stream.reconfigure(encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """Run one invocation and return its exit code without exiting the process."""
    _use_utf8_streams()
    arguments = list(sys.argv[1:] if argv is None else argv)
    machine = wants_machine_mode(arguments)
    request_id = new_request_id()

    try:
        return _dispatch(arguments, machine, request_id)
    except CliFailure as failure:
        return render_failure(failure, machine=machine, request_id=request_id)
    except click.Abort:
        return 130
    except click.ClickException as failure:
        # Covers UsageError, which is the one a caller actually hits: an unknown
        # command, an unknown flag, or a missing value.
        return render_failure(
            _click_failure(arguments, failure), machine=machine, request_id=request_id
        )
    except KeyboardInterrupt:
        # Not an internal failure: the user stopped it. 130 is the shell's
        # convention and is outside the contract's own classes on purpose.
        return 130
    except ValidationError as error:
        # A request model refused a value the caller supplied. That is bad
        # input with a field name attached, not an internal fault, and it must
        # not arrive as one.
        return render_failure(invalid_parameters(error), machine=machine, request_id=request_id)
    except Exception as error:
        return render_failure(internal_failure(error), machine=machine, request_id=request_id)


def run() -> None:
    """Console-script entrypoint."""
    raise SystemExit(main())


def _click_failure(arguments: list[str], failure: click.ClickException) -> CliFailure:
    """Turn common auth spelling mistakes into a safe, executable correction."""
    command_words = [item for item in arguments if item != JSON_FLAG]
    if command_words[:1] != ["auth"]:
        return unknown_command(failure.format_message())

    choices = "google or github"
    next_actions = [
        "auth login --provider google --json",
        "auth login --provider github --json",
    ]
    if command_words[:2] == ["auth", "login"]:
        provider_index = (
            command_words.index("--provider") if "--provider" in command_words else None
        )
        if provider_index is not None and provider_index + 1 < len(command_words):
            supplied = command_words[provider_index + 1]
            if supplied not in {"google", "github"}:
                return CliFailure(
                    "AI_STP_VALIDATION_ERROR",
                    f"invalid auth provider; expected {choices}",
                    details={"parameter": "provider", "allowed": "google, github"},
                    next_actions=next_actions,
                )
        return CliFailure(
            "AI_STP_VALIDATION_ERROR",
            f"auth login requires --provider with {choices}",
            details={"parameter": "provider", "allowed": "google, github"},
            next_actions=next_actions,
        )

    if len(command_words) >= 2 and command_words[1] in {"google", "github"}:
        return CliFailure(
            "AI_STP_VALIDATION_ERROR",
            f"auth commands start with 'auth login'; choose {choices}",
            details={"command": "auth login", "allowed": "google, github"},
            next_actions=next_actions,
        )
    return unknown_command(failure.format_message())
