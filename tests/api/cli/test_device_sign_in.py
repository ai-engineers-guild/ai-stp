"""The device sign-in journey: real CLI client code against the real `/v1` app.

Replaces the `#71`-mock journey in `tests/unit/test_cli_cloud.py`. The corpus
mock still owns wire-format cases; this file owns the journey — pending is a
typed answer, approval happens through the same endpoint a browser uses, and
the issued credentials revoke through the same logout the production server
serves.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import update
from tests.api.cli.conftest import WebApprover
from tests.support.asgi_sync import SyncAsgiServer

from ai_stp_cli.cloud import login, session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.secrets import open_store
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import AccountSession, DeviceAuthorization

DEVICE_ID = new_id("device")
PUBLIC_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

ApproverFactory = Callable[[], WebApprover]


def _age_device_poll(cli_server: SyncAsgiServer, device_code: str) -> None:
    """Move `last_poll_at` past the interval so the next poll is not paced."""

    async def age() -> None:
        async with cli_server.app.state.sessionmaker() as db:
            await db.execute(
                update(DeviceAuthorization)
                .where(DeviceAuthorization.device_code == device_code)
                .values(last_poll_at=datetime.now(UTC) - timedelta(hours=1))
            )
            await db.commit()

    cli_server.call(age)


def _bearer_status(cli_server: SyncAsgiServer, token: str, path: str) -> int:
    """A plain authenticated GET against the real app, no CLI client."""
    assert cli_server.transport is not None
    with httpx.Client(
        transport=cli_server.transport,
        base_url="http://127.0.0.1",
        headers={"Authorization": f"Bearer {token}"},
    ) as web:
        return web.get(path).status_code


def test_sign_in_pending_then_approved(
    cli_endpoint: Endpoint,
    web_approver: ApproverFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The application-level journey: begin → approve → complete → revoke."""
    from ai_stp_cli.application import auth
    from ai_stp_cli.commands import passport

    monkeypatch.setattr(auth, "endpoint", lambda: cli_endpoint)
    approver = web_approver()

    passport.developer_init({})
    before = passport.developer_show({}).payload

    answer = auth.begin({"provider": "github"})
    approval = answer.payload
    assert approval.user_code
    assert approval.browser_opened is False
    # The second phase is not discoverable from the payload alone (#359): the
    # answer names the task surface that finishes the pending approval.
    assert answer.continuations[0].argv[1:4] == ["start", "--intent", "account"]

    store, _warning = open_store()
    held_pending = session.load_pending(store)
    assert held_pending is not None
    # The display fields ride along so a task opened after `auth login` can
    # still show the code (#359).
    assert held_pending.user_code == approval.user_code
    assert held_pending.verification_uri == approval.verification_uri

    # Not yet approved: a typed answer, the pending record stays.
    with pytest.raises(CliFailure) as pending:
        auth.complete({})
    assert pending.value.code == "AI_STP_AUTHORIZATION_PENDING"

    approved = approver.approve(approval.user_code)
    assert approved.status_code == 200, approved.text

    finished = auth.complete({}).payload
    assert finished.state == "authenticated"
    assert finished.account_id == approver.account_id

    # `ADR-0060`: ownership moves onto the server's account, as a revision.
    after = passport.developer_show({}).payload
    assert after.owner_id == approver.account_id
    assert after.owner_id != before.owner_id
    assert after.parent_revision_ids == [before.revision_id]

    # The pending record is consumed, not left to be polled again.
    assert session.load_pending(store) is None

    # The issued credential revokes through the real logout.
    held = session.load(store)
    assert held is not None
    logout = login.revoke_session(cli_endpoint, held.access_token)
    assert logout.revoked is True


