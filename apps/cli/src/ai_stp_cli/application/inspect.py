"""Cheap local inspection. Expert `capabilities` and a later task start share this."""

from ai_stp_cli.config import catalog_and_sync_enabled
from ai_stp_cli.local.database import SCHEMA_VERSION
from ai_stp_cli.runtime import cli_version, installation
from ai_stp_contracts.machine_help import Capabilities
from ai_stp_foundation.harnesses import HARNESS_IDS


def capabilities() -> Capabilities:
    """What this process can do right now, without a registry dump."""
    from ai_stp_cli.registry import command_paths, registry_digest

    catalog_enabled, sync_enabled = catalog_and_sync_enabled()
    return Capabilities(
        cli_version=cli_version(),
        installation=installation(),
        registry_digest=registry_digest(),
        local_schema_version=SCHEMA_VERSION,
        supported_harnesses=sorted(HARNESS_IDS),
        catalog_enabled=catalog_enabled,
        sync_enabled=sync_enabled,
        command_paths=command_paths(),
    )
