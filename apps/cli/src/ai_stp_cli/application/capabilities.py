"""What this installation can do right now (`capabilities --json`).

Apart from `inspect` on purpose: an agent probes this before anything else,
and the doctor checks and task-intent models that module imports cost the
probe about 0.3s it never used (docs/engineering/cli-performance.md).
"""

from ai_stp_cli import config
from ai_stp_cli.local import database
from ai_stp_cli.runtime import cli_version, installation
from ai_stp_contracts.cli.registry import Capabilities
from ai_stp_foundation.harnesses import HARNESS_IDS


def capabilities() -> Capabilities:
    """What this process can do right now, without a registry dump."""
    from ai_stp_cli.application.inventory import classified_paths, classify, expert_reason
    from ai_stp_cli.application.qualify import report
    from ai_stp_cli.registry import command_paths, registry_digest

    classified_paths()
    for path in (tuple(item.split()) for item in command_paths()):
        if classify(path) == "expert":
            expert_reason(path)
    report()
    catalog_enabled, sync_enabled = config.catalog_and_sync_enabled()
    return Capabilities(
        cli_version=cli_version(),
        installation=installation(),
        registry_digest=registry_digest(),
        local_schema_version=database.SCHEMA_VERSION,
        supported_harnesses=sorted(HARNESS_IDS),
        catalog_enabled=catalog_enabled,
        sync_enabled=sync_enabled,
        command_paths=command_paths(),
    )
