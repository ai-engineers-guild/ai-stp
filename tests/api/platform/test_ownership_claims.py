# pyright: reportUnusedFunction=false
"""API coverage for verified-maintainer claim transfer (SPEC-057 REQ-5717)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.app import create_app
from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import (
    Account,
    AccountAuthorVerification,
    AuditEvent,
    CatalogMetadata,
    Device,
    OwnershipClaim,
    OwnershipRevision,
)
from ai_stp_platform.official_upstream import OFFICIAL_ACCOUNT_ID

pytestmark = pytest.mark.platform

COMPONENT_ID = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
PASSPORT = {
    "schema_version": 1,
    "kind": "component",
    "stable_id": COMPONENT_ID,
    "owner_id": OFFICIAL_ACCOUNT_ID,
    "name": "official-skill",
    "description": "Official catalog component under claim transfer tests.",
    "version": "1.0",
}


@pytest_asyncio.fixture
async def harness(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings, str]]:
    pre = settings_factory(database_url=migrated_database_url)
    app0 = create_app(pre)
    staff_id = ""
    async with app0.router.lifespan_context(app0):
        staff_id, _device, _token = await _seed_account_device(app0.state.sessionmaker)
    settings = settings_factory(
        database_url=migrated_database_url,
        admin_account_ids=staff_id,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app.state.sessionmaker, settings, staff_id


async def _seed_account_device(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> tuple[str, str, str]:
    async with sessionmaker() as db:
        account = Account(id=new_id("account"))
        device = Device(
            id=new_id("device"),
            account_id=account.id,
            public_key="dGVzdC1wdWJsaWMta2V5LWNsYWltcw==",
            state="active",
        )
        db.add(account)
        db.add(device)
        await db.flush()
        issued = await issue_session(
            db, account_id=account.id, device_id=device.id, ttl_seconds=3600
        )
        await db.commit()
        return account.id, device.id, issued.raw_token


async def _token_for(sessionmaker: async_sessionmaker[AsyncSession], account_id: str) -> str:
    async with sessionmaker() as db:
        device = Device(
            id=new_id("device"),
            account_id=account_id,
            public_key="dGVzdC1wdWJsaWMtc3RhZmYtY2xhaW0=",
            state="active",
        )
        db.add(device)
        await db.flush()
        issued = await issue_session(
            db, account_id=account_id, device_id=device.id, ttl_seconds=3600
        )
        await db.commit()
        return issued.raw_token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed_official_component(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    versions: tuple[str, ...] = ("1.0", "1.1", "2.0"),
) -> None:
    async with sessionmaker() as db:
        if await db.get(Account, OFFICIAL_ACCOUNT_ID) is None:
            db.add(Account(id=OFFICIAL_ACCOUNT_ID))
        for version in versions:
            db.add(
                CatalogMetadata(
                    owner_account_id=OFFICIAL_ACCOUNT_ID,
                    object_kind="component",
                    stable_id=COMPONENT_ID,
                    version=version,
                    current_revision_id="revision_" + "0" * 64,
                    visibility="public",
                    lifecycle_state="active",
                    name="official-skill",
                    passport_document=dict(PASSPORT, version=version),
                )
            )
        await db.commit()


async def _seed_verified(sessionmaker: async_sessionmaker[AsyncSession], account_id: str) -> None:
    async with sessionmaker() as db:
        db.add(AccountAuthorVerification(account_id=account_id, verified=True, reason="maintainer"))
        await db.commit()


async def test_claim_preview_staff_approve_deny_audit_and_history(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings, str],
) -> None:
    client, sessionmaker, _settings, staff_id = harness
    await _seed_official_component(sessionmaker)
    requester_id, _device, token = await _seed_account_device(sessionmaker)
    await _seed_verified(sessionmaker, requester_id)
    staff_token = await _token_for(sessionmaker, staff_id)
    stranger_id, _sd, stranger_token = await _seed_account_device(sessionmaker)
    await _seed_verified(sessionmaker, stranger_id)

    created = await client.post(
        "/v1/ownership-claims",
        headers=_auth(token),
        json={
            "schema_version": 1,
            "stable_id": COMPONENT_ID,
            "reason": "I maintain the upstream repository.",
            "evidence": "https://github.com/example/demo/commits",
            "idempotency_key": "claim-key-00000001",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["state"] == "requested"
    assert body["preview"]["stable_id"] == COMPONENT_ID
    assert body["preview"]["current_owner_account_id"] == OFFICIAL_ACCOUNT_ID
    assert body["preview"]["versions"] == ["1.0", "1.1", "2.0"]
    assert body["preview"]["major_lines"] == [1, 2]
    claim_id = body["claim_id"]

    forbidden = await client.post(
        f"/v1/staff/ownership-claims/{claim_id}/approve",
        headers=_auth(token),
        json={
            "schema_version": 1,
            "reason": "not staff",
            "idempotency_key": "approve-key-0000001",
        },
    )
    assert forbidden.status_code == 403

    denied_other = await client.post(
        "/v1/ownership-claims",
        headers=_auth(stranger_token),
        json={
            "schema_version": 1,
            "stable_id": COMPONENT_ID,
            "reason": "I also maintain it.",
            "evidence": "https://github.com/example/demo/pulls",
            "idempotency_key": "claim-key-00000002",
        },
    )
    assert denied_other.status_code == 201, denied_other.text
    other_claim = denied_other.json()["claim_id"]
    deny = await client.post(
        f"/v1/staff/ownership-claims/{other_claim}/deny",
        headers=_auth(staff_token),
        json={
            "schema_version": 1,
            "reason": "evidence does not match the listed maintainers",
            "idempotency_key": "deny-key-0000000001",
        },
    )
    assert deny.status_code == 200, deny.text
    assert deny.json()["state"] == "denied"

    approve = await client.post(
        f"/v1/staff/ownership-claims/{claim_id}/approve",
        headers=_auth(staff_token),
        json={
            "schema_version": 1,
            "reason": "upstream maintainers match the claim evidence",
            "idempotency_key": "approve-key-0000002",
        },
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["state"] == "approved"

    async with sessionmaker() as db:
        rows = list(
            (
                await db.execute(
                    select(CatalogMetadata).where(CatalogMetadata.stable_id == COMPONENT_ID)
                )
            )
            .scalars()
            .all()
        )
        assert {row.owner_account_id for row in rows} == {requester_id}
        assert all(row.passport_document == dict(PASSPORT, version=row.version) for row in rows)
        denied_row = await db.get(OwnershipClaim, other_claim)
        assert denied_row is not None
        assert denied_row.state == "denied"
        revisions = list(
            (
                await db.execute(
                    select(OwnershipRevision).where(OwnershipRevision.claim_id == claim_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(revisions) == 1
        denied_revisions = list(
            (
                await db.execute(
                    select(OwnershipRevision).where(OwnershipRevision.claim_id == other_claim)
                )
            )
            .scalars()
            .all()
        )
        assert denied_revisions == []
        audits = list(
            (
                await db.execute(
                    select(AuditEvent).where(AuditEvent.target_table == "ownership_claim")
                )
            )
            .scalars()
            .all()
        )
        actions = {event.action for event in audits}
        assert "ownership.claim_requested" in actions
        assert "ownership.claim_approved" in actions
        assert "ownership.claim_denied" in actions

    history = await client.get(
        f"/v1/owner/objects/component/{COMPONENT_ID}/ownership-revisions",
        headers=_auth(token),
    )
    assert history.status_code == 200, history.text
    items = history.json()["items"]
    assert len(items) == 1
    assert items[0]["from_account_id"] == OFFICIAL_ACCOUNT_ID
    assert items[0]["to_account_id"] == requester_id
    assert items[0]["major_lines"] == [1, 2]


async def test_unverified_account_cannot_claim_official_component(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings, str],
) -> None:
    client, sessionmaker, _settings, _staff_id = harness
    await _seed_official_component(sessionmaker)
    _requester_id, _device, token = await _seed_account_device(sessionmaker)
    response = await client.post(
        "/v1/ownership-claims",
        headers=_auth(token),
        json={
            "schema_version": 1,
            "stable_id": COMPONENT_ID,
            "reason": "please transfer this",
            "evidence": "I wrote the README",
            "idempotency_key": "claim-key-unverified1",
        },
    )
    assert response.status_code == 403
