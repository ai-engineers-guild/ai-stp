"""Legal account activation accepts exact current policy revisions."""

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
from ai_stp_platform.models import Account, AccountPolicyAcceptance

pytestmark = pytest.mark.platform


@pytest_asyncio.fixture
async def harness(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession]]]:
    app = create_app(settings_factory(database_url=migrated_database_url))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        yield client, app.state.sessionmaker


@pytest.mark.asyncio
async def test_pending_account_is_activated_only_after_current_dual_acceptance(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, sessionmaker = harness
    async with sessionmaker() as db:
        account = Account(id=new_id("account"), status="onboarding_pending")
        db.add(account)
        await db.flush()
        issued = await issue_session(db, account_id=account.id, device_id=None, ttl_seconds=3600)
        await db.commit()

    headers = {"Authorization": f"Bearer {issued.raw_token}"}
    me = await client.get("/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["account_status"] == "onboarding_pending"

    blocked = await client.get("/v1/account", headers=headers)
    assert blocked.status_code == 403

    required = await client.get("/v1/auth/onboarding", params={"locale": "en"}, headers=headers)
    assert required.status_code == 200
    revisions = required.json()
    stale = await client.post(
        "/v1/auth/onboarding/complete",
        params={"locale": "en"},
        headers=headers,
        json={
            "service_rules_revision_id": "drev_stale",
            "personal_data_consent_revision_id": revisions["personal_data_consent_revision_id"],
        },
    )
    assert stale.status_code == 400

    completed = await client.post(
        "/v1/auth/onboarding/complete",
        params={"locale": "en"},
        headers=headers,
        json={
            "service_rules_revision_id": revisions["service_rules_revision_id"],
            "personal_data_consent_revision_id": revisions["personal_data_consent_revision_id"],
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["account_status"] == "active"

    repeated = await client.post(
        "/v1/auth/onboarding/complete",
        params={"locale": "en"},
        headers=headers,
        json={
            "service_rules_revision_id": revisions["service_rules_revision_id"],
            "personal_data_consent_revision_id": revisions["personal_data_consent_revision_id"],
        },
    )
    assert repeated.status_code == 200

    async with sessionmaker() as db:
        acceptances = await db.scalars(
            select(AccountPolicyAcceptance).where(AccountPolicyAcceptance.account_id == account.id)
        )
        rows = list(acceptances)
    assert {(row.acceptance_type, row.document_revision_id) for row in rows} == {
        ("service_rules", revisions["service_rules_revision_id"]),
        ("personal_data_consent", revisions["personal_data_consent_revision_id"]),
    }
    assert all(row.accepted_at is not None and row.locale == "en" for row in rows)
