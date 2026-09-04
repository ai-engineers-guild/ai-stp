# pyright: reportUnusedFunction=false
"""API coverage for database-bound ownership transfer requests (SPEC-057)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.app import create_app
from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_foundation.ids import new_id
from ai_stp_platform.catalog_transfer import transfer_catalog_line
from ai_stp_platform.models import (
    Account,
    CatalogIdentity,
    CatalogMetadata,
    Device,
    OfficialSyncOutbox,
    OfficialUpstreamSource,
    OfficialUpstreamSync,
    OwnershipClaim,
    OwnershipRevision,
    ReportCase,
)
from ai_stp_platform.official_upstream import OFFICIAL_ACCOUNT_ID
from ai_stp_platform.queue.models import Job
from ai_stp_platform.queue.states import JobState, JobType

pytestmark = pytest.mark.platform

COMPONENT_ID = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
PASSPORT = {
    "schema_version": 1,
    "kind": "component",
    "stable_id": COMPONENT_ID,
    "owner_id": OFFICIAL_ACCOUNT_ID,
    "name": "official-skill",
    "description": "Official catalog component under claim transfer tests.",
    "version": "1.0",
}


@pytest_asyncio.fixture
async def harness(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings, str]]:
    pre = settings_factory(database_url=migrated_database_url)
    app0 = create_app(pre)
    staff_id = ""
    async with app0.router.lifespan_context(app0):
        staff_id, _device, _token = await _seed_account_device(app0.state.sessionmaker)
    settings = settings_factory(
        database_url=migrated_database_url,
        admin_account_ids=staff_id,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app.state.sessionmaker, settings, staff_id


async def _seed_account_device(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> tuple[str, str, str]:
    async with sessionmaker() as db:
        account = Account(id=new_id("account"))
        device = Device(
            id=new_id("device"),
            account_id=account.id,
            public_key="dGVzdC1wdWJsaWMta2V5LWNsYWltcw==",
            state="active",
        )
        db.add(account)
        db.add(device)
        await db.flush()
        issued = await issue_session(
            db, account_id=account.id, device_id=device.id, ttl_seconds=3600
        )
        await db.commit()
        return account.id, device.id, issued.raw_token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed_official_component(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    versions: tuple[str, ...] = ("1.0", "1.1", "2.0"),
) -> None:
    async with sessionmaker() as db:
        if await db.get(Account, OFFICIAL_ACCOUNT_ID) is None:
            db.add(Account(id=OFFICIAL_ACCOUNT_ID))
        for version in versions:
            db.add(
                CatalogMetadata(
                    owner_account_id=OFFICIAL_ACCOUNT_ID,
                    object_kind="component",
                    stable_id=COMPONENT_ID,
                    version=version,
                    current_revision_id="revision_" + "0" * 64,
                    visibility="public",
                    lifecycle_state="active",
                    name="official-skill",
                    passport_document=dict(PASSPORT, version=version),
                )
            )
        await db.commit()


async def test_claim_preview_has_no_http_decision_path(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings, str],
) -> None:
    client, sessionmaker, _settings, _staff_id = harness
    await _seed_official_component(sessionmaker)
    requester_id, _device, token = await _seed_account_device(sessionmaker)

    created = await client.post(
        "/v1/ownership-claims",
        headers=_auth(token),
        json={
            "schema_version": 1,
            "stable_id": COMPONENT_ID,
            "reason": "I maintain the upstream repository.",
            "evidence": "https://github.com/example/demo/commits",
            "idempotency_key": "claim-key-00000001",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["state"] == "requested"
    assert body["preview"]["stable_id"] == COMPONENT_ID
    assert body["preview"]["current_owner_account_id"] == OFFICIAL_ACCOUNT_ID
    assert body["preview"]["versions"] == ["1.0", "1.1", "2.0"]
    assert body["preview"]["major_lines"] == [1, 2]
    claim_id = body["claim_id"]

    decision = await client.post(
        f"/v1/staff/ownership-claims/{claim_id}/approve",
        headers=_auth(token),
        json={
            "schema_version": 1,
            "reason": "not staff",
            "idempotency_key": "approve-key-0000001",
        },
    )
    assert decision.status_code == 404

    async with sessionmaker() as db:
        rows = list(
            (
                await db.execute(
                    select(CatalogMetadata).where(CatalogMetadata.stable_id == COMPONENT_ID)
                )
            )
            .scalars()
            .all()
        )
        assert {row.owner_account_id for row in rows} == {OFFICIAL_ACCOUNT_ID}
        assert all(row.passport_document == dict(PASSPORT, version=row.version) for row in rows)
        claim = await db.get(OwnershipClaim, claim_id)
        assert claim is not None
        assert claim.requester_account_id == requester_id
        assert claim.state == "requested"


async def test_unverified_account_can_request_transfer(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings, str],
) -> None:
    client, sessionmaker, _settings, _staff_id = harness
    await _seed_official_component(sessionmaker)
    _requester_id, _device, token = await _seed_account_device(sessionmaker)
    response = await client.post(
        "/v1/ownership-claims",
        headers=_auth(token),
        json={
            "schema_version": 1,
            "stable_id": COMPONENT_ID,
            "reason": "please transfer this",
            "evidence": "I wrote the README",
            "idempotency_key": "claim-key-unverified1",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["state"] == "requested"


async def test_database_transfer_fences_official_source_and_approves_legacy_claim(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings, str],
) -> None:
    _client, sessionmaker, _settings, operator_id = harness
    recipient_id, _device, _token = await _seed_account_device(sessionmaker)
    now = datetime.now(UTC)
    async with sessionmaker() as db:
        db.add(
            CatalogIdentity(
                stable_id=COMPONENT_ID,
                owner_account_id=OFFICIAL_ACCOUNT_ID,
                canonical_name="official-skill",
                canonical_name_normalized="official-skill",
                ownership_revision_id="",
            )
        )
        for version in ("1.0", "1.1"):
            db.add(
                CatalogMetadata(
                    owner_account_id=OFFICIAL_ACCOUNT_ID,
                    object_kind="component",
                    stable_id=COMPONENT_ID,
                    version=version,
                    current_revision_id="revision_" + "0" * 64,
                    visibility="public",
                    lifecycle_state="active",
                    name="official-skill",
                    passport_document=dict(PASSPORT, version=version),
                )
            )
        source = OfficialUpstreamSource(
            id="official-transfer-test",
            slot="official",
            kind="git",
            repository_url="https://github.com/acme/tool",
            tracked_ref="main",
            component_subpath="skills/demo",
            component_type="skill",
            projection_kind="native_files",
            harness_id="claude-code",
            target_scope="global",
            projection_root="skills/demo",
            projection_shape="tree",
            owner_account_id=OFFICIAL_ACCOUNT_ID,
            actor_device_id="device_01JZZK7B8N4M6P2R9T5V0X3Y7Z",
            stable_id=COMPONENT_ID,
            name="official-skill",
            upstream_project_name="Demo",
            upstream_maintainer="Acme",
            reviewed_description="Reviewed component body.",
            reviewed_license="MIT",
            tags=["code-review"],
            enabled=True,
            inventory_state="enabled",
            update_policy="daily",
        )
        db.add(source)
        await db.flush()
        attempt = OfficialUpstreamSync(
            source_id=source.id,
            utc_day=now.date(),
            trigger_key=now.date().isoformat(),
            result="publication_started",
            state="queued",
            expected_owner_account_id=OFFICIAL_ACCOUNT_ID,
            expected_ownership_revision_id="",
        )
        db.add(attempt)
        await db.flush()
        outbox = OfficialSyncOutbox(
            id=new_id("outbox"),
            source_id=source.id,
            attempt_id=attempt.id,
            idempotency_key="official-transfer-test-outbox",
            state="pending",
        )
        db.add(outbox)
        attempt.outbox_id = outbox.id
        job = Job(
            job_type=JobType.OFFICIAL_UPSTREAM_SYNC,
            payload={"source_id": source.id, "attempt_id": attempt.id},
            state=JobState.QUEUED,
            idempotency_key="official-transfer-test-job",
            run_after=now,
            expires_at=now + timedelta(hours=1),
        )
        db.add(job)
        await db.flush()
        attempt.job_id = job.id
        case = ReportCase(
            id=new_id("report"),
            reporter_account_id=recipient_id,
            topic="ownership_transfer",
            object_kind="component",
            stable_id=COMPONENT_ID,
            state="submitted",
            vulnerability=False,
            payload={"recipient_account_id": recipient_id},
            locale="en",
            group_key=f"ownership_transfer:{COMPONENT_ID}:{recipient_id}",
            idempotency_key="official-transfer-test-case",
        )
        db.add(case)
        claim = OwnershipClaim(
            id=new_id("operation"),
            object_kind="component",
            stable_id=COMPONENT_ID,
            requester_account_id=recipient_id,
            from_account_id=OFFICIAL_ACCOUNT_ID,
            to_account_id=recipient_id,
            reason="I maintain this component.",
            evidence="https://github.com/acme/tool/commits",
            state="requested",
            preview={},
            idempotency_key=case.idempotency_key,
        )
        db.add(claim)
        await db.flush()

        revision = await transfer_catalog_line(
            db,
            case_id=case.id,
            expected_owner_account_id=OFFICIAL_ACCOUNT_ID,
            expected_ownership_revision_id="",
            recipient_account_id=recipient_id,
            reason="upstream maintainer confirmed",
            evidence="https://github.com/acme/tool/commits",
            operator_account_id=operator_id,
        )
        await db.commit()

        identity = await db.get(CatalogIdentity, COMPONENT_ID)
        source = await db.get(OfficialUpstreamSource, source.id)
        attempt = await db.get(OfficialUpstreamSync, attempt.id)
        outbox = await db.get(OfficialSyncOutbox, outbox.id)
        job = await db.get(Job, job.id)
        case = await db.get(ReportCase, case.id)
        claim = await db.get(OwnershipClaim, claim.id)
        versions = list(
            (
                await db.scalars(
                    select(CatalogMetadata).where(CatalogMetadata.stable_id == COMPONENT_ID)
                )
            ).all()
        )
        stored_revision = await db.scalar(
            select(OwnershipRevision).where(OwnershipRevision.id == revision.id)
        )
        assert identity is not None and identity.owner_account_id == recipient_id
        assert source is not None and not source.enabled and source.inventory_state == "transferred"
        assert source.update_policy == "disabled" and source.ownership_revision_id == revision.id
        assert attempt is not None and attempt.state == "cancelled_transferred"
        assert outbox is not None and outbox.state == "cancelled"
        assert job is not None and job.state == JobState.CANCELLED
        assert case is not None and case.state == "resolved"
        assert claim is not None and claim.state == "approved"
        assert stored_revision is not None and stored_revision.claim_id == claim.id
        assert {row.owner_account_id for row in versions} == {recipient_id}
