"""Cloud credentials as this installation holds them (issue #75).

Only the secure store from `ADR-0058` ever sees a token. What lands in ordinary
local state is the safe metadata a caller needs to decide what to do next:
which account, which device, and when the session stops being usable.

The four states in `SPEC-011`'s terms are decided here rather than at each call
site. "Not signed in" and "signed in but expired" lead to different next
actions, and so do "expired" and "the device was revoked" — the first is fixed
by refreshing, the second only by a new sign-in with a new key.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.secrets import SecretStore, load_json, open_store, promote, store_json
from ai_stp_contracts.machine_help import AuthStatus, SessionState
from ai_stp_foundation.timestamps import format_timestamp, parse_timestamp

#: The entry the secure store holds. One entry, one document: a token and the
#: metadata that describes it must not be able to drift apart.
CREDENTIALS_ENTRY: Final[str] = "cloud-credentials"

#: A sign-in that has started and not finished. The device code is the bearer of
#: a pending authorization, so it lives in the credential store like any other
#: secret rather than in ordinary local state.
PENDING_ENTRY: Final[str] = "pending-authorization"

_ACCESS = "access_token"
_REFRESH = "refresh_token"
_ACCOUNT = "account_id"
_DEVICE = "device_id"
_EXPIRES = "expires_at"
_STATE = "state"


@dataclass(frozen=True)
class Session:
    """One held session. The tokens are here; nothing prints them."""

    account_id: str
    device_id: str
    access_token: str
    refresh_token: str
    expires_at: str
    revoked: bool = False

    def state(self, *, now: datetime | None = None) -> SessionState:
        if self.revoked:
            return "revoked"
        moment = now or datetime.now(UTC)
        return "expired" if parse_timestamp(self.expires_at) <= moment else "authenticated"


def expiry(expires_in: int, *, now: datetime | None = None) -> str:
    """When an access token stops being usable, as a contract timestamp."""
    return format_timestamp((now or datetime.now(UTC)) + timedelta(seconds=expires_in))


def load(store: SecretStore) -> Session | None:
    """The held session, or `None` when this installation has none."""
    # A refresh token left in a file after the machine gained a real credential
    # store is the stale-credential defect `ADR-0058` names.
    promote(store, CREDENTIALS_ENTRY)
    document = load_json(store, CREDENTIALS_ENTRY)
    if document is None:
        return None
    missing = [
        name for name in (_ACCESS, _REFRESH, _ACCOUNT, _DEVICE, _EXPIRES) if name not in document
    ]
    if missing:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "stored cloud credentials are incomplete",
            details={"missing": missing[0]},
            next_actions=["auth logout --json"],
        )
    return Session(
        account_id=document[_ACCOUNT],
        device_id=document[_DEVICE],
        access_token=document[_ACCESS],
        refresh_token=document[_REFRESH],
        expires_at=document[_EXPIRES],
        revoked=document.get(_STATE) == "revoked",
    )


def save(store: SecretStore, session: Session) -> None:
    store_json(
        store,
        CREDENTIALS_ENTRY,
        {
            _ACCOUNT: session.account_id,
            _DEVICE: session.device_id,
            _ACCESS: session.access_token,
            _REFRESH: session.refresh_token,
            _EXPIRES: session.expires_at,
            _STATE: "revoked" if session.revoked else "active",
        },
    )


def clear(store: SecretStore) -> None:
    """Forget the session. Local data is untouched by construction: nothing
    outside the credential entry is addressed here."""
    store.drop(CREDENTIALS_ENTRY)


@dataclass(frozen=True)
class Pending:
    """A sign-in awaiting the user's approval."""

    provider: str
    device_code: str
    interval: int
    expires_in: int


def load_pending(store: SecretStore) -> Pending | None:
    document = load_json(store, PENDING_ENTRY)
    if document is None:
        return None
    try:
        return Pending(
            provider=document["provider"],
            device_code=document["device_code"],
            interval=int(document["interval"]),
            expires_in=int(document["expires_in"]),
        )
    except (KeyError, ValueError) as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the pending sign-in record is unreadable",
            details={"exception": type(error).__name__},
            next_actions=["auth login --provider google --json"],
        ) from error


def save_pending(store: SecretStore, pending: Pending) -> None:
    store_json(
        store,
        PENDING_ENTRY,
        {
            "provider": pending.provider,
            "device_code": pending.device_code,
            "interval": str(pending.interval),
            "expires_in": str(pending.expires_in),
        },
    )


def clear_pending(store: SecretStore) -> None:
    store.drop(PENDING_ENTRY)


def status(*, now: datetime | None = None) -> tuple[AuthStatus, str | None]:
    """The four-way answer, and any warning the credential store raised."""
    store, warning = open_store()
    session = load(store)
    if session is None:
        return (
            AuthStatus(
                state="local_only",
                account_id=None,
                expires_at=None,
                credential_store=None,
            ),
            warning,
        )
    return (
        AuthStatus(
            state=session.state(now=now),
            account_id=session.account_id,
            expires_at=session.expires_at,
            credential_store=store.tier,
        ),
        warning,
    )
