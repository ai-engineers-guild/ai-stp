from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_foundation.ids import new_id
from ai_stp_platform.catalog_seed import FIXTURE_COMPONENT_ID, load_first_party_seed
from ai_stp_platform.models import Account, CatalogMetadata

pytestmark = pytest.mark.platform


@pytest.mark.asyncio
async def test_reaction_is_idempotent_listed_and_removable(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    async with sessionmaker() as db:
        await load_first_party_seed(db)
        account = Account(id=new_id("account"))
        db.add(account)
        await db.flush()
        session = await issue_session(db, account_id=account.id, device_id=None, ttl_seconds=3600)
        await db.commit()
    headers = {"Authorization": f"Bearer {session.raw_token}"}
    path = f"/v1/account/catalog-reactions/component/{FIXTURE_COMPONENT_ID}"

    first = await client.put(path, headers=headers)
    repeated = await client.put(path, headers=headers)
    listed = await client.get("/v1/account/catalog-reactions", headers=headers)

    assert first.status_code == repeated.status_code == listed.status_code == 200
    assert first.json()["likes_count"] == repeated.json()["likes_count"] == 1
    assert listed.json()["items"][0]["summary"]["stable_id"] == FIXTURE_COMPONENT_ID

    removed = await client.delete(path, headers=headers)
    empty = await client.get("/v1/account/catalog-reactions", headers=headers)
    assert removed.json() == {"schema_version": 1, "liked": False, "likes_count": 0}
    assert empty.json()["items"] == []

    async with sessionmaker() as db:
        counts = (
            await db.scalars(
                select(CatalogMetadata.likes_count).where(
                    CatalogMetadata.stable_id == FIXTURE_COMPONENT_ID
                )
            )
        ).all()
    assert counts and set(counts) == {0}
