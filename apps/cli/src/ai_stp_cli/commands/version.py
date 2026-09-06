"""`ai-stp version` — which build is running (issue #72)."""

import sys
from collections.abc import Mapping

from ai_stp_cli.answer import Answer
from ai_stp_cli.runtime import cli_version
from ai_stp_contracts.machine_help import VersionReport
from ai_stp_contracts.schemas import current_inventory


def run(_parameters: Mapping[str, object]) -> Answer[VersionReport]:
    """Report the build and the contract versions it speaks.

    The wire major is included because an agent comparing it with a server can
    tell a version mismatch from a missing feature — two problems with different
    next actions.
    """
    inventory = current_inventory()
    return Answer(
        VersionReport(
            cli_version=cli_version(),
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}."
            f"{sys.version_info.micro}",
            standard_family=inventory.standard_family,
            contract_digest=inventory.contract_digest,
        )
    )
