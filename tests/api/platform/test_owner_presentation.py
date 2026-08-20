"""Owner-only mutable component presentation API coverage."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, CatalogMetadata, ComponentMedia

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


@pytest.mark.asyncio
async def test_owner_can_update_only_component_presentation(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    owner_id, token = await _account_with_session(sessionmaker)
    stable_id = new_id("component")
    async with sessionmaker() as db:
        db.add(
            CatalogMetadata(
                owner_account_id=owner_id,
                object_kind="component",
                stable_id=stable_id,
                version="1.0",
                current_revision_id="revision_" + "0" * 64,
                visibility="public",
                lifecycle_state="active",
                name="immutable-name",
                passport_document={"description": "Passport description"},
            )
        )
        await db.commit()

    response = await client.put(
        f"/v1/owner/objects/component/{stable_id}/presentation",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "schema_version": 1,
            "bio": "Mutable catalog bio",
            "media": [
                {
                    "kind": "youtube",
                    "url": "dQw4w9WgXcQ",
                    "alt": "Demo video",
                    "caption": "Walkthrough",
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["bio"] == "Mutable catalog bio"
    async with sessionmaker() as db:
        metadata = await db.scalar(
            select(CatalogMetadata).where(CatalogMetadata.stable_id == stable_id)
        )
        assert metadata is not None
        assert metadata.name == "immutable-name"
        assert metadata.passport_document == {"description": "Passport description"}
        assert metadata.presentation_bio == "Mutable catalog bio"
        media = await db.scalar(select(ComponentMedia).where(ComponentMedia.stable_id == stable_id))
        assert media is not None
        assert media.youtube_video_id == "dQw4w9WgXcQ"


@pytest.mark.asyncio
async def test_non_owner_cannot_read_component_presentation(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    owner_id, _owner_token = await _account_with_session(sessionmaker)
    _other_id, other_token = await _account_with_session(sessionmaker)
    stable_id = new_id("component")
    async with sessionmaker() as db:
        db.add(
            CatalogMetadata(
                owner_account_id=owner_id,
                object_kind="component",
                stable_id=stable_id,
                version="1.0",
                current_revision_id="revision_" + "0" * 64,
                visibility="public",
                lifecycle_state="active",
                name="owned",
            )
        )
        await db.commit()

    response = await client.get(
        f"/v1/owner/objects/component/{stable_id}/presentation",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_owner_can_upload_component_media_and_save_presentation(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    owner_id, token = await _account_with_session(sessionmaker)
    stable_id = new_id("component")
    async with sessionmaker() as db:
        db.add(
            CatalogMetadata(
                owner_account_id=owner_id,
                object_kind="component",
                stable_id=stable_id,
                version="1.0",
                current_revision_id="revision_" + "0" * 64,
                visibility="public",
                lifecycle_state="active",
                name="with-media",
            )
        )
        await db.commit()

    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
        b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd"
        b"\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    upload = await client.post(
        f"/v1/owner/objects/component/{stable_id}/presentation/media",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "image/png",
        },
        content=png,
    )
    assert upload.status_code == 201
    body = upload.json()
    assert body["kind"] == "image"
    assert body["public_url"].startswith("/v1/media/component/")
    media_id = body["media_id"]

    served = await client.get(body["public_url"])
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("image/")
    assert served.content == png

    saved = await client.put(
        f"/v1/owner/objects/component/{stable_id}/presentation",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "schema_version": 1,
            "bio": "Bio with upload",
            "media": [
                {
                    "kind": "image",
                    "url": body["public_url"],
                    "alt": "Uploaded still",
                    "caption": "Cover",
                }
            ],
        },
    )
    assert saved.status_code == 200
    assert saved.json()["media"][0]["url"] == body["public_url"]

    async with sessionmaker() as db:
        row = await db.get(ComponentMedia, media_id)
        assert row is not None
        assert row.source_type == "upload"
        assert row.alt == "Uploaded still"
        assert row.object_key is not None
        assert row.public_url == body["public_url"]


@pytest.mark.asyncio
async def test_component_media_upload_rejects_bad_mime(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    owner_id, token = await _account_with_session(sessionmaker)
    stable_id = new_id("component")
    async with sessionmaker() as db:
        db.add(
            CatalogMetadata(
                owner_account_id=owner_id,
                object_kind="component",
                stable_id=stable_id,
                version="1.0",
                current_revision_id="revision_" + "0" * 64,
                visibility="public",
                lifecycle_state="active",
                name="reject-mime",
            )
        )
        await db.commit()

    response = await client.post(
        f"/v1/owner/objects/component/{stable_id}/presentation/media",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "image/svg+xml",
        },
        content=b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
    )
    assert response.status_code == 400
