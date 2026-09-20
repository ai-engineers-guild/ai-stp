"""The device sign-in journey: real CLI client code against the real `/v1` app.

Replaces the `#71`-mock journey in `tests/unit/test_cli_cloud.py`. The corpus
mock still owns wire-format cases; this file owns the journey — pending is a
typed answer, approval happens through the same endpoint a browser uses, and
the issued credentials revoke through the same logout the production server
serves.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.support.asgi_sync import SyncAsgiServer

from ai_stp_api.session import issue_session
from ai_stp_cli.cloud import login, session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.secrets import open_store
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account

DEVICE_ID = new_id("device")
PUBLIC_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


async def _seed_web_session(sessionmaker: async_sessionmaker[AsyncSession], account_id: str) -> str:
    """An account with a browser session — the approver side of the flow."""
    async with sessionmaker() as db:
        db.add(Account(id=account_id))
        issued = await issue_session(db, account_id=account_id, device_id=None, ttl_seconds=3600)
        await db.commit()
        return issued.raw_token


def _approve(server: SyncAsgiServer, user_code: str, session_token: str) -> httpx.Response:
    """The browser side: approve the user code under the seeded web session."""
    assert server.transport is not None
    with httpx.Client(
        transport=server.transport,
        base_url="http://127.0.0.1",
        headers={"Authorization": f"Bearer {session_token}"},
    ) as web:
        return web.post("/v1/auth/device/approve", json={"user_code": user_code})


def test_sign_in_pending_then_approved(
    cli_server: SyncAsgiServer,
    cli_endpoint: Endpoint,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The application-level journey: begin → approve → complete → revoke."""
    from ai_stp_cli.application import auth
    from ai_stp_cli.commands import passport

    monkeypatch.setattr(auth, "endpoint", lambda: cli_endpoint)
    sessionmaker = cli_server.app.state.sessionmaker
    account_id = new_id("account")
    web_token = cli_server.call(_seed_web_session, sessionmaker, account_id)

    passport.developer_init({})
    before = passport.developer_show({}).payload

    approval = auth.begin({"provider": "github"}).payload
    assert approval.user_code
    assert approval.browser_opened is False

    # Not yet approved: a typed answer, the pending record stays.
    with pytest.raises(CliFailure) as pending:
        auth.complete({})
    assert pending.value.code == "AI_STP_AUTHORIZATION_PENDING"

    approved = _approve(cli_server, approval.user_code, web_token)
    assert approved.status_code == 200, approved.text

    finished = auth.complete({}).payload
    assert finished.state == "authenticated"
    assert finished.account_id == account_id

    # `ADR-0060`: ownership moves onto the server's account, as a revision.
    after = passport.developer_show({}).payload
    assert after.owner_id == account_id
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
    cli_server: SyncAsgiServer, cli_endpoint: Endpoint
) -> None:
    sessionmaker = cli_server.app.state.sessionmaker
    web_token = cli_server.call(_seed_web_session, sessionmaker, new_id("account"))

    response = _approve(cli_server, "XXXX-YYYY", web_token)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "AI_STP_NOT_FOUND"


def test_pending_polls_are_not_paced_but_a_success_is(
    cli_server: SyncAsgiServer, cli_endpoint: Endpoint
) -> None:
    """The server persists `last_poll_at` only on a committed request.

    A pending poll raises a typed error, `get_db` rolls back, and the pacing
    write goes with it — so pending polls answer `AUTHORIZATION_PENDING` every
    time. A *successful* exchange commits `last_poll_at`, and a re-poll inside
    the interval is rate limited before the consumed-status check.
    """
    sessionmaker = cli_server.app.state.sessionmaker
    account_id = new_id("account")
    web_token = cli_server.call(_seed_web_session, sessionmaker, account_id)

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

    assert _approve(cli_server, started.user_code, web_token).status_code == 200
    tokens = login.exchange(
        cli_endpoint,
        started,
        device_id=DEVICE_ID,
        public_key=PUBLIC_KEY,
        display_name="boundary-test",
    )
    assert tokens.account_id == account_id

    with pytest.raises(CliFailure) as limited:
        login.exchange(
            cli_endpoint,
            started,
            device_id=DEVICE_ID,
            public_key=PUBLIC_KEY,
            display_name="boundary-test",
        )
    assert limited.value.code == "AI_STP_RATE_LIMITED"
