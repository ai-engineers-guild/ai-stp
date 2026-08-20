"""`ai-stp device` — the local identity of this installation (issue #73).

Its own group rather than a corner of `auth`, because the two answer different
questions. A device identity is created on first run, offline, and exists
whether or not an account ever does; a session may never exist at all. Folding
them together would make "no account yet" and "no device identity" look the
same, and their next actions differ.
"""

from collections.abc import Mapping

from ai_stp_cli import identity
from ai_stp_cli.answer import Answer, with_warning
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.machine_help import DeviceIdentity


def init(_parameters: Mapping[str, object]) -> Answer[DeviceIdentity]:
    """Create the identity of this installation, or return the one already here.

    Idempotent, and the only command in this group whose job is to create. The
    first run needs no `sudo` and no account: an identity exists whether or not
    anyone ever signs in.
    """
    made, warning = identity.load_or_create()
    return with_warning(made.report(), warning)


def show(_parameters: Mapping[str, object]) -> Answer[DeviceIdentity]:
    """Report the identity, creating nothing.

    This used to mint one, while declaring itself `read` in the registry. That
    made observing an installation change it, and the mutability class an agent
    plans around describe something the command did not do. `SPEC-009` REQ-902
    is explicit that reading does not bring state into existence, so the absence
    of an identity is now an answer rather than a trigger.
    """
    found, warning = identity.current()
    if found is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "this installation has no device identity yet",
            next_actions=["device init --json"],
        )
    return with_warning(found.report(), warning)


def reset(parameters: Mapping[str, object]) -> Answer[DeviceIdentity]:
    """Retire this identity and mint a fresh one.

    `SPEC-002` REQ-207: resuming cloud access needs a new sign-in **and** a new
    key, so neither the identifier nor the key is reused. The retired identifier
    is remembered so it cannot come back, and no local data is touched
    (REQ-205).
    """
    if not parameters.get("confirm"):
        raise CliFailure(
            "AI_STP_USER_DECISION_REQUIRED",
            "resetting the device identity discards its key and cannot be undone",
            details={"command": "device reset"},
            next_actions=["device reset --confirm --json"],
        )
    fresh, warning = identity.reset()
    return with_warning(fresh.report(), warning)
