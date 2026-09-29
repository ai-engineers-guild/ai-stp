"""B2B-07 #201: organization invitation links and the email-domain allowlist."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.session import issue_session
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, AuditEvent, OAuthIdentity
from ai_stp_platform.organization_models import (
    CorporateInvitation,
    CorporateMailDelivery,
    Organization,
    OrganizationMembership,
)
from ai_stp_platform.queue.models import Job
from ai_stp_platform.queue.states import JobType

pytestmark = pytest.mark.platform


async def _account_token(
    sessionmaker: async_sessionmaker[AsyncSession], *, account_id: str | None = None
) -> tuple[str, str]:
    async with sessionmaker() as db:
        account = await db.get(Account, account_id) if account_id else None
        if account is None:
            account = Account(id=account_id or new_id("account"), status="active")
            db.add(account)
            await db.flush()
        issued = await issue_session(db, account_id=account.id, device_id=None, ttl_seconds=3600)
        await db.commit()
        return account.id, issued.raw_token


async def _provisioned_account(
    sessionmaker: async_sessionmaker[AsyncSession], email: str
) -> tuple[str, str]:
    """Account with a linked, verified OAuth identity carrying ``email``."""
    account_id, token = await _account_token(sessionmaker)
    async with sessionmaker() as db:
        db.add(
            OAuthIdentity(
                account_id=account_id,
                provider="github",
                provider_subject=email,
                email=email,
                email_verified=True,
                state="linked",
            )
        )
        await db.commit()
    return account_id, token


async def _bootstrap(
    client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    key: str,
) -> tuple[str, dict[str, str], int]:
    account_id, token = await _account_token(sessionmaker)
    response = await client.post(
        "/v1/corporate/bootstrap",
        json={
            "schema_version": 1,
            "organization_name": key,
            "superadmin_account_id": account_id,
            "idempotency_key": key,
        },
        headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
    )
    assert response.status_code == 200, response.text
    organization_id = response.json()["organization_id"]
    async with sessionmaker() as db:
        revision = (
            await db.scalar(
                select(Organization.policy_revision).where(Organization.id == organization_id)
            )
        ) or 1
    return organization_id, {"Authorization": f"Bearer {token}"}, revision


async def test_invitation_lifecycle_create_accept_reuse_and_revoke(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    client, sessionmaker, _settings = db_api_client
    organization_id, auth, revision = await _bootstrap(client, sessionmaker, "invite-lifecycle-001")
    base = f"/v1/corporate/organizations/{organization_id}"

    create = await client.post(
        f"{base}/invitations",
        json={
            "schema_version": 1,
            "recipient_email": "invitee@example.com",
            "display_name": "Invited User",
            "role": "staff",
            "authorization_revision": revision,
            "idempotency_key": "invite-create-0001",
        },
        headers=auth,
    )
    assert create.status_code == 200, create.text
    invitation = create.json()
    assert invitation["state"] == "pending"
    token = invitation["token"]
    assert token

    # Idempotent replay of the create returns the stored view without a secret.
    replay = await client.post(
        f"{base}/invitations",
        json={
            "schema_version": 1,
            "recipient_email": "invitee@example.com",
            "display_name": "Invited User",
            "role": "staff",
            "authorization_revision": revision,
            "idempotency_key": "invite-create-0001",
        },
        headers=auth,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["invitation_id"] == invitation["invitation_id"]
    assert replay.json()["token"] is None

    listed = await client.get(f"{base}/invitations", headers=auth)
    assert listed.status_code == 200, listed.text
    assert [item["invitation_id"] for item in listed.json()["items"]] == [
        invitation["invitation_id"]
    ]
    assert listed.json()["items"][0]["token"] is None

    # Bad token is rejected and audited.
    _, invitee_token = await _provisioned_account(sessionmaker, "invitee@example.com")
    bad_token = await client.post(
        f"/v1/corporate/invitations/{invitation['invitation_id']}/accept",
        json={
            "schema_version": 1,
            "token": "tok_" + "0" * 40,
            "idempotency_key": "accept-bad-00001",
        },
        headers={"Authorization": f"Bearer {invitee_token}"},
    )
    assert bad_token.status_code == 400, bad_token.text

    accepted = await client.post(
        f"/v1/corporate/invitations/{invitation['invitation_id']}/accept",
        json={"schema_version": 1, "token": token, "idempotency_key": "accept-ok-000001"},
        headers={"Authorization": f"Bearer {invitee_token}"},
    )
    assert accepted.status_code == 200, accepted.text
    member = accepted.json()
    assert member["role"] == "staff"
    assert member["state"] == "active"
    async with sessionmaker() as db:
        membership = await db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.account_id == member["account_id"],
            )
        )
        assert membership is not None and membership.role == "staff"

    # The accepting account can safely replay; anyone else cannot reuse it.
    _, stranger_token = await _provisioned_account(sessionmaker, "stranger@example.com")
    replay_accept = await client.post(
        f"/v1/corporate/invitations/{invitation['invitation_id']}/accept",
        json={"schema_version": 1, "token": token, "idempotency_key": "accept-replay-001"},
        headers={"Authorization": f"Bearer {invitee_token}"},
    )
    assert replay_accept.status_code == 200, replay_accept.text
    reuse = await client.post(
        f"/v1/corporate/invitations/{invitation['invitation_id']}/accept",
        json={"schema_version": 1, "token": token, "idempotency_key": "accept-reuse-0001"},
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert reuse.status_code == 409, reuse.text

    # A second invitation: revoke, then accept is rejected.
    second = await client.post(
        f"{base}/invitations",
        json={
            "schema_version": 1,
            "recipient_email": "second@example.com",
            "display_name": "Second User",
            "role": "lead",
            "authorization_revision": revision,
            "idempotency_key": "invite-create-0002",
        },
        headers=auth,
    )
    assert second.status_code == 200, second.text
    revoked = await client.post(
        f"{base}/invitations/{second.json()['invitation_id']}/revoke",
        json={
            "schema_version": 1,
            "authorization_revision": revision,
            "idempotency_key": "invite-revoke-0001",
        },
        headers=auth,
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["state"] == "revoked"
    _, second_token = await _provisioned_account(sessionmaker, "second@example.com")
    accept_revoked = await client.post(
        f"/v1/corporate/invitations/{second.json()['invitation_id']}/accept",
        json={
            "schema_version": 1,
            "token": second.json()["token"],
            "idempotency_key": "accept-revoked-1",
        },
        headers={"Authorization": f"Bearer {second_token}"},
    )
    assert accept_revoked.status_code == 409, accept_revoked.text

    # Audit trail exists and never carries the raw token.
    async with sessionmaker() as db:
        events = (
            (
                await db.execute(
                    select(AuditEvent).where(
                        AuditEvent.organization_id == organization_id,
                        AuditEvent.action.like("member.invitation%"),
                    )
                )
            )
            .scalars()
            .all()
        )
        actions = {event.action for event in events}
        assert {
            "member.invitation_created",
            "member.invitation_accepted",
            "member.invitation_revoked",
            "member.invitation_token_invalid",
            "member.invitation_replayed",
        } <= actions
        for event in events:
            assert token not in str(event.payload)
            assert token not in str(event.reason)


async def test_invitation_expiry_and_domain_policy(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    client, sessionmaker, _settings = db_api_client
    organization_id, auth, revision = await _bootstrap(client, sessionmaker, "invite-expiry-0001")
    base = f"/v1/corporate/organizations/{organization_id}"

    policy = await client.put(
        f"{base}/membership/policy",
        json={
            "schema_version": 1,
            "allowed_email_domains": ["allowed.example", "@sub.example.com"],
            "authorization_revision": revision,
            "idempotency_key": "policy-write-0001",
        },
        headers=auth,
    )
    assert policy.status_code == 200, policy.text
    new_revision = policy.json()["authorization_revision"]
    assert new_revision != revision
    assert policy.json()["allowed_email_domains"] == ["allowed.example", "sub.example.com"]

    # Member creation honors the allowlist too.
    denied_member = await client.post(
        f"{base}/members",
        json={
            "schema_version": 1,
            "email": "nope@other.example",
            "display_name": "Denied",
            "role": "staff",
            "authorization_revision": new_revision,
            "idempotency_key": "member-denied-0001",
        },
        headers=auth,
    )
    assert denied_member.status_code == 400, denied_member.text

    denied_invite = await client.post(
        f"{base}/invitations",
        json={
            "schema_version": 1,
            "recipient_email": "nope@other.example",
            "display_name": "Denied",
            "role": "staff",
            "authorization_revision": new_revision,
            "idempotency_key": "invite-denied-0001",
        },
        headers=auth,
    )
    assert denied_invite.status_code == 400, denied_invite.text

    create = await client.post(
        f"{base}/invitations",
        json={
            "schema_version": 1,
            "recipient_email": "ok@allowed.example",
            "display_name": "Allowed",
            "role": "staff",
            "authorization_revision": new_revision,
            "idempotency_key": "invite-allowed-0001",
        },
        headers=auth,
    )
    assert create.status_code == 200, create.text
    invitation = create.json()

    # Force expiry, then accept rejects and persists the transition.
    async with sessionmaker() as db:
        row = await db.get(CorporateInvitation, invitation["invitation_id"])
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    _, ok_token = await _provisioned_account(sessionmaker, "ok@allowed.example")
    expired = await client.post(
        f"/v1/corporate/invitations/{invitation['invitation_id']}/accept",
        json={
            "schema_version": 1,
            "token": invitation["token"],
            "idempotency_key": "accept-expired-1",
        },
        headers={"Authorization": f"Bearer {ok_token}"},
    )
    assert expired.status_code == 400, expired.text
    async with sessionmaker() as db:
        row = await db.get(CorporateInvitation, invitation["invitation_id"])
        assert row is not None and row.state == "expired"

    # After the policy is relaxed to another domain, accepting the old
    # recipient email is rejected at the domain gate.
    relaxed = await client.put(
        f"{base}/membership/policy",
        json={
            "schema_version": 1,
            "allowed_email_domains": ["else.example"],
            "authorization_revision": new_revision,
            "idempotency_key": "policy-write-0002",
        },
        headers=auth,
    )
    assert relaxed.status_code == 200, relaxed.text
    pending = await client.post(
        f"{base}/invitations",
        json={
            "schema_version": 1,
            "recipient_email": "user@else.example",
            "display_name": "Else",
            "role": "staff",
            "authorization_revision": relaxed.json()["authorization_revision"],
            "idempotency_key": "invite-else-0001",
        },
        headers=auth,
    )
    assert pending.status_code == 200, pending.text
    # Tighten the policy again so the pending invite's domain is now excluded.
    await client.put(
        f"{base}/membership/policy",
        json={
            "schema_version": 1,
            "allowed_email_domains": ["blocked.example"],
            "authorization_revision": relaxed.json()["authorization_revision"],
            "idempotency_key": "policy-write-0003",
        },
        headers=auth,
    )
    _, else_token = await _provisioned_account(sessionmaker, "user@else.example")
    domain_rejected = await client.post(
        f"/v1/corporate/invitations/{pending.json()['invitation_id']}/accept",
        json={
            "schema_version": 1,
            "token": pending.json()["token"],
            "idempotency_key": "accept-domain-001",
        },
        headers={"Authorization": f"Bearer {else_token}"},
    )
    assert domain_rejected.status_code == 400, domain_rejected.text


async def test_invitation_authorization_and_duplicate_member(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    client, sessionmaker, _settings = db_api_client
    organization_id, auth, revision = await _bootstrap(client, sessionmaker, "invite-authz-00001")
    base = f"/v1/corporate/organizations/{organization_id}"
    body = {
        "schema_version": 1,
        "recipient_email": "denied@example.com",
        "display_name": "Denied",
        "role": "staff",
        "authorization_revision": revision,
        "idempotency_key": "invite-authz-0001",
    }
    assert (await client.post(f"{base}/invitations", json=body)).status_code in {401, 403}
    _, foreign_token = await _account_token(sessionmaker)
    foreign = await client.post(
        f"{base}/invitations",
        json=body,
        headers={"Authorization": f"Bearer {foreign_token}"},
    )
    assert foreign.status_code in {401, 403}, foreign.text

    # An OAuth-joined member cannot be invited again.
    member_id, member_token = await _provisioned_account(sessionmaker, "joined@example.com")
    async with sessionmaker() as db:
        db.add(
            OrganizationMembership(
                organization_id=organization_id,
                account_id=member_id,
                display_name="Joined",
                role="staff",
                state="active",
            )
        )
        await db.commit()
    duplicate = await client.post(
        f"{base}/invitations",
        json={
            **body,
            "recipient_email": "joined@example.com",
            "idempotency_key": "invite-dup-000001",
        },
        headers=auth,
    )
    assert duplicate.status_code == 409, duplicate.text
    # A member without member.invite cannot create invitations either.
    denied = await client.post(
        f"{base}/invitations",
        json={**body, "idempotency_key": "invite-authz-0002"},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert denied.status_code in {401, 403}, denied.text

    unknown = await client.post(
        "/v1/corporate/invitations/invite_00000000000000000000000000/accept",
        json={
            "schema_version": 1,
            "token": "tok_" + "0" * 40,
            "idempotency_key": "accept-404-00001",
        },
        headers=auth,
    )
    assert unknown.status_code == 404, unknown.text


async def test_invitation_mail_delivery_state_surfaces(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    """The invitation views join the mail ledger so a failed delivery is
    visible to admins instead of failing silently."""
    client, sessionmaker, _settings = db_api_client
    organization_id, auth, revision = await _bootstrap(client, sessionmaker, "invite-mail-000001")
    base = f"/v1/corporate/organizations/{organization_id}"

    create = await client.post(
        f"{base}/invitations",
        json={
            "schema_version": 1,
            "recipient_email": "mail@example.com",
            "display_name": "Mail User",
            "role": "staff",
            "authorization_revision": revision,
            "idempotency_key": "invite-mail-00001",
        },
        headers=auth,
    )
    assert create.status_code == 200, create.text
    invitation = create.json()
    assert invitation["delivery_state"] == "queued"
    assert invitation["delivery_error"] is None

    # A ledger row and a delivery job exist; the ledger never holds the token.
    async with sessionmaker() as db:
        delivery = await db.scalar(
            select(CorporateMailDelivery).where(
                CorporateMailDelivery.invitation_id == invitation["invitation_id"]
            )
        )
        assert delivery is not None
        assert delivery.state == "queued"
        assert delivery.to_email_normalized == "mail@example.com"
        token = invitation["token"]
        for value in vars(delivery).values():
            assert token not in str(value)
        job = await db.scalar(
            select(Job).where(
                Job.idempotency_key == f"deliver_corporate_invitation:{invitation['invitation_id']}"
            )
        )
        assert job is not None
        assert job.job_type == JobType.DELIVER_CORPORATE_INVITATION
        assert job.payload.get("delivery_id") == delivery.id

    # Idempotent replay answers the stored view.
    replay = await client.post(
        f"{base}/invitations",
        json={
            "schema_version": 1,
            "recipient_email": "mail@example.com",
            "display_name": "Mail User",
            "role": "staff",
            "authorization_revision": revision,
            "idempotency_key": "invite-mail-00001",
        },
        headers=auth,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["delivery_state"] == "queued"
    assert replay.json()["token"] is None

    # A worker failure lands in the ledger and surfaces on the list.
    async with sessionmaker() as db:
        row = await db.get(CorporateMailDelivery, delivery.id)
        assert row is not None
        row.state = "failed"
        row.error = "resend: sender domain is not verified"
        await db.commit()
    listed = await client.get(f"{base}/invitations", headers=auth)
    assert listed.status_code == 200, listed.text
    item = next(
        entry
        for entry in listed.json()["items"]
        if entry["invitation_id"] == invitation["invitation_id"]
    )
    assert item["delivery_state"] == "failed"
    assert item["delivery_error"] == "resend: sender domain is not verified"
    assert item["token"] is None


async def test_invitation_email_confirmation_flow(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    """A sign-in whose verified email misses the invite claims it; the invited
    inbox confirms by mailed token and activates the membership."""
    client, sessionmaker, _settings = db_api_client
    organization_id, auth, revision = await _bootstrap(client, sessionmaker, "invite-confirm-01")
    base = f"/v1/corporate/organizations/{organization_id}"

    create = await client.post(
        f"{base}/invitations",
        json={
            "schema_version": 1,
            "recipient_email": "invitee@example.com",
            "display_name": "Invited User",
            "role": "staff",
            "authorization_revision": revision,
            "idempotency_key": "invite-confirm-0001",
        },
        headers=auth,
    )
    assert create.status_code == 200, create.text
    invitation = create.json()
    token = invitation["token"]
    accept_url = f"/v1/corporate/invitations/{invitation['invitation_id']}/accept"
    confirm_url = f"/v1/corporate/invitations/{invitation['invitation_id']}/confirm"

    # Confirm on an unclaimed invitation cannot proceed.
    claimant_id, claimant_token = await _provisioned_account(sessionmaker, "other-mail@example.com")
    early = await client.post(
        confirm_url,
        json={"schema_version": 1, "token": token, "idempotency_key": "confirm-early-01"},
        headers={"Authorization": f"Bearer {claimant_token}"},
    )
    assert early.status_code == 409, early.text

    # A sign-in whose verified email differs claims the invitation: the API
    # binds the claimant and mails a confirmation to the invited address.
    claimed = await client.post(
        accept_url,
        json={"schema_version": 1, "token": token, "idempotency_key": "accept-claim-001"},
        headers={"Authorization": f"Bearer {claimant_token}"},
    )
    assert claimed.status_code == 409, claimed.text
    assert claimed.json()["error"]["details"]["reason"] == "email_confirmation_sent"

    async with sessionmaker() as db:
        row = await db.get(CorporateInvitation, invitation["invitation_id"])
        assert row is not None
        assert row.state == "email_confirm_pending"
        assert row.claimant_account_id == claimant_id
        assert row.confirmation_token_hash
        assert token not in row.confirmation_token_hash
        jobs = (
            (
                await db.execute(
                    select(Job).where(Job.idempotency_key.like("deliver_corporate_invitation:%"))
                )
            )
            .scalars()
            .all()
        )
        confirm_jobs = [job for job in jobs if job.payload.get("mail_variant") == "confirmation"]
        assert len(confirm_jobs) == 1
        confirm_token = confirm_jobs[0].payload["confirm_token"]
        assert isinstance(confirm_token, str) and confirm_token != token
        delivery = await db.scalar(
            select(CorporateMailDelivery).where(CorporateMailDelivery.invitation_id == row.id)
        )
        assert delivery is not None and delivery.state == "queued"
        for value in vars(delivery).values():
            assert confirm_token not in str(value)

    # The listed view exposes the claim state to admins.
    listed = await client.get(f"{base}/invitations", headers=auth)
    item = next(
        entry
        for entry in listed.json()["items"]
        if entry["invitation_id"] == invitation["invitation_id"]
    )
    assert item["state"] == "email_confirm_pending"
    assert item["claimant_account_id"] == claimant_id

    # A different account cannot hijack the claim.
    _, rival_token = await _provisioned_account(sessionmaker, "rival@example.com")
    rival = await client.post(
        accept_url,
        json={"schema_version": 1, "token": token, "idempotency_key": "accept-rival-001"},
        headers={"Authorization": f"Bearer {rival_token}"},
    )
    assert rival.status_code == 409, rival.text

    # Confirm needs the mailed token and the claimant session.
    bad_confirm = await client.post(
        confirm_url,
        json={
            "schema_version": 1,
            "token": "tok_" + "0" * 40,
            "idempotency_key": "confirm-bad-0001",
        },
        headers={"Authorization": f"Bearer {claimant_token}"},
    )
    assert bad_confirm.status_code == 400, bad_confirm.text
    wrong_account = await client.post(
        confirm_url,
        json={
            "schema_version": 1,
            "token": confirm_token,
            "idempotency_key": "confirm-rival-01",
        },
        headers={"Authorization": f"Bearer {rival_token}"},
    )
    assert wrong_account.status_code == 409, wrong_account.text

    # The claimant re-accepting resends the confirmation with a rotated token.
    resend = await client.post(
        accept_url,
        json={"schema_version": 1, "token": token, "idempotency_key": "accept-resend-01"},
        headers={"Authorization": f"Bearer {claimant_token}"},
    )
    assert resend.status_code == 409, resend.text
    async with sessionmaker() as db:
        jobs = (
            (
                await db.execute(
                    select(Job).where(Job.idempotency_key.like("deliver_corporate_invitation:%"))
                )
            )
            .scalars()
            .all()
        )
        confirm_jobs = [job for job in jobs if job.payload.get("mail_variant") == "confirmation"]
        assert len(confirm_jobs) == 2
        rotated = [
            job.payload["confirm_token"]
            for job in confirm_jobs
            if job.payload["confirm_token"] != confirm_token
        ]
        assert len(rotated) == 1
        confirm_token = rotated[0]
        assert isinstance(confirm_token, str)

    confirmed = await client.post(
        confirm_url,
        json={
            "schema_version": 1,
            "token": confirm_token,
            "idempotency_key": "confirm-ok-000001",
        },
        headers={"Authorization": f"Bearer {claimant_token}"},
    )
    assert confirmed.status_code == 200, confirmed.text
    member = confirmed.json()
    assert member["role"] == "staff" and member["state"] == "active"

    async with sessionmaker() as db:
        row = await db.get(CorporateInvitation, invitation["invitation_id"])
        assert row is not None
        assert row.state == "accepted"
        assert row.accepted_account_id == claimant_id
        assert row.confirmation_token_hash is None
        membership = await db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.account_id == claimant_id,
            )
        )
        assert membership is not None and membership.role == "staff"
        events = (
            (
                await db.execute(
                    select(AuditEvent).where(
                        AuditEvent.organization_id == organization_id,
                        AuditEvent.action.like("member.invitation%"),
                    )
                )
            )
            .scalars()
            .all()
        )
        actions = {event.action for event in events}
        assert {
            "member.invitation_email_confirm_sent",
            "member.invitation_claimed",
            "member.invitation_confirm_token_invalid",
            "member.invitation_confirm_account_mismatch",
            "member.invitation_accepted",
        } <= actions
        for event in events:
            assert confirm_token not in str(event.payload)
            assert confirm_token not in str(event.reason)

    # Confirm replays idempotently for the accepting account.
    replay = await client.post(
        confirm_url,
        json={
            "schema_version": 1,
            "token": confirm_token,
            "idempotency_key": "confirm-replay-01",
        },
        headers={"Authorization": f"Bearer {claimant_token}"},
    )
    assert replay.status_code == 200, replay.text
