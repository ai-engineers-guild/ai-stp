"""Corporate installation heartbeat API (t-heartbeat, GitHub #215).

The corporate `router.py` include is integration-owned wiring; these tests
mount the heartbeat router on the real application directly so the slice is
verified end-to-end in this worktree.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any, Self

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.support.api_settings import make_settings

from ai_stp_api.app import create_app
from ai_stp_api.session import issue_session
from ai_stp_api.slices.corporate import heartbeat as heartbeat_routes
from ai_stp_api.slices.corporate.heartbeat import router as heartbeat_router
from ai_stp_api.slices.corporate.heartbeat_report import router as heartbeat_report_router
from ai_stp_contracts.auth import DeviceRefreshRequest, device_refresh_message
from ai_stp_contracts.heartbeat import InstallationHeartbeatRequest, heartbeat_signature_message
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.heartbeat_models import InstallationHeartbeat, InstallationHeartbeatEvent
from ai_stp_platform.models import Account, Device
from ai_stp_platform.organization_models import Organization, OrganizationMembership
from ai_stp_platform.telemetry_policy_models import TelemetryPolicy, TelemetryRevocation
from ai_stp_platform.tenant_scope import set_tenant_scope

pytestmark = pytest.mark.platform
_DEVICE_KEYS: dict[str, Ed25519PrivateKey] = {}


def _now() -> datetime:
    return datetime.now(UTC)


@pytest_asyncio.fixture
async def heartbeat_client(
    tmp_path: Path, migrated_database_url: str
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession]]]:
    settings = make_settings(tmp_path, database_url=migrated_database_url)
    app = create_app(settings)
    app.include_router(heartbeat_router, prefix="/v1")
    app.include_router(heartbeat_report_router, prefix="/v1")
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app.state.sessionmaker


async def _account_with_device(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> tuple[str, str, str]:
    async with sessionmaker() as db:
        account = Account(id=new_id("account"), status="active")
        signer = Ed25519PrivateKey.generate()
        device = Device(
            id=new_id("device"),
            account_id=account.id,
            public_key=base64.b64encode(signer.public_key().public_bytes_raw()).decode("ascii"),
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
        signature = signer.sign(heartbeat_signature_message(path.split("/")[4], report))
        json = {**json, "signature": base64.urlsafe_b64encode(signature).rstrip(b"=").decode()}
    return await client.put(path, json=json, headers=headers)


async def test_bound_heartbeat_refuses_stale_and_reenabled_policy_without_breaking_legacy(
    heartbeat_client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, sessionmaker = heartbeat_client
    account, device, token = await _account_with_device(sessionmaker)
    organization = await _bootstrap(client, account, "hb-bound-policy-0001")
    path = f"/v1/corporate/organizations/{organization}/telemetry/heartbeat"
    auth = {"Authorization": f"Bearer {token}"}
    moment = _now()
    policy = await client.get(path + "/policy", headers=auth)
    assert policy.status_code == 200
    assert policy.json()["policy_version"] == 0
    first = await _put(
        client, path, json=_payload(account, device, moment, policy_version=0), headers=auth
    )
    assert first.status_code == 200, first.text
    duplicate = await _put(
        client, path, json=_payload(account, device, moment, policy_version=0), headers=auth
    )
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["revision"] == 1
    conflicting = await _put(
        client,
        path,
        json=_payload(account, device, moment, policy_version=0, health_state="failing"),
        headers=auth,
    )
    assert conflicting.status_code == 409, conflicting.text

    async with sessionmaker() as db:
        await set_tenant_scope(db, organization)
        db.add(
            TelemetryPolicy(
                organization_id=organization,
                raw_retention_days=90,
                aggregate_retention_days=365,
                legal_basis="consent",
                notice_revision=0,
                policy_version=1,
            )
        )
        await db.commit()
    policy = await client.get(path + "/policy", headers=auth)
    assert policy.json()["policy_version"] == 1
    relabeled = await _put(
        client, path, json=_payload(account, device, moment, policy_version=1), headers=auth
    )
    assert relabeled.status_code == 409, relabeled.text
    stale = await _put(
        client,
        path,
        json=_payload(account, device, moment + timedelta(seconds=1), policy_version=0),
        headers=auth,
    )
    assert stale.status_code == 409, stale.text
    async with sessionmaker() as db:
        await set_tenant_scope(db, organization)
        row = await db.get(InstallationHeartbeat, (organization, device))
        assert row is not None and row.revision == 1
        count = await db.scalar(
            select(func.count())
            .select_from(InstallationHeartbeatEvent)
            .where(
                InstallationHeartbeatEvent.organization_id == organization,
            )
        )
        assert count == 1

    queued = _payload(account, device, moment + timedelta(seconds=2), policy_version=1)
    for version, enabled in [(2, False), (3, True)]:
        async with sessionmaker() as db:
            await set_tenant_scope(db, organization)
            policy_row = await db.get(TelemetryPolicy, organization)
            assert policy_row is not None
            policy_row.heartbeat_enabled = enabled
            policy_row.policy_version = version
            await db.commit()
    stale = await _put(client, path, json=queued, headers=auth)
    assert stale.status_code == 409, stale.text
    current = await _put(
        client,
        path,
        json=_payload(account, device, moment + timedelta(seconds=3), policy_version=3),
        headers=auth,
    )
    assert current.status_code == 200, current.text
    assert current.json()["revision"] == 2
    legacy = await _put(
        client, path, json=_payload(account, device, moment + timedelta(seconds=4)), headers=auth
    )
    assert legacy.status_code == 200, legacy.text
    assert legacy.json()["revision"] == 3


@pytest.mark.parametrize("change", ["policy", "expiry"])
async def test_queued_heartbeat_rechecks_admission_after_actual_tenant_lock_wait(
    heartbeat_client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    client, sessionmaker = heartbeat_client
    account, device, token = await _account_with_device(sessionmaker)
    organization = await _bootstrap(client, account, f"hb-policy-lock-0001-{change}")
    path = f"/v1/corporate/organizations/{organization}/telemetry/heartbeat"
    auth = {"Authorization": f"Bearer {token}"}
    async with sessionmaker() as db:
        await set_tenant_scope(db, organization)
        db.add(
            TelemetryPolicy(
                organization_id=organization,
                raw_retention_days=90,
                aggregate_retention_days=365,
                legal_basis="consent",
                notice_revision=0,
                policy_version=1,
            )
        )
        await db.commit()
    async with sessionmaker() as writer:
        await set_tenant_scope(writer, organization)
        await writer.scalar(
            select(Organization).where(Organization.id == organization).with_for_update()
        )
        pid = await writer.scalar(text("SELECT pg_backend_pid()"))
        assert isinstance(pid, int)
        pending = asyncio.create_task(
            _put(client, path, json=_payload(account, device, policy_version=1), headers=auth)
        )
        try:
            # Observe a real PostgreSQL wait on this fixture's writer. A sleep
            # alone cannot establish ordering or the policy snapshot in use.
            async with sessionmaker() as observer, asyncio.timeout(10):
                while not await observer.scalar(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE datname=current_database() "
                        "AND :owner_pid=ANY(pg_blocking_pids(pid)))"
                    ),
                    {"owner_pid": pid},
                ):
                    assert not pending.done(), "heartbeat bypassed the held tenant mutation lock"
                    await asyncio.sleep(0.05)
            if change == "policy":
                policy = await writer.get(TelemetryPolicy, organization)
                assert policy is not None
                policy.heartbeat_interval_seconds = 1200
                policy.policy_version = 2
            else:
                expired_at = _now() + timedelta(minutes=6)

                class ExpiredClock(datetime):
                    @classmethod
                    def now(cls, tz: tzinfo | None = None) -> Self:
                        return cls.fromtimestamp(expired_at.timestamp(), tz)

                monkeypatch.setattr(heartbeat_routes, "datetime", ExpiredClock)
            await writer.commit()
            refused = await asyncio.wait_for(pending, 10)
            assert refused.status_code == (409 if change == "policy" else 400), refused.text
        finally:
            if not pending.done():
                pending.cancel()
            try:
                await writer.rollback()
                with suppress(asyncio.CancelledError):
                    await pending
            finally:
                monkeypatch.setattr(heartbeat_routes, "datetime", datetime)
    async with sessionmaker() as db:
        await set_tenant_scope(db, organization)
        assert await db.get(InstallationHeartbeat, (organization, device)) is None
        count = await db.scalar(
            select(func.count())
            .select_from(InstallationHeartbeatEvent)
            .where(
                InstallationHeartbeatEvent.organization_id == organization,
            )
        )
        assert count == 0
    current = await _put(
        client,
        path,
        json=_payload(account, device, policy_version=2 if change == "policy" else 1),
        headers=auth,
    )
    assert current.status_code == 200, current.text


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
    signature = _DEVICE_KEYS[device_id].sign(device_refresh_message(request))
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
    report_path = f"/v1/corporate/organizations/{organization_id}/telemetry/heartbeat-report"
    unknown = await client.get(report_path, headers=auth)
    assert unknown.status_code == 200, unknown.text
    assert unknown.json()["items"][0]["status"] == "unknown"

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
    async with sessionmaker() as db:
        await set_tenant_scope(db, organization_id)
        events = (
            await db.scalars(
                select(InstallationHeartbeatEvent).where(
                    InstallationHeartbeatEvent.organization_id == organization_id,
                    InstallationHeartbeatEvent.device_id == device_id,
                )
            )
        ).all()
        assert len(events) == 2
    history = await client.get(f"{report_path}?view=history&period=24h", headers=auth)
    assert history.status_code == 200, history.text
    assert sum(bucket["received"] for bucket in history.json()["items"][0]["buckets"]) == 2
    hidden = await client.get(f"{report_path}?team=team_foreign", headers=auth)
    assert hidden.status_code == 200 and hidden.json()["items"] == []
    hidden_employee = await client.get(f"{report_path}?employee=account_foreign", headers=auth)
    assert hidden_employee.status_code == 200 and hidden_employee.json()["items"] == []
    async with sessionmaker() as db:
        await set_tenant_scope(db, organization_id)
        member = await db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.account_id == account_id,
            )
        )
        assert member is not None
        member.role = "member"
        await db.commit()
    denied = await client.get(report_path, headers=auth)
    assert denied.status_code == 403


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


async def test_superadmin_can_set_one_minute_heartbeat_policy(
    heartbeat_client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, sessionmaker = heartbeat_client
    account_id, _device_id, token = await _account_with_device(sessionmaker)
    organization_id = await _bootstrap(client, account_id, "hb-policy-edit-scenario-0006")
    auth = {"Authorization": f"Bearer {token}"}
    context = await client.get(
        f"/v1/corporate/organizations/{organization_id}/context", headers=auth
    )
    assert context.status_code == 200, context.text
    assert "telemetry.manage" in context.json()["capabilities"]
    revision = context.json()["organization"]["authorization_revision"]
    path = f"/v1/corporate/organizations/{organization_id}/telemetry/policy"
    saved = await client.put(
        path,
        headers=auth,
        json={
            "schema_version": 1,
            "raw_retention_days": 90,
            "aggregate_retention_days": 365,
            "legal_basis": "consent",
            "notice_revision": 0,
            "heartbeat_enabled": True,
            "heartbeat_interval_seconds": 60,
            "heartbeat_retry_base_seconds": 60,
            "heartbeat_retry_max_seconds": 3600,
            "heartbeat_stale_after_seconds": 3600,
            "expected_policy_revision": 0,
            "authorization_revision": revision,
            "idempotency_key": "hb-policy-edit-scenario-0006",
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["heartbeat_interval_seconds"] == 60
    report = await client.get(
        f"/v1/corporate/organizations/{organization_id}/telemetry/heartbeat-report",
        headers=auth,
    )
    assert report.status_code == 200, report.text
    assert report.json()["interval_seconds"] == 60


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


async def test_heartbeat_boundary_rejects_unsigned_stale_and_wrong_org(
    heartbeat_client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """The signed-request cutover leaves no reader fallback for old clients.

    A `0.0.29`-shape body has no `signature` field at all; it must be rejected
    before mutation, never parsed into an implicit unsigned accept. The same
    boundary refuses a stale `checked_at`, a future one, and a signature that
    binds a different organization than the route's.
    """
    client, sessionmaker = heartbeat_client
    account_id, device_id, token = await _account_with_device(sessionmaker)
    organization_id = await _bootstrap(client, account_id, "hb-boundary-scenario-0005")
    auth = {"Authorization": f"Bearer {token}"}
    path = f"/v1/corporate/organizations/{organization_id}/telemetry/heartbeat"

    unsigned = _payload(account_id, device_id)
    unsigned.pop("signature")
    refused = await client.put(path, json=unsigned, headers=auth)
    assert refused.status_code in {400, 422}, refused.text

    stale = await _put(
        client,
        path,
        json=_payload(account_id, device_id, checked_at=_now() - timedelta(minutes=10)),
        headers=auth,
    )
    assert stale.status_code == 400, stale.text

    future = await _put(
        client,
        path,
        json=_payload(account_id, device_id, checked_at=_now() + timedelta(minutes=10)),
        headers=auth,
    )
    assert future.status_code == 400, future.text

    signer = _DEVICE_KEYS[device_id]
    report = InstallationHeartbeatRequest.model_validate(_payload(account_id, device_id))
    foreign_signature = signer.sign(heartbeat_signature_message("org_other", report))
    foreign = await client.put(
        path,
        json={
            **report.model_dump(mode="json"),
            "signature": base64.urlsafe_b64encode(foreign_signature).rstrip(b"=").decode(),
        },
        headers=auth,
    )
    assert foreign.status_code == 400, foreign.text

    missing = await client.get(path, headers=auth)
    assert missing.status_code == 200
    assert missing.json()["health_state"] == "unknown"


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


async def test_history_names_the_true_last_beat_outside_the_window(
    heartbeat_client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """A stale device keeps its real `last_heartbeat_at` when the window holds no events."""
    client, sessionmaker = heartbeat_client
    account_id, device_id, token = await _account_with_device(sessionmaker)
    organization_id = await _bootstrap(client, account_id, "hb-history-stale-0007")
    auth = {"Authorization": f"Bearer {token}"}
    old = _now() - timedelta(days=2)
    async with sessionmaker() as db:
        await set_tenant_scope(db, organization_id)
        db.add(
            InstallationHeartbeat(
                organization_id=organization_id,
                device_id=device_id,
                account_id=account_id,
                cli_version="1.4.2",
                capabilities=["cli.heartbeat"],
                reported_state="active",
                checked_at=old,
                received_at=old,
            )
        )
        db.add(
            InstallationHeartbeatEvent(
                organization_id=organization_id,
                device_id=device_id,
                account_id=account_id,
                checked_at=old,
                received_at=old,
                reported_state="active",
                interval_seconds=3600,
                policy_version=1,
            )
        )
        await db.commit()
    history = await client.get(
        f"/v1/corporate/organizations/{organization_id}/telemetry/heartbeat-report"
        "?view=history&period=24h",
        headers=auth,
    )
    assert history.status_code == 200, history.text
    row = history.json()["items"][0]
    assert row["status"] == "stale"
    assert row["last_heartbeat_at"] == format_timestamp(old)
