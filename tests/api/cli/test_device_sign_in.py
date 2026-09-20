"""The device sign-in journey: real CLI client code against the real `/v1` app.

Replaces the `#71`-mock journey in `tests/unit/test_cli_cloud.py`. The corpus
mock still owns wire-format cases; this file owns the journey — pending is a
typed answer, approval happens through the same endpoint a browser uses, and
the issued credentials revoke through the same logout the production server
serves.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from tests.api.cli.conftest import WebApprover
from tests.support.asgi_sync import SyncAsgiServer

from ai_stp_cli.cloud import login, session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.secrets import open_store
from ai_stp_foundation.ids import new_id

DEVICE_ID = new_id("device")
PUBLIC_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

ApproverFactory = Callable[[], WebApprover]


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

    approval = auth.begin({"provider": "github"}).payload
    assert approval.user_code
    assert approval.browser_opened is False

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

    store, _warning = open_store()
    # The pending record is consumed, not left to be polled again.
    assert session.load_pending(store) is None

    # The issued credential revokes through the real logout.
    held = session.load(store)
    assert held is not None
    logout = login.revoke_session(cli_endpoint, held.access_token)
    assert logout.revoked is True


def test_approve_with_an_unknown_code_is_a_typed_answer(
    web_approver: ApproverFactory,
) -> None:
    response = web_approver().approve("XXXX-YYYY")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "AI_STP_NOT_FOUND"


def test_pending_polls_are_not_paced_but_a_success_is(
    cli_endpoint: Endpoint, web_approver: ApproverFactory
) -> None:
    """The server persists `last_poll_at` only on a committed request.

    A pending poll raises a typed error, `get_db` rolls back, and the pacing
    write goes with it — so pending polls answer `AUTHORIZATION_PENDING` every
    time. A *successful* exchange commits `last_poll_at`, and a re-poll inside
    the interval is rate limited before the consumed-status check.
    """
    approver = web_approver()

    started = login.start(cli_endpoint, "github")
    for _ in range(2):
        with pytest.raises(CliFailure) as pending:
            login.exchange(
                cli_endpoint,
                started,
                device_id=DEVICE_ID,
                public_key=PUBLIC_KEY,
                display_name="boundary-test",
            )
        assert pending.value.code == "AI_STP_AUTHORIZATION_PENDING"

    assert approver.approve(started.user_code).status_code == 200
    tokens = login.exchange(
        cli_endpoint,
        started,
        device_id=DEVICE_ID,
        public_key=PUBLIC_KEY,
        display_name="boundary-test",
    )
    assert tokens.account_id == approver.account_id

    with pytest.raises(CliFailure) as limited:
        login.exchange(
            cli_endpoint,
            started,
            device_id=DEVICE_ID,
            public_key=PUBLIC_KEY,
            display_name="boundary-test",
        )
    assert limited.value.code == "AI_STP_RATE_LIMITED"


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
