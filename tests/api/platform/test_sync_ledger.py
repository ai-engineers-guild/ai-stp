"""API/PostgreSQL tests for private revision sync ledger (SPEC-025 REQ-2501..2510)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any, cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.app import create_app
from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_api.slices.sync.cursor import decode_sync_cursor
from ai_stp_api.slices.sync.validation import (
    expected_content_digest,
    expected_revision_id,
    seal_revision_document,
)
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import (
    Account,
    AuditEvent,
    Device,
    SyncEntityHead,
    SyncEventReceipt,
    SyncOutbox,
    SyncRevision,
)
from ai_stp_platform.queue.models import Job

pytestmark = pytest.mark.platform


def _build_event(
    *,
    account_id: str,
    device_id: str,
    entity_id: str,
    entity_kind: str = "developer_passport",
    parents: list[str] | None = None,
    expected_head: str | None = None,
    operation: str = "upsert",
    payload: dict[str, object] | None = None,
    event_id: str = "event-00000001",
    idempotency_key: str = "0123456789abcdef",
    created_at: str = "2026-08-07T00:00:00.000Z",
) -> dict[str, Any]:
    body = payload if payload is not None else {"preference": "dark"}
    parent_ids = list(parents or [])
    doc = seal_revision_document(
        entity_id=entity_id,
        entity_kind=entity_kind,
        parent_revision_ids=parent_ids,
        operation=operation,
        payload=body,
        device_id=device_id,
        actor_id=account_id,
        created_at=created_at,
    )
    return {
        "schema_version": 1,
        "event_id": event_id,
        "entity_id": entity_id,
        "entity_kind": entity_kind,
        "revision_id": expected_revision_id(doc),
        "parent_revision_ids": parent_ids,
        "device_id": device_id,
        "actor_id": account_id,
        "operation": operation,
        "content_digest": expected_content_digest(body),
        "created_at": created_at,
        "idempotency_key": idempotency_key,
        "expected_head_revision_id": expected_head,
        "payload": body,
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


async def _seed_device_session(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    revoked: bool = False,
) -> tuple[str, str, str]:
    """Return (account_id, device_id, raw_token)."""
    async with sessionmaker() as db:
        account = Account(id=new_id("account"))
        device = Device(
            id=new_id("device"),
            account_id=account.id,
            public_key="dGVzdC1wdWJsaWMta2V5LWZvci1zeW5jLXRlc3Rz",
            state="revoked" if revoked else "active",
        )
        db.add(account)
        db.add(device)
        await db.flush()
        issued = await issue_session(
            db,
            account_id=account.id,
            device_id=device.id,
            ttl_seconds=3600,
        )
        await db.commit()
        return account.id, device.id, issued.raw_token


async def test_push_accept_idempotent_and_no_second_effect(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str],
) -> None:
    client, sessionmaker, _ = harness
    account_id, device_id, token = await _seed_device_session(sessionmaker)
    entity_id = new_id("developer")
    event = _build_event(account_id=account_id, device_id=device_id, entity_id=entity_id)
    headers = {"Authorization": f"Bearer {token}"}

    first = await client.post(
        "/v1/sync/push",
        headers=headers,
        json={"schema_version": 1, "events": [event]},
    )
    assert first.status_code == 200, first.text
    body1 = first.json()
    assert body1["receipts"][0]["state"] == "accepted"
    cursor1 = body1["receipts"][0]["cursor"]
    head1 = body1["receipts"][0]["server_head_revision_id"]

    second = await client.post(
        "/v1/sync/push",
        headers=headers,
        json={"schema_version": 1, "events": [event]},
    )
    assert second.status_code == 200
    body2 = second.json()
    assert body2["receipts"][0] == body1["receipts"][0]
    assert body2["receipts"][0]["cursor"] == cursor1
    assert body2["receipts"][0]["server_head_revision_id"] == head1

    async with sessionmaker() as db:
        rev_count = await db.scalar(select(func.count()).select_from(SyncRevision))
        out_count = await db.scalar(select(func.count()).select_from(SyncOutbox))
        receipt_count = await db.scalar(select(func.count()).select_from(SyncEventReceipt))
        job_count = await db.scalar(select(func.count()).select_from(Job))
        assert rev_count == 1
        assert out_count == 1
        assert receipt_count == 1
        assert job_count == 0


async def test_fast_forward_conflict_and_two_parent_merge(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str],
) -> None:
    client, sessionmaker, _ = harness
    account_id, device_id, token = await _seed_device_session(sessionmaker)
    entity_id = new_id("developer")
    headers = {"Authorization": f"Bearer {token}"}

    root = _build_event(
        account_id=account_id,
        device_id=device_id,
        entity_id=entity_id,
        event_id="event-root-0001",
        idempotency_key="idem-root-00000001",
        payload={"preference": "a"},
    )
    r0 = await client.post(
        "/v1/sync/push", headers=headers, json={"schema_version": 1, "events": [root]}
    )
    assert r0.status_code == 200
    root_id = r0.json()["receipts"][0]["revision_id"]

    branch_a = _build_event(
        account_id=account_id,
        device_id=device_id,
        entity_id=entity_id,
        parents=[root_id],
        expected_head=root_id,
        event_id="event-branch-a001",
        idempotency_key="idem-branch-a000001",
        payload={"preference": "b"},
        created_at="2026-08-07T00:01:00.000Z",
    )
    ra = await client.post(
        "/v1/sync/push", headers=headers, json={"schema_version": 1, "events": [branch_a]}
    )
    assert ra.status_code == 200
    assert ra.json()["receipts"][0]["state"] == "accepted"
    head_a = ra.json()["receipts"][0]["revision_id"]

    # Divergent: client still bases on root while server is at branch_a.
    branch_b = _build_event(
        account_id=account_id,
        device_id=device_id,
        entity_id=entity_id,
        parents=[root_id],
        expected_head=root_id,
        event_id="event-branch-b001",
        idempotency_key="idem-branch-b000001",
        payload={"preference": "c"},
        created_at="2026-08-07T00:02:00.000Z",
    )
    rb = await client.post(
        "/v1/sync/push", headers=headers, json={"schema_version": 1, "events": [branch_b]}
    )
    assert rb.status_code == 200
    receipt_b = rb.json()["receipts"][0]
    assert receipt_b["state"] == "conflict"
    assert receipt_b["conflict"]["server_head_revision_id"] == head_a
    assert receipt_b["conflict"]["common_ancestor_revision_id"] == root_id

    async with sessionmaker() as db:
        head = await db.get(SyncEntityHead, {"account_id": account_id, "entity_id": entity_id})
        assert head is not None
        assert head.revision_id == head_a
        retained = await db.get(
            SyncRevision,
            {"account_id": account_id, "revision_id": branch_b["revision_id"]},
        )
        assert retained is not None

    # Explicit two-parent merge from the two real branches.
    merge = _build_event(
        account_id=account_id,
        device_id=device_id,
        entity_id=entity_id,
        parents=[head_a, branch_b["revision_id"]],
        expected_head=head_a,
        event_id="event-merge-00001",
        idempotency_key="idem-merge-00000001",
        payload={"preference": "merged"},
        created_at="2026-08-07T00:03:00.000Z",
    )
    rm = await client.post(
        "/v1/sync/push", headers=headers, json={"schema_version": 1, "events": [merge]}
    )
    assert rm.status_code == 200, rm.text
    assert rm.json()["receipts"][0]["state"] == "accepted"
    assert rm.json()["receipts"][0]["revision_id"] == merge["revision_id"]


async def test_parallel_pushes_serialize_account_sequence_and_initial_head(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str],
) -> None:
    """Components rather than developer passports, and the kind matters here.

    This is about serialising two concurrent pushes and about two devices
    racing to create the same entity's first revision. It used developer
    passports because they were a convenient independent entity; an account now
    holds exactly one, so two distinct ones are refused before either race can
    happen. A component is the right vehicle for a test about ordering.
    """
    client, sessionmaker, _ = harness
    account_id, device_id, token = await _seed_device_session(sessionmaker)
    headers = {"Authorization": f"Bearer {token}"}

    first = _build_event(
        account_id=account_id,
        device_id=device_id,
        entity_id=new_id("component"),
        entity_kind="component_private",
        event_id="event-parallel-0001",
        idempotency_key="idem-parallel-000001",
    )
    second = _build_event(
        account_id=account_id,
        device_id=device_id,
        entity_id=new_id("component"),
        entity_kind="component_private",
        event_id="event-parallel-0002",
        idempotency_key="idem-parallel-000002",
        payload={"preference": "light"},
    )
    first_response, second_response = await asyncio.gather(
        client.post(
            "/v1/sync/push", headers=headers, json={"schema_version": 1, "events": [first]}
        ),
        client.post(
            "/v1/sync/push", headers=headers, json={"schema_version": 1, "events": [second]}
        ),
    )
    assert first_response.status_code == 200, first_response.text
    assert second_response.status_code == 200, second_response.text

    entity_id = new_id("component")
    left = _build_event(
        account_id=account_id,
        device_id=device_id,
        entity_id=entity_id,
        entity_kind="component_private",
        event_id="event-initial-race-1",
        idempotency_key="idem-initial-race001",
    )
    right = _build_event(
        account_id=account_id,
        device_id=device_id,
        entity_id=entity_id,
        entity_kind="component_private",
        event_id="event-initial-race-2",
        idempotency_key="idem-initial-race002",
        payload={"preference": "light"},
    )
    left_response, right_response = await asyncio.gather(
        client.post("/v1/sync/push", headers=headers, json={"schema_version": 1, "events": [left]}),
        client.post(
            "/v1/sync/push", headers=headers, json={"schema_version": 1, "events": [right]}
        ),
    )
    assert left_response.status_code == 200, left_response.text
    assert right_response.status_code == 200, right_response.text
    states = {
        left_response.json()["receipts"][0]["state"],
        right_response.json()["receipts"][0]["state"],
    }
    assert states == {"accepted", "conflict"}

    async with sessionmaker() as db:
        outbox_rows = list(
            (
                await db.execute(
                    select(SyncOutbox.sequence)
                    .where(SyncOutbox.account_id == account_id)
                    .order_by(SyncOutbox.sequence)
                )
            ).scalars()
        )
        head_count = await db.scalar(
            select(func.count())
            .select_from(SyncEntityHead)
            .where(
                SyncEntityHead.account_id == account_id,
                SyncEntityHead.entity_id == entity_id,
            )
        )
        assert outbox_rows == [1, 2, 3]
        assert head_count == 1


async def test_tombstone_pull_and_history_preserved(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str],
) -> None:
    client, sessionmaker, _ = harness
    account_id, device_id, token = await _seed_device_session(sessionmaker)
    entity_id = new_id("developer")
    headers = {"Authorization": f"Bearer {token}"}
    root = _build_event(account_id=account_id, device_id=device_id, entity_id=entity_id)
    r0 = await client.post(
        "/v1/sync/push", headers=headers, json={"schema_version": 1, "events": [root]}
    )
    root_id = r0.json()["receipts"][0]["revision_id"]
    tomb = _build_event(
        account_id=account_id,
        device_id=device_id,
        entity_id=entity_id,
        parents=[root_id],
        expected_head=root_id,
        operation="tombstone",
        payload={},
        event_id="event-tomb-00001",
        idempotency_key="idem-tomb-00000001",
        created_at="2026-08-07T00:05:00.000Z",
    )
    rt = await client.post(
        "/v1/sync/push", headers=headers, json={"schema_version": 1, "events": [tomb]}
    )
    assert rt.status_code == 200
    assert rt.json()["receipts"][0]["state"] == "accepted"

    pull = await client.get("/v1/sync/pull", headers=headers, params={"page_size": 20})
    assert pull.status_code == 200
    items = pull.json()["items"]
    assert len(items) == 2
    assert items[1]["operation"] == "tombstone"
    async with sessionmaker() as db:
        assert await db.scalar(select(func.count()).select_from(SyncRevision)) == 2


async def test_pull_pagination_and_cursor_rejection(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str],
) -> None:
    client, sessionmaker, _ = harness
    account_id, device_id, token = await _seed_device_session(sessionmaker)
    headers = {"Authorization": f"Bearer {token}"}
    entity_id = new_id("developer")
    root = _build_event(account_id=account_id, device_id=device_id, entity_id=entity_id)
    r0 = await client.post(
        "/v1/sync/push", headers=headers, json={"schema_version": 1, "events": [root]}
    )
    assert r0.status_code == 200
    head_id = r0.json()["receipts"][0]["revision_id"]
    for index in range(2):
        child = _build_event(
            account_id=account_id,
            device_id=device_id,
            entity_id=entity_id,
            parents=[head_id],
            expected_head=head_id,
            event_id=f"event-page-{index:04d}",
            idempotency_key=f"idem-page-{index:08d}xx",
            payload={"n": index},
            created_at=f"2026-08-07T00:0{index + 1}:00.000Z",
        )
        resp = await client.post(
            "/v1/sync/push", headers=headers, json={"schema_version": 1, "events": [child]}
        )
        assert resp.status_code == 200, resp.text
        head_id = resp.json()["receipts"][0]["revision_id"]

    page1 = await client.get("/v1/sync/pull", headers=headers, params={"page_size": 2})
    assert page1.status_code == 200
    body1 = page1.json()
    assert len(body1["items"]) == 2
    assert body1["page"]["next_cursor"] is not None
    sequences = [item["sequence"] for item in body1["items"]]

    page2 = await client.get(
        "/v1/sync/pull",
        headers=headers,
        params={"page_size": 2, "cursor": body1["page"]["next_cursor"]},
    )
    assert page2.status_code == 200
    body2 = page2.json()
    sequences2 = [item["sequence"] for item in body2["items"]]
    assert not set(sequences) & set(sequences2)
    assert sequences + sequences2 == sorted(sequences + sequences2)
    assert len(sequences) + len(sequences2) == 3

    bad = await client.get(
        "/v1/sync/pull",
        headers=headers,
        params={"cursor": "not-a-valid-signed-cursor"},
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "AI_STP_VALIDATION_ERROR"

    # Cross-account cursor
    _other_account, _other_device, other_token = await _seed_device_session(sessionmaker)
    foreign = await client.get(
        "/v1/sync/pull",
        headers={"Authorization": f"Bearer {other_token}"},
        params={"cursor": body1["page"]["next_cursor"]},
    )
    assert foreign.status_code == 400


async def test_pull_one_event_returns_cursor_on_last_page(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str],
) -> None:
    client, sessionmaker, secret = harness
    account_id, device_id, token = await _seed_device_session(sessionmaker)
    headers = {"Authorization": f"Bearer {token}"}
    entity_id = new_id("developer")
    root = _build_event(account_id=account_id, device_id=device_id, entity_id=entity_id)
    pushed = await client.post(
        "/v1/sync/push", headers=headers, json={"schema_version": 1, "events": [root]}
    )
    assert pushed.status_code == 200

    pull = await client.get("/v1/sync/pull", headers=headers, params={"page_size": 20})
    assert pull.status_code == 200
    body = pull.json()
    assert len(body["items"]) == 1
    cursor = body["page"]["next_cursor"]
    assert cursor is not None
    position = decode_sync_cursor(secret=secret, token=cursor, account_id=account_id)
    assert position.sequence == body["items"][0]["sequence"]


async def test_pull_saved_cursor_immediately_returns_empty_page(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str],
) -> None:
    client, sessionmaker, _secret = harness
    account_id, device_id, token = await _seed_device_session(sessionmaker)
    headers = {"Authorization": f"Bearer {token}"}
    entity_id = new_id("developer")
    root = _build_event(account_id=account_id, device_id=device_id, entity_id=entity_id)
    pushed = await client.post(
        "/v1/sync/push", headers=headers, json={"schema_version": 1, "events": [root]}
    )
    assert pushed.status_code == 200
    first = await client.get("/v1/sync/pull", headers=headers)
    saved = first.json()["page"]["next_cursor"]
    assert saved is not None

    empty = await client.get("/v1/sync/pull", headers=headers, params={"cursor": saved})
    assert empty.status_code == 200
    assert empty.json()["items"] == []
    assert empty.json()["page"]["next_cursor"] == saved


async def test_pull_saved_cursor_after_append_returns_only_new_event(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str],
) -> None:
    client, sessionmaker, _secret = harness
    account_id, device_id, token = await _seed_device_session(sessionmaker)
    headers = {"Authorization": f"Bearer {token}"}
    entity_id = new_id("developer")
    root = _build_event(account_id=account_id, device_id=device_id, entity_id=entity_id)
    first_push = await client.post(
        "/v1/sync/push", headers=headers, json={"schema_version": 1, "events": [root]}
    )
    assert first_push.status_code == 200
    head_id = first_push.json()["receipts"][0]["revision_id"]
    first_pull = await client.get("/v1/sync/pull", headers=headers)
    saved = first_pull.json()["page"]["next_cursor"]
    first_sequence = first_pull.json()["items"][0]["sequence"]
    assert saved is not None

    child = _build_event(
        account_id=account_id,
        device_id=device_id,
        entity_id=entity_id,
        parents=[head_id],
        expected_head=head_id,
        event_id="event-append-0001",
        idempotency_key="idem-append-000001xx",
        payload={"n": 1},
        created_at="2026-08-07T00:01:00.000Z",
    )
    second_push = await client.post(
        "/v1/sync/push", headers=headers, json={"schema_version": 1, "events": [child]}
    )
    assert second_push.status_code == 200

    resumed = await client.get("/v1/sync/pull", headers=headers, params={"cursor": saved})
    assert resumed.status_code == 200
    items = resumed.json()["items"]
    assert len(items) == 1
    assert items[0]["sequence"] != first_sequence
    assert items[0]["event_id"] == "event-append-0001"


async def test_revoked_device_rejected_before_write(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str],
) -> None:
    client, sessionmaker, _ = harness
    account_id, device_id, token = await _seed_device_session(sessionmaker, revoked=True)
    entity_id = new_id("developer")
    event = _build_event(account_id=account_id, device_id=device_id, entity_id=entity_id)
    headers = {"Authorization": f"Bearer {token}"}

    push = await client.post(
        "/v1/sync/push",
        headers=headers,
        json={"schema_version": 1, "events": [event]},
    )
    assert push.status_code == 403
    assert push.json()["error"]["code"] == "AI_STP_DEVICE_REVOKED"

    pull = await client.get("/v1/sync/pull", headers=headers)
    assert pull.status_code == 403
    assert pull.json()["error"]["code"] == "AI_STP_DEVICE_REVOKED"

    async with sessionmaker() as db:
        assert await db.scalar(select(func.count()).select_from(SyncRevision)) == 0
        assert await db.scalar(select(func.count()).select_from(SyncOutbox)) == 0
        assert await db.scalar(select(func.count()).select_from(SyncEventReceipt)) == 0


async def test_tenant_isolation(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str],
) -> None:
    client, sessionmaker, _ = harness
    a_account, a_device, a_token = await _seed_device_session(sessionmaker)
    b_account, b_device, b_token = await _seed_device_session(sessionmaker)
    entity_a = new_id("developer")
    event = _build_event(account_id=a_account, device_id=a_device, entity_id=entity_a)
    await client.post(
        "/v1/sync/push",
        headers={"Authorization": f"Bearer {a_token}"},
        json={"schema_version": 1, "events": [event]},
    )
    pull_b = await client.get(
        "/v1/sync/pull",
        headers={"Authorization": f"Bearer {b_token}"},
    )
    assert pull_b.status_code == 200
    assert pull_b.json()["items"] == []
    del b_account, b_device


async def test_audit_redaction_and_no_broker_job(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str],
) -> None:
    client, sessionmaker, _ = harness
    account_id, device_id, token = await _seed_device_session(sessionmaker)
    entity_id = new_id("developer")
    event = _build_event(account_id=account_id, device_id=device_id, entity_id=entity_id)
    await client.post(
        "/v1/sync/push",
        headers={"Authorization": f"Bearer {token}"},
        json={"schema_version": 1, "events": [event]},
    )
    async with sessionmaker() as db:
        audits = list((await db.execute(select(AuditEvent))).scalars().all())
        assert audits
        for row in audits:
            payload = row.payload or {}
            text = str(payload).lower()
            assert "cursor" not in text
            assert "token" not in text
            assert "preference" not in text
            assert "signature" not in text
        assert await db.scalar(select(func.count()).select_from(Job)) == 0


async def test_a_second_developer_identity_is_refused_and_names_the_held_one(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str],
) -> None:
    """An account holds one developer passport, and the server is where that holds.

    `passport developer init` mints a new identity in a fresh installation, so
    a reinstall or a second machine produces a second one. Both used to be
    accepted, and the account's stream then carried a sequence no device could
    apply: one-per-installation is a client rule too, so a fresh device refused
    the second, the atomic page rolled back, and that device could never sync
    again. Observed on production with three identities in one stream.

    Refusing here keeps the stream applicable by construction, and the receipt
    names the identity the account holds — without it the device cannot tell
    which passport to adopt, and adopting is one of the two ways out.
    """
    client, sessionmaker, _ = harness
    account_id, device_id, token = await _seed_device_session(sessionmaker)
    headers = {"Authorization": f"Bearer {token}"}

    first_id = new_id("developer")
    accepted = await client.post(
        "/v1/sync/push",
        headers=headers,
        json={
            "schema_version": 1,
            "events": [
                _build_event(account_id=account_id, device_id=device_id, entity_id=first_id)
            ],
        },
    )
    assert accepted.json()["receipts"][0]["state"] == "accepted"

    second_id = new_id("developer")
    refused = await client.post(
        "/v1/sync/push",
        headers=headers,
        json={
            "schema_version": 1,
            "events": [
                _build_event(
                    account_id=account_id,
                    device_id=device_id,
                    entity_id=second_id,
                    event_id="event-00000002",
                    idempotency_key="fedcba9876543210",
                )
            ],
        },
    )
    receipt = refused.json()["receipts"][0]
    assert receipt["state"] == "rejected"
    assert receipt["error_code"] == "AI_STP_CONFLICT"
    assert receipt["conflicting_entity_id"] == first_id

    async with sessionmaker() as db:
        kept = await db.scalar(
            select(func.count())
            .select_from(SyncRevision)
            .where(SyncRevision.entity_kind == "developer_passport")
        )
        assert kept == 1, "the refused identity must not enter the ledger"


async def test_a_tombstoned_developer_identity_can_be_replaced(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str],
) -> None:
    """Replacing is tombstoning the old identity and pushing the new one.

    The refusal above must not become a trap: an account that wants the other
    device's passport has to be able to say so. A tombstoned identity is not
    live, so the path stays open — and it is explicit, which is the point.
    """
    client, sessionmaker, _ = harness
    account_id, device_id, token = await _seed_device_session(sessionmaker)
    headers = {"Authorization": f"Bearer {token}"}

    first_id = new_id("developer")
    created = await client.post(
        "/v1/sync/push",
        headers=headers,
        json={
            "schema_version": 1,
            "events": [
                _build_event(account_id=account_id, device_id=device_id, entity_id=first_id)
            ],
        },
    )
    head = created.json()["receipts"][0]["server_head_revision_id"]

    buried = await client.post(
        "/v1/sync/push",
        headers=headers,
        json={
            "schema_version": 1,
            "events": [
                _build_event(
                    account_id=account_id,
                    device_id=device_id,
                    entity_id=first_id,
                    operation="tombstone",
                    payload={},
                    parents=[head],
                    expected_head=head,
                    event_id="event-00000002",
                    idempotency_key="fedcba9876543210",
                )
            ],
        },
    )
    assert buried.json()["receipts"][0]["state"] == "accepted", buried.text

    second_id = new_id("developer")
    replaced = await client.post(
        "/v1/sync/push",
        headers=headers,
        json={
            "schema_version": 1,
            "events": [
                _build_event(
                    account_id=account_id,
                    device_id=device_id,
                    entity_id=second_id,
                    event_id="event-00000003",
                    idempotency_key="00112233445566aa",
                )
            ],
        },
    )
    assert replaced.json()["receipts"][0]["state"] == "accepted", replaced.text


@pytest.mark.asyncio
async def test_an_accepted_merge_delivers_the_parent_a_conflict_kept_out_of_the_stream(
    harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    """The outbox has to be self-contained, or a fresh device can never catch up.

    A refused push still stores its revision — the server needs it to describe
    the conflict — but does not enqueue it. When the device then merges locally
    and pushes the merge, the merge is accepted and enqueued with a parent that
    is in `sync_revision` and in no outbox row. Every device that did not
    already hold that parent then refuses the whole page, correctly, with `a
    parent revision is not in the local registry`, and the account is wedged
    for good: the stream can never be applied and the cursor can never move.

    Observed on the deployed environment, where it left an account whose only
    entity could not be pulled by a clean install.
    """
    client, sessionmaker, _ = harness
    account_id, device_id, token = await _seed_device_session(sessionmaker)
    headers = {"Authorization": f"Bearer {token}"}
    entity_id = new_id("component")

    root = _build_event(
        account_id=account_id,
        device_id=device_id,
        entity_id=entity_id,
        entity_kind="component_private",
        event_id="event-merge-parent-01",
        idempotency_key="idem-mergeparent0001",
    )
    accepted = await client.post(
        "/v1/sync/push", headers=headers, json={"schema_version": 1, "events": [root]}
    )
    assert accepted.json()["receipts"][0]["state"] == "accepted", accepted.text

    kept = _build_event(
        account_id=account_id,
        device_id=device_id,
        entity_id=entity_id,
        entity_kind="component_private",
        parents=[root["revision_id"]],
        expected_head=root["revision_id"],
        payload={"preference": "kept"},
        event_id="event-merge-side-a-01",
        idempotency_key="idem-mergesidea00001",
    )
    side = await client.post(
        "/v1/sync/push", headers=headers, json={"schema_version": 1, "events": [kept]}
    )
    assert side.json()["receipts"][0]["state"] == "accepted", side.text

    # Same parent, stale expectation: stored for the conflict report, never sent.
    refused = _build_event(
        account_id=account_id,
        device_id=device_id,
        entity_id=entity_id,
        entity_kind="component_private",
        parents=[root["revision_id"]],
        expected_head=root["revision_id"],
        payload={"preference": "refused"},
        event_id="event-merge-side-b-01",
        idempotency_key="idem-mergesideb00001",
    )
    conflicted = await client.post(
        "/v1/sync/push", headers=headers, json={"schema_version": 1, "events": [refused]}
    )
    assert conflicted.json()["receipts"][0]["state"] == "conflict", conflicted.text

    merge = _build_event(
        account_id=account_id,
        device_id=device_id,
        entity_id=entity_id,
        entity_kind="component_private",
        parents=[kept["revision_id"], refused["revision_id"]],
        expected_head=kept["revision_id"],
        payload={"preference": "merged"},
        event_id="event-merge-commit-01",
        idempotency_key="idem-mergecommit00001",
    )
    merged = await client.post(
        "/v1/sync/push", headers=headers, json={"schema_version": 1, "events": [merge]}
    )
    assert merged.json()["receipts"][0]["state"] == "accepted", merged.text

    async with sessionmaker() as db:
        rows = (
            await db.execute(
                select(SyncOutbox.revision_id, SyncOutbox.parent_revision_ids)
                .where(SyncOutbox.account_id == account_id)
                .order_by(SyncOutbox.sequence)
            )
        ).all()
    delivered = [str(revision_id) for revision_id, _parents in rows]
    named: set[str] = set()
    for _revision_id, parents in rows:
        for parent in cast(list[str], parents or []):
            named.add(str(parent))
    missing = sorted(name for name in named if name not in delivered)
    assert not missing, (
        f"the stream references {missing}, which it never delivers; a device that "
        f"does not already hold them can never apply this account's page. Delivered: "
        f"{delivered}"
    )
