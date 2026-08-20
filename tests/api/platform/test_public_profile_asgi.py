"""ASGI tests for public profile draft/publish/avatar S3 path (SPEC-028)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.app import create_app
from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_api.slices.profile import service as profile_service
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, AccountAuthorVerification, OAuthIdentity
from ai_stp_platform.storage.avatar_store import AvatarObjectStore
from ai_stp_platform.storage.memory import MemoryObjectClient

pytestmark = pytest.mark.platform


@pytest_asyncio.fixture
async def harness(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession], Any]]:
    settings = settings_factory(database_url=migrated_database_url)
    assert settings.service.environment == "test"
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app.state.sessionmaker, app.state


async def _seed_session(
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
async def test_draft_does_not_change_public_until_publish(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], Any],
) -> None:
    client, sessionmaker, _ = harness
    account_id, token = await _seed_session(sessionmaker)
    headers = _auth(token)

    public_before = await client.get(f"/v1/publishers/{account_id}")
    assert public_before.status_code == 200
    assert public_before.json().get("empty") is True

    draft = await client.put(
        "/v1/account/public-profile/draft",
        headers=headers,
        json={
            "display_name": "Draft Author",
            "bio": "work in progress",
            "links": [{"label": "Site", "url": "https://example.com/draft"}],
            "avatar_asset_id": None,
        },
    )
    assert draft.status_code == 200, draft.text
    body = draft.json()
    assert body["state"] == "draft"
    digest = body["draft"]["content_digest"]
    assert digest.startswith("sha256:")

    public_mid = await client.get(f"/v1/publishers/{account_id}")
    assert public_mid.status_code == 200
    mid = public_mid.json()
    assert mid.get("empty") is True or mid.get("display_name") is None

    preview = await client.get("/v1/account/public-profile/preview", headers=headers)
    assert preview.status_code == 200
    assert preview.json()["preview"] is True
    assert preview.json()["projection"]["display_name"] == "Draft Author"
    assert "private" in preview.headers.get("cache-control", "").lower()

    published = await client.post(
        "/v1/account/public-profile/publish",
        headers={**headers, "Idempotency-Key": "pub-1"},
        json={"content_digest": digest},
    )
    assert published.status_code == 200, published.text
    assert published.json()["published"] is True

    public_after = await client.get(f"/v1/publishers/{account_id}")
    assert public_after.status_code == 200
    pub = public_after.json()
    assert pub["display_name"] == "Draft Author"
    assert pub["bio"] == "work in progress"
    assert "email" not in pub
    assert pub["links"][0]["url"].startswith("https://")


@pytest.mark.asyncio
async def test_avatar_upload_writes_object_store_and_serves_media(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], Any],
) -> None:
    client, sessionmaker, app_state = harness
    account_id, token = await _seed_session(sessionmaker)
    headers = _auth(token)
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    upload = await client.post(
        "/v1/account/public-profile/avatar",
        headers={**headers, "Content-Type": "image/png"},
        content=png,
    )
    assert upload.status_code == 201, upload.text
    data = upload.json()
    assert data["state"] == "ready"
    assert data["public_url"] == f"/v1/media/avatars/{data['avatar_asset_id']}"
    assert data["object_key"]
    assert data["content_digest"].startswith("sha256:")

    mem: MemoryObjectClient = app_state.object_client
    assert mem.put_count >= 1
    assert any(isinstance(v.get("body"), bytes) and v["body"] == png for v in mem.objects.values())

    media = await client.get(data["public_url"])
    assert media.status_code == 200
    assert media.content == png
    assert media.headers["content-type"].startswith("image/png")

    draft = await client.put(
        "/v1/account/public-profile/draft",
        headers=headers,
        json={
            "display_name": "With Avatar",
            "bio": None,
            "links": [],
            "avatar_asset_id": data["avatar_asset_id"],
        },
    )
    assert draft.status_code == 200
    digest = draft.json()["draft"]["content_digest"]
    pub = await client.post(
        "/v1/account/public-profile/publish",
        headers={**headers, "Idempotency-Key": "pub-avatar"},
        json={"content_digest": digest},
    )
    assert pub.status_code == 200
    public = await client.get(f"/v1/publishers/{account_id}")
    assert public.json()["avatar_url"] == data["public_url"]


@pytest.mark.asyncio
async def test_avatar_rejects_bad_mime_and_oversize(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], Any],
) -> None:
    client, sessionmaker, _ = harness
    _, token = await _seed_session(sessionmaker)
    headers = _auth(token)

    bad = await client.post(
        "/v1/account/public-profile/avatar",
        headers={**headers, "Content-Type": "image/gif"},
        content=b"GIF89a",
    )
    assert bad.status_code == 400

    huge = await client.post(
        "/v1/account/public-profile/avatar",
        headers={**headers, "Content-Type": "image/png"},
        content=b"x" * (5 * 1024 * 1024 + 1),
    )
    assert huge.status_code == 400


@pytest.mark.asyncio
async def test_avatar_from_identity_fetches_and_stores_bytes(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], Any],
) -> None:
    _client, sessionmaker, app_state = harness
    account_id, _token = await _seed_session(sessionmaker)
    async with sessionmaker() as db:
        db.add(
            OAuthIdentity(
                account_id=account_id,
                provider="github",
                provider_subject="gh-1",
                email="a@example.com",
                email_verified=True,
                avatar_url="https://avatars.githubusercontent.com/u/1?v=4",
                display_name="gh",
                state="linked",
            )
        )
        await db.commit()

    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "avatars.githubusercontent.com"
        return httpx.Response(200, content=png, headers={"content-type": "image/png"})

    store: AvatarObjectStore = app_state.avatar_store
    transport = httpx.MockTransport(handler)
    async with sessionmaker() as db:
        async with httpx.AsyncClient(transport=transport) as http:
            result = await profile_service.create_avatar_from_identity(
                db,
                store,
                account_id=account_id,
                provider="github",
                http_client=http,
            )
        await db.commit()

    assert result["state"] == "ready"
    assert result["object_key"]
    assert result["public_url"].startswith("/v1/media/avatars/")
    mem: MemoryObjectClient = app_state.object_client
    assert mem.put_count >= 1
    assert any(v.get("body") == png for v in mem.objects.values())


@pytest.mark.asyncio
async def test_publish_precondition_and_owner_get(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], Any],
) -> None:
    client, sessionmaker, _ = harness
    _account_id, token = await _seed_session(sessionmaker)
    headers = _auth(token)

    draft = await client.put(
        "/v1/account/public-profile/draft",
        headers=headers,
        json={"display_name": "P", "bio": None, "links": [], "avatar_asset_id": None},
    )
    assert draft.status_code == 200
    digest = draft.json()["draft"]["content_digest"]

    wrong = await client.post(
        "/v1/account/public-profile/publish",
        headers={**headers, "Idempotency-Key": "bad"},
        json={"content_digest": "sha256:deadbeef"},
    )
    assert wrong.status_code == 412

    owner = await client.get("/v1/account/public-profile", headers=headers)
    assert owner.status_code == 200
    assert owner.json()["draft"]["content_digest"] == digest

    unauth = await client.get("/v1/account/public-profile")
    assert unauth.status_code == 401


@pytest.mark.asyncio
async def test_owner_editor_falls_back_to_published_revision_when_draft_is_absent(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], Any],
) -> None:
    client, sessionmaker, _ = harness
    _account_id, token = await _seed_session(sessionmaker)
    headers = _auth(token)
    fields = {
        "display_name": "Published editor source",
        "bio": "The editor must not look empty after publishing.",
        "links": [{"label": "Docs", "url": "https://example.com/docs"}],
        "avatar_asset_id": None,
    }

    draft = await client.put("/v1/account/public-profile/draft", headers=headers, json=fields)
    assert draft.status_code == 200, draft.text
    digest = draft.json()["draft"]["content_digest"]
    revision_id = draft.json()["draft"]["revision_id"]
    published = await client.post(
        "/v1/account/public-profile/publish",
        headers={**headers, "Idempotency-Key": "published-editor-source"},
        json={"content_digest": digest},
    )
    assert published.status_code == 200, published.text

    owner = await client.get("/v1/account/public-profile", headers=headers)
    assert owner.status_code == 200, owner.text
    payload = owner.json()
    assert payload["draft"]["revision_id"] is None
    assert payload["editable"]["source"] == "published"
    assert payload["editable"]["base_revision_id"] == revision_id
    assert payload["editable"]["base_content_digest"] == digest
    assert payload["editable"]["fields"] == fields


@pytest.mark.asyncio
async def test_profile_accepts_maximum_bio_and_publish_requires_idempotency_key(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], Any],
) -> None:
    client, sessionmaker, _ = harness
    account_id, token = await _seed_session(sessionmaker)
    headers = _auth(token)
    bio = "x" * 1500

    draft = await client.put(
        "/v1/account/public-profile/draft",
        headers=headers,
        json={"display_name": "Boundary", "bio": bio, "links": [], "avatar_asset_id": None},
    )
    assert draft.status_code == 200, draft.text
    digest = draft.json()["draft"]["content_digest"]

    missing_key = await client.post(
        "/v1/account/public-profile/publish",
        headers=headers,
        json={"content_digest": digest},
    )
    assert missing_key.status_code == 400

    published = await client.post(
        "/v1/account/public-profile/publish",
        headers={**headers, "Idempotency-Key": "profile-boundary"},
        json={"content_digest": digest},
    )
    assert published.status_code == 200, published.text
    public = await client.get(f"/v1/publishers/{account_id}")
    assert public.json()["bio"] == bio

    async with sessionmaker() as db:
        db.add(AccountAuthorVerification(account_id=account_id, verified=True))
        await db.commit()
    verified = await client.get(f"/v1/publishers/{account_id}")
    assert verified.json()["author_verified"] is True

    async with sessionmaker() as db:
        row = await db.get(AccountAuthorVerification, account_id)
        assert row is not None
        row.verified = False
        await db.commit()
    revoked = await client.get(f"/v1/publishers/{account_id}")
    assert revoked.json()["author_verified"] is False


@pytest.mark.asyncio
async def test_ssrf_blocked_for_private_identity_url(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], Any],
) -> None:
    _client, sessionmaker, app_state = harness
    account_id, _token = await _seed_session(sessionmaker)
    async with sessionmaker() as db:
        db.add(
            OAuthIdentity(
                account_id=account_id,
                provider="github",
                provider_subject="gh-ssrf",
                email="b@example.com",
                email_verified=True,
                avatar_url="https://127.0.0.1/secret.png",
                display_name="gh",
                state="linked",
            )
        )
        await db.commit()

    store: AvatarObjectStore = app_state.avatar_store
    async with sessionmaker() as db:
        with pytest.raises(Exception) as excinfo:
            await profile_service.create_avatar_from_identity(
                db,
                store,
                account_id=account_id,
                provider="github",
            )
        assert (
            "not allowed" in str(excinfo.value).lower()
            or getattr(excinfo.value, "category", None) is not None
        )
