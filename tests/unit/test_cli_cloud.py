"""The cloud boundary, driven entirely by the `#71` mock: no server exists yet."""

import dataclasses
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast

import httpx
import pytest

from ai_stp_cli.cloud import client, login, session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import passports
from ai_stp_cli.secrets import open_store
from ai_stp_contracts.auth import DeviceAuthorizationResponse, DeviceTokenResponse
from ai_stp_contracts.http import API_BASE_PATH
from ai_stp_contracts.mock import MOCK_BASE_URL, build_transport
from ai_stp_foundation.ids import new_id

#: The corpus fixes these, and the mock matches on the request body, so a test
#: that invented its own values would simply not be answered.
FIXTURE_DEVICE = "device_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
FIXTURE_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
FIXTURE_NAME = "fixture-device"
APPROVED_CODE = "FIXTUREdeviceCODE0123456789abcdefGHIJKLM"
PENDING_CODE = "FIXTUREpendingCODE0123456789abcdefGHIJKL"
EXPIRED_CODE = "FIXTUREexpiredCODE0123456789abcdefGHIJKL"

MOCK = Endpoint(MOCK_BASE_URL)


def _started(device_code: str, *, interval: int = 1, expires_in: int = 60) -> login.Started:
    return login.Started(
        device_code=device_code,
        user_code="ABCD-EFGH",
        verification_uri=f"{MOCK_BASE_URL}/device",
        verification_uri_complete=f"{MOCK_BASE_URL}/device?code=ABCD-EFGH",
        expires_in=expires_in,
        interval=interval,
    )


def _poll(device_code: str, **kwargs: object) -> DeviceTokenResponse:
    return login.poll(
        MOCK,
        _started(device_code),
        device_id=FIXTURE_DEVICE,
        public_key=FIXTURE_KEY,
        display_name=FIXTURE_NAME,
        transport=build_transport(),
        pause=lambda _seconds: None,
        **kwargs,  # pyright: ignore[reportArgumentType]
    )


def test_only_https_is_accepted() -> None:
    # This is the connection a device key and a refresh token travel over.
    assert client.check_base_url("https://example.test/v1/") == "https://example.test/v1"
    for bad in ("http://example.test", "ftp://example.test", "example.test"):
        with pytest.raises(CliFailure, match="must use HTTPS"):
            client.check_base_url(bad)


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        # Credentials in the authority make a URL look like it points somewhere
        # it does not, and nothing here would ever need them.
        ("https://user:pass@elsewhere.test/v1", "must carry no credentials"),
        ("https://@elsewhere.test/v1", "must carry no credentials"),
        # No authority at all: a prefix check accepted this and left the path to
        # be interpreted by whatever saw the string next.
        ("https:///v1", "names no host"),
        ("https://", "names no host"),
        ("https://example.test/v1?token=leaked", "no query or fragment"),
        ("https://example.test/v1#fragment", "no query or fragment"),
        ("https://exam ple.test/v1", "no whitespace"),
    ],
)
def test_an_address_unfit_to_send_secrets_to_is_refused(address: str, expected: str) -> None:
    with pytest.raises(CliFailure, match=expected):
        client.check_base_url(address)


def test_an_accepted_address_is_normalised() -> None:
    # One interpretation for every later caller, rather than one per parser.
    assert client.check_base_url("  https://example.test/v1//  ") == "https://example.test/v1"
    assert client.check_base_url("https://example.test") == "https://example.test"
    assert client.check_base_url("https://example.test:8443/v1") == "https://example.test:8443/v1"


def test_starting_an_authorization_returns_what_the_user_must_approve() -> None:
    started = login.start(MOCK, "google", transport=build_transport())
    assert started.user_code
    assert started.verification_uri.startswith("https://")
    assert started.expires_in > 0
    assert started.interval >= 1


def test_an_approved_authorization_yields_credentials_bound_to_this_device() -> None:
    credentials = _poll(APPROVED_CODE)
    assert credentials.device_id == FIXTURE_DEVICE
    assert credentials.account_id.startswith("account_")
    assert credentials.access_token and credentials.refresh_token
    assert credentials.token_type == "Bearer"


def test_a_declined_or_expired_authorization_is_a_decision_not_a_wait() -> None:
    # `#71` made these typed errors precisely so a client cannot mistake
    # "not yet" for "no credentials issued".
    with pytest.raises(CliFailure) as raised:
        _poll(EXPIRED_CODE)
    assert raised.value.code == "AI_STP_AUTHORIZATION_EXPIRED"


def test_a_pending_authorization_is_waited_on_and_then_gives_up_bounded() -> None:
    clock = iter([0.0, 0.0, 1.0, 999.0])
    with pytest.raises(CliFailure) as raised:
        _poll(PENDING_CODE, now=lambda: next(clock))
    assert raised.value.code == "AI_STP_AUTHORIZATION_EXPIRED"
    assert raised.value.exit_code == 3


