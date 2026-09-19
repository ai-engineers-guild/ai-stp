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
import sqlite3
import sys
from collections.abc import Mapping, Sequence
from typing import Any, Final

import click
from pydantic import ValidationError

from ai_stp_cli.application.inspect import SHIPPED_INTENT_NAMES
from ai_stp_cli.application.inventory import (
    everyday_intent,
    everyday_success_start_intent,
    intent_for_command_prefix,
    is_forbidden_wayback,
    teaches_forbidden_wayback,
)
from ai_stp_cli.application.outcome import (
    envelope_actions,
    intent_start_continuation,
    operation_id_of,
)
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
from ai_stp_foundation.envelope import Continuation, continuation_argv

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
        # Click cannot model a required flag, so every boolean is declared
        # optional here; a declaration that requires one is enforced in
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


def _everyday_success_envelope(
    path: tuple[str, ...],
    mutability: str,
    continuations: list[Continuation],
    actions: list[str],
) -> tuple[list[Continuation], list[str]]:
    """Drop qualify-forbidden success way-back, then attach `task start`.

    A plan that already named `install apply` used to skip rewrite because
    continuations were non-empty. FOLLOW_ACTOR would then type the leaf.
    Terminal apply is still not started again: that would loop.
    """
    kept_continuations = [
        item
        for item in continuations
        if not is_forbidden_wayback(" ".join(continuation_argv(item)))
    ]
    kept_actions = [item for item in actions if not is_forbidden_wayback(item)]
    intent = everyday_success_start_intent(
        path,
        mutability,
        has_continuations=bool(kept_continuations),
    )
    if intent is None:
        return kept_continuations, kept_actions
    start = intent_start_continuation(intent)
    held = " ".join(start.argv)
    return [start], [held, *[item for item in kept_actions if item != held]]