def test_a_foreign_device_key_names_the_rebind_reason(
    cli_server: SyncAsgiServer,
    cli_endpoint: Endpoint,
    web_approver: ApproverFactory,
) -> None:
    """The exchange qualifies a foreign key so the CLI can name the rebind.

    `reason=device_key_foreign` is the detail `_way_back_for` keys the
    `device reset` recovery on (#359); an unqualified denial suggests none.
    This covers the exchange leg; `test_devices_lifecycle` covers
    `POST /v1/devices`.
    """
    from ai_stp_api.slices.devices.crypto import normalize_public_key
    from ai_stp_platform.models import Account, Device

    foreign_owner = new_id("account")
    sessionmaker = cli_server.app.state.sessionmaker

    async def seed() -> None:
        async with sessionmaker() as db:
            db.add(Account(id=foreign_owner))
            db.add(
                Device(
                    id=new_id("device"),
                    account_id=foreign_owner,
                    # The lookup compares the canonical form; seeding the raw
                    # padded key would never match.
                    public_key=normalize_public_key(PUBLIC_KEY),
                    state="active",
                )
            )
            await db.commit()

    cli_server.call(seed)

    approver = web_approver()
    started = login.start(cli_endpoint, "github")
    assert approver.approve(started.user_code).status_code == 200

    with pytest.raises(CliFailure) as raised:
        login.exchange(
            cli_endpoint,
            started,
            device_id=DEVICE_ID,
            public_key=PUBLIC_KEY,
            display_name="boundary-test",
        )
    assert raised.value.code == "AI_STP_PERMISSION_DENIED"
    assert raised.value.details.get("reason") == "device_key_foreign"
    assert any("device reset" in action for action in raised.value.next_actions)


def test_approve_with_an_unknown_code_is_a_typed_answer(
    web_approver: ApproverFactory,
) -> None:
    response = web_approver().approve("XXXX-YYYY")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "AI_STP_NOT_FOUND"


def test_pending_polls_are_paced_and_the_pace_survives_refusals(
    cli_endpoint: Endpoint, cli_server: SyncAsgiServer, web_approver: ApproverFactory
) -> None:
    """Poll pacing is committed before the refusal, so it throttles pending polls too.

    A typed `AUTHORIZATION_PENDING` still leaves `last_poll_at` written; an
    immediate re-poll answers `RATE_LIMITED` instead. Aging the stamp past the
    interval frees the flow without a wait.
    """
    approver = web_approver()

    started = login.start(cli_endpoint, "github")
    with pytest.raises(CliFailure) as pending:
        login.exchange(
            cli_endpoint,
            started,
            device_id=DEVICE_ID,
            public_key=PUBLIC_KEY,
            display_name="boundary-test",
        )
    assert pending.value.code == "AI_STP_AUTHORIZATION_PENDING"

    with pytest.raises(CliFailure) as limited:
        login.exchange(
            cli_endpoint,
            started,
            device_id=DEVICE_ID,
            public_key=PUBLIC_KEY,
            display_name="boundary-test",
        )
    assert limited.value.code == "AI_STP_RATE_LIMITED"

    _age_device_poll(cli_server, started.device_code)
    assert approver.approve(started.user_code).status_code == 200
    tokens = login.exchange(
        cli_endpoint,
        started,
        device_id=DEVICE_ID,
        public_key=PUBLIC_KEY,
        display_name="boundary-test",
    )
    assert tokens.account_id == approver.account_id

    from ai_stp_platform.models import Device

    async def stored_label() -> tuple[str | None, str | None]:
        async with cli_server.app.state.sessionmaker() as db:
            device = await db.get(Device, str(DEVICE_ID))
            if device is None:
                return (None, None)
            return (device.display_name, device.user_agent)

    label, agent = cli_server.call(stored_label)
    assert label == "boundary-test"
    # The exchange also captures the caller's transport metadata.
    assert agent is not None and agent.startswith("ai-stp-cli/")

    with pytest.raises(CliFailure) as limited_again:
        login.exchange(
            cli_endpoint,
            started,
            device_id=DEVICE_ID,
            public_key=PUBLIC_KEY,
            display_name="boundary-test",
        )
    assert limited_again.value.code == "AI_STP_RATE_LIMITED"

    _age_device_poll(cli_server, started.device_code)
    with pytest.raises(CliFailure) as consumed:
        login.exchange(
            cli_endpoint,
            started,
            device_id=DEVICE_ID,
            public_key=PUBLIC_KEY,
            display_name="boundary-test",
        )
    assert consumed.value.code == "AI_STP_AUTHORIZATION_EXPIRED"