def test_polling_never_goes_faster_than_the_server_asked() -> None:
    waits: list[float] = []
    clock = iter([0.0, 0.0, 1.0, 999.0])
    with pytest.raises(CliFailure):
        login.poll(
            MOCK,
            _started(PENDING_CODE, interval=0),
            device_id=FIXTURE_DEVICE,
            public_key=FIXTURE_KEY,
            display_name=FIXTURE_NAME,
            transport=build_transport(),
            pause=waits.append,
            now=lambda: next(clock),
        )
    # The server answers `AI_STP_RATE_LIMITED` to a client that polls faster,
    # so an interval of zero is floored rather than obeyed.
    assert waits and min(waits) >= login.MIN_POLL_INTERVAL


def test_a_body_that_does_not_match_the_contract_is_refused() -> None:
    def wrong(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    with (
        client.open_client(MOCK, transport=httpx.MockTransport(wrong)) as http,
        pytest.raises(CliFailure, match="does not match the published contract"),
    ):
        client.call(http, "GET", "/health/live", DeviceAuthorizationResponse)


def test_a_body_that_is_not_json_is_refused() -> None:
    def rubbish(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>a proxy said hello</html>")

    with (
        client.open_client(MOCK, transport=httpx.MockTransport(rubbish)) as http,
        pytest.raises(CliFailure, match="does not match the published contract"),
    ):
        client.call(http, "GET", "/health/live", DeviceAuthorizationResponse)


@pytest.mark.parametrize("status", [500, 502, 503, 504, 429])
def test_a_transient_failure_is_retried_a_bounded_number_of_times(status: int) -> None:
    seen: list[int] = []

    def flaky(_request: httpx.Request) -> httpx.Response:
        seen.append(status)
        return httpx.Response(status, json={"error": {"code": "AI_STP_RATE_LIMITED"}})

    with (
        client.open_client(MOCK, transport=httpx.MockTransport(flaky)) as http,
        pytest.raises(CliFailure),
    ):
        client.call(
            http,
            "GET",
            "/health/live",
            DeviceAuthorizationResponse,
            attempts=3,
            pause=lambda _seconds: None,
        )
    assert len(seen) == 3


@pytest.mark.parametrize(
    "code",
    ["AI_STP_AUTH_REQUIRED", "AI_STP_DEVICE_REVOKED", "AI_STP_AUTHORIZATION_DECLINED"],
)
def test_a_refusal_is_never_retried(code: str) -> None:
    # Repeating a decision produces the same decision, and hammering a declined
    # sign-in is exactly what an agent must not do.
    seen: list[str] = []

    def refuses(_request: httpx.Request) -> httpx.Response:
        seen.append(code)
        return httpx.Response(503, json={"error": {"code": code}})

    with (
        client.open_client(MOCK, transport=httpx.MockTransport(refuses)) as http,
        pytest.raises(CliFailure) as raised,
    ):
        client.call(
            http,
            "GET",
            "/health/live",
            DeviceAuthorizationResponse,
            attempts=3,
            pause=lambda _seconds: None,
        )
    assert len(seen) == 1
    assert raised.value.code == code


def test_a_corrupt_catalog_row_is_not_retried_despite_its_retryable_status() -> None:
    # This one ships with 500, which the status table calls retryable. The
    # stored bytes will not become valid between two attempts half a second
    # apart, so the code has to win over the status.
    seen: list[str] = []

    def corrupt(_request: httpx.Request) -> httpx.Response:
        seen.append("AI_STP_CATALOG_INTEGRITY")
        return httpx.Response(500, json={"error": {"code": "AI_STP_CATALOG_INTEGRITY"}})

    with (
        client.open_client(MOCK, transport=httpx.MockTransport(corrupt)) as http,
        pytest.raises(CliFailure) as raised,
    ):
        client.call(
            http,
            "GET",
            "/health/live",
            DeviceAuthorizationResponse,
            attempts=3,
            pause=lambda _seconds: None,
        )
    assert len(seen) == 1
    assert raised.value.code == "AI_STP_CATALOG_INTEGRITY"


def test_the_servers_own_pacing_is_honoured_and_bounded() -> None:
    waits: list[float] = []

    def slow_down(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "3600"}, json={})

    with (
        client.open_client(MOCK, transport=httpx.MockTransport(slow_down)) as http,
        pytest.raises(CliFailure),
    ):
        client.call(
            http,
            "GET",
            "/health/live",
            DeviceAuthorizationResponse,
            attempts=2,
            pause=waits.append,
        )
    # Honoured, but a server asking for an hour must not hang the caller.
    assert waits == [60.0]


def test_an_unreachable_platform_is_a_typed_dependency_failure() -> None:
    def refuse(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to https://internal.example/secret?token=abc")

    with (
        client.open_client(MOCK, transport=httpx.MockTransport(refuse)) as http,
        pytest.raises(CliFailure) as raised,
    ):
        client.call(
            http,
            "GET",
            "/health/live",
            DeviceAuthorizationResponse,
            attempts=1,
        )
    assert raised.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"
    assert raised.value.retryable
    # The exception text carries a URL with a query; only the type is published.
    assert raised.value.details == {"exception": "ConnectError"}
    assert "token" not in raised.value.message


def test_an_unregistered_server_code_is_not_passed_through() -> None:
    # The registry is closed. A caller matching on codes must never see one that
    # is not in it, whatever a server sends.
    def invents(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"code": "SOMETHING_NEW", "message": "hi"}})

    with (
        client.open_client(MOCK, transport=httpx.MockTransport(invents)) as http,
        pytest.raises(CliFailure) as raised,
    ):
        client.call(http, "GET", "/health/live", DeviceAuthorizationResponse, attempts=1)
    assert raised.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"


