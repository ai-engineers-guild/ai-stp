"""Signing in: the device-code flow, key binding and ownership transfer (#75).

The flow is RFC 8628-shaped and brokered by our own platform, decided in `#71`
because the agent commonly runs over SSH and in containers where a loopback
listener has nowhere to listen. The consequence is the property the acceptance
criteria ask for: **no password and no provider token ever reaches the CLI**.
The user approves in a browser, and what comes back here is a code the platform
issued, exchanged for credentials bound to this device's public key.

Two things happen after a successful exchange, and both are obligations written
down elsewhere. The device public key binds to the account at exchange (`#71`).
And `ADR-0060` assigns to this issue the transfer of local passport ownership
from the locally minted identifier to the account the server issued — as an
ordinary revision, because `owner_id` is content.
"""

import socket
import time
import uuid
import webbrowser
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import httpx

from ai_stp_cli import identity
from ai_stp_cli.cloud import client, session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import passports
from ai_stp_cli.local.database import open_registry
from ai_stp_cli.secrets import SecretStore, open_store
from ai_stp_contracts.auth import (
    AuthLogoutResponse,
    DeviceAuthorizationRequest,
    DeviceAuthorizationResponse,
    DeviceTokenRequest,
    DeviceTokenResponse,
    OAuthProvider,
)

#: How long to keep polling regardless of what the server said, so a mistaken
#: `expires_in` cannot leave a terminal waiting forever.
MAX_POLL_SECONDS: Final[float] = 900.0

#: The floor under the server's `interval`. `#71` says the server answers
#: `AI_STP_RATE_LIMITED` to a client that polls faster, so this is politeness
#: with teeth.
MIN_POLL_INTERVAL: Final[float] = 1.0


@dataclass(frozen=True)
class Started:
    """What the user has to act on, and what to poll with."""

    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int


def new_idempotency_key() -> str:
    """A fresh key for one logical create.

    Random rather than derived from the request: two starts for the same
    provider are two different intents, and a derived key would fold them into
    one. `uuid4().hex` is 32 characters from the allowed alphabet.
    """
    return uuid.uuid4().hex


def start(
    endpoint: Endpoint,
    provider: OAuthProvider,
    *,
    transport: httpx.BaseTransport | None = None,
) -> Started:
    """Ask the platform to begin an authorization.

    The idempotency key is minted once, here, and travels with every retry of
    this one logical start. That is the whole point of it: the generic retry
    below cannot tell "the server never saw this" from "the server committed it
    and the answer was lost", so without a key a lost reply became a second
    pending authorization and a second code the user was never shown.
    """
    request = DeviceAuthorizationRequest(provider=provider, idempotency_key=new_idempotency_key())
    with client.open_client(endpoint, transport=transport) as http:
        answer = client.call(
            http,
            "POST",
            "/auth/device",
            DeviceAuthorizationResponse,
            body=request,
            attempts=endpoint.max_attempts,
        )
    return Started(
        device_code=answer.device_code,
        user_code=answer.user_code,
        verification_uri=str(answer.verification_uri),
        verification_uri_complete=str(answer.verification_uri_complete),
        expires_in=answer.expires_in,
        interval=answer.interval,
    )


def open_browser(started: Started, *, opener: Callable[[str], bool] = webbrowser.open) -> bool:
    """Try to put the approval page in front of the user.

    Failure is not an error. A machine with no browser is the normal case for
    this flow, which is why `verification_uri` and `user_code` stay required in
    the contract and are reported whether or not this succeeds.
    """
    try:
        return bool(opener(started.verification_uri_complete))
    except Exception:  # pragma: no cover - depends on the desktop environment
        return False


def exchange(
    endpoint: Endpoint,
    started: Started,
    *,
    device_id: str,
    public_key: str,
    display_name: str,
    transport: httpx.BaseTransport | None = None,
) -> DeviceTokenResponse:
    """Ask once whether the user has approved, and take the credentials if so.

    One call, not a loop. `AI_STP_AUTHORIZATION_PENDING` reaches the caller as
    the typed answer it is, so a machine caller decides when to ask again
    instead of being held for as long as a person takes to reach a browser.
    """
    request = DeviceTokenRequest(
        device_code=started.device_code,
        device_id=device_id,
        public_key=public_key,
        display_name=display_name,
    )
    with client.open_client(endpoint, transport=transport) as http:
        return client.call(
            http,
            "POST",
            "/auth/device/token",
            DeviceTokenResponse,
            body=request,
            # A poll is not a retry: the server is answering correctly each
            # time, and the pacing belongs to whoever is waiting.
            attempts=1,
        )