def _callback_for(command: Command) -> Any:
    def _invoke(**parameters: object) -> None:
        context = click.get_current_context()
        state: Mapping[str, object] = context.find_root().obj or {}
        parameters.pop(_JSON_PARAMETER, None)
        declared = _as_declared(command, parameters)
        _require_declared_flags(command, declared)
        answer = command.handler(declared)
        extra_warnings: tuple[str, ...] = ()
        extra_actions: tuple[str, ...] = ()
        try:
            from ai_stp_cli.self_update.service import maybe_notice

            extra_warnings, extra_actions = maybe_notice(
                command.descriptor.path,
                machine=bool(state.get("machine")),
                tty=sys.stdout.isatty(),
            )
        except Exception:
            extra_warnings, extra_actions = (), ()
        continuations, actions = envelope_actions(answer)
        continuations, actions = _everyday_success_envelope(
            tuple(command.descriptor.path),
            command.descriptor.mutability,
            continuations,
            actions,
        )
        for action in extra_actions:
            if action not in actions:
                actions.append(action)
        render_success(
            answer.payload,
            machine=bool(state.get("machine")),
            request_id=str(state.get("request_id") or new_request_id()),
            operation_id=operation_id_of(answer),
            next_actions=actions,
            continuations=continuations,
            warnings=[*answer.warnings, *extra_warnings],
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
                "a required option was not supplied",
                details={"command": command.name, "option": f"--{declared.name}"},
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
        # Path-exact: a wayback token "capabilities" would hide
        # `toolchain harness-capabilities`.
        hidden=is_forbidden_wayback(" ".join(command.descriptor.path))
        or tuple(command.descriptor.path)
        in {
            ("capabilities",),
            ("doctor",),
            ("version",),
            ("install", "recover"),
            ("install", "resume"),
            ("task", "cancel"),
        },
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


#: What each group of commands is for, in one line.
#:
#: `--help` used to answer "Commands for component." — the group name, spelled
#: back. Every leaf is described precisely in `help --agent`, but a caller
#: reaches the group first, and a reader who does not already know what
#: `select` or `target` means learned nothing from the place built to tell
#: them. Repeating the name is not a description; it only looks like one.
_GROUP_SUMMARIES: Final[dict[tuple[str, ...], str]] = {
    ("component", "skill"): "The Agent Skills authoring contract for one package.",
    ("provider", "update"): "Move a harness's provider to the newest released version.",
    ("provider", "reinstall"): "Install one exact provider version into the same path again.",
    ("attestation",): "Sign exact test evidence with this device's key.",
    ("auth",): "Sign in, inspect or remove the optional cloud session.",
    ("component",): "Author and version single components.",
    ("component", "adaptation"): "Add another harness-native projection to one authoring tree.",
    (
        "component",
        "materialize",
    ): "Derive a missing harness adaptation from a pinned component version.",
    (
        "component",
        "portability",
    ): "Record a private local overlay from an explicit portability claim.",
    (
        "component",
        "program",
    ): "Install, invoke and remove a catalog cli component as a shared executable.",
    ("component", "passport"): "Read, enrich and validate a component's passport.",
    ("component", "scaffold"): "Start a new component from a declared layout.",
    ("component", "source"): "Resolve an external source to an exact, checkable identity.",
    ("component", "source", "evidence"): "Recorded proof about an external source, over time.",
    ("component", "template"): "Render a component's declared template.",
    ("component", "version"): "List recorded versions and release the next one.",
    ("config",): "Read and change this installation's settings.",
    ("consent",): "Grant and withdraw consent for unverified candidates.",
    ("contract",): "The coordinated standard family and the other contract axes this build speaks.",
    ("corporate",): "Organization-governed catalog assignments this account can read.",
    (
        "corporate",
        "assignment",
    ): "The winning corporate assignment for one employee and catalog line.",
    ("device",): "This machine's identity in the local registry.",
    ("eval",): "Score a setup against a profile before installing it.",
    ("eval", "component"): "Score every advertised adaptation of one component version.",
    ("harness",): "Install, update and remove the harness program itself.",
    ("grant",): "Share a private object with another account.",
    ("grant", "invitation"): "Invitations offered but not yet accepted.",
    ("github",): "Read selected GitHub repositories through the connected App.",
    ("github", "source"): "Prepare an exact GitHub snapshot for publication.",
    ("install",): "Start the install intent. Expert plan/apply remain for recovery.",
    ("install", "transaction"): "Coordinate one setup across several provider-owned roots.",
    ("link",): "Open the matching page on the web.",
    ("owner",): "What this account has published, as its owner sees it.",
    ("owner", "object"): "One owned object across all of its versions.",
    ("owner", "version"): "One exact owned version.",
    ("passport",): "Passports describing the developer and this device.",
    ("passport", "developer"): "The developer passport this account publishes under.",
    ("passport", "device"): "The passport describing this machine.",
    ("project",): "Look inside a directory: projects, components and their index.",
    ("project", "link"): "Bind one local project to an authoritative remote project.",
    ("project", "link", "plan"): "Plan a project link without changing local or remote state.",
    ("project", "revision"): "Publish and read organization project-ledger revisions.",
    ("project", "sync"): "Plan and apply one explicit project synchronization decision.",
    ("project", "unlink-plan"): "Plan removal of one project link without changing state.",
    ("provider",): "Inspect the setup manager that writes the harness.",
    ("publication",): "Start the publish intent. Expert plan/confirm remain for recovery.",
    ("registry",): "Inspect catalog identity. Everyday bytes go through the install intent.",
    ("registry", "port"): "Import a setup captured elsewhere into this registry.",
    ("report",): "Report an object to the catalogue's moderators.",
    ("select",): "Everyday composition is the install intent.",
    ("setup",): "Whole setups: change, install, or recover a preserved copy.",
    ("setup", "compose"): "Freeze a new setup from catalog and embedded sources.",
    ("setup", "recast"): "Record a complete setup for another harness with provenance.",
    ("setup", "export"): "Write a review tree of one recorded local setup.",
    ("setup", "import"): "Bring an existing configuration in as a setup.",
    ("setup", "preserve"): "Save a complete native setup and recover its identity.",
    ("publication", "visibility"): "Plan and explicitly confirm owner distribution access changes.",
    ("setup", "preserved"): "Find saved native setups and verify their recovery state.",
    ("setup", "restore"): "Return to a saved setup after preserving the current configuration.",
    ("environment",): "Coordinate separate harness setups for one project.",
    ("setup", "publish"): "Publish a setup together with the components it pins.",
    ("setup", "scaffold"): "Start a new setup from a declared harness layout.",
    ("setup", "update"): "Replace one embedded component with a confirmed exact snapshot.",
    ("skill",): "Install this CLI's own agent skill into a harness.",
    ("sync",): "Explicit account sync after the account intent.",
    ("target",): "The installed state on a harness: status, drift, backups, rollback.",
    ("task",): "Start, continue, inspect, and cancel a durable agent task.",
    ("telemetry",): "The anonymous install ping, and whether it is on.",
    ("toolchain",): "Harnesses this machine can reach, and the tools they need.",
    ("update",): "Check, plan and apply a replacement of this CLI distribution.",
}

#: Groups worth showing by example rather than by sentence alone.
_GROUP_EXAMPLES: Final[dict[tuple[str, ...], tuple[str, ...]]] = {
    ("auth",): ("ai-stp task start --intent account --idempotency-key account-session-01 --json",),
    ("install",): (
        "ai-stp task start --intent install --idempotency-key install-session-01 --json",
    ),
    ("publication",): (
        "ai-stp task start --intent publish --idempotency-key publish-session-01 --json",
    ),
    ("select",): (
        "ai-stp task start --intent install --idempotency-key install-session-01 --json",
    ),
    ("component",): (
        "ai-stp task start --intent author --idempotency-key author-session-01 --json",
    ),
    ("setup", "compose"): (
        "ai-stp task start --intent change --idempotency-key change-session-01 --json",
    ),
    ("config",): (
        "ai-stp task start --intent initialize --idempotency-key initialize-session-01 --json",
    ),
    ("setup",): (
        "ai-stp task start --intent change --idempotency-key change-session-01 --json",
        "ai-stp task start --intent install --idempotency-key install-session-01 --json",
    ),
    ("eval",): ("ai-stp task intents --json",),
    ("environment",): (
        "ai-stp task start --intent install --idempotency-key install-session-01 --json",
    ),
    ("install", "transaction"): (
        "ai-stp task start --intent install --idempotency-key install-session-01 --json",
    ),
    ("setup", "preserve"): (
        "ai-stp task start --intent switch --idempotency-key switch-session-01 --json",
    ),
    ("setup", "preserved"): (
        "ai-stp task start --intent switch --idempotency-key switch-session-01 --json",
    ),
    ("project", "link"): (
        "ai-stp task start --intent install --idempotency-key install-session-01 --json",
    ),
    ("update",): ("ai-stp task intents --json",),
    ("provider",): ("ai-stp task intents --json",),
    ("publication", "visibility"): (
        "ai-stp task start --intent publish --idempotency-key publish-session-01 --json",
    ),
    ("setup", "publish"): (
        "ai-stp task start --intent publish --idempotency-key publish-session-01 --json",
    ),
    ("registry",): (
        "ai-stp task start --intent install --idempotency-key install-session-01 --json",
    ),
    ("sync",): ("ai-stp task start --intent account --idempotency-key account-session-01 --json",),
    ("target",): (
        "ai-stp task start --intent inspect --idempotency-key inspect-session-01 --json",
        "ai-stp task start --intent switch --idempotency-key switch-session-01 --json",
    ),
    ("project",): (
        "ai-stp task start --intent inspect --idempotency-key inspect-session-01 --json",
        "ai-stp task start --intent install --idempotency-key install-session-01 --json",
    ),
}


def _group_content(path: tuple[str, ...]) -> tuple[str, str | None]:
    summary = _GROUP_SUMMARIES.get(path)
    if summary is None:  # pragma: no cover — a new group without a line fails a test
        summary = f"Commands for {' '.join(path)}."
    examples = _GROUP_EXAMPLES.get(path)
    if examples is None:
        return summary, None
    return summary, "\b\nExamples:\n" + "\n".join(f"  {line}" for line in examples)


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
        epilog=("First run:\n  ai-stp task intents --json"),
    )

    for command in sorted(COMMANDS, key=lambda item: item.name):
        path = command.descriptor.path
        if len(path) > MAXIMUM_PATH_DEPTH:
            raise CliFailure(
                "AI_STP_INTERNAL",
                "command path is deeper than the contract allows",
                details={
                    "command": command.name,
                    "depth": str(len(path)),
                    "maximum": str(MAXIMUM_PATH_DEPTH),
                },
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
                    "a command and a group claim the same name",
                    details={"command": command.name, "name": step},
                )
            parent = existing
        parent.add_command(_click_command(command))
    _hide_groups_without_visible_commands(root)
    return root


