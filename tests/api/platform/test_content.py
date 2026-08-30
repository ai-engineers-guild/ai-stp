"""ASGI tests for public content, repository import and staff publication."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.api.platform.conftest import make_settings, make_test_auth
from tests.unit.platform.article_fixtures import pair_snapshot, staff_payload

from ai_stp_api.app import create_app
from ai_stp_api.session import issue_session
from ai_stp_api.settings import ContentSettings, Settings
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, AuditEvent, Device

pytestmark = pytest.mark.platform

IMPORT_TOKEN = "content-import-token-for-tests-32b"


@pytest_asyncio.fixture
async def harness(
    migrated_database_url: str,
    tmp_path: Path,
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings]]:
    settings = make_settings(
        tmp_path,
        database_url=migrated_database_url,
        content=ContentSettings(import_token=IMPORT_TOKEN),
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app.state.sessionmaker, settings


def _import_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {IMPORT_TOKEN}"}


async def _seed_staff(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> tuple[str, str]:
    async with sessionmaker() as db:
        account = Account(id=new_id("account"))
        device = Device(
            id=new_id("device"),
            account_id=account.id,
            public_key="dGVzdC1wdWJsaWMta2V5LXB1Ymxpc2g=",
            state="active",
        )
        db.add(account)
        db.add(device)
        await db.flush()
        issued = await issue_session(
            db, account_id=account.id, device_id=device.id, ttl_seconds=3600
        )
        await db.commit()
        return account.id, issued.raw_token


@pytest.mark.asyncio
async def test_import_forbidden_without_token(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, _sessionmaker, _settings = harness
    missing = await client.get("/v1/content/repository/state")
    assert missing.status_code == 403
    assert missing.json()["error"]["code"] == "AI_STP_CONTENT_IMPORT_FORBIDDEN"


@pytest.mark.asyncio
async def test_public_list_and_detail_merge_sources_and_etag(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
    tmp_path: Path,
    migrated_database_url: str,
) -> None:
    client, sessionmaker, _settings = harness
    snapshot = pair_snapshot()
    imported = await client.post(
        "/v1/content/repository/import",
        headers=_import_headers(),
        json=snapshot.model_dump(mode="json"),
    )
    assert imported.status_code == 200, imported.text
    staff_id, staff_token = await _seed_staff(sessionmaker)
    staff_settings = make_settings(
        tmp_path,
        database_url=migrated_database_url,
        content=ContentSettings(import_token=IMPORT_TOKEN),
        auth=make_test_auth(admin_account_ids=staff_id),
    )
    app = create_app(staff_settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as staff_client:
            created = await staff_client.put(
                "/v1/staff/content/article/staff-note",
                headers={"Authorization": f"Bearer {staff_token}"},
                json=staff_payload().model_dump(mode="json"),
            )
            assert created.status_code == 200, created.text
            listed = await staff_client.get("/v1/content", params={"locale": "en"})
            assert listed.status_code == 200
            assert "public" in listed.headers["cache-control"]
            slugs = [item["slug"] for item in listed.json()["items"]]
            assert slugs == ["safe-setup", "staff-note"] or set(slugs) == {
                "safe-setup",
                "staff-note",
            }
            detail = await staff_client.get(
                "/v1/content/article/safe-setup", params={"locale": "en"}
            )
            assert detail.status_code == 200
            body = detail.json()
            assert body["body"] == "Use exact versions."
            assert body["source_kind"] == "repository"
            assert "actor_account_id" not in body
            etag = detail.headers["etag"]
            cached = await staff_client.get(
                "/v1/content/article/safe-setup",
                params={"locale": "en"},
                headers={"If-None-Match": etag},
            )
            assert cached.status_code == 304
            missing = await staff_client.get("/v1/content/article/missing", params={"locale": "en"})
            assert missing.status_code == 404


@pytest.mark.asyncio
async def test_staff_stale_and_allowlist(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
    tmp_path: Path,
    migrated_database_url: str,
) -> None:
    _client, sessionmaker, _settings = harness
    staff_id, staff_token = await _seed_staff(sessionmaker)
    _outsider_id, outsider_token = await _seed_staff(sessionmaker)

    settings = make_settings(
        tmp_path,
        database_url=migrated_database_url,
        content=ContentSettings(import_token=IMPORT_TOKEN),
        auth=make_test_auth(admin_account_ids=staff_id),
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            denied = await client.put(
                "/v1/staff/content/article/staff-note",
                headers={"Authorization": f"Bearer {outsider_token}"},
                json=staff_payload().model_dump(mode="json"),
            )
            assert denied.status_code == 403
            created = await client.put(
                "/v1/staff/content/article/staff-note",
                headers={"Authorization": f"Bearer {staff_token}"},
                json=staff_payload().model_dump(mode="json"),
            )
            assert created.status_code == 200, created.text
            stale = await client.put(
                "/v1/staff/content/article/staff-note",
                headers={"Authorization": f"Bearer {staff_token}"},
                json=staff_payload(expected_active_digest="sha256:" + "0" * 64).model_dump(
                    mode="json"
                ),
            )
            assert stale.status_code == 409
            assert stale.json()["error"]["code"] == "AI_STP_CONTENT_STALE"
            digest = created.json()["active_digest"]
            unpublished = await client.request(
                "DELETE",
                "/v1/staff/content/article/staff-note",
                headers={"Authorization": f"Bearer {staff_token}"},
                json={"schema_version": 1, "expected_active_digest": digest},
            )
            assert unpublished.status_code == 200, unpublished.text
            async with app.state.sessionmaker() as db:
                events = list((await db.execute(select(AuditEvent))).scalars())
            assert events
            joined = json_payloads(events)
            assert "Staff body EN." not in joined
            assert IMPORT_TOKEN not in joined


def json_payloads(events: list[AuditEvent]) -> str:
    return "".join(str(event.payload) for event in events)