def revoke_session(
    endpoint: Endpoint,
    access_token: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> AuthLogoutResponse:
    """End the server's half of the session this installation holds.

    Dropping the local credential entry stops this installation from using the
    token; it does not stop the token. Until the server revokes it, a copy taken
    from a backup, a shell history or a shared machine stays usable for the rest
    of the session lifetime, which is fourteen days by default. Signing out has
    to mean the credential is dead, not merely forgotten here.

    Retried under the client's normal bounds: the call is idempotent, and a
    sign-out that failed on a dropped connection is exactly the case where
    trying again is both safe and what the user asked for.
    """
    with client.open_client(endpoint, transport=transport, access_token=access_token) as http:
        return client.call(http, "POST", "/auth/logout", AuthLogoutResponse)


def poll(
    endpoint: Endpoint,
    started: Started,
    *,
    device_id: str,
    public_key: str,
    display_name: str,
    transport: httpx.BaseTransport | None = None,
    pause: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> DeviceTokenResponse:
    """Wait for the user's decision, bounded, and then take the credentials.

    Only for a caller that has asked to wait. The machine path is `exchange`,
    which answers once — this loop exists so a person at a terminal is not made
    to run the same command until it takes.

    `AI_STP_AUTHORIZATION_PENDING` is the only answer worth waiting on. Declined
    and expired are decisions, and `#71` made them typed errors precisely so a
    client cannot mistake "not yet" for "no credentials issued".
    """
    interval = max(float(started.interval), MIN_POLL_INTERVAL)
    deadline = now() + min(float(started.expires_in), MAX_POLL_SECONDS)

    while True:
        try:
            return exchange(
                endpoint,
                started,
                device_id=device_id,
                public_key=public_key,
                display_name=display_name,
                transport=transport,
            )
        except CliFailure as failure:
            if failure.code != "AI_STP_AUTHORIZATION_PENDING":
                raise
        if now() >= deadline:
            raise CliFailure(
                "AI_STP_AUTHORIZATION_EXPIRED",
                "the sign-in was not approved in time",
                next_actions=["auth login --provider google --json"],
            )
        pause(interval)


def complete(
    credentials: DeviceTokenResponse,
    *,
    registry_path: Path,
    store: SecretStore | None = None,
) -> tuple[session.Session, tuple[str, ...]]:
    """Store the session and move local ownership onto the account."""
    target = store or open_store()[0]
    held = session.Session(
        account_id=credentials.account_id,
        device_id=credentials.device_id,
        access_token=credentials.access_token,
        refresh_token=credentials.refresh_token,
        expires_at=session.expiry(credentials.expires_in),
    )
    # The owner record first, then the credentials, then the passports. Every
    # later revision reads its `owner_id` from that record, so while it still
    # named the local identity the handover undid itself on the next refresh.
    passports.adopt(credentials.account_id)
    session.save(target, held)

    moved: tuple[str, ...] = ()
    if registry_path.exists():
        with closing(open_registry(registry_path)) as connection:
            moved = passports.reconcile_owner(connection, device_id=credentials.device_id)
    return held, moved


def device_display_name() -> str:
    """A name a person can recognise in their device list.

    The host name, which is not a secret and is what the account owner will be
    comparing against. No path and no environment value.
    """
    name = socket.gethostname().strip() or "unnamed device"
    return name[:100]


def local_identity() -> tuple[str, str, str | None]:
    """This device's identifier, public key and any credential-store warning."""
    current, warning = identity.load_or_create()
    if current.state == "revoked":
        raise CliFailure(
            "AI_STP_DEVICE_REVOKED",
            "this device identity is revoked and cannot sign in",
            next_actions=["device reset --confirm --json"],
        )
    return current.device_id, current.report().public_key, warning
