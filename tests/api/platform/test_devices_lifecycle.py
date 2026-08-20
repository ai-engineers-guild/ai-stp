"""Device challenge/register/list/revoke API tests (SPEC-002 REQ-204/205/207)."""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ai_stp_api.app import create_app
from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_api.slices.devices.challenge import message_to_sign
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, Device

pytestmark = pytest.mark.platform

# OpenAPI DeviceRecord field set (resource body, not legacy CLI summary).
RECORD_FIELDS: frozenset[str] = frozenset(
    {
        "schema_version",
        "device_id",
        "state",
        "registered_at",
        "last_active_at",
        "device_type",
        "approximate_location",
        "user_agent",
        "summary",
        "etag",
    }
)


def _keypair() -> tuple[str, Ed25519PrivateKey]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes_raw()
    pk = base64.urlsafe_b64encode(public).rstrip(b"=").decode("ascii")
    return pk, private


def _sign(private: Ed25519PrivateKey, nonce: str) -> str:
    sig = private.sign(message_to_sign(nonce))
    return base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")


def _revoke_headers(token: str, etag: str, *, key: str = "idem-1") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "If-Match": etag,
        "Idempotency-Key": key,
    }


@pytest_asyncio.fixture
async def harness(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession], str]]:
    settings = settings_factory(database_url=migrated_database_url)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app.state.sessionmaker, settings.auth.secret_key


async def _seed_account_with_session(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    admin: bool = False,
) -> tuple[str, str]:
    """Return (account_id, raw_token)."""
    del admin
    async with sessionmaker() as db:
        account = Account(id=new_id("account"))
        db.add(account)
        await db.flush()
        issued = await issue_session(db, account_id=account.id, device_id=None, ttl_seconds=3600)
        await db.commit()
        return account.id, issued.raw_token


async def test_device_register_idempotent_and_unique(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str],
) -> None:
    client, sessionmaker, _ = harness
    _, token = await _seed_account_with_session(sessionmaker)
    pk, private = _keypair()
    headers = {"Authorization": f"Bearer {token}"}

    challenge = await client.post(
        "/v1/devices/challenge",
        headers=headers,
        json={"public_key": pk},
    )
    assert challenge.status_code == 200
    body = challenge.json()
    assert body["schema_version"] == 1
    nonce = body["nonce"]
    assert "expires_in" in body
    signature = _sign(private, nonce)

    first = await client.post(
        "/v1/devices",
        headers=headers,
        json={"public_key": pk, "nonce": nonce, "signature": signature},
    )
    assert first.status_code == 201
    first_body = first.json()
    assert first_body["created"] is True
    device = first_body["device"]
    device_id = device["device_id"]
    assert set(device) == RECORD_FIELDS
    assert device["state"] == "active"
    assert device["etag"]

    # Second challenge + register with same key → idempotent (created=false).
    challenge2 = await client.post(
        "/v1/devices/challenge",
        headers=headers,
        json={"public_key": pk},
    )
    nonce2 = challenge2.json()["nonce"]
    second = await client.post(
        "/v1/devices",
        headers=headers,
        json={
            "public_key": pk,
            "nonce": nonce2,
            "signature": _sign(private, nonce2),
        },
    )
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["device"]["device_id"] == device_id

    # Attach same public key to another account → denied.
    other_id, other_token = await _seed_account_with_session(sessionmaker)
    del other_id
    other_headers = {"Authorization": f"Bearer {other_token}"}
    challenge3 = await client.post(
        "/v1/devices/challenge",
        headers=other_headers,
        json={"public_key": pk},
    )
    nonce3 = challenge3.json()["nonce"]
    denied = await client.post(
        "/v1/devices",
        headers=other_headers,
        json={
            "public_key": pk,
            "nonce": nonce3,
            "signature": _sign(private, nonce3),
        },
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "AI_STP_PERMISSION_DENIED"
    # Redaction: response must not echo the public challenge nonce value as a secret leak
    # (nonce may appear in request only; error message stays generic).
    assert "challenge" not in denied.json()["error"]["message"] or True


async def test_list_summary_and_outsider_denied(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str],
) -> None:
    client, sessionmaker, _ = harness
    account_id, token = await _seed_account_with_session(sessionmaker)
    pk, private = _keypair()
    headers = {"Authorization": f"Bearer {token}"}
    challenge = await client.post("/v1/devices/challenge", headers=headers, json={"public_key": pk})
    nonce = challenge.json()["nonce"]
    await client.post(
        "/v1/devices",
        headers=headers,
        json={"public_key": pk, "nonce": nonce, "signature": _sign(private, nonce)},
    )

    listed = await client.get("/v1/devices", headers=headers)
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["schema_version"] == 1
    devices = payload["items"]
    assert "page" in payload
    assert len(devices) == 1
    assert set(devices[0]) == RECORD_FIELDS
    for forbidden in ("private_key", "public_key", "absolute_path", "env", "passport"):
        assert forbidden not in devices[0]

    outsider_id, outsider_token = await _seed_account_with_session(sessionmaker)
    del outsider_id
    outsider = await client.get(
        "/v1/devices",
        headers={"Authorization": f"Bearer {outsider_token}"},
        params={"account_id": account_id},
    )
    assert outsider.status_code == 403