def _hide_groups_without_visible_commands(group: click.Group) -> None:
    """Drop drained choreography groups from human `--help`.

    `setup compose` only exists so plan/apply stay invokable. Once those
    leaves are `hidden`, the empty group still taught `compose` on
    `setup --help`. Recurse first so a parent that only held such groups
    also hides. The root stays listed even if a future drain emptied it.
    """
    for command in group.commands.values():
        if isinstance(command, click.Group):
            _hide_groups_without_visible_commands(command)
    if group.name == PROGRAM_NAME:
        return
    if any(not command.hidden for command in group.commands.values()):
        return
    if group.commands:
        group.hidden = True


def _valued_options(argv: list[str]) -> frozenset[str]:
    """The options of the named command that consume the token after them.

    Read from the registry rather than guessed: which spellings take a value is
    exactly what decides whether the next token is a flag or an opaque value,
    and the declarations already say so.
    """
    for command in sorted(COMMANDS, key=lambda item: len(item.descriptor.path), reverse=True):
        path = command.descriptor.path
        if argv[: len(path)] == path:
            return frozenset(
                f"--{parameter.name}"
                for parameter in command.descriptor.parameters
                if parameter.value_type != "boolean"
            )
    return frozenset()


def _help_requested(argv: list[str]) -> bool:
    """Whether help was asked for, as syntax rather than as a matching string.

    `--help` anywhere in argv used to count. But

        ai-stp component program invoke --id X --arg --help --json

    is an agent asking an installed program to describe itself: the second
    token is an opaque value this CLI forwards, and reading it as a request for
    usage refused exactly the call that learns what a tool can do. A value is a
    value wherever it appears, and everything after `--` is operand text.
    """
    # The machine flag is accepted at every level, so it may sit before the
    # command; the path is what the tokens say once it is set aside.
    valued = _valued_options([token for token in argv if token != JSON_FLAG])
    expecting = False
    for token in argv:
        if expecting:
            expecting = False
            continue
        if token == "--":
            return False
        if token in _HELP_FLAGS:
            return True
        expecting = token in valued
    return False