def test_the_contract_version_is_negotiated_on_every_call() -> None:
    seen: list[str] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("X-AI-STP-Schema-Version", ""))
        return httpx.Response(500, json={})

    with (
        client.open_client(MOCK, transport=httpx.MockTransport(record)) as http,
        pytest.raises(CliFailure),
    ):
        client.call(
            http,
            "GET",
            "/health/live",
            DeviceAuthorizationResponse,
            attempts=1,
        )
    assert seen == ["1"]


def test_a_session_moves_between_the_four_states() -> None:
    now = datetime.now(UTC)
    held = session.Session(
        account_id=new_id("account"),
        device_id=new_id("device"),
        access_token="a",
        refresh_token="r",
        expires_at=session.expiry(3600, now=now),
    )
    assert held.state(now=now) == "authenticated"
    assert held.state(now=now + timedelta(hours=2)) == "expired"

    revoked = dataclasses.replace(held, revoked=True)
    # Revocation outranks the clock: a fresh token on a revoked device is still
    # unusable, and the repair is a new key, not a refresh.
    assert revoked.state(now=now) == "revoked"


def test_a_stored_session_round_trips_and_status_reports_it() -> None:
    store, _warning = open_store()
    assert session.load(store) is None
    report, _ = session.status()
    assert report.state == "local_only"
    assert report.credential_store is None

    held = session.Session(
        account_id=new_id("account"),
        device_id=new_id("device"),
        access_token="secret-access",
        refresh_token="secret-refresh",
        expires_at=session.expiry(3600),
    )
    session.save(store, held)
    assert session.load(store) == held

    report, _ = session.status()
    assert report.state == "authenticated"
    assert report.account_id == held.account_id
    assert "secret-" not in report.model_dump_json()


def test_an_incomplete_stored_session_is_named_not_guessed() -> None:
    from ai_stp_cli.secrets import store_json

    store, _warning = open_store()
    store_json(store, session.CREDENTIALS_ENTRY, {"account_id": new_id("account")})
    with pytest.raises(CliFailure, match="incomplete") as raised:
        session.load(store)
    assert raised.value.next_actions == ["auth logout --json"]


def test_logging_out_forgets_the_session_and_nothing_else() -> None:
    from ai_stp_cli import identity

    current, _ = identity.load_or_create()
    store, _warning = open_store()
    session.save(
        store,
        session.Session(
            account_id=new_id("account"),
            device_id=current.device_id,
            access_token="a",
            refresh_token="r",
            expires_at=session.expiry(3600),
        ),
    )

    session.clear(store)
    assert session.load(store) is None
    # The device identity is untouched: signing out is not starting over.
    assert identity.load_or_create()[0].device_id == current.device_id


def test_a_pending_authorization_round_trips_through_the_credential_store() -> None:
    # The device code is the bearer of a pending authorization, so it belongs in
    # the credential store rather than in ordinary local state.
    store, _warning = open_store()
    assert session.load_pending(store) is None
    pending = session.Pending(
        provider="google", device_code=PENDING_CODE, interval=5, expires_in=60
    )
    session.save_pending(store, pending)
    assert session.load_pending(store) == pending
    session.clear_pending(store)
    assert session.load_pending(store) is None


def test_a_damaged_pending_record_is_named() -> None:
    from ai_stp_cli.secrets import store_json

    store, _warning = open_store()
    store_json(store, session.PENDING_ENTRY, {"provider": "google"})
    with pytest.raises(CliFailure, match="pending sign-in record is unreadable"):
        session.load_pending(store)


def test_a_revoked_device_cannot_start_a_sign_in() -> None:
    import json as json_module

    from ai_stp_cli import identity, paths

    current, _ = identity.load_or_create()
    paths.write_private(
        paths.device_file(),
        json_module.dumps(
            {
                "device_id": current.device_id,
                "created_at": current.created_at,
                "state": "revoked",
                "retired": [],
            }
        ),
    )
    with pytest.raises(CliFailure) as raised:
        login.local_identity()
    assert raised.value.code == "AI_STP_DEVICE_REVOKED"
    assert raised.value.exit_code == 3


def test_the_display_name_is_the_host_and_carries_no_path() -> None:
    name = login.device_display_name()
    assert name and "/" not in name and len(name) <= 100


def test_opening_a_browser_that_is_not_there_is_not_a_failure() -> None:
    # A machine with no browser is the normal case for this flow, which is why
    # the plain address and code stay required in the contract.
    def refuses(_url: str) -> bool:
        raise RuntimeError("no display")

    assert login.open_browser(_started(APPROVED_CODE), opener=refuses) is False
    assert login.open_browser(_started(APPROVED_CODE), opener=lambda _url: True) is True


def _mock_endpoint() -> Endpoint:
    return Endpoint(MOCK_BASE_URL, transport=build_transport())


def _always_opens(_started: login.Started, **_options: object) -> bool:
    return True


