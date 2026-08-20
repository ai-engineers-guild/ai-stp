"""`ai-stp auth status` — the platform relationship of this installation (#73, #75).

Local only: it reads what is stored and never asks the platform. Four states,
because their repairs differ — `expired` is fixed by signing in again, `revoked`
needs a new device key too, and `local_only` is not a fault at all.
"""

from collections.abc import Mapping

from ai_stp_cli.answer import Answer, with_warning
from ai_stp_cli.cloud import session
from ai_stp_contracts.machine_help import AuthStatus


def run(_parameters: Mapping[str, object]) -> Answer[AuthStatus]:
    """Report the session this installation holds, if it holds one."""
    report, warning = session.status()
    return with_warning(report, warning)
