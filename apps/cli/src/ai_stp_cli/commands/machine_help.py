"""The introspection commands (issue #72, docs/agent/machine-help.md).

They answer different questions on purpose. `capabilities` reports versions,
supported harnesses, whether the catalogue and sync are on, and every
`command_path`. Durable journeys start at `task intents`; `help --agent`
remains the full registry and is larger; `schema` resolves the schema URNs
every other payload names. All introspection responses read the same registry
and model map, so they cannot disagree about which commands or schemas exist.
"""

from collections.abc import Mapping
from typing import cast

from ai_stp_cli.answer import Answer
from ai_stp_cli.application.inventory import MIXED_HELP_PREFIXES, intent_for_command_prefix
from ai_stp_cli.application.outcome import intent_start_continuation
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.runtime import cli_version
from ai_stp_contracts.machine_help import (
    Capabilities,
    CliSchemaDocument,
    CliSchemaEntry,
    CliSchemaIndex,
    CommandDescriptor,
    MachineErrorDescriptor,
    MachineHelp,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.envelope import Continuation
from ai_stp_foundation.errors import ERROR_CODES


def _intents_continuation() -> Continuation:
    return Continuation(
        kind="inspect",
        path=["task", "intents"],
        argv=["task", "intents", "--json"],
        actor="cli",
    )


def _scoped(commands: list[CommandDescriptor], requested: object) -> list[CommandDescriptor]:
    """Every command under one path, or all of them when none is named."""
    wanted = str(requested or "").split()
    if not wanted:
        return commands
    kept = [command for command in commands if command.path[: len(wanted)] == wanted]
    if not kept:
        continuation = _intents_continuation()
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no command lives under that path",
            details={"path": " ".join(wanted)},
            continuations=[continuation],
            next_actions=["task intents --json"],
        )
    return kept


def _found(commands: list[CommandDescriptor], requested: object) -> list[CommandDescriptor]:
    """Commands whose path or summary mentions the needle, or all without one.

    A no-match is a refusal, not an empty list: `commands` is declared
    non-empty, so an honest miss is an error rather than a malformed payload.
    """
    needle = str(requested or "").strip().lower()
    if not needle:
        return commands
    kept = [
        command
        for command in commands
        if needle in " ".join(command.path).lower() or needle in command.summary.lower()
    ]
    if not kept:
        continuation = _intents_continuation()
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no command mentions that text",
            details={"find": needle},
            continuations=[continuation],
            next_actions=["task intents --json"],
        )
    return kept


def capabilities(_parameters: Mapping[str, object]) -> Answer[Capabilities]:
    """Report what this installation can do right now."""
    from ai_stp_cli.application.inspect import capabilities as inspect_capabilities

    return Answer(inspect_capabilities())


def registry(parameters: Mapping[str, object]) -> Answer[MachineHelp]:
    """Emit the command registry, whole or scoped to one family.

    `--agent` names the caller and is accepted with or without: this command
    has exactly one answer, and refusing to give it until the caller repeated
    the command's only meaning was a stop with nothing behind it.

    `--path` narrows it. The full registry is every command this build offers,
    and an agent that needs `project sync apply` does not need the other two
    hundred descriptors to construct it — reading them all is work it has to do
    again on every task, and the relevance judgement is exactly what a bounded
    answer removes. The scope is a command path because that is what the
    registry already owns; an intent vocabulary would be a second registry to
    keep in step with this one. Either way the answer names the build it
    describes, so a scoped read and a full one stay comparable.

    An unscoped dump still carries a `task intents` continuation so a caller
    that landed here by habit is steered back to the everyday catalog. A scoped
    dump of a family a shipped intent already drains carries that start. Mixed
    families that are not 1:1 with an intent list `task intents`.

    `--find` filters within the `--path` scope by a text match against the
    command path and summary, so an agent that does not know the family name
    can reach the same descriptors without dumping the whole registry.
    """
    from ai_stp_cli.registry import GLOBAL_OPTIONS, descriptors, registry_digest

    payload = MachineHelp(
        cli_version=cli_version(),
        registry_digest=registry_digest(),
        global_options=list(GLOBAL_OPTIONS),
        commands=_found(
            _scoped(descriptors(), parameters.get("path")),
            parameters.get("find"),
        ),
        error_codes=[
            MachineErrorDescriptor(
                code=code,
                exit_class=entry.exit_class,
                handling=entry.handling,
                description=entry.description,
            )
            for code, entry in sorted(ERROR_CODES.items())
        ],
    )
    path = parameters.get("path")
    if not path:
        return Answer(payload, continuations=(_intents_continuation(),))
    words = str(path).split()
    intent = intent_for_command_prefix(words)
    if intent is not None:
        return Answer(payload, continuations=(intent_start_continuation(intent),))
    if words and words[0] in MIXED_HELP_PREFIXES:
        return Answer(payload, continuations=(_intents_continuation(),))
    return Answer(payload)


def schema_list(_parameters: Mapping[str, object]) -> Answer[CliSchemaIndex]:
    """Every exported schema id this build resolves.

    The same `EXPORTED_MODELS` map the generated `schemas/v1` files are written
    from, read at runtime — so the index can name a schema that has no file
    drift, and `schema show` answers the same document the gate publishes.
    """
    from ai_stp_contracts.schemas import EXPORTED_MODELS
    from ai_stp_foundation.schemas import schema_id

    return Answer(
        CliSchemaIndex(
            cli_version=cli_version(),
            schemas=[
                CliSchemaEntry(name=name, urn=schema_id(name)) for name in sorted(EXPORTED_MODELS)
            ],
        )
    )


def schema_show(parameters: Mapping[str, object]) -> Answer[CliSchemaDocument]:
    """Resolve one schema id to its JSON Schema document.

    `--id` accepts the bare name (`cli-task-input-install`), the full URN an
    `input_schema` or `result_schema` member carries, or the generated file
    name. Anything else is refused rather than guessed at — an agent that got
    a near-miss id is told so, with the index one continuation away.
    """
    from ai_stp_contracts.schemas import EXPORTED_MODELS
    from ai_stp_foundation.schemas import schema_id

    requested = str(parameters.get("id") or "")
    name = requested.removeprefix("urn:ai-stp:schema:v1:").removesuffix(".schema.json")
    model = EXPORTED_MODELS.get(name)
    if model is None:
        continuation = Continuation(
            kind="inspect",
            path=["schema", "list"],
            argv=["schema", "list", "--json"],
            actor="cli",
        )
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no exported schema has that id",
            details={"id": requested},
            continuations=[continuation],
            next_actions=["schema list --json"],
        )
    document = model if isinstance(model, dict) else model.model_json_schema()
    return Answer(
        CliSchemaDocument(
            cli_version=cli_version(),
            name=name,
            urn=schema_id(name),
            document=cast(dict[str, JsonValue], document),
        )
    )
