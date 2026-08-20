"""Account-scoped selection impact stays owner-bound. Blast radius is CLI-only."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, CatalogMetadata

pytestmark = pytest.mark.platform


async def _account_with_session(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> tuple[str, str]:
    async with sessionmaker() as db:
        account = Account(id=new_id("account"))
        db.add(account)
        await db.flush()
        issued = await issue_session(db, account_id=account.id, device_id=None, ttl_seconds=3600)
        await db.commit()
        return account.id, issued.raw_token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_selection_impact_requires_authentication(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, _sessionmaker, _settings = db_api_client
    response = await client.get(
        "/v1/selection/impact",
        params={"candidate_id": new_id("setup"), "candidate_version": "1.0"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AI_STP_AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_selection_impact_does_not_enumerate_foreign_private_objects(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    _owner_id, token = await _account_with_session(sessionmaker)
    other_id, _other_token = await _account_with_session(sessionmaker)
    stable_id = new_id("setup")
    async with sessionmaker() as db:
        db.add(
            CatalogMetadata(
                owner_account_id=other_id,
                object_kind="setup",
                stable_id=stable_id,
                version="1.0",
                current_revision_id="revision_" + "0" * 64,
                visibility="private",
                lifecycle_state="draft",
                name="secret",
                passport_digest="sha256:" + "a" * 64,
                passport_document={"kind": "setup"},
            )
        )
        await db.commit()
    response = await client.get(
        "/v1/selection/impact",
        params={"candidate_id": stable_id, "candidate_version": "1.0"},
        headers=_auth(token),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "AI_STP_NOT_FOUND"


@pytest.mark.asyncio
async def test_blast_radius_route_is_absent(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    _account_id, token = await _account_with_session(sessionmaker)
    response = await client.get(
        "/v1/selection/blast-radius",
        params={
            "component_id": new_id("component"),
            "component_version": "1.0",
            "scenario": "advisory",
        },
        headers=_auth(token),
    )
    assert response.status_code == 404
