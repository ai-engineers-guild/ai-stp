"""Executable acceptance evidence for product-mode resolution (#225)."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.session import issue_session
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import Organization, OrganizationMembership

pytestmark = pytest.mark.platform


async def test_product_mode_is_independent_from_auth_and_fails_closed(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Any],
) -> None:
    client, sessionmaker, _settings = db_api_client
    async with sessionmaker() as db:
        account = Account(id=new_id("account"))
        personal = Organization(
            id=new_id("organization"),
            kind="personal",
            owner_account_id=account.id,
            display_name="Personal",
        )
        corporate = Organization(
            id=new_id("organization"),
            kind="corporate",
            owner_account_id=None,
            display_name="Corporate",
        )
        db.add_all(
            [
                account,
                personal,
                corporate,
                OrganizationMembership(
                    organization_id=personal.id,
                    account_id=account.id,
                    role="owner",
                    state="active",
                ),
                OrganizationMembership(
                    organization_id=corporate.id,
                    account_id=account.id,
                    role="owner",
                    state="active",
                ),
            ]
        )
        issued = await issue_session(db, account_id=account.id, device_id=None, ttl_seconds=3600)
        await db.commit()

    authenticated = {"Authorization": f"Bearer {issued.raw_token}"}
    anonymous = await client.get("/v1/context")
    assert anonymous.status_code == 200
    assert anonymous.json()["mode"] == "local"
    assert anonymous.json()["organization_id"] is None

    personal_context = await client.get("/v1/context", headers=authenticated)
    assert personal_context.status_code == 200
    assert personal_context.json()["mode"] == "personal"
    assert personal_context.json()["organization_id"] == personal.id

    corporate_context = await client.get(
        "/v1/context",
        headers={**authenticated, "X-AI-STP-Organization-Id": corporate.id},
    )
    assert corporate_context.status_code == 200
    assert corporate_context.json()["mode"] == "corporate"
    assert corporate_context.json()["organization_id"] == corporate.id

    forged_remote = await client.get(
        "/v1/context",
        headers={"X-AI-STP-Organization-Id": corporate.id},
    )
    assert forged_remote.status_code == 401
    assert forged_remote.json()["error"]["code"] == "AI_STP_AUTH_REQUIRED"

    unknown_mode = await client.get("/v1/context", headers={"X-AI-STP-Product-Mode": "staging"})
    assert unknown_mode.status_code == 400
    assert unknown_mode.json()["error"]["code"] == "AI_STP_VALIDATION_ERROR"

    local_with_org = await client.get(
        "/v1/context",
        headers={
            **authenticated,
            "X-AI-STP-Product-Mode": "local",
            "X-AI-STP-Organization-Id": corporate.id,
        },
    )
    assert local_with_org.status_code == 401
