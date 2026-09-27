"""One authenticated CLI session boundary for cloud command families."""

from ai_stp_cli.cloud import login, session
from ai_stp_cli.cloud.client import login_actions, login_continuations
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.secrets import open_store


def required(purpose: str) -> session.Session:
    """Return a usable session without exposing either bearer credential."""
    store, _warning = open_store()
    held = session.load(store)
    if held is not None and not held.revoked and held.state() == "expired":
        # The access half ages out on the reported expiry; the refresh half
        # lives longer, so an expired session is renewed in place before the
        # caller is sent back through the device flow.
        held = _renewed(held)
    if held is None or held.state() == "expired":
        raise CliFailure(
            "AI_STP_AUTH_REQUIRED",
            "this action requires an authenticated cloud session",
            details={"purpose": purpose},
            next_actions=login_actions(),
            continuations=login_continuations(),
        )
    if held.state() == "revoked":
        # A revoked key cannot sign again, so this is the one refusal where
        # retiring it is the way back rather than a way to lose an identity.
        # An expired session above is a different thing and gets a different
        # answer: the key is healthy, only the session aged out.
        raise CliFailure(
            "AI_STP_DEVICE_REVOKED",
            "this device has been revoked",
            next_actions=["device reset --confirm --json", *login_actions()],
        )
    return held


def _renewed(held: session.Session) -> session.Session:
    """Refresh an expired session in place; re-raise only a revoked device."""
    from ai_stp_cli.application.auth import endpoint

    try:
        return login.renew(endpoint(), held)
    except CliFailure as failure:
        if failure.code == "AI_STP_DEVICE_REVOKED":
            raise
        # Any other renewal failure leaves the session at its true state —
        # expired — which is exactly the AUTH_REQUIRED branch above.
        return held
