"""The two introspection commands (issue #72, docs/agent/machine-help.md).

They answer different questions on purpose. `capabilities` is a cheap optional
orientation call — versions, supported harnesses, whether the catalogue and
sync are on. The canonical Skill starts with `doctor` and `help --agent`; the
latter is the full registry and is larger. Both introspection responses read the
same registry, so they cannot disagree about which commands exist.
"""

from collections.abc import Mapping

from ai_stp_cli.answer import Answer
from ai_stp_cli.config import catalog_and_sync_enabled
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local.database import SCHEMA_VERSION
from ai_stp_cli.runtime import cli_version, installation
from ai_stp_contracts.machine_help import (
    Capabilities,
    CommandDescriptor,
    MachineErrorDescriptor,
    MachineHelp,
)
from ai_stp_foundation.errors import ERROR_CODES
from ai_stp_foundation.harnesses import HARNESS_IDS


def _scoped(commands: list[CommandDescriptor], requested: object) -> list[CommandDescriptor]:
    """Every command under one path, or all of them when none is named."""
    wanted = str(requested or "").split()
    if not wanted:
        return commands
    kept = [command for command in commands if command.path[: len(wanted)] == wanted]
    if not kept:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no command lives under that path",
            details={"path": " ".join(wanted)},
            next_actions=["capabilities --json", "help --agent --json"],
        )
    return kept


def capabilities(_parameters: Mapping[str, object]) -> Answer[Capabilities]:
    """Report what this installation can do right now."""
    from ai_stp_cli.registry import command_paths, registry_digest

    catalog_enabled, sync_enabled = catalog_and_sync_enabled()
    return Answer(
        Capabilities(
            cli_version=cli_version(),
            installation=installation(),
            registry_digest=registry_digest(),
            local_schema_version=SCHEMA_VERSION,
            supported_harnesses=sorted(HARNESS_IDS),
            catalog_enabled=catalog_enabled,
            sync_enabled=sync_enabled,
            command_paths=command_paths(),
        )
    )


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
    """
    from ai_stp_cli.registry import GLOBAL_OPTIONS, descriptors, registry_digest

    return Answer(
        MachineHelp(
            cli_version=cli_version(),
            registry_digest=registry_digest(),
            global_options=list(GLOBAL_OPTIONS),
            commands=_scoped(descriptors(), parameters.get("path")),
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
    )