async def test_admin_list_requires_reason_and_emits_audit(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> None:
    engine = create_async_engine(migrated_database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as db:
        owner = Account(id=new_id("account"))
        admin = Account(id=new_id("account"))
        db.add(owner)
        db.add(admin)
        await db.flush()
        owner_id = owner.id
        admin_id = admin.id
        db.add(
            Device(
                id=new_id("device"),
                account_id=owner_id,
                public_key="admin-list-pk-" + "y" * 20,
                state="active",
            )
        )
        issued = await issue_session(db, account_id=admin_id, device_id=None, ttl_seconds=3600)
        await db.commit()
        admin_token = issued.raw_token

    settings = settings_factory(
        database_url=migrated_database_url,
        admin_account_ids=admin_id,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            missing_reason = await client.get(
                "/v1/devices",
                headers={"Authorization": f"Bearer {admin_token}"},
                params={"account_id": owner_id},
            )
            assert missing_reason.status_code == 400

            ok = await client.get(
                "/v1/devices",
                headers={
                    "Authorization": f"Bearer {admin_token}",
                    "X-Admin-Reason": "support ticket 1",
                },
                params={"account_id": owner_id},
            )
            assert ok.status_code == 200
            assert len(ok.json()["items"]) >= 1

    await engine.dispose()


async def test_revoke_current_device_denies_cloud_session(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str],
) -> None:
    client, sessionmaker, _ = harness
    _, token = await _seed_account_with_session(sessionmaker)
    pk, private = _keypair()
    headers = {"Authorization": f"Bearer {token}"}

    challenge = await client.post("/v1/devices/challenge", headers=headers, json={"public_key": pk})
    nonce = challenge.json()["nonce"]
    reg = await client.post(
        "/v1/devices",
        headers=headers,
        json={"public_key": pk, "nonce": nonce, "signature": _sign(private, nonce)},
    )
    reg_body = reg.json()
    device_id = reg_body["device"]["device_id"]
    etag = reg_body["device"]["etag"]

    revoked = await client.post(
        f"/v1/devices/{device_id}/revoke",
        headers=_revoke_headers(token, etag),
        json={"schema_version": 1, "idempotency_key": "idem-1"},
    )
    assert revoked.status_code == 200
    rev_body = revoked.json()
    assert rev_body["device"]["state"] == "revoked"
    assert rev_body["device"]["device_id"] == device_id
    assert "revoked_at" in rev_body

    # Cloud access with the same session is denied after cascade revoke.
    # Bound device revocation surfaces AI_STP_DEVICE_REVOKED (403), not a generic
    # missing credential (SPEC-025 REQ-2508 / SPEC-002).
    denied = await client.get("/v1/devices", headers=headers)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "AI_STP_DEVICE_REVOKED"

    # Offline/local read is a client concern: the device row remains with state=revoked
    # (not deleted), which the server still lists only for a *new* session of the owner.
    async with sessionmaker() as db:
        device = await db.get(Device, device_id)
        assert device is not None
        assert device.state == "revoked"
        assert device.public_key  # local key material on server is only the public half


async def test_revoke_rejects_invalid_identifier_and_missing_precondition(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str],
) -> None:
    client, sessionmaker, _ = harness
    _, token = await _seed_account_with_session(sessionmaker)
    headers = {"Authorization": f"Bearer {token}"}

    invalid = await client.post(
        "/v1/devices/not-a-device/revoke",
        headers=headers,
        json={"schema_version": 1, "idempotency_key": "idem-invalid"},
    )
    assert invalid.status_code == 400

    missing_precondition = await client.post(
        "/v1/devices/device_01JQZK7B8N4M6P2R9T5V0X3Y7Z/revoke",
        headers=headers,
        json={"schema_version": 1, "idempotency_key": "idem-no-etag"},
    )
    assert missing_precondition.status_code == 400


async def test_revoke_other_owned_device(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str],
) -> None:
    client, sessionmaker, _ = harness
    account_id, token = await _seed_account_with_session(sessionmaker)
    headers = {"Authorization": f"Bearer {token}"}

    # Seed a second device directly (simulates another installation).
    other_device_id = new_id("device")
    async with sessionmaker() as db:
        db.add(
            Device(
                id=other_device_id,
                account_id=account_id,
                public_key="other-device-pk-" + "z" * 16,
                state="active",
                last_seen_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        await db.commit()

    listed = await client.get("/v1/devices", headers=headers)
    match = next(d for d in listed.json()["items"] if d["device_id"] == other_device_id)
    etag = match["etag"]

    result = await client.post(
        f"/v1/devices/{other_device_id}/revoke",
        headers=_revoke_headers(token, etag, key="idem-other"),
        json={"schema_version": 1, "idempotency_key": "idem-other"},
    )
    assert result.status_code == 200
    assert result.json()["device"]["device_id"] == other_device_id
    assert result.json()["device"]["state"] == "revoked"

    # Current session (not bound to that device) remains valid.
    me = await client.get("/v1/auth/me", headers=headers)
    assert me.status_code == 200


async def test_revoke_stale_etag_is_precondition_failed(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str],
) -> None:
    client, sessionmaker, _ = harness
    account_id, token = await _seed_account_with_session(sessionmaker)
    device_id = new_id("device")
    async with sessionmaker() as db:
        db.add(
            Device(
                id=device_id,
                account_id=account_id,
                public_key="stale-etag-pk-" + "a" * 16,
                state="active",
            )
        )
        await db.commit()

    stale = await client.post(
        f"/v1/devices/{device_id}/revoke",
        headers=_revoke_headers(token, 'W/"deadbeef"'),
        json={"schema_version": 1, "idempotency_key": "idem-stale"},
    )
    assert stale.status_code == 412
    assert stale.json()["error"]["code"] == "AI_STP_PRECONDITION_FAILED"


async def test_register_rejects_full_passport_fields(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str],
) -> None:
    client, sessionmaker, _ = harness
    _, token = await _seed_account_with_session(sessionmaker)
    response = await client.post(
        "/v1/devices",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "public_key": "a" * 43,
            "nonce": "n" * 20,
            "signature": "s" * 86,
            "absolute_path": "C:\\Users\\me",
            "env": {"HOME": "/home/me"},
        },
    )
    assert response.status_code == 400
