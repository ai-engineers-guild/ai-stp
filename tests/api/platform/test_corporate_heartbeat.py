"""Corporate installation heartbeat API (t-heartbeat, GitHub #215).

The corporate `router.py` include is integration-owned wiring; these tests
mount the heartbeat router on the real application directly so the slice is
verified end-to-end in this worktree.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from nacl.signing import SigningKey
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.support.api_settings import make_settings

from ai_stp_api.app import create_app
from ai_stp_api.session import issue_session
from ai_stp_api.slices.corporate.heartbeat import router as heartbeat_router
from ai_stp_contracts.auth import DeviceRefreshRequest, device_refresh_message
from ai_stp_contracts.heartbeat import InstallationHeartbeatRequest, heartbeat_signature_message
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.heartbeat_models import InstallationHeartbeat
from ai_stp_platform.models import Account, Device
from ai_stp_platform.organization_models import OrganizationMembership
from ai_stp_platform.telemetry_policy_models import TelemetryPolicy, TelemetryRevocation
from ai_stp_platform.tenant_scope import set_tenant_scope

pytestmark = pytest.mark.platform
_DEVICE_KEYS: dict[str, SigningKey] = {}


def _now() -> datetime:
    return datetime.now(UTC)


@pytest_asyncio.fixture
async def heartbeat_client(
    tmp_path: Path, migrated_database_url: str
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession]]]:
    settings = make_settings(tmp_path, database_url=migrated_database_url)
    app = create_app(settings)
    app.include_router(heartbeat_router, prefix="/v1")
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app.state.sessionmaker


async def _account_with_device(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> tuple[str, str, str]:
    async with sessionmaker() as db:
        account = Account(id=new_id("account"), status="active")
        signer = SigningKey.generate()
        device = Device(
            id=new_id("device"),
            account_id=account.id,
            public_key=base64.b64encode(bytes(signer.verify_key)).decode("ascii"),
            state="active",
        )
        db.add_all([account, device])
        await db.flush()
        issued = await issue_session(
            db, account_id=account.id, device_id=device.id, ttl_seconds=3600
        )
        await db.commit()
        _DEVICE_KEYS[device.id] = signer
        return account.id, device.id, issued.raw_token


async def _bootstrap(client: AsyncClient, account_id: str, key: str) -> str:
    response = await client.post(
        "/v1/corporate/bootstrap",
        json={
            "schema_version": 1,
            "organization_name": key,
            "superadmin_account_id": account_id,
            "idempotency_key": key,
        },
        headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
    )
    assert response.status_code == 200, response.text
    return response.json()["organization_id"]


def _payload(
    account_id: str, device_id: str, checked_at: datetime | None = None, **overrides: Any
) -> dict[str, Any]:
    moment = checked_at or _now()
    payload: dict[str, Any] = {
        "schema_version": 1,
        "account_id": account_id,
        "device_id": device_id,
        "cli_version": "1.4.2",
        "capabilities": ["cli.heartbeat"],
        "last_sync_at": format_timestamp(moment - timedelta(minutes=5)),
        "health_state": "active",
        "checked_at": format_timestamp(moment),
        "signature": "A" * 86,
    }
    payload.update(overrides)
    return payload


async def _put(
    client: AsyncClient, path: str, *, json: dict[str, Any], headers: dict[str, str]
) -> Any:
    device_id = json["device_id"]
    signer = _DEVICE_KEYS.get(device_id)
    if signer is not None:
        report = InstallationHeartbeatRequest.model_validate(json)
        signature = signer.sign(heartbeat_signature_message(path.split("/")[4], report)).signature
        json = {**json, "signature": base64.urlsafe_b64encode(signature).rstrip(b"=").decode()}
    return await client.put(path, json=json, headers=headers)


async def test_device_can_renew_session_with_its_key(
    heartbeat_client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, sessionmaker = heartbeat_client
    account_id, device_id, token = await _account_with_device(sessionmaker)
    organization_id = await _bootstrap(client, account_id, "hb-renew-scenario-0001")
    request = DeviceRefreshRequest(
        device_id=device_id, checked_at=format_timestamp(_now()), signature="A" * 86
    )
    denied = await client.post(
        "/v1/auth/device/refresh",
        json=request.model_dump(mode="json"),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert denied.status_code == 400
    signature = _DEVICE_KEYS[device_id].sign(device_refresh_message(request)).signature
    signed = request.model_copy(
        update={"signature": base64.urlsafe_b64encode(signature).rstrip(b"=").decode()}
    )
    renewed = await client.post(
        "/v1/auth/device/refresh",
        json=signed.model_dump(mode="json"),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert renewed.status_code == 200, renewed.text
    policy = await client.get(
        f"/v1/corporate/organizations/{organization_id}/telemetry/heartbeat/policy",
        headers={"Authorization": f"Bearer {renewed.json()['access_token']}"},
    )
    assert policy.status_code == 200


async def test_heartbeat_write_is_idempotent_and_delayed_writes_cannot_regress(
    heartbeat_client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, sessionmaker = heartbeat_client
    account_id, device_id, token = await _account_with_device(sessionmaker)
    organization_id = await _bootstrap(client, account_id, "hb-idempotent-scenar-0001")
    auth = {"Authorization": f"Bearer {token}"}
    path = f"/v1/corporate/organizations/{organization_id}/telemetry/heartbeat"

    first_payload = _payload(account_id, device_id)
    first = await _put(client, path, json=first_payload, headers=auth)
    assert first.status_code == 200, first.text
    assert first.json()["health_state"] == "active"
    assert first.json()["revision"] == 1

    forged = await client.put(
        path,
        json={**first_payload, "signature": "A" * 86},
        headers=auth,
    )
    assert forged.status_code == 400

    replay = await _put(client, path, json=first_payload, headers=auth)
    assert replay.status_code == 200, replay.text
    assert replay.json()["revision"] == 1

    delayed = await _put(
        client,
        path,
        json=_payload(
            account_id,
            device_id,
            checked_at=_now() - timedelta(minutes=2),
            cli_version="0.0.1",
            health_state="failing",
        ),
        headers=auth,
    )
    assert delayed.status_code == 200, delayed.text
    assert delayed.json()["revision"] == 1
    assert delayed.json()["cli_version"] == "1.4.2"

    newer = await _put(
        client,
        path,
        json=_payload(account_id, device_id, checked_at=_now() + timedelta(seconds=30)),
        headers=auth,
    )
    assert newer.status_code == 200, newer.text
    assert newer.json()["revision"] == 2


async def test_heartbeat_health_states_and_staleness_read_time(
    heartbeat_client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, sessionmaker = heartbeat_client
    account_id, device_id, token = await _account_with_device(sessionmaker)
    organization_id = await _bootstrap(client, account_id, "hb-states-scenario-0002")
    auth = {"Authorization": f"Bearer {token}"}
    path = f"/v1/corporate/organizations/{organization_id}/telemetry/heartbeat"

    missing = await client.get(path, headers=auth)
    assert missing.status_code == 200, missing.text
    assert missing.json()["health_state"] == "unknown"

    assert (
        await _put(client, path, json=_payload(account_id, device_id), headers=auth)
    ).status_code == 200
    own = await client.get(path, headers=auth)
    assert own.json()["health_state"] == "active"

    async with sessionmaker() as db:
        row = await db.get(InstallationHeartbeat, (organization_id, device_id))
        assert row is not None
        row.received_at = datetime.now(UTC) - timedelta(hours=25)
        await db.commit()

    stale = await client.get(path, headers=auth)
    assert stale.json()["health_state"] == "stale"

    disabled = await _put(
        client,
        path,
        json=_payload(
            account_id,
            device_id,
            checked_at=_now() + timedelta(minutes=1),
            health_state="disabled",
        ),
        headers=auth,
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["health_state"] == "disabled"


async def test_organization_policy_controls_cadence_staleness_and_revocation(
    heartbeat_client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, sessionmaker = heartbeat_client
    account_id, device_id, token = await _account_with_device(sessionmaker)
    organization_id = await _bootstrap(client, account_id, "hb-policy-scenario-0005")
    auth = {"Authorization": f"Bearer {token}"}
    write_path = f"/v1/corporate/organizations/{organization_id}/telemetry/heartbeat"
    policy_path = f"/v1/corporate/organizations/{organization_id}/telemetry/heartbeat/policy"

    async with sessionmaker() as db:
        await set_tenant_scope(db, organization_id)
        db.add(
            TelemetryPolicy(
                organization_id=organization_id,
                raw_retention_days=90,
                aggregate_retention_days=365,
                legal_basis="consent",
                notice_revision=0,
                heartbeat_interval_seconds=900,
                heartbeat_stale_after_seconds=3600,
                policy_version=1,
            )
        )
        await db.commit()

    settings = await client.get(policy_path, headers=auth)
    assert settings.status_code == 200, settings.text
    assert settings.json()["interval_seconds"] == 900
    assert settings.json()["stale_after_seconds"] == 3600

    written = await _put(client, write_path, json=_payload(account_id, device_id), headers=auth)
    assert written.status_code == 200, written.text
    async with sessionmaker() as db:
        await set_tenant_scope(db, organization_id)
        row = await db.get(InstallationHeartbeat, (organization_id, device_id))
        assert row is not None
        row.received_at = _now() - timedelta(hours=2)
        await db.commit()
    stale = await client.get(write_path, headers=auth)
    assert stale.json()["health_state"] == "stale"
    assert stale.json()["stale_after_seconds"] == 3600

    async with sessionmaker() as db:
        await set_tenant_scope(db, organization_id)
        policy_row = await db.get(TelemetryPolicy, organization_id)
        assert policy_row is not None
        policy_row.heartbeat_enabled = False
        await db.commit()
    disabled = await _put(
        client,
        write_path,
        json=_payload(account_id, device_id, checked_at=_now() + timedelta(minutes=1)),
        headers=auth,
    )
    assert disabled.status_code == 403

    async with sessionmaker() as db:
        await set_tenant_scope(db, organization_id)
        policy_row = await db.get(TelemetryPolicy, organization_id)
        assert policy_row is not None
        policy_row.heartbeat_enabled = True
        db.add(
            TelemetryRevocation(
                organization_id=organization_id,
                subject_kind="account",
                subject_id=account_id,
                state="revoked",
                legal_basis="consent",
                notice_revision=0,
            )
        )
        await db.commit()
    revoked = await _put(
        client,
        write_path,
        json=_payload(account_id, device_id, checked_at=_now() + timedelta(minutes=2)),
        headers=auth,
    )
    assert revoked.status_code == 403


async def test_heartbeat_rejects_foreign_identity_and_deviceless_sessions(
    heartbeat_client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, sessionmaker = heartbeat_client
    account_id, device_id, token = await _account_with_device(sessionmaker)
    organization_id = await _bootstrap(client, account_id, "hb-identity-scenario-0003")
    auth = {"Authorization": f"Bearer {token}"}
    path = f"/v1/corporate/organizations/{organization_id}/telemetry/heartbeat"

    foreign_account = await _put(
        client, path, json=_payload(new_id("account"), device_id), headers=auth
    )
    assert foreign_account.status_code == 403

    foreign_device = await _put(
        client, path, json=_payload(account_id, new_id("device")), headers=auth
    )
    assert foreign_device.status_code == 403

    async with sessionmaker() as db:
        cookie_session = await issue_session(
            db, account_id=account_id, device_id=None, ttl_seconds=3600
        )
        await db.commit()
    deviceless = await _put(
        client,
        path,
        json=_payload(account_id, device_id),
        headers={"Authorization": f"Bearer {cookie_session.raw_token}"},
    )
    assert deviceless.status_code == 400


async def test_heartbeat_tenant_and_role_isolation(
    heartbeat_client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, sessionmaker = heartbeat_client
    owner_id, owner_device, owner_token = await _account_with_device(sessionmaker)
    member_id, member_device, member_token = await _account_with_device(sessionmaker)
    outsider_id, outsider_device, outsider_token = await _account_with_device(sessionmaker)
    organization_id = await _bootstrap(client, owner_id, "hb-tenant-scenario-0004")
    async with sessionmaker() as db:
        await set_tenant_scope(db, organization_id)
        db.add(
            OrganizationMembership(
                organization_id=organization_id,
                account_id=member_id,
                role="member",
            )
        )
        await db.commit()

    owner_auth = {"Authorization": f"Bearer {owner_token}"}
    member_auth = {"Authorization": f"Bearer {member_token}"}
    outsider_auth = {"Authorization": f"Bearer {outsider_token}"}
    write_path = f"/v1/corporate/organizations/{organization_id}/telemetry/heartbeat"
    list_path = f"/v1/corporate/organizations/{organization_id}/telemetry/heartbeats"

    assert (
        await _put(client, write_path, json=_payload(owner_id, owner_device), headers=owner_auth)
    ).status_code == 200
    assert (
        await _put(client, write_path, json=_payload(member_id, member_device), headers=member_auth)
    ).status_code == 200

    denied = await _put(
        client,
        write_path,
        json=_payload(outsider_id, outsider_device),
        headers=outsider_auth,
    )
    assert denied.status_code == 403

    member_list = await client.get(list_path, headers=member_auth)
    assert member_list.status_code == 200, member_list.text
    assert {item["account_id"] for item in member_list.json()["items"]} == {member_id}

    owner_list = await client.get(list_path, headers=owner_auth)
    assert owner_list.status_code == 200, owner_list.text
    assert {item["account_id"] for item in owner_list.json()["items"]} == {
        owner_id,
        member_id,
    }

    outsider_list = await client.get(list_path, headers=outsider_auth)
    assert outsider_list.status_code == 403

    filtered = await client.get(list_path, params={"health_state": "stale"}, headers=owner_auth)
    assert filtered.status_code == 200
    assert filtered.json()["items"] == []
