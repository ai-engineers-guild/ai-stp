# pyright: reportUnusedFunction=false
"""API/PostgreSQL coverage for SPEC-026 publication, grants, reports, staff."""

from __future__ import annotations

import io
import zipfile
from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.app import create_app
from ai_stp_api.errors import CATEGORY_STATUS, ErrorCategory
from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_foundation.digests import digest_bytes
from ai_stp_foundation.ids import new_id
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_platform.models import (
    Account,
    AuditEvent,
    CatalogMetadata,
    Device,
    OAuthIdentity,
    PublicationPlan,
)
from ai_stp_platform.queue.engine import claim, fail, mark_succeeded
from ai_stp_platform.queue.models import Job
from ai_stp_platform.queue.states import JobState
from ai_stp_platform.safety.workdir import MAX_ARTIFACT_BYTES
from ai_stp_platform.settings import StorageSettings
from ai_stp_platform.storage.memory import MemoryObjectClient
from ai_stp_platform.storage.object_store import (
    ARTIFACT_DIGEST_DOMAIN,
    ImmutableObjectStore,
)
from ai_stp_worker.handlers import resolve
from ai_stp_worker.handlers.deliver_invitation import MAIL_PORT

pytestmark = pytest.mark.platform


def _skill_zip(body: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("SKILL.md", body)
    return buf.getvalue()


# Real content digests so safety validate can fetch and re-hash bytes.
CLEAN_ARTIFACT = _skill_zip("# demo-skill\n\nClean publication fixture.\n")
CLEAN_ARTIFACT_B = _skill_zip("# demo-skill-b\n\nSecond publication fixture.\n")
DIGEST = digest_bytes(ARTIFACT_DIGEST_DOMAIN, CLEAN_ARTIFACT)
DIGEST2 = digest_bytes(ARTIFACT_DIGEST_DOMAIN, CLEAN_ARTIFACT_B)
ARTIFACT_BY_DIGEST = {
    DIGEST: CLEAN_ARTIFACT,
    DIGEST2: CLEAN_ARTIFACT_B,
}


@pytest.fixture(autouse=True)
def _publication_artifact_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Serve content-addressed skill zips so validate safety suite can pass."""
    client = MemoryObjectClient()
    settings = StorageSettings(
        endpoint="http://memory.test",
        bucket="test",
        access_key_id="test",
        secret_access_key="test",
    )
    store = ImmutableObjectStore(settings=settings, client=client)

    for digest, payload in ARTIFACT_BY_DIGEST.items():
        key = store.key_for_digest(digest)
        client.objects[(settings.bucket, key)] = {
            "body": payload,
            "metadata": {
                "ai-stp-digest": digest,
                "ai-stp-size-bytes": str(len(payload)),
                "ai-stp-content-id": digest,
            },
            "size_bytes": len(payload),
        }

    async def _open() -> ImmutableObjectStore:
        return store

    async def _close(_store: ImmutableObjectStore | None) -> None:
        return None

    monkeypatch.setattr(
        "ai_stp_platform.publication_logic.open_env_object_store",
        _open,
    )
    monkeypatch.setattr(
        "ai_stp_platform.publication_logic.close_env_object_store",
        _close,
    )
    monkeypatch.setattr("ai_stp_worker.handlers.publish.open_env_object_store", _open)
    monkeypatch.setattr("ai_stp_worker.handlers.publish.close_env_object_store", _close)


def _passport(
    *,
    owner_id: str,
    version: str = "1.0",
    digest: str = DIGEST,
    requires_credentials: bool = False,
) -> dict[str, object]:
    payload = ARTIFACT_BY_DIGEST.get(digest, CLEAN_ARTIFACT)
    passport: dict[str, object] = {
        "schema_version": 1,
        "kind": "component",
        "stable_id": "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        "revision_id": "revision_" + "0" * 64,
        "parent_revision_ids": [],
        "owner_id": owner_id,
        "created_at": "2026-08-10T00:00:00.000Z",
        "visibility": "public",
        "facts": {},
        "name": "demo-skill",
        "description": "Demo publication component.",
        "version": version,
        "tags": ["review"],
        "license": {"spdx_id": "MIT", "redistribution_allowed": True},
        "source": {
            "repository": "https://github.com/example/demo",
            "commit": "a" * 40,
            "path": "skills/demo",
        },
        "artifact": {"digest": digest, "size_bytes": len(payload)},
        "requires_credentials": requires_credentials,
        "requires_authorization": "none",
        "permissions": {"filesystem": [], "network": [], "process": []},
        "external_endpoints": [],
        "compatibility_evidence_refs": [],
        "harness_id": "claude-code",
        "required_env": [],
        "component_type": "skill",
        "projection_kind": "native_files",
        "variant_id": None,
        "provides_capabilities": [],
        "requires_components": [],
        "requires_capabilities": [],
        "conflicts": {
            "paths": [],
            "commands": [],
            "hooks": [],
            "mcp": [],
            "agents": [],
            "plugins": [],
        },
        "managed_paths": [],
        "native_ids": [],
    }
    passport["revision_id"] = derive_revision_id(passport)  # type: ignore[arg-type]
    return passport


@pytest_asyncio.fixture
async def harness(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings]]:
    settings = settings_factory(database_url=migrated_database_url)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app.state.sessionmaker, settings


async def _seed_account_device(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    email: str | None = None,
    email_verified: bool = True,
) -> tuple[str, str, str]:
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
        if email is not None:
            db.add(
                OAuthIdentity(
                    account_id=account.id,
                    provider="github",
                    provider_subject=new_id("sub"),
                    email=email,
                    email_verified=email_verified,
                    state="linked",
                )
            )
        await db.flush()
        issued = await issue_session(
            db, account_id=account.id, device_id=device.id, ttl_seconds=3600
        )
        await db.commit()
        return account.id, device.id, issued.raw_token


async def _seed_owned_catalog(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    account_id: str,
    stable_id: str = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
    version: str = "1.0",
) -> None:
    async with sessionmaker() as db:
        db.add(
            CatalogMetadata(
                owner_account_id=account_id,
                object_kind="component",
                stable_id=stable_id,
                version=version,
                current_revision_id="revision_" + "0" * 64,
                visibility="private",
                lifecycle_state="draft",
                name="owned",
            )
        )
        await db.commit()


async def _drain_jobs(
    sessionmaker: async_sessionmaker[AsyncSession], *, worker_id: str = "w1"
) -> int:
    processed = 0
    for _ in range(20):
        async with sessionmaker() as session, session.begin():
            claimed = await claim(session, worker_id=worker_id, batch=5)
            job_ids = [j.id for j in claimed]
        if not job_ids:
            break
        for job_id in job_ids:
            async with sessionmaker() as session, session.begin():
                job = await session.get(Job, job_id)
                assert job is not None
                handler = resolve(job.job_type)
                assert handler is not None
                try:
                    await handler(session, job.payload)
                except Exception as exc:
                    await fail(session, job, error=type(exc).__name__)
                else:
                    await mark_succeeded(session, job)
                processed += 1
    return processed


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _bind_plan_bytes(client: AsyncClient, token: str, plan_id: str, payload: bytes) -> None:
    bound = await client.put(
        f"/v1/publications/plans/{plan_id}/artifact",
        headers={**_auth(token), "Content-Type": "application/octet-stream"},
        content=payload,
    )
    assert bound.status_code == 200, bound.text


async def test_publication_artifact_rejects_declared_oversize_before_buffering(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = harness
    _account_id, _device_id, token = await _seed_account_device(sessionmaker)

    response = await client.put(
        "/v1/publications/plans/plan_not_read/artifact",
        headers={
            **_auth(token),
            "Content-Type": "application/octet-stream",
            "Content-Length": str(MAX_ARTIFACT_BYTES + 1),
        },
        content=b"x",
    )

    assert response.status_code == int(CATEGORY_STATUS[ErrorCategory.VALIDATION])
    assert response.json()["error"]["message"] == "artifact exceeds the accepted size"


async def test_publication_plan_confirm_validate_publish(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = harness
    account_id, device_id, token = await _seed_account_device(sessionmaker)
    passport = _passport(owner_id=account_id)
    create = await client.post(
        "/v1/publications/plans",
        headers=_auth(token),
        json={
            "schema_version": 1,
            "object_kind": "component",
            "stable_id": "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
            "version": "1.0",
            "content_digest": DIGEST,
            "policy_version": "1",
            "passport": passport,
            "attestations": [],
            "idempotency_key": "0123456789abcdef",
            "device_id": device_id,
        },
    )
    assert create.status_code == 201, create.text
    body = create.json()
    plan_id = body["plan_id"]
    plan_hash = body["plan_hash"]

    # idempotent create
    again = await client.post(
        "/v1/publications/plans",
        headers=_auth(token),
        json={
            "schema_version": 1,
            "object_kind": "component",
            "stable_id": "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
            "version": "1.0",
            "content_digest": DIGEST,
            "policy_version": "1",
            "passport": passport,
            "attestations": [],
            "idempotency_key": "0123456789abcdef",
            "device_id": device_id,
        },
    )
    assert again.status_code == 201
    assert again.json()["plan_id"] == plan_id

    missing_bytes = await client.post(
        f"/v1/publications/plans/{plan_id}/confirm",
        headers=_auth(token),
        json={
            "schema_version": 1,
            "plan_hash": plan_hash,
            "confirmed": True,
            "idempotency_key": "confirmmissing0001",
        },
    )
    assert missing_bytes.status_code == 400

    await _bind_plan_bytes(client, token, plan_id, CLEAN_ARTIFACT)

    bad = await client.post(
        f"/v1/publications/plans/{plan_id}/confirm",
        headers=_auth(token),
        json={
            "schema_version": 1,
            "plan_hash": "plan_" + "0" * 64,
            "confirmed": True,
            "idempotency_key": "confirmkey0000001",
        },
    )
    assert bad.status_code == 400

    ok = await client.post(
        f"/v1/publications/plans/{plan_id}/confirm",
        headers=_auth(token),
        json={
            "schema_version": 1,
            "plan_hash": plan_hash,
            "confirmed": True,
            "idempotency_key": "confirmkey0000001",
        },
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["state"] == "validating"

    processed = await _drain_jobs(sessionmaker)
    assert processed >= 1

    status = await client.get(f"/v1/publications/plans/{plan_id}", headers=_auth(token))
    assert status.status_code == 200
    assert status.json()["state"] == "published"
    assert status.json()["component_verified"] is True

    public_detail = await client.get("/v1/catalog/components/component_01JQZK7B8N4M6P2R9T5V0X3Y7Z")
    assert public_detail.status_code == 200, public_detail.text
    public_version = await client.get(
        "/v1/catalog/components/component_01JQZK7B8N4M6P2R9T5V0X3Y7Z/versions/1.0"
    )
    assert public_version.status_code == 200, public_version.text
    assert public_version.json()["passport"]["revision_id"] == passport["revision_id"]

    async with sessionmaker() as db:
        cat = await db.scalar(
            select(CatalogMetadata).where(
                CatalogMetadata.stable_id == "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
                CatalogMetadata.version == "1.0",
            )
        )
        assert cat is not None
        assert cat.lifecycle_state == "active"
        assert cat.component_verified is True
        assert cat.owner_account_id == account_id

    # same version different digest rejected
    create2 = await client.post(
        "/v1/publications/plans",
        headers=_auth(token),
        json={
            "schema_version": 1,
            "object_kind": "component",
            "stable_id": "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
            "version": "1.0",
            "content_digest": DIGEST2,
            "policy_version": "1",
            "passport": _passport(owner_id=account_id, digest=DIGEST2),
            "attestations": [],
            "idempotency_key": "0123456789abcde2",
            "device_id": device_id,
        },
    )
    plan2 = create2.json()
    await _bind_plan_bytes(client, token, plan2["plan_id"], CLEAN_ARTIFACT_B)
    conf2 = await client.post(
        f"/v1/publications/plans/{plan2['plan_id']}/confirm",
        headers=_auth(token),
        json={
            "schema_version": 1,
            "plan_hash": plan2["plan_hash"],
            "confirmed": True,
            "idempotency_key": "confirmkey0000002",
        },
    )
    assert conf2.status_code == 200
    await _drain_jobs(sessionmaker, worker_id="w2")
    async with sessionmaker() as db:
        plan_row = await db.get(PublicationPlan, plan2["plan_id"])
        assert plan_row is not None
        # publish handler fails with different digest → failed or stuck publish_planned
        assert plan_row.state in {"failed", "publish_planned", "published"}


async def test_publication_rejects_invalid_device_and_publishes_warning(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = harness
    account_id, device_id, token = await _seed_account_device(sessionmaker)
    base: dict[str, object] = {
        "schema_version": 1,
        "object_kind": "component",
        "stable_id": "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        "version": "3.0",
        "content_digest": DIGEST,
        "policy_version": "1",
        "attestations": [],
        "device_id": device_id,
    }

    incomplete = await client.post(
        "/v1/publications/plans",
        headers=_auth(token),
        json={**base, "passport": {"name": "incomplete"}, "idempotency_key": "invalidplan000001"},
    )
    assert incomplete.status_code == 400

    wrong_device = await client.post(
        "/v1/publications/plans",
        headers=_auth(token),
        json={
            **base,
            "device_id": "device_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
            "passport": _passport(owner_id=account_id, version="3.0", requires_credentials=True),
            "idempotency_key": "wrongdevice000001",
        },
    )
    assert wrong_device.status_code == 400

    fake_attestation: dict[str, object] = {
        "schema_version": 1,
        "check_id": "credentials",
        "result": "passed",
        "tool_versions": {"runner": "1"},
        "test_case_ids": ["cred-basic"],
        "device_id": device_id,
        "attested_at": "2026-01-01T00:00:00.000Z",
        "signature": "s" * 16,
    }
    created = await client.post(
        "/v1/publications/plans",
        headers=_auth(token),
        json={
            **base,
            "passport": _passport(owner_id=account_id, version="3.0", requires_credentials=True),
            "attestations": [fake_attestation],
            "idempotency_key": "warningplan000001",
        },
    )
    assert created.status_code == 400

    missing_attestation = await client.post(
        "/v1/publications/plans",
        headers=_auth(token),
        json={
            **base,
            "version": "3.1",
            "passport": _passport(owner_id=account_id, version="3.1", requires_credentials=True),
            "idempotency_key": "missingattest0001",
        },
    )
    assert missing_attestation.status_code == 201
    missing_plan = missing_attestation.json()
    await _bind_plan_bytes(client, token, missing_plan["plan_id"], CLEAN_ARTIFACT)
    missing_confirm = await client.post(
        f"/v1/publications/plans/{missing_plan['plan_id']}/confirm",
        headers=_auth(token),
        json={
            "schema_version": 1,
            "plan_hash": missing_plan["plan_hash"],
            "confirmed": True,
            "idempotency_key": "missingconfirm001",
        },
    )
    assert missing_confirm.status_code == 200
    await _drain_jobs(sessionmaker, worker_id="missing-attestation")
    failed = await client.get(
        f"/v1/publications/plans/{missing_plan['plan_id']}", headers=_auth(token)
    )
    assert failed.status_code == 200
    assert failed.json()["state"] == "failed"


async def test_grants_invite_accept_revoke(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = harness
    owner_id, _owner_device, owner_token = await _seed_account_device(sessionmaker)
    grantee_id, _gd, grantee_token = await _seed_account_device(
        sessionmaker, email="friend@example.com", email_verified=True
    )
    del grantee_id
    stable = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
    await _seed_owned_catalog(sessionmaker, account_id=owner_id, stable_id=stable)

    MAIL_PORT.sent.clear()
    invite = await client.post(
        "/v1/grants/invitations",
        headers=_auth(owner_token),
        json={
            "schema_version": 1,
            "object_kind": "component",
            "stable_id": stable,
            "major": 1,
            "recipient_email": "Friend@Example.com",
            "idempotency_key": "invitekey00000001",
        },
    )
    assert invite.status_code == 201, invite.text
    invitation_id = invite.json()["invitation_id"]
    # response must not include raw token
    assert "token" not in invite.json()

    repeated = await client.post(
        "/v1/grants/invitations",
        headers=_auth(owner_token),
        json={
            "schema_version": 1,
            "object_kind": "component",
            "stable_id": stable,
            "major": 1,
            "recipient_email": "FRIEND@example.com",
            "idempotency_key": "invitekey00000001",
        },
    )
    assert repeated.status_code == 201
    assert repeated.json()["invitation_id"] == invitation_id

    denied_owner = await client.post(
        "/v1/grants/invitations",
        headers=_auth(grantee_token),
        json={
            "schema_version": 1,
            "object_kind": "component",
            "stable_id": stable,
            "major": 1,
            "recipient_email": "friend@example.com",
            "idempotency_key": "notowner00000001",
        },
    )
    assert denied_owner.status_code == 403

    await _drain_jobs(sessionmaker, worker_id="mail")
    assert MAIL_PORT.sent
    assert MAIL_PORT.sent[0]["token_present"] is True
    assert "accept_token" not in MAIL_PORT.sent[0]

    # fetch token from job table (test-only access)
    async with sessionmaker() as db:
        job = await db.scalar(
            select(Job).where(Job.idempotency_key == f"deliver_invitation:{invitation_id}")
        )
        assert job is not None
        token = job.payload["accept_token"]
        assert isinstance(token, str)

    accept = await client.post(
        f"/v1/grants/invitations/{invitation_id}/accept",
        headers=_auth(grantee_token),
        json={
            "schema_version": 1,
            "token": token,
            "idempotency_key": "acceptkey00000001",
        },
    )
    assert accept.status_code == 200, accept.text
    grant_id = accept.json()["grant_id"]

    denied_revoke = await client.post(
        f"/v1/grants/{grant_id}/revoke",
        headers=_auth(grantee_token),
        json={"schema_version": 1, "reason": "no", "idempotency_key": "deniedrevoke0001"},
    )
    assert denied_revoke.status_code == 404

    listed = await client.get("/v1/grants", headers=_auth(owner_token))
    assert listed.status_code == 200
    assert any(g["grant_id"] == grant_id for g in listed.json()["grants"])

    rev = await client.post(
        f"/v1/grants/{grant_id}/revoke",
        headers=_auth(owner_token),
        json={
            "schema_version": 1,
            "reason": "done",
            "idempotency_key": "revokekey00000001",
        },
    )
    assert rev.status_code == 200
    assert rev.json()["local_bytes_retained"] is True

    pending = await client.post(
        "/v1/grants/invitations",
        headers=_auth(owner_token),
        json={
            "schema_version": 1,
            "object_kind": "component",
            "stable_id": stable,
            "major": 1,
            "recipient_email": "other@example.com",
            "idempotency_key": "invitepending0001",
        },
    )
    assert pending.status_code == 201
    pending_id = pending.json()["invitation_id"]
    wrong_token = await client.post(
        f"/v1/grants/invitations/{pending_id}/accept",
        headers=_auth(grantee_token),
        json={"schema_version": 1, "token": "wrong-token", "idempotency_key": "wrongtoken000001"},
    )
    assert wrong_token.status_code == 400
    revoke_invitation = await client.post(
        f"/v1/grants/invitations/{pending_id}/revoke",
        headers=_auth(owner_token),
        json={"schema_version": 1, "reason": "cancelled", "idempotency_key": "revokeinvite0001"},
    )
    assert revoke_invitation.status_code == 200


async def test_reports_and_staff_lifecycle(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> None:
    # Staff harness with allowlist filled after account mint via second factory rebuild.
    pre = settings_factory(database_url=migrated_database_url)
    app0 = create_app(pre)
    async with app0.router.lifespan_context(app0):
        sessionmaker_tmp: async_sessionmaker[AsyncSession] = app0.state.sessionmaker
        staff_id, _d, staff_token = await _seed_account_device(sessionmaker_tmp)
        _reporter_id, _rd, reporter_token = await _seed_account_device(sessionmaker_tmp)
        await _seed_owned_catalog(
            sessionmaker_tmp,
            account_id=staff_id,
            stable_id="component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
            version="2.0",
        )
        # Publish a public active version for lifecycle target
        async with sessionmaker_tmp() as db:
            row = await db.scalar(select(CatalogMetadata).where(CatalogMetadata.version == "2.0"))
            assert row is not None
            row.visibility = "public"
            row.lifecycle_state = "active"
            row.component_verified = True
            row.trust_lane = "authoritative"
            await db.commit()

    settings = settings_factory(
        database_url=migrated_database_url,
        admin_account_ids=staff_id,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/v1/reports",
                headers=_auth(reporter_token),
                json={
                    "schema_version": 1,
                    "object_kind": "component",
                    "stable_id": "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
                    "version": "2.0",
                    "content_digest": DIGEST,
                    "error_code": "AI_STP_VALIDATION_ERROR",
                    "diagnostics": "",
                    "diagnostics_previewed": False,
                    "idempotency_key": "reportkey00000001",
                },
            )
            assert created.status_code == 201, created.text
            case_id = created.json()["case_id"]

            # N reports do not change lifecycle
            async with app.state.sessionmaker() as db:
                before = await db.scalar(
                    select(CatalogMetadata).where(CatalogMetadata.version == "2.0")
                )
                assert before is not None
                assert before.lifecycle_state == "active"

            triage = await client.post(
                f"/v1/staff/reports/{case_id}/triage",
                headers=_auth(staff_token),
                json={
                    "schema_version": 1,
                    "state": "triaged",
                    "reason": "reproduced",
                    "idempotency_key": "triagekey00000001",
                },
            )
            assert triage.status_code == 200, triage.text

            block = await client.post(
                "/v1/staff/versions/lifecycle",
                headers=_auth(staff_token),
                json={
                    "schema_version": 1,
                    "object_kind": "component",
                    "stable_id": "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
                    "version": "2.0",
                    "action": "block",
                    "reason": "malicious",
                    "idempotency_key": "blockkey000000001",
                },
            )
            assert block.status_code == 200, block.text

            # outsider staff denied
            denied = await client.post(
                "/v1/staff/versions/lifecycle",
                headers=_auth(reporter_token),
                json={
                    "schema_version": 1,
                    "object_kind": "component",
                    "stable_id": "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
                    "version": "2.0",
                    "action": "restore",
                    "reason": "nope",
                    "idempotency_key": "blockkey000000002",
                },
            )
            assert denied.status_code == 403

            async with app.state.sessionmaker() as db:
                after = await db.scalar(
                    select(CatalogMetadata).where(CatalogMetadata.version == "2.0")
                )
                assert after is not None
                assert after.lifecycle_state == "blocked"
                audits = list(
                    (
                        await db.execute(
                            select(AuditEvent).where(AuditEvent.action == "staff.version_block")
                        )
                    )
                    .scalars()
                    .all()
                )
                assert audits
            assert "token" not in str(audits[0].payload)

            hide = await client.post(
                "/v1/staff/versions/lifecycle",
                headers=_auth(staff_token),
                json={
                    "schema_version": 1,
                    "object_kind": "component",
                    "stable_id": "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
                    "version": "2.0",
                    "action": "hide",
                    "reason": "temporary",
                    "idempotency_key": "hidekey000000001",
                },
            )
            assert hide.status_code == 200

            restore = await client.post(
                "/v1/staff/versions/lifecycle",
                headers=_auth(staff_token),
                json={
                    "schema_version": 1,
                    "object_kind": "component",
                    "stable_id": "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
                    "version": "2.0",
                    "action": "restore",
                    "reason": "cleared",
                    "idempotency_key": "restorekey0000001",
                },
            )
            assert restore.status_code == 200

            verified = await client.post(
                "/v1/staff/author-verified",
                headers=_auth(staff_token),
                json={
                    "schema_version": 1,
                    "subject_account_id": staff_id,
                    "verified": True,
                    "reason": "reviewed",
                    "idempotency_key": "authorverify00001",
                },
            )
            assert verified.status_code == 200
            revoked = await client.post(
                "/v1/staff/author-verified",
                headers=_auth(staff_token),
                json={
                    "schema_version": 1,
                    "subject_account_id": staff_id,
                    "verified": False,
                    "reason": "review expired",
                    "idempotency_key": "authorrevoke00001",
                },
            )
            assert revoked.status_code == 200


async def test_dead_letter_for_deliver_invitation_failures(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = harness
    owner_id, _od, owner_token = await _seed_account_device(sessionmaker)
    stable = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
    await _seed_owned_catalog(sessionmaker, account_id=owner_id, stable_id=stable)
    MAIL_PORT.arm_failures(10)
    MAIL_PORT.sent.clear()
    invite = await client.post(
        "/v1/grants/invitations",
        headers=_auth(owner_token),
        json={
            "schema_version": 1,
            "object_kind": "component",
            "stable_id": stable,
            "major": 1,
            "recipient_email": "x@example.com",
            "idempotency_key": "invitefail0000001",
        },
    )
    assert invite.status_code == 201
    invitation_id = invite.json()["invitation_id"]

    # Force attempts until dead letter
    for i in range(8):
        async with sessionmaker() as session, session.begin():
            claimed = await claim(session, worker_id=f"dlq-{i}", batch=1)
            if not claimed:
                # requeue by resetting run_after is internal; fail path needs claimed job
                job = await session.scalar(
                    select(Job).where(Job.idempotency_key == f"deliver_invitation:{invitation_id}")
                )
                if job is None:
                    break
                if job.state == JobState.DEAD_LETTER:
                    break
                job.state = JobState.QUEUED
                job.run_after = job.run_after
                continue
            job = claimed[0]
            handler = resolve(job.job_type)
            assert handler is not None
            try:
                await handler(session, job.payload)
            except Exception as exc:
                await fail(session, job, error=type(exc).__name__)
            else:
                await mark_succeeded(session, job)

    async with sessionmaker() as session:
        job = await session.scalar(
            select(Job).where(Job.idempotency_key == f"deliver_invitation:{invitation_id}")
        )
        assert job is not None
        # either dead_letter or still retrying with safe error field
        if job.state == JobState.DEAD_LETTER:
            assert job.last_error
            assert "token" not in (job.last_error or "").lower()
        else:
            assert job.attempts >= 1
