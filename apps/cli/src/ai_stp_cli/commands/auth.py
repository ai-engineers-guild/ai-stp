"""`ai-stp auth login` and `ai-stp auth logout` (issue #75).

Sign-in is a device-code flow brokered by our platform. The user approves in a
browser and the CLI never sees a password or a provider token — that is the
property, not a side effect: the agent commonly runs where a loopback listener
has nowhere to listen, which is why `#71` chose this shape.
"""

from collections.abc import Mapping
from typing import Final

from ai_stp_cli import config
from ai_stp_cli.answer import Answer, with_warning
from ai_stp_cli.cloud import login, session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local.database import configured_path
from ai_stp_cli.secrets import open_store
from ai_stp_contracts.auth import OAUTH_PROVIDERS, OAuthProvider
from ai_stp_contracts.machine_help import AuthStatus, DeviceApproval

#: Re-exported from the contract that owns the set.
PROVIDERS: tuple[OAuthProvider, ...] = OAUTH_PROVIDERS


def endpoint() -> Endpoint:
    """Where the platform is, from the effective configuration."""
    report = config.effective_config()
    address = next(value for value in report.values if value.path == "catalog.url")
    return Endpoint(str(address.value))


def begin(parameters: Mapping[str, object]) -> Answer[DeviceApproval]:
    """Start a sign-in and report what the user must approve.

    Two commands rather than one blocking call, because the protocol has two
    phases and because `#72` fixed that this CLI never blocks on a human
    decision — a command that polled until someone walked to their browser would
    hang in CI and in a container, which is the same reason `#71` chose a
    device-code flow over a loopback redirect.

    They are two commands rather than one with a mode flag because they answer
    with different payloads, and a command declares exactly one `result_schema`.
    One command would have to advertise a schema it does not always produce.
    """
    provider = _provider(parameters.get("provider"))
    device_id, _public_key, warning = login.local_identity()
    started = login.start(endpoint(), provider)
    store, store_warning = open_store()
    session.save_pending(
        store,
        session.Pending(
            provider=provider,
            device_code=started.device_code,
            interval=started.interval,
            expires_in=started.expires_in,
        ),
    )
    # Only when asked. See `login.open_browser` for why this is not automatic.
    opened = login.open_browser(started) if bool(parameters.get("open-browser")) else False
    return with_warning(
        DeviceApproval(
            provider=provider,
            user_code=started.user_code,
            verification_uri=started.verification_uri,
            verification_uri_complete=started.verification_uri_complete,
            expires_in=started.expires_in,
            browser_opened=opened,
            device_id=device_id,
        ),
        warning or store_warning,
    )


#: Outcomes that end an authorization. Everything else — a lost network, a rate
#: limit, a dependency that did not answer — leaves the pending record alone,
#: because the code the user is looking at is still the one that will work.
TERMINAL_OUTCOMES: Final[frozenset[str]] = frozenset(
    {
        "AI_STP_AUTHORIZATION_DECLINED",
        "AI_STP_AUTHORIZATION_EXPIRED",
        "AI_STP_NOT_FOUND",
    }
)


def complete(parameters: Mapping[str, object]) -> Answer[AuthStatus]:
    """Finish the sign-in that is pending, if the user has approved it.

    One question by default. It used to poll for up to fifteen minutes, which
    held an agent process for as long as a person took to reach their browser —
    and `#72` had already fixed that this CLI never blocks on a human decision.
    `--wait` is opt-in and bounded, for a person at a terminal who would
    otherwise run the same command until it takes; the answer is the same
    schema either way.

    A failure that is not a decision preserves the pending record. The previous
    handler caught every typed failure and cleared it, although its comment
    spoke only of declined and expired, so one lost network reply destroyed a
    code the user had already been shown and sent them back to the browser.
    """
    store, warning = open_store()
    pending = session.load_pending(store)
    if pending is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no sign-in is waiting to be finished",
            next_actions=["auth login --provider google --json"],
        )
    device_id, public_key, _warning = login.local_identity()
    started = login.Started(
        device_code=pending.device_code,
        user_code="",
        verification_uri="",
        verification_uri_complete="",
        expires_in=pending.expires_in,
        interval=pending.interval,
    )
    ask = login.poll if parameters.get("wait") else login.exchange

    try:
        credentials = ask(
            endpoint(),
            started,
            device_id=device_id,
            public_key=public_key,
            display_name=login.device_display_name(),
        )
    except CliFailure as failure:
        if failure.code in TERMINAL_OUTCOMES:
            session.clear_pending(store)
        raise

    session.clear_pending(store)
    login.complete(credentials, registry_path=configured_path(), store=store)
    report, _ = session.status()
    return with_warning(report, warning)


def _provider(raw: object) -> OAuthProvider:
    if raw is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a sign-in provider is required",
            details={"allowed": ", ".join(PROVIDERS)},
            next_actions=["auth login --provider google --json"],
        )
    value = str(raw)
    if value not in PROVIDERS:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "unknown sign-in provider",
            details={"allowed": ", ".join(PROVIDERS), "provider": value},
        )
    return value  # pyright: ignore[reportReturnType]


#: Refusals that mean the session this installation held is already gone. The
#: local entry is stale rather than the sign-out incomplete, so there is nothing
#: to warn about — the user asked for a state that already holds.
_ALREADY_ENDED: Final[frozenset[str]] = frozenset({"AI_STP_AUTH_REQUIRED", "AI_STP_DEVICE_REVOKED"})


def logout(_parameters: Mapping[str, object]) -> Answer[AuthStatus]:
    """End the cloud session on both sides, and touch nothing else.

    Local registry rows, passports and the device identity survive: signing out
    is not starting over, and `offline-capability.md` keeps the whole local
    contour working without an account.

    The server is asked first and the local entry is dropped either way. That
    order is deliberate: the credential is needed to revoke itself, so clearing
    first would make revocation impossible. Dropping it regardless is what keeps
    `logout` honest offline — a machine with no network must still be able to
    stop holding a credential, and a command that refused would leave the token
    on disk, which is worse than the session outliving it.

    A server that could not be reached is reported as a warning, not a failure.
    The local outcome the user asked for did happen; what did not happen is the
    remote half, and an agent needs that difference in the envelope rather than
    in an exit code.
    """
    store, warning = open_store()
    warnings = [] if warning is None else [warning]
    try:
        held = session.load(store)
    except CliFailure:
        # Unusable stored credentials cannot authorize their own revocation.
        # Dropping them is still the right outcome and still the safe one.
        held = None
    if held is not None:
        try:
            login.revoke_session(endpoint(), held.access_token)
        except CliFailure as failure:
            if failure.code not in _ALREADY_ENDED:
                # Not "try again": the credential this call would need is about
                # to be dropped, so no later run from this installation can
                # revoke that session. Revoking the device is the remaining way,
                # and `ADR-0018` puts it on the web.
                warnings.append(
                    "the cloud session was forgotten here but the server was not "
                    "reached, so it stays valid until it expires; revoke this "
                    "device from the web to end it now"
                )
    session.clear(store)
    report, _warning = session.status()
    return Answer(report, warnings=tuple(warnings))
