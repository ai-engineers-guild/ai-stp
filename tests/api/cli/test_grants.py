"""Grant journeys: the real `/v1/grants` surface over the seeded corpus.

Replaces the `/v1`-mock journeys in `tests/unit/test_cli_grants.py`. Ownership
comes from the seed (`SEED_OWNER_ACCOUNT_ID` owns `FIXTURE_COMPONENT_ID`), the
recipient is a real account, and the invitation token is read from the outbox
row the delivery job carries — the test-side equivalent of the mailbox. What
stays in the unit file is transport fault injection (a dropped connection
re-sends the same idempotency key) and the local confirmation/registry gates.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable

import pytest
from sqlalchemy import select
from tests.api.cli.conftest import WebApprover, issue_token
from tests.support.asgi_sync import SyncAsgiServer
from tests.support.catalog_seed import FIXTURE_COMPONENT_ID, SEED_OWNER_ACCOUNT_ID

from ai_stp_cli.cloud import grants, session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.grants import (
    CliGrantAccessView,
    DirectGrantCreateRequest,
    GrantAcceptRequest,
    GrantInvitationCreateRequest,
    GrantRevokeRequest,
)
from ai_stp_platform.models import OAuthIdentity
from ai_stp_platform.queue.models import Job
from ai_stp_platform.queue.states import JobType

GRANTEE_EMAIL = "grantee@example.test"


def _direct_request(recipient: str) -> DirectGrantCreateRequest:
    return DirectGrantCreateRequest(
        object_kind="component",
        stable_id=FIXTURE_COMPONENT_ID,
        major=1,
        recipient_kind="user_id",
        recipient=recipient,
        idempotency_key=secrets.token_hex(8),
    )


def _invitation_request() -> GrantInvitationCreateRequest:
    return GrantInvitationCreateRequest(
        object_kind="component",
        stable_id=FIXTURE_COMPONENT_ID,
        major=1,
        recipient_email=GRANTEE_EMAIL,
        idempotency_key=secrets.token_hex(8),
    )


def _link_verified_email(cli_server: SyncAsgiServer, account_id: str, email: str) -> None:
    """The grantee's verified provider identity — what `accept` matches on."""
    sessionmaker = cli_server.app.state.sessionmaker

    async def seed() -> None:
        async with sessionmaker() as db:
            db.add(
                OAuthIdentity(
                    account_id=account_id,
                    provider="github",
                    provider_subject=secrets.token_hex(8),
                    email=email,
                    email_verified=True,
                    state="linked",
                )
            )
            await db.commit()

    cli_server.call(seed)


def _delivered_token(cli_server: SyncAsgiServer, invitation_id: str) -> str:
    """Read the token the delivery job carries — the test-side mailbox."""
    sessionmaker = cli_server.app.state.sessionmaker

    async def read() -> str | None:
        async with sessionmaker() as db:
            rows = list(
                (
                    await db.execute(
                        select(Job).where(Job.job_type == JobType.DELIVER_INVITATION.value)
                    )
                )
                .scalars()
                .all()
            )
            for row in rows:
                if row.payload.get("invitation_id") == invitation_id:
                    token = row.payload.get("accept_token")
                    return token if isinstance(token, str) else None
            return None

    token = cli_server.call(read)
    assert token is not None, "the invitation was never queued for delivery"
    return token


def test_a_direct_grant_reaches_the_grantee_and_revokes(
    cli_server: SyncAsgiServer,
    cli_endpoint: Endpoint,
    seeded_catalog: None,
    web_approver: Callable[[], WebApprover],
) -> None:
    owner_token = issue_token(cli_server, SEED_OWNER_ACCOUNT_ID)
    grantee = web_approver()

    grant = grants.direct(cli_endpoint, owner_token, _direct_request(grantee.account_id))
    assert grant.state == "active"
    assert grant.stable_id == FIXTURE_COMPONENT_ID

    owner_view = grants.list_all(cli_endpoint, owner_token)
    assert any(item.grant_id == grant.grant_id for item in owner_view.grants)
    # list_grants selects on owner OR grantee — the recipient sees it too.
    grantee_view = grants.list_all(cli_endpoint, grantee.token)
    assert any(item.grant_id == grant.grant_id for item in grantee_view.grants)

    revoked = grants.revoke_grant(
        cli_endpoint,
        owner_token,
        grant.grant_id,
        GrantRevokeRequest(reason="done", idempotency_key=secrets.token_hex(8)),
    )
    assert revoked.revoked is True
    assert revoked.local_bytes_retained is True


def test_an_invitation_is_accepted_with_the_delivered_token(
    cli_server: SyncAsgiServer,
    cli_endpoint: Endpoint,
    seeded_catalog: None,
    web_approver: Callable[[], WebApprover],
) -> None:
    owner_token = issue_token(cli_server, SEED_OWNER_ACCOUNT_ID)
    grantee = web_approver()
    _link_verified_email(cli_server, grantee.account_id, GRANTEE_EMAIL)

    invitation = grants.invite(cli_endpoint, owner_token, _invitation_request())
    assert invitation.invitation_id
    assert invitation.state == "pending"

    token = _delivered_token(cli_server, invitation.invitation_id)
    grant = grants.accept(
        cli_endpoint,
        grantee.token,
        invitation.invitation_id,
        GrantAcceptRequest(token=token, idempotency_key=secrets.token_hex(8)),
    )
    assert grant.state == "active"
    assert grant.grantee_account_id == grantee.account_id

    owner_view = grants.list_all(cli_endpoint, owner_token)
    assert any(
        item.invitation_id == invitation.invitation_id and item.state == "accepted"
        for item in owner_view.invitations
    )
    assert any(item.grant_id == grant.grant_id for item in owner_view.grants)


def test_a_non_owner_is_refused_by_the_server(
    cli_endpoint: Endpoint,
    seeded_catalog: None,
    web_approver: Callable[[], WebApprover],
) -> None:
    """The decision is the server's, not the client's: PERMISSION, not a guess."""
    outsider = web_approver()

    with pytest.raises(CliFailure) as direct:
        grants.direct(cli_endpoint, outsider.token, _direct_request(outsider.account_id))
    assert direct.value.code == "AI_STP_PERMISSION_DENIED"

    with pytest.raises(CliFailure) as invite:
        grants.invite(cli_endpoint, outsider.token, _invitation_request())
    assert invite.value.code == "AI_STP_PERMISSION_DENIED"


def test_the_grant_command_converts_the_real_wire_view(
    cli_server: SyncAsgiServer,
    cli_endpoint: Endpoint,
    seeded_catalog: None,
    web_approver: Callable[[], WebApprover],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_stp_cli.commands import grants as command

    owner_token = issue_token(cli_server, SEED_OWNER_ACCOUNT_ID)
    grantee = web_approver()

    def authenticated(_purpose: str) -> session.Session:
        return session.Session(
            account_id=SEED_OWNER_ACCOUNT_ID,
            device_id="device_test",
            access_token=owner_token,
            refresh_token="",
            expires_at="2099-01-01T00:00:00.000Z",
        )

    monkeypatch.setattr(command, "_session", authenticated)
    monkeypatch.setattr(command, "endpoint", lambda: cli_endpoint)

    result = command.direct(
        {
            "kind": "component",
            "id": FIXTURE_COMPONENT_ID,
            "major": 1,
            "recipient-kind": "user_id",
            "recipient": grantee.account_id,
            "idempotency-key": secrets.token_hex(8),
            "confirm": True,
        }
    ).payload

    assert isinstance(result, CliGrantAccessView)
    assert result.stable_id == FIXTURE_COMPONENT_ID
    assert result.state == "active"