def test_concurrent_exchanges_mint_exactly_one_credential_pair(
    cli_server: SyncAsgiServer,
    cli_endpoint: Endpoint,
    web_approver: ApproverFactory,
) -> None:
    """Two pollers that both see `approved` must not both get credentials.

    The poll throttle paces sequential polls but cannot order two requests
    already in flight; the grant's `approved → consumed` transition is claimed
    in one UPDATE so the loser reloads and sees the winner's verdict.
    """
    import asyncio

    from tests.support.api_settings import make_test_auth

    from ai_stp_api.errors import ApiError, ErrorCategory
    from ai_stp_api.slices.auth.device_flow import exchange_device_code

    approver = web_approver()
    started = login.start(cli_endpoint, "github")
    assert approver.approve(started.user_code).status_code == 200
    _age_device_poll(cli_server, started.device_code)

    async def attempt() -> dict[str, object] | ApiError:
        async with cli_server.app.state.sessionmaker() as db:
            try:
                result = await exchange_device_code(
                    db,
                    auth=make_test_auth(),
                    device_code=started.device_code,
                    device_id=new_id("device"),
                    public_key=PUBLIC_KEY,
                    display_name="boundary-test",
                )
                await db.commit()
            except ApiError as error:
                await db.rollback()
                return error
            return result

    async def race() -> tuple[dict[str, object] | ApiError, dict[str, object] | ApiError]:
        return await asyncio.gather(attempt(), attempt())

    outcomes = cli_server.call(race)
    minted = [outcome for outcome in outcomes if isinstance(outcome, dict)]
    refused = [outcome for outcome in outcomes if isinstance(outcome, ApiError)]
    assert len(minted) == 1, "exactly one poller may hold credentials"
    assert minted[0]["account_id"] == approver.account_id
    assert len(refused) == 1
    # The loser's verdict depends on where its initial read lands: before the
    # winner's `last_poll_at` commit it loses the atomic consume and sees
    # `consumed` → EXPIRED; after it, the poll throttle answers first →
    # RATE_LIMITED. Both are honest refusals; the minted-count assertion above
    # is the invariant this test exists for.
    assert refused[0].category in {
        ErrorCategory.AUTHORIZATION_EXPIRED,
        ErrorCategory.RATE_LIMITED,
    }


def test_concurrent_starts_share_one_authorization(
    cli_server: SyncAsgiServer,
) -> None:
    """Two starts racing on one idempotency key commit one row and both get
    it back — the unique key, not the earlier replay read, arbitrates."""
    import asyncio

    from tests.support.api_settings import make_test_auth

    from ai_stp_api.slices.auth.device_flow import start_device_authorization

    key = login.new_idempotency_key()

    async def attempt() -> str:
        async with cli_server.app.state.sessionmaker() as db:
            row = await start_device_authorization(
                db,
                provider="github",
                auth=make_test_auth(),
                idempotency_key=key,
            )
            await db.commit()
            return row.device_code

    async def race() -> tuple[str, str]:
        return await asyncio.gather(attempt(), attempt())

    first, second = cli_server.call(race)
    assert first == second


