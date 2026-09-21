"""`ai-stp auth status` — the platform relationship of this installation (#73, #75).

Local only: it reads what is stored and never asks the platform. Four states,
because their repairs differ — `expired` is fixed by signing in again, `revoked`
needs a new device key too, and `local_only` is not a fault at all.
"""

from collections.abc import Mapping

from ai_stp_cli.answer import Answer
from ai_stp_cli.cloud import session
from ai_stp_cli.secrets import open_store
from ai_stp_contracts.machine_help import AuthStatus


def run(_parameters: Mapping[str, object]) -> Answer[AuthStatus]:
    """Report the session this installation holds, if it holds one.

    `local_only` while a pending authorization sits in the store reads as
    "nothing is going on" — the state set is closed, so the pending record is
    named as a warning instead of a fifth state (#359).
    """
    report, warning = session.status()
    store, store_warning = open_store()
    warnings = [item for item in (warning, store_warning) if item is not None]
    if session.load_pending(store) is not None:
        warnings.append("a sign-in is waiting for approval; auth complete --json finishes it")
    return Answer(report, warnings=tuple(warnings))