def test_the_whole_sign_in_runs_against_the_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    # `#75` requires the CLI to be exercisable before a server exists. The
    # transport lives on the endpoint, so this is the same code path the real
    # platform will take.
    from ai_stp_cli import identity, paths
    from ai_stp_cli.commands import auth, passport

    monkeypatch.setattr(auth, "endpoint", _mock_endpoint)
    monkeypatch.setattr(login, "device_display_name", lambda: FIXTURE_NAME)
    monkeypatch.setattr(login, "open_browser", _always_opens)

    # The mock answers only for the fixture's device identity, so this run
    # adopts it rather than inventing one the corpus never agreed to. The key
    # moves with the record: they are minted together and named after each
    # other, so rewriting one alone would leave an identity that cannot sign.
    from ai_stp_cli import secrets as secrets_module

    current, _ = identity.load_or_create()
    store = secrets_module.FileStore()
    minted = store.get(identity.key_entry(current.device_id))
    assert minted is not None
    store.put(identity.key_entry(FIXTURE_DEVICE), minted)
    paths.write_private(
        paths.device_file(),
        f'{{"device_id": "{FIXTURE_DEVICE}", "created_at": "{current.created_at}", '
        '"state": "active", "retired": []}',
    )
    monkeypatch.setattr(
        login,
        "local_identity",
        lambda: (FIXTURE_DEVICE, FIXTURE_KEY, None),
    )

    passport.developer_init({})
    before = passport.developer_show({}).payload

    # Not asked for, so not opened. `webbrowser.open` launches the desktop's
    # declared default and waits for it: a machine command that promised to
    # print a code and return instead hung for six minutes and forty seconds on
    # a machine whose default is slow to start, and the browser that opened was
    # not the one anybody wanted. The contract already required `user_code` and
    # `verification_uri` so the caller can decide.
    quiet = auth.begin({"provider": "google"}).payload
    assert quiet.browser_opened is False

    started = auth.begin({"provider": "google", "open-browser": True}).payload
    assert started.user_code
    assert started.browser_opened is True
    assert started.device_id == FIXTURE_DEVICE

    store, _warning = open_store()
    pending = session.load_pending(store)
    assert pending is not None
    # The corpus fixes which code is approved; the started one is the mock's.
    session.save_pending(store, dataclasses.replace(pending, device_code=APPROVED_CODE))

    finished = auth.complete({}).payload
    assert finished.state == "authenticated"
    assert finished.account_id

    # `ADR-0060`: ownership moves onto the server's account, as a revision.
    after = passport.developer_show({}).payload
    assert after.owner_id == finished.account_id
    assert after.owner_id != before.owner_id
    assert after.parent_revision_ids == [before.revision_id]

    # The pending record is consumed, not left to be polled again.
    assert session.load_pending(store) is None


def test_completing_without_a_pending_sign_in_is_a_typed_answer() -> None:
    from ai_stp_cli.commands import auth

    with pytest.raises(CliFailure, match="no sign-in is waiting") as raised:
        auth.complete({})
    assert raised.value.code == "AI_STP_NOT_FOUND"


@pytest.mark.parametrize("given", [None, "gitlab"])
def test_an_unusable_provider_is_refused(given: object) -> None:
    from ai_stp_cli.commands import auth

    with pytest.raises(CliFailure, match="provider"):
        auth.begin({"provider": given})


def test_a_declined_sign_in_clears_the_pending_record(monkeypatch: pytest.MonkeyPatch) -> None:
    # Leaving it pending would make the next `--await` poll a dead code.
    from ai_stp_cli.commands import auth

    monkeypatch.setattr(auth, "endpoint", _mock_endpoint)
    monkeypatch.setattr(login, "local_identity", lambda: (FIXTURE_DEVICE, FIXTURE_KEY, None))
    monkeypatch.setattr(login, "device_display_name", lambda: FIXTURE_NAME)

    store, _warning = open_store()
    session.save_pending(
        store,
        session.Pending(provider="google", device_code=EXPIRED_CODE, interval=1, expires_in=60),
    )
    with pytest.raises(CliFailure) as raised:
        auth.complete({})
    assert raised.value.code == "AI_STP_AUTHORIZATION_EXPIRED"
    assert session.load_pending(store) is None


def _hold_session(token: str = "a") -> None:
    """Give this installation a usable cloud session to sign out of."""
    store, _warning = open_store()
    session.save(
        store,
        session.Session(
            account_id=new_id("account"),
            device_id=new_id("device"),
            access_token=token,
            refresh_token="r",
            expires_at=session.expiry(3600),
        ),
    )


#: What the sign-out warns when the remote half did not happen. The credential
#: store raises its own warning on every call here, so tests assert on this one
#: rather than on an empty tuple.
_SESSION_SURVIVED = "stays valid until it expires"


def _logout_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    route: Callable[[httpx.Request], httpx.Response],
    *,
    attempts: int = 1,
) -> None:
    from ai_stp_cli.commands import auth

    monkeypatch.setattr(
        auth,
        "endpoint",
        lambda: Endpoint(
            "https://platform.example",
            max_attempts=attempts,
            transport=httpx.MockTransport(route),
        ),
    )


