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
from ai_stp_cli.runtime import cli_version
from ai_stp_contracts.machine_help import Capabilities, MachineErrorDescriptor, MachineHelp
from ai_stp_foundation.errors import ERROR_CODES
from ai_stp_foundation.harnesses import HARNESS_IDS


def capabilities(_parameters: Mapping[str, object]) -> Answer[Capabilities]:
    """Report what this installation can do right now."""
    from ai_stp_cli.registry import command_paths

    catalog_enabled, sync_enabled = catalog_and_sync_enabled()
    return Answer(
        Capabilities(
            cli_version=cli_version(),
            supported_harnesses=sorted(HARNESS_IDS),
            catalog_enabled=catalog_enabled,
            sync_enabled=sync_enabled,
            command_paths=command_paths(),
        )
    )


def registry(_parameters: Mapping[str, object]) -> Answer[MachineHelp]:
    """Emit the full command registry.

    `--agent` is required by the parser rather than optional: this command
    exists only to produce the machine registry — human usage is what `--help`
    is for — and an optional flag that changes nothing would be noise in a
    contract five harness projections read.
    """
    from ai_stp_cli.registry import GLOBAL_OPTIONS, descriptors

    return Answer(
        MachineHelp(
            cli_version=cli_version(),
            global_options=list(GLOBAL_OPTIONS),
            commands=descriptors(),
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
