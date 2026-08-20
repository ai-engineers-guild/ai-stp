"""Authorization matrix owner / outsider / admin (SPEC-002 REQ-206)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ai_stp_api.app import create_app
from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, AuditEvent, Device

pytestmark = pytest.mark.platform


@pytest_asyncio.fixture
async def matrix_env(
    migrated_database_url: str,
) -> AsyncIterator[dict[str, str]]:
    engine = create_async_engine(migrated_database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as db:
        owner = Account(id=new_id("account"))
        outsider = Account(id=new_id("account"))
        admin = Account(id=new_id("account"))
        db.add_all([owner, outsider, admin])
        await db.flush()
        device = Device(
            id=new_id("device"),
            account_id=owner.id,
            public_key="matrix-pk-" + "m" * 24,
            state="active",
        )
        db.add(device)
        owner_session = await issue_session(
            db, account_id=owner.id, device_id=None, ttl_seconds=3600
        )
        outsider_session = await issue_session(
            db, account_id=outsider.id, device_id=None, ttl_seconds=3600
        )
        admin_session = await issue_session(
            db, account_id=admin.id, device_id=None, ttl_seconds=3600
        )
        await db.commit()
        env = {
            "owner_id": owner.id,
            "outsider_id": outsider.id,
            "admin_id": admin.id,
            "device_id": device.id,
            "owner_token": owner_session.raw_token,
            "outsider_token": outsider_session.raw_token,
            "admin_token": admin_session.raw_token,
            "database_url": migrated_database_url,
        }
    await engine.dispose()
    yield env


async def test_owner_can_list_and_revoke_own_device(
    matrix_env: dict[str, str],
    settings_factory: Callable[..., Settings],
) -> None:
    settings = settings_factory(
        database_url=str(matrix_env["database_url"]),
        admin_account_ids=str(matrix_env["admin_id"]),
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {matrix_env['owner_token']}"}
            listed = await client.get("/v1/devices", headers=headers)
            assert listed.status_code == 200
            items = listed.json()["items"]
            ids = [d["device_id"] for d in items]
            assert matrix_env["device_id"] in ids
            etag = next(d["etag"] for d in items if d["device_id"] == matrix_env["device_id"])

            revoked = await client.post(
                f"/v1/devices/{matrix_env['device_id']}/revoke",
                headers={
                    **headers,
                    "If-Match": etag,
                    "Idempotency-Key": "authz-revoke-1",
                },
                json={"schema_version": 1, "idempotency_key": "authz-revoke-1"},
            )
            assert revoked.status_code == 200
            assert revoked.json()["device"]["state"] == "revoked"


async def test_outsider_denied_for_list_and_revoke(
    matrix_env: dict[str, str],
    settings_factory: Callable[..., Settings],
) -> None:
    settings = settings_factory(
        database_url=str(matrix_env["database_url"]),
        admin_account_ids=str(matrix_env["admin_id"]),
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {matrix_env['outsider_token']}"}
            listed = await client.get(
                "/v1/devices",
                headers=headers,
                params={"account_id": matrix_env["owner_id"]},
            )
            assert listed.status_code == 403

            revoked = await client.post(
                f"/v1/devices/{matrix_env['device_id']}/revoke",
                headers={
                    **headers,
                    "If-Match": 'W/"guess"',
                    "Idempotency-Key": "authz-outsider-1",
                },
                json={"schema_version": 1, "idempotency_key": "authz-outsider-1"},
            )
            assert revoked.status_code == 403
            # Account id alone is never an authority: same code for missing/foreign.
            assert revoked.json()["error"]["code"] == "AI_STP_PERMISSION_DENIED"


async def test_admin_read_with_reason_writes_audit(
    matrix_env: dict[str, str],
    settings_factory: Callable[..., Settings],
) -> None:
    settings = settings_factory(
        database_url=str(matrix_env["database_url"]),
        admin_account_ids=str(matrix_env["admin_id"]),
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {
                "Authorization": f"Bearer {matrix_env['admin_token']}",
                "X-Admin-Reason": "incident-review",
            }
            listed = await client.get(
                "/v1/devices",
                headers=headers,
                params={"account_id": matrix_env["owner_id"]},
            )
            assert listed.status_code == 200

    engine = create_async_engine(str(matrix_env["database_url"]))
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as db:
        from sqlalchemy import select

        events = (
            (await db.execute(select(AuditEvent).where(AuditEvent.action == "device.admin_list")))
            .scalars()
            .all()
        )
        assert events
        assert events[0].reason == "incident-review"
        assert "token" not in repr(events[0].payload).lower()
    await engine.dispose()