def _dispatch(argv: list[str], machine: bool, request_id: str) -> int:
    if machine and _help_requested(argv):
        raise unknown_command("usage text is not machine readable")
    if not [item for item in argv if item != JSON_FLAG] and not machine:
        argv = ["--help"]
    elif not [item for item in argv if item != JSON_FLAG]:
        raise unknown_command("no command given")

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


def _registry_failure(error: sqlite3.DatabaseError) -> CliFailure | None:
    """Translate sqlite's two operator-state shapes; leave the rest internal.

    The messages are sqlite's canonical error strings, stable across versions.
    `OperationalError` is a subclass of `DatabaseError`, so a lock that outlived
    the busy timeout arrives here too — that one is retryable, because waiting
    is exactly what resolves it.
    """
    from ai_stp_cli.local.database import configured_path
    from ai_stp_cli.paths import redact_home

    text = str(error).lower()
    place = redact_home(configured_path())
    if "database is locked" in text or "database table is locked" in text:
        return CliFailure(
            "AI_STP_CONFLICT",
            "another process holds the local registry; retry when it finishes",
            retryable=True,
            details={"registry": place},
        )
    if "file is not a database" in text or "database disk image is malformed" in text:
        return CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the local registry file cannot be read as a database",
            details={"registry": place, "reason": type(error).__name__},
        )
    return None


def main(argv: Sequence[str] | None = None) -> int:
    """Run one invocation and return its exit code without exiting the process."""
    _use_utf8_streams()
    arguments = list(sys.argv[1:] if argv is None else argv)
    machine = wants_machine_mode(arguments)
    request_id = new_request_id()

    try:
        return _dispatch(arguments, machine, request_id)
    except CliFailure as failure:
        return render_failure(
            _handler_covered_leaf_failure(arguments, failure),
            machine=machine,
            request_id=request_id,
        )
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
    except sqlite3.DatabaseError as error:
        # A damaged or contended registry is the operator's state, not our
        # bug: a truncated file used to answer `AI_STP_INTERNAL` with no file
        # named and nothing saying local state (not the tool) is at fault.
        # Only sqlite's own two shapes are translated; everything else stays
        # an internal fault, because it is one.
        translated = _registry_failure(error)
        if translated is None:
            return render_failure(internal_failure(error), machine=machine, request_id=request_id)
        return render_failure(translated, machine=machine, request_id=request_id)
    except Exception as error:
        return render_failure(internal_failure(error), machine=machine, request_id=request_id)