def test_logging_out_keeps_the_local_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_stp_cli.commands import auth, passport

    passport.developer_init({})
    before = passport.developer_show({}).payload

    _hold_session()
    _logout_endpoint(
        monkeypatch,
        lambda _request: httpx.Response(200, json={"schema_version": 1, "revoked": True}),
    )
    answer = auth.logout({})
    assert answer.payload.state == "local_only"
    # Signing out is not starting over.
    assert passport.developer_show({}).payload.revision_id == before.revision_id


def test_logging_out_revokes_the_session_on_the_server(monkeypatch: pytest.MonkeyPatch) -> None:
    # Dropping the local entry stops this installation from using the token; it
    # does not stop the token. A copy taken elsewhere would stay usable for the
    # rest of the session lifetime unless the server is told.
    from ai_stp_cli.commands import auth

    seen: list[tuple[str, str, str | None]] = []

    def route(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.headers.get("authorization")))
        return httpx.Response(200, json={"schema_version": 1, "revoked": True})

    _hold_session(token="the-held-token")
    _logout_endpoint(monkeypatch, route)

    answer = auth.logout({})
    assert seen == [("POST", f"{API_BASE_PATH}/auth/logout", "Bearer the-held-token")]
    assert answer.payload.state == "local_only"
    assert not any(_SESSION_SURVIVED in item for item in answer.warnings)
    store, _warning = open_store()
    assert session.load(store) is None


def test_logging_out_offline_still_forgets_the_credential_and_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Refusing offline would leave the token on disk, which is worse than the
    # session outliving it. The difference belongs in the envelope, not in an
    # exit code.
    from ai_stp_cli.commands import auth

    def route(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    _hold_session()
    _logout_endpoint(monkeypatch, route)

    answer = auth.logout({})
    assert answer.payload.state == "local_only"
    assert any(_SESSION_SURVIVED in item for item in answer.warnings)
    store, _warning = open_store()
    assert session.load(store) is None


def test_logging_out_of_an_already_dead_session_warns_about_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The stored entry is stale rather than the sign-out incomplete: the state
    # the user asked for already holds, so there is nothing to report.
    from ai_stp_cli.commands import auth

    def route(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "schema_version": 1,
                "error": {
                    "code": "AI_STP_AUTH_REQUIRED",
                    "message": "authentication required",
                    "retryable": False,
                },
            },
        )

    _hold_session()
    _logout_endpoint(monkeypatch, route)

    answer = auth.logout({})
    assert answer.payload.state == "local_only"
    assert not any(_SESSION_SURVIVED in item for item in answer.warnings)
    store, _warning = open_store()
    assert session.load(store) is None


def test_logging_out_without_a_session_asks_the_server_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_stp_cli.commands import auth

    def route(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("logout without a held session must not call the platform")

    _logout_endpoint(monkeypatch, route)
    answer = auth.logout({})
    assert answer.payload.state == "local_only"
    assert not any(_SESSION_SURVIVED in item for item in answer.warnings)


def test_transferring_ownership_twice_adds_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import closing

    from ai_stp_cli.commands import passport
    from ai_stp_cli.local.database import configured_path, open_registry

    passport.developer_init({})
    passport.device_refresh({})
    account = new_id("account")

    with closing(open_registry(configured_path())) as connection:
        passports.adopt(account)
        moved = passports.reconcile_owner(connection, device_id=FIXTURE_DEVICE)
        assert len(moved) == 2
        again = passports.reconcile_owner(connection, device_id=FIXTURE_DEVICE)
        assert again == ()


def test_an_authenticated_call_carries_the_bearer_and_follows_no_redirect() -> None:
    # A redirect on an authenticated call would resend the token to wherever the
    # redirect points, so it is refused rather than followed.
    seen: list[str] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Authorization", ""))
        return httpx.Response(302, headers={"Location": "https://elsewhere.invalid/"})

    with (
        client.open_client(
            MOCK, transport=httpx.MockTransport(record), access_token="secret-access"
        ) as http,
        pytest.raises(CliFailure),
    ):
        client.call(http, "GET", "/account", DeviceAuthorizationResponse, attempts=1)
    assert seen == ["Bearer secret-access"]


@pytest.mark.parametrize("retry_after", ["not-a-number", None])
def test_an_unusable_retry_after_falls_back_to_the_clients_own_backoff(
    retry_after: str | None,
) -> None:
    waits: list[float] = []
    headers = {} if retry_after is None else {"Retry-After": retry_after}

    def rate_limited(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers=headers, json={})

    with (
        client.open_client(MOCK, transport=httpx.MockTransport(rate_limited)) as http,
        pytest.raises(CliFailure),
    ):
        client.call(
            http, "GET", "/health/live", DeviceAuthorizationResponse, attempts=2, pause=waits.append
        )
    assert waits == [client.BACKOFF_SECONDS]


def test_an_error_body_that_is_not_an_envelope_still_yields_a_registered_code() -> None:
    # A proxy or a load balancer can answer instead of the platform, and what it
    # sends is not the contract's error envelope.
    def gateway(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="<html>Bad Request</html>")

    with (
        client.open_client(MOCK, transport=httpx.MockTransport(gateway)) as http,
        pytest.raises(CliFailure) as raised,
    ):
        client.call(http, "GET", "/health/live", DeviceAuthorizationResponse, attempts=1)
    assert raised.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"


def test_the_local_identity_is_read_for_a_sign_in() -> None:
    from ai_stp_cli import identity

    current, _ = identity.load_or_create()
    device_id, public_key, _warning = login.local_identity()
    assert device_id == current.device_id
    assert public_key == current.report().public_key


def test_the_endpoint_comes_from_the_effective_configuration() -> None:
    from ai_stp_cli.commands import auth

    assert auth.endpoint().base_url.startswith("https://")


def test_a_transport_failure_on_the_first_attempt_is_retried() -> None:
    # The path where there is no response at all to read pacing from.
    waits: list[float] = []
    attempts: list[int] = []

    def flaky(_request: httpx.Request) -> httpx.Response:
        attempts.append(len(attempts))
        raise httpx.ReadTimeout("timed out")

    with (
        client.open_client(MOCK, transport=httpx.MockTransport(flaky)) as http,
        pytest.raises(CliFailure) as raised,
    ):
        client.call(
            http, "GET", "/health/live", DeviceAuthorizationResponse, attempts=2, pause=waits.append
        )
    assert len(attempts) == 2
    assert waits == [client.BACKOFF_SECONDS]
    assert raised.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"


def test_an_additive_server_field_is_accepted_and_preserved() -> None:
    # `SPEC-011` REQ-1102 and `schema-evolution.md`: within the supported major
    # an unknown optional field is preserved, not rejected. One additive server
    # field must never hard-fail every installed CLI.
    def newer(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "schema_version": 1,
                "device_code": "C" * 40,
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://example.invalid/device",
                "verification_uri_complete": "https://example.invalid/device?code=ABCD-EFGH",
                "expires_in": 600,
                "interval": 5,
                "a_field_from_a_newer_server": "preserved",
            },
        )

    with client.open_client(MOCK, transport=httpx.MockTransport(newer)) as http:
        answer = client.call(http, "POST", "/auth/device", DeviceAuthorizationResponse, attempts=1)
    assert answer.user_code == "ABCD-EFGH"
    assert getattr(answer, "a_field_from_a_newer_server", None) == "preserved"