def test_a_pending_answer_keeps_the_pending_record(
    cli_endpoint: Endpoint,
    web_approver: ApproverFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A machine `complete` asks once; "not yet" must not destroy the code.

    The corpus-mock version stubbed `login.exchange` to prove the bookkeeping.
    Against the real server the pending answer is produced, not simulated.
    """
    from ai_stp_cli.application import auth

    monkeypatch.setattr(auth, "endpoint", lambda: cli_endpoint)
    web_approver()  # the account exists; the code is simply never approved

    auth.begin({"provider": "github"})
    store, _warning = open_store()
    assert session.load_pending(store) is not None

    with pytest.raises(CliFailure) as raised:
        auth.complete({})
    assert raised.value.code == "AI_STP_AUTHORIZATION_PENDING"
    assert session.load_pending(store) is not None, "a pending sign-in was destroyed"


def test_an_expired_authorization_is_a_terminal_decision(
    cli_server: SyncAsgiServer,
    cli_endpoint: Endpoint,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The server's expired answer clears the pending record — not a wait."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from ai_stp_cli.application import auth
    from ai_stp_platform.models import DeviceAuthorization

    monkeypatch.setattr(auth, "endpoint", lambda: cli_endpoint)
    auth.begin({"provider": "github"})
    store, _warning = open_store()
    pending = session.load_pending(store)
    assert pending is not None

    sessionmaker = cli_server.app.state.sessionmaker

    async def expire() -> None:
        async with sessionmaker() as db:
            await db.execute(
                update(DeviceAuthorization)
                .where(DeviceAuthorization.device_code == pending.device_code)
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
            await db.commit()

    cli_server.call(expire)

    with pytest.raises(CliFailure) as raised:
        auth.complete({})
    assert raised.value.code == "AI_STP_AUTHORIZATION_EXPIRED"
    assert session.load_pending(store) is None


def test_waiting_is_opt_in_and_bounded(
    cli_endpoint: Endpoint,
    web_approver: ApproverFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--wait` polls the real server until its own deadline, then gives up.

    The pending record's `expires_in`/`interval` drive the bound — shortening
    them keeps the test at seconds rather than minutes. Each poll is a real
    exchange; the server keeps answering pending because nobody approves.
    """
    import dataclasses

    from ai_stp_cli.application import auth

    monkeypatch.setattr(auth, "endpoint", lambda: cli_endpoint)
    web_approver()

    auth.begin({"provider": "github"})
    store, _warning = open_store()
    pending = session.load_pending(store)
    assert pending is not None
    session.save_pending(store, dataclasses.replace(pending, interval=1, expires_in=2))

    with pytest.raises(CliFailure) as raised:
        auth.complete({"wait": True})
    assert raised.value.code == "AI_STP_AUTHORIZATION_EXPIRED"
    # Expiry is a decision, so the record is gone.
    assert session.load_pending(store) is None


def test_an_approved_code_that_was_never_exchanged_expires(
    cli_endpoint: Endpoint, cli_server: SyncAsgiServer, web_approver: ApproverFactory
) -> None:
    """Approval does not make the code a standing credential-issuing capability.

    The grant's `expires_at` bounds every status, so a code approved but never
    polled past its deadline answers `AUTHORIZATION_EXPIRED` like any other.
    """
    approver = web_approver()
    started = login.start(cli_endpoint, "github")
    assert approver.approve(started.user_code).status_code == 200

    async def expire() -> None:
        async with cli_server.app.state.sessionmaker() as db:
            await db.execute(
                update(DeviceAuthorization)
                .where(DeviceAuthorization.device_code == started.device_code)
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
            await db.commit()

    cli_server.call(expire)

    with pytest.raises(CliFailure) as raised:
        login.exchange(
            cli_endpoint,
            started,
            device_id=DEVICE_ID,
            public_key=PUBLIC_KEY,
            display_name="boundary-test",
        )
    assert raised.value.code == "AI_STP_AUTHORIZATION_EXPIRED"


def test_start_replays_the_idempotency_key(
    cli_server: SyncAsgiServer,
) -> None:
    """A retried start with the same key answers the same pending grant."""
    assert cli_server.transport is not None
    key = login.new_idempotency_key()
    body = {"schema_version": 1, "provider": "github", "idempotency_key": key}
    with httpx.Client(transport=cli_server.transport, base_url="http://127.0.0.1") as http:
        first = http.post("/v1/auth/device", json=body)
        second = http.post("/v1/auth/device", json=body)
        other = http.post(
            "/v1/auth/device",
            json={"schema_version": 1, "provider": "google", "idempotency_key": key},
        )
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["device_code"] == second.json()["device_code"]
    assert first.json()["user_code"] == second.json()["user_code"]
    assert other.status_code == 409
    assert other.json()["error"]["code"] == "AI_STP_CONFLICT"


def test_the_session_pair_reports_and_enforces_distinct_lifetimes(
    cli_endpoint: Endpoint,
    cli_server: SyncAsgiServer,
    web_approver: ApproverFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`expires_in` is the access token's real TTL; the refresh half lives longer.

    The reported value used to claim 24h while both sessions silently lived
    fourteen days. Now the access row expires when the wire said it would and
    the refresh row is a `refresh`-kind session that no ordinary route accepts.
    """
    from ai_stp_cli.application import auth

    monkeypatch.setattr(auth, "endpoint", lambda: cli_endpoint)
    approver = web_approver()
    approval = auth.begin({"provider": "github"}).payload
    assert approver.approve(approval.user_code).status_code == 200
    finished = auth.complete({}).payload
    assert finished.state == "authenticated"

    store, _warning = open_store()
    held = session.load(store)
    assert held is not None

    async def rows() -> list[tuple[str, datetime]]:
        async with cli_server.app.state.sessionmaker() as db:
            from sqlalchemy import select

            result = await db.execute(
                select(AccountSession.kind, AccountSession.expires_at).where(
                    AccountSession.account_id == held.account_id,
                    AccountSession.device_id == held.device_id,
                )
            )
            return [(str(kind), expires) for kind, expires in result.all()]

    cli_rows = cli_server.call(rows)
    kinds = {kind for kind, _expires in cli_rows}
    assert kinds == {"access", "refresh"}
    now = datetime.now(UTC)
    for kind, expires in cli_rows:
        remaining = (expires - now).total_seconds()
        if kind == "access":
            assert remaining <= 86400 + 60
        else:
            assert remaining > 86400

    # The refresh credential is not a general bearer.
    assert _bearer_status(cli_server, held.refresh_token, "/v1/auth/me") == 401
    # The access half still is.
    assert _bearer_status(cli_server, held.access_token, "/v1/auth/me") == 200


def test_refresh_mints_a_new_pair_and_logout_ends_both_halves(
    cli_endpoint: Endpoint,
    cli_server: SyncAsgiServer,
    web_approver: ApproverFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`renew` drives the signed refresh path; logout kills the whole pair."""
    from ai_stp_cli.application import auth

    monkeypatch.setattr(auth, "endpoint", lambda: cli_endpoint)
    approver = web_approver()
    approval = auth.begin({"provider": "github"}).payload
    assert approver.approve(approval.user_code).status_code == 200
    auth.complete({})

    store, _warning = open_store()
    held = session.load(store)
    assert held is not None
    assert _bearer_status(cli_server, held.access_token, "/v1/auth/me") == 200

    renewed = login.renew(cli_endpoint, held)
    assert renewed.account_id == held.account_id
    assert renewed.device_id == held.device_id
    assert renewed.access_token != held.access_token
    assert _bearer_status(cli_server, renewed.access_token, "/v1/auth/me") == 200

    logout = login.revoke_session(cli_endpoint, renewed.access_token)
    assert logout.revoked is True
    # Neither half of the pair survives sign-out.
    assert _bearer_status(cli_server, renewed.access_token, "/v1/auth/me") == 401
    assert _bearer_status(cli_server, renewed.refresh_token, "/v1/auth/me") == 401
    with pytest.raises(CliFailure) as dead:
        login.renew(cli_endpoint, renewed)
    assert dead.value.code == "AI_STP_AUTH_REQUIRED"