def run() -> None:
    """Console-script entrypoint."""
    raise SystemExit(main())


def _auth_providers() -> tuple[str, ...]:
    """The providers `auth login` declares, read from the one place they live.

    Restating `google, github` here would be a second copy of a closed
    vocabulary that `registry.py` already owns — the same duplication the
    registry exists to prevent.
    """
    for command in COMMANDS:
        if command.descriptor.path == ["auth", "login"]:
            for parameter in command.descriptor.parameters:
                if parameter.name == "provider":
                    return tuple(parameter.choices)
    return ()  # pragma: no cover — `auth login` is a declared command


def _option_value(command_words: Sequence[str], name: str) -> str | None:
    """The value written for `--name`, in either spelling Click accepts."""
    flag = f"--{name}"
    prefix = f"--{name}="
    for index, word in enumerate(command_words):
        if word.startswith(prefix):
            return word.split("=", 1)[1]
        if word == flag and index + 1 < len(command_words):
            return command_words[index + 1]
    return None


def _supplied_provider(command_words: list[str]) -> str | None:
    """The value written for `--provider`, in either spelling Click accepts.

    `--provider=google` is one token. Looking for the literal `--provider` found
    nothing there and answered "auth login requires --provider" for a call that
    supplied one correctly — sending the caller to edit the one argument that
    was right while `--bogus`, the actual failure, went unmentioned.
    """
    return _option_value(command_words, "provider")


INCOMPLETE_GROUP_MESSAGE: Final[str] = "incomplete command group; list shipped intents"


def _is_click_usage(message: str) -> bool:
    """Click group help lists expert leaves. That dump is not a machine error."""
    held = message.strip()
    if held in {"Missing command.", "Missing command"}:
        return True
    if held.startswith("Usage:") or "\nCommands:\n" in message:
        return True
    return held.endswith("Missing command.") or held.endswith("Missing command")


def _leading_words(arguments: Sequence[str]) -> list[str]:
    return [item for item in arguments if item != JSON_FLAG and not item.startswith("-")]


def _declared_path(words: Sequence[str]) -> tuple[str, ...] | None:
    declared = {tuple(command.descriptor.path) for command in COMMANDS}
    for length in range(len(words), 0, -1):
        candidate = tuple(words[:length])
        if candidate in declared:
            return candidate
    return None


def _intent_for_group(words: Sequence[str]) -> str | None:
    if _declared_path(words) is not None:
        return None
    intent = intent_for_command_prefix(words)
    if intent is not None:
        return intent
    if words and words[0] in SHIPPED_INTENT_NAMES:
        return words[0]
    return None


def _covered_leaf_intent(arguments: Sequence[str]) -> str | None:
    command_words = [item for item in arguments if item != JSON_FLAG]
    words = _leading_words(command_words)
    if _option_value(command_words, "action") in {"backup", "rollback"}:
        return None
    if words[:2] == ["auth", "login"] and _supplied_provider(command_words) in _auth_providers():
        return None
    path = _declared_path(words)
    if path is None:
        return None
    return everyday_intent(path)


def _handler_covered_leaf_failure(arguments: list[str], failure: CliFailure) -> CliFailure:
    """A bare `install plan --json` used to teach `--proposal`."""
    if failure.code == "AI_STP_VALIDATION_ERROR":
        command_words = [item for item in arguments if item != JSON_FLAG]
        if not any(item.startswith("-") for item in command_words):
            intent = _covered_leaf_intent(arguments)
            if intent is not None:
                return _intent_start_failure(intent)
    return _rewrite_everyday_wayback(arguments, failure)


def _rewrite_everyday_wayback(arguments: list[str], failure: CliFailure) -> CliFailure:
    """Extra flags used to keep `install plan --proposal` on the envelope."""
    intent = _covered_leaf_intent(arguments)
    if intent is None:
        return failure
    empty = not failure.continuations and not failure.next_actions
    if not teaches_forbidden_wayback(failure.next_actions) and not empty:
        return failure
    start = intent_start_continuation(intent)
    held = " ".join(start.argv)
    kept = [item for item in failure.next_actions if not is_forbidden_wayback(item)]
    actions = [held, *[item for item in kept if item != held]]
    continuations = list(failure.continuations) or [start]
    return CliFailure(
        failure.code,
        failure.message,
        retryable=failure.retryable,
        details=dict(failure.details),
        operation_id=failure.operation_id,
        next_actions=actions,
        continuations=continuations,
    )