def test_a_newer_wire_major_is_named_rather_than_called_malformed() -> None:
    # It would be refused either way, because the models pin `schema_version`.
    # The point is which code an agent sees: "upgrade this CLI" and "the server
    # is broken" have different next actions.
    def next_major(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"schema_version": 2, "anything": True})

    with (
        client.open_client(MOCK, transport=httpx.MockTransport(next_major)) as http,
        pytest.raises(CliFailure) as raised,
    ):
        client.call(http, "POST", "/auth/device", DeviceAuthorizationResponse, attempts=1)
    assert raised.value.code == "AI_STP_SCHEMA_UNSUPPORTED"
    assert raised.value.details["found"] == "2"
    assert raised.value.next_actions == ["version --json"]


def test_a_body_without_a_schema_version_is_still_checked_against_the_model() -> None:
    def bare(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not an object"])

    with (
        client.open_client(MOCK, transport=httpx.MockTransport(bare)) as http,
        pytest.raises(CliFailure, match="does not match the published contract"),
    ):
        client.call(http, "POST", "/auth/device", DeviceAuthorizationResponse, attempts=1)


def _invalid_response_cases() -> list[object]:
    from ai_stp_contracts.fixtures import cases_of_kind

    return list(cases_of_kind("invalid_response"))


@pytest.mark.parametrize("case", _invalid_response_cases(), ids=lambda item: str(item.case_id))
def test_the_client_refuses_every_body_the_corpus_calls_invalid(case: object) -> None:
    # `#71` built these to prove the CLI does not quietly accept a broken
    # server. The corpus test proves the *model* rejects them; this proves the
    # client turns that rejection into a typed failure. Between the two sits one
    # lenient line in `_decode`, and without this the model test would still
    # pass while the CLI accepted the body.
    from ai_stp_contracts.fixtures import FixtureCase
    from ai_stp_contracts.openapi import OPERATIONS

    fixture = cast(FixtureCase, case)
    operation = next(item for item in OPERATIONS if item.operation_id == fixture.operation_id)

    def broken(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(fixture.status, json=dict(fixture.body or {}))

    with (
        client.open_client(MOCK, transport=httpx.MockTransport(broken)) as http,
        pytest.raises(CliFailure) as raised,
    ):
        assert operation.response is not None
        client.call(http, "GET", "/health/live", operation.response, attempts=1)

    # A client-side refusal, not a server error: what arrived does not match the
    # published contract, and acting on it would mean acting on something nobody
    # agreed to.
    assert raised.value.code in {"AI_STP_VALIDATION_ERROR", "AI_STP_SCHEMA_UNSUPPORTED"}
    assert raised.value.exit_code == 2


def test_the_corpus_still_carries_bodies_a_client_must_refuse() -> None:
    # If this ever reaches zero, the check above silently stops proving
    # anything while still passing.
    assert len(_invalid_response_cases()) >= 9


def test_signing_in_survives_the_next_environment_change(monkeypatch: pytest.MonkeyPatch) -> None:
    """The handover used to undo itself, and nothing loud happened when it did.

    `transfer_ownership` moved the passport heads but left the owner record
    naming the locally minted identity. Every later revision reads `owner_id`
    from that record, so the first environment change — a new OS build, a new
    architecture, a renamed host — refreshed the device passport and committed a
    revision that owned the object straight back to the local identity. The
    object's history then alternated owners with no one having asked for it.
    """
    import platform as platform_module
    from contextlib import closing

    from ai_stp_cli import identity
    from ai_stp_cli.local import passports as local_passports
    from ai_stp_cli.local import revisions as local_revisions
    from ai_stp_cli.local.database import configured_path, open_registry

    registry_path = configured_path()
    device, _ = identity.load_or_create()
    with closing(open_registry(registry_path)) as connection:
        local_passports.init_developer(connection, device_id=device.device_id)
        local_passports.ensure_device(connection, device_id=device.device_id)

    account = new_id("account")
    credentials = DeviceTokenResponse(
        account_id=account,
        device_id=device.device_id,
        access_token="a",
        refresh_token="r",
        expires_in=3600,
    )
    store, _ = open_store()
    login.complete(credentials, registry_path=registry_path, store=store)

    # The environment now looks different, which is what refreshes the passport.
    monkeypatch.setattr(platform_module, "machine", lambda: "s390x")
    with closing(open_registry(registry_path)) as connection:
        refreshed = local_passports.ensure_device(connection, device_id=device.device_id)
        developer_id = local_passports.developer_stable_id(connection)
        assert developer_id is not None
        developer_head = local_revisions.head(connection, developer_id)

    assert refreshed.envelope.owner_id == account
    assert developer_head is not None
    assert developer_head.envelope.owner_id == account
    assert local_passports.owner().account_id == account


def test_machine_completion_asks_once_and_keeps_the_pending_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two halves of the defect, in one test.

    It polled for up to fifteen minutes, holding an agent for as long as a
    person took to reach a browser. And it caught every typed failure to clear
    the pending record, although its comment spoke only of declined and expired
    — so one lost network reply destroyed a code the user had already been shown.
    """
    from ai_stp_cli.commands import auth
    from ai_stp_cli.secrets import open_store

    asked: list[int] = []

    def pending_once(*_args: object, **_kwargs: object) -> DeviceTokenResponse:
        asked.append(1)
        raise CliFailure("AI_STP_AUTHORIZATION_PENDING", "not yet")

    monkeypatch.setattr(auth, "endpoint", _mock_endpoint)
    monkeypatch.setattr(login, "device_display_name", lambda: FIXTURE_NAME)
    monkeypatch.setattr(login, "local_identity", lambda: (FIXTURE_DEVICE, FIXTURE_KEY, None))
    monkeypatch.setattr(login, "exchange", pending_once)

    store, _warning = open_store()
    session.save_pending(
        store,
        session.Pending(provider="google", device_code=PENDING_CODE, interval=1, expires_in=60),
    )

    with pytest.raises(CliFailure) as raised:
        auth.complete({})

    assert raised.value.code == "AI_STP_AUTHORIZATION_PENDING"
    assert asked == [1], "a machine call must ask exactly once"
    assert session.load_pending(store) is not None, "a pending sign-in was destroyed"


@pytest.mark.parametrize(
    ("code", "survives"),
    [
        # Not decisions: the code the user is looking at still works.
        ("AI_STP_DEPENDENCY_UNAVAILABLE", True),
        ("AI_STP_RATE_LIMITED", True),
        ("AI_STP_AUTHORIZATION_PENDING", True),
        # Decisions: there is nothing left to finish.
        ("AI_STP_AUTHORIZATION_DECLINED", False),
        ("AI_STP_AUTHORIZATION_EXPIRED", False),
    ],
)
def test_only_a_decision_clears_the_pending_sign_in(
    code: str, survives: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_stp_cli.commands import auth
    from ai_stp_cli.secrets import open_store

    def refuse(*_args: object, **_kwargs: object) -> DeviceTokenResponse:
        raise CliFailure(code, "refused")

    monkeypatch.setattr(auth, "endpoint", _mock_endpoint)
    monkeypatch.setattr(login, "device_display_name", lambda: FIXTURE_NAME)
    monkeypatch.setattr(login, "local_identity", lambda: (FIXTURE_DEVICE, FIXTURE_KEY, None))
    monkeypatch.setattr(login, "exchange", refuse)

    store, _warning = open_store()
    session.save_pending(
        store,
        session.Pending(provider="google", device_code=PENDING_CODE, interval=1, expires_in=60),
    )

    with pytest.raises(CliFailure):
        auth.complete({})

    assert (session.load_pending(store) is not None) is survives


def test_waiting_is_opt_in_and_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    """`--wait` is for a person; it answers with the same schema either way."""
    from ai_stp_cli.commands import auth
    from ai_stp_cli.secrets import open_store

    asked: list[int] = []

    def pending(*_args: object, **_kwargs: object) -> DeviceTokenResponse:
        asked.append(1)
        raise CliFailure("AI_STP_AUTHORIZATION_PENDING", "not yet")

    monkeypatch.setattr(auth, "endpoint", _mock_endpoint)
    monkeypatch.setattr(login, "device_display_name", lambda: FIXTURE_NAME)
    monkeypatch.setattr(login, "local_identity", lambda: (FIXTURE_DEVICE, FIXTURE_KEY, None))
    monkeypatch.setattr(login, "exchange", pending)
    import time as time_module

    def instantly(seconds: float) -> None:
        """The wait is bounded by the deadline, not by real elapsed time."""

    monkeypatch.setattr(time_module, "sleep", instantly)

    store, _warning = open_store()
    session.save_pending(
        store,
        session.Pending(provider="google", device_code=PENDING_CODE, interval=1, expires_in=2),
    )

    with pytest.raises(CliFailure) as raised:
        auth.complete({"wait": True})

    assert raised.value.code == "AI_STP_AUTHORIZATION_EXPIRED"
    assert len(asked) > 1, "waiting asked only once"
    # Expiry is a decision, so the record is gone.
    assert session.load_pending(store) is None


def test_one_logical_start_carries_one_key_through_every_attempt() -> None:
    """What the key is for, checked as the retry that made it necessary.

    The generic retry cannot tell "the server never saw this" from "the server
    committed it and the answer was lost". Without a stable key the second case
    became a second pending authorization and a second code the user was never
    shown.
    """
    seen: list[str] = []

    def lose_the_first_answer(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content)["idempotency_key"])
        if len(seen) == 1:
            raise httpx.ConnectError("the answer was lost", request=request)
        return httpx.Response(
            201,
            json={
                "schema_version": 1,
                "device_code": APPROVED_CODE,
                "user_code": "BCDF-GHJK",
                "verification_uri": f"{MOCK_BASE_URL}/device",
                "verification_uri_complete": f"{MOCK_BASE_URL}/device?code=BCDF-GHJK",
                "expires_in": 600,
                "interval": 5,
            },
        )

    started = login.start(
        dataclasses.replace(MOCK, max_attempts=3),
        "google",
        transport=httpx.MockTransport(lose_the_first_answer),
    )

    assert started.user_code
    assert len(seen) == 2, "the request was not retried"
    assert seen[0] == seen[1], "the retry asked for a second authorization"


def test_two_starts_are_two_intents_and_do_not_share_a_key() -> None:
    keys = {login.new_idempotency_key() for _ in range(50)}
    assert len(keys) == 50
    import re

    from ai_stp_contracts.http import IDEMPOTENCY_KEY_PATTERN

    assert all(re.fullmatch(IDEMPOTENCY_KEY_PATTERN, key) for key in keys)


# --- loopback cleartext (`#194`) ------------------------------------------


@pytest.mark.parametrize(
    "address",
    [
        "http://localhost:8000/v1",
        "http://127.0.0.1:8000/v1",
        "http://127.0.0.53/v1",
        "http://[::1]:8000/v1",
    ],
)
def test_cleartext_is_accepted_for_loopback(address: str) -> None:
    # A development stack runs the API with no TLS, and refusing it made the CLI
    # unable to reach a healthy local backend at all.
    assert client.check_base_url(address).startswith("http://")


@pytest.mark.parametrize(
    "address",
    [
        "http://example.com/v1",
        "http://192.168.1.10:8000/v1",
        "http://10.0.0.5/v1",
        # Not localhost: the exception is an exact match, not a prefix or a
        # suffix, or a name ending in it would inherit the exception.
        "http://localhost.evil.test/v1",
        "http://notlocalhost/v1",
        # Numeric spellings a resolver might send to the loopback interface but
        # `ipaddress` does not recognise. Failing closed on a spelling we cannot
        # read is the safe direction when it decides whether cleartext is used.
        "http://2130706433/v1",
        "http://0177.0.0.1/v1",
        "http://127.1/v1",
    ],
)
def test_cleartext_is_refused_for_anything_else(address: str) -> None:
    with pytest.raises(CliFailure, match="must use HTTPS") as raised:
        client.check_base_url(address)
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_https_is_unchanged_and_the_scheme_is_never_rewritten() -> None:
    assert client.check_base_url("https://api.test/v1/") == "https://api.test/v1"
    # Forcing `https` on the way out would silently point a development stack at
    # a port that is not listening for TLS.
    assert client.check_base_url("http://localhost:8000/") == "http://localhost:8000"
    # A scheme that is neither is still refused outright.
    with pytest.raises(CliFailure, match="must use HTTPS"):
        client.check_base_url("ftp://localhost/v1")


def test_the_default_catalog_url_carries_no_api_prefix() -> None:
    """The shipped default must not repeat what the client already adds.

    `client.call` prefixes every path with `API_BASE_PATH`, so a base address
    ending in `/v1` produces `/v1/v1/...`. Measured against a real server that
    returns 404, which the CLI reports as `AI_STP_NOT_FOUND` — reading as "no
    such object" when the truth is "wrong address", and costing an hour to tell
    apart.
    """
    from ai_stp_cli import config

    default = next(item for item in config.declared_fields() if item.path == "catalog.url").default
    assert isinstance(default, str)
    assert not default.rstrip("/").endswith(API_BASE_PATH)


def test_a_configured_base_address_is_not_given_the_prefix_twice() -> None:
    import httpx

    seen: list[str] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json={"schema_version": 1, "status": "alive"})

    endpoint = client.Endpoint("https://ai-stp.example", transport=httpx.MockTransport(record))
    with client.open_client(endpoint) as http:
        http.get(f"{API_BASE_PATH}/health/live")
    assert seen == ["/v1/health/live"]
