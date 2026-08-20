"""One authenticated CLI session boundary for cloud command families."""

from ai_stp_cli.cloud import session
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.secrets import open_store


def required(purpose: str) -> session.Session:
    """Return a usable session without exposing either bearer credential."""
    store, _warning = open_store()
    held = session.load(store)
    if held is None or held.state() == "expired":
        raise CliFailure(
            "AI_STP_AUTH_REQUIRED",
            f"{purpose} requires an authenticated cloud session",
            next_actions=["auth login --provider github --json"],
        )
    if held.state() == "revoked":
        raise CliFailure(
            "AI_STP_DEVICE_REVOKED",
            "this device has been revoked",
            next_actions=["device reset --confirm --json", "auth login --provider github --json"],
        )
    return held