def _intent_start_failure(intent: str) -> CliFailure:
    continuation = intent_start_continuation(intent)
    return CliFailure(
        "AI_STP_VALIDATION_ERROR",
        "this group is a task intent; start it through the task engine",
        details={"intent": intent},
        continuations=[continuation],
        next_actions=[" ".join(continuation.argv)],
    )


def _missing_start_key_failure(command_words: Sequence[str], message: str) -> CliFailure | None:
    """A known intent without the key is still that start, not a registry dump."""
    if "Missing option '--idempotency-key'" not in message:
        return None
    if _declared_path(_leading_words(command_words)) != ("task", "start"):
        return None
    held = _option_value(command_words, "intent")
    if held not in SHIPPED_INTENT_NAMES:
        return None
    start = _intent_start_failure(held)
    return CliFailure(
        start.code,
        "task start needs an idempotency key",
        details=start.details,
        continuations=start.continuations,
        next_actions=start.next_actions,
    )


def _missing_answer_task_failure(
    command_words: Sequence[str], words: Sequence[str], message: str
) -> CliFailure | None:
    """A named or unique blocked question is still that answer, not a dump."""
    if tuple(words[:2]) not in {("task", "answer"), ("task", "continue")}:
        return None
    from ai_stp_cli.application.task import missing_answer_hint

    if "Missing option '--task'" in message:
        return missing_answer_hint()
    if "Missing option '--revision'" in message:
        held = _option_value(command_words, "task")
        if held is None:
            return None
        return missing_answer_hint(task_id=held)
    return None


def _task_intents_failure(message: str) -> CliFailure:
    continuation = Continuation(
        kind="inspect",
        path=["task", "intents"],
        argv=["task", "intents", "--json"],
        actor="cli",
    )
    return CliFailure(
        "AI_STP_VALIDATION_ERROR",
        message,
        continuations=[continuation],
        next_actions=["task intents --json"],
    )


def _invented_task_verb_failure() -> CliFailure:
    return _task_intents_failure(
        "the task engine verbs are start, answer, continue, status, and cancel"
    )


def _start_intent_parse_failure(command_words: Sequence[str], message: str) -> CliFailure | None:
    """A start without a shipped intent lists the catalog, not Click's choice dump."""
    if _declared_path(_leading_words(command_words)) != ("task", "start"):
        return None
    if "Missing option '--intent'" in message or (
        "--intent" in message and "requires an argument" in message
    ):
        return _task_intents_failure("task start needs an intent")
    if "Invalid value" in message and "--intent" in message:
        held = _option_value(command_words, "intent")
        if not held or held.startswith("-"):
            return _task_intents_failure("task start needs an intent")
        return _task_intents_failure("the task intent is not supported")
    return None


def _click_failure(arguments: list[str], failure: click.ClickException) -> CliFailure:
    """Turn parse failures into a safe, executable correction.

    A group that a shipped intent already drains must not teach its expert
    leaves. `install --json` used to answer "Missing command" and point at
    `help --agent`, which is how a weak model learned `install plan`.

    A `task_covered` leaf with missing flags is the same start. `auth login
    --json` used to list `--provider google|github`. A declared `auth login`
    that already has a supported `--provider` and fails for another flag
    keeps Click's subject, so

        ai-stp auth login --provider google --bogus --json

    still names `--bogus`. Backup and rollback `--action` stay expert recovery.
    """
    command_words = [item for item in arguments if item != JSON_FLAG]
    intent = _intent_for_group(_leading_words(command_words))
    if intent is not None:
        return _intent_start_failure(intent)
    words = _leading_words(command_words)
    if words[:1] == ["task"] and _declared_path(words) is None:
        return _invented_task_verb_failure()
    missing_intent = _start_intent_parse_failure(command_words, failure.format_message())
    if missing_intent is not None:
        return missing_intent
    missing_key = _missing_start_key_failure(command_words, failure.format_message())
    if missing_key is not None:
        return missing_key
    missing_answer = _missing_answer_task_failure(command_words, words, failure.format_message())
    if missing_answer is not None:
        return missing_answer
    detail = failure.format_message()
    covered = _covered_leaf_intent(arguments)
    if covered is not None:
        return _intent_start_failure(covered)
    if _is_click_usage(detail):
        detail = INCOMPLETE_GROUP_MESSAGE
    return unknown_command(detail)
