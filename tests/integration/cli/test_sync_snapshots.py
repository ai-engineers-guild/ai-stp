"""Released snapshots travel independently of draft heads and remain recoverable."""

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Literal, cast

import pytest

from ai_stp_cli.local import cache, revisions, sync_state, versions
from ai_stp_cli.local.database import open_registry
from ai_stp_contracts.http import PageInfo
from ai_stp_contracts.sync import SyncEvent, SyncEventReceipt, SyncPullResponse, SyncStreamEvent
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.ids import new_id

pytestmark = pytest.mark.cli
AT = "2026-09-08T00:00:00.000Z"


def _draft(account: str, stable: str, kind: str) -> dict[str, JsonValue]:
    return {
        "schema_version": 1,
        "kind": kind,
        "stable_id": stable,
        "owner_id": account,
        "created_at": AT,
        "visibility": "private",
        "parent_revision_ids": [],
        "facts": {},
    }


def _release(
    connection: sqlite3.Connection, draft: revisions.StoredRevision, device: str, number: str
) -> tuple[revisions.StoredRevision, versions.Recorded]:
    db = connection
    body = cast(dict[str, JsonValue], draft.envelope.model_dump(mode="json"))
    body["version"] = number
    body["parent_revision_ids"] = []
    snapshot = revisions.store_snapshot(db, body, device_id=device)
    version = versions.record(
        db,
        stable_id=draft.stable_id,
        version=number,
        passport_digest=cache.digest_of(cast(JsonValue, snapshot.envelope.model_dump(mode="json"))),
        revision_id=snapshot.revision_id,
        at=AT,
    )
    return snapshot, version


def _accepted(event: SyncEvent) -> SyncEventReceipt:
    return SyncEventReceipt(
        event_id=event.event_id,
        state="accepted",
        revision_id=event.revision_id,
        server_head_revision_id=event.revision_id,
        cursor=None,
        conflict=None,
        conflicting_entity_id=None,
        error_code=None,
    )


def _page(event: SyncEvent, sequence: int) -> SyncPullResponse:
    stream = SyncStreamEvent(
        **event.model_dump(exclude={"idempotency_key", "expected_head_revision_id"}),
        sequence=sequence,
    )
    return SyncPullResponse(items=[stream], page=PageInfo(next_cursor=str(sequence), page_size=1))


@pytest.mark.parametrize("kind", ["component", "setup"])
def test_first_sync_transfers_snapshot_without_moving_draft_head(
    tmp_path: Path, kind: Literal["component", "setup"]
) -> None:
    account, device, stable = new_id("account"), new_id("device"), new_id(kind)
    with (
        closing(open_registry(tmp_path / "a.sqlite")) as a,
        closing(open_registry(tmp_path / "b.sqlite")) as b,
    ):
        draft = revisions.commit(a, _draft(account, stable, kind), device_id=device)
        snapshot, version = _release(a, draft, device, "1.0")
        event = sync_state.prepare(a, account_id=account, device_id=device, stored=draft).request
        sync_state.apply_page(b, account_id=account, response=_page(event, 1), at=AT)
        assert revisions.head(b, stable) == revisions.get(b, draft.revision_id)
        assert revisions.get(b, snapshot.revision_id) is not None
        assert versions.line(b, stable) == (version,)
        assert revisions.head(a, stable) == draft


def test_release_after_accepted_push_changes_transport_identity_and_replays(tmp_path: Path) -> None:
    account, device, stable = new_id("account"), new_id("device"), new_id("component")
    with (
        closing(open_registry(tmp_path / "a.sqlite")) as a,
        closing(open_registry(tmp_path / "b.sqlite")) as b,
    ):
        draft = revisions.commit(a, _draft(account, stable, "component"), device_id=device)
        original = sync_state.prepare(a, account_id=account, device_id=device, stored=draft).request
        sync_state.record_receipt(a, account_id=account, receipt=_accepted(original))
        sync_state.apply_page(b, account_id=account, response=_page(original, 1), at=AT)
        snapshot, version = _release(a, draft, device, "1.0")
        updated = sync_state.prepare(a, account_id=account, device_id=device, stored=draft).request
        assert updated.event_id != original.event_id
        assert updated.parent_revision_ids == [original.revision_id]
        assert updated.expected_head_revision_id == original.revision_id
        assert (
            sync_state.prepare(a, account_id=account, device_id=device, stored=draft).request
            == updated
        )
        sync_state.apply_page(b, account_id=account, response=_page(updated, 2), at=AT)
        assert revisions.head(b, stable) == revisions.get(b, draft.revision_id)
        assert revisions.get(b, snapshot.revision_id) is not None
        assert versions.line(b, stable) == (version,)
        assert sync_state.apply_page(b, account_id=account, response=_page(updated, 2), at=AT)[
            :2
        ] == (0, 1)


def _rebind(event: SyncEvent, payload: dict[str, object]) -> SyncEvent:
    from ai_stp_foundation.digests import digest_canonical
    from ai_stp_foundation.revisions import revision_id

    body = event.model_dump(
        exclude={
            "idempotency_key",
            "expected_head_revision_id",
            "event_id",
            "revision_id",
            "content_digest",
        }
    )
    body["payload"] = payload
    return event.model_copy(
        update={
            "payload": payload,
            "content_digest": digest_canonical("ai-stp:revision:v1", cast(JsonValue, payload)),
            "revision_id": revision_id(cast(dict[str, JsonValue], body)),
        }
    )


def test_legacy_missing_reference_is_retained_then_repaired_without_skipping(
    tmp_path: Path,
) -> None:
    import json

    from ai_stp_cli.local import sync_versions

    account, device, stable = new_id("account"), new_id("device"), new_id("component")
    with (
        closing(open_registry(tmp_path / "a.sqlite")) as a,
        closing(open_registry(tmp_path / "b.sqlite")) as b,
    ):
        draft = revisions.commit(a, _draft(account, stable, "component"), device_id=device)
        snapshot, version = _release(a, draft, device, "1.0")
        current = sync_state.prepare(a, account_id=account, device_id=device, stored=draft).request
        payload = json.loads(json.dumps(current.payload))
        del payload["sync_released_versions"][0]["snapshot"]
        legacy = _rebind(current, payload)
        # Reproduce the exact journal shape written by the released old client.
        a.execute(
            "UPDATE sync_event SET request_json = ?, remote_revision_id = ?, sync_key = ? "
            "WHERE event_id = ?",
            (
                legacy.model_dump_json(),
                legacy.revision_id,
                draft.revision_id,
                legacy.event_id,
            ),
        )
        sync_state.record_receipt(a, account_id=account, receipt=_accepted(legacy))
        sync_state.apply_page(b, account_id=account, response=_page(legacy, 1), at=AT)
        count, pending = sync_versions.pending(b, account=account)
        assert count == 1 and pending[0].revision_id == snapshot.revision_id
        assert pending[0].event_id == legacy.event_id
        assert versions.line(b, stable) == ()
        assert sync_state.cursor(b, account) == "1"
        assert sync_versions.pending(b, account=new_id("account")) == (0, [])
        repaired = sync_state.prepare(a, account_id=account, device_id=device, stored=draft).request
        assert repaired.parent_revision_ids == [legacy.revision_id]
        sync_state.apply_page(b, account_id=account, response=_page(repaired, 2), at=AT)
        assert sync_versions.pending(b, account=account) == (0, [])
        assert versions.line(b, stable) == (version,)
        assert (
            b.execute(
                "SELECT COUNT(*) FROM sync_event WHERE account_id = ?", (account,)
            ).fetchone()[0]
            == 2
        )
        assert sync_state.abandoned_events(b, account) == frozenset()


@pytest.mark.parametrize(
    "tamper",
    [
        "identity",
        "content",
        "digest",
        "version",
        "kind",
        "parents",
        "boolean_schema",
        "missing_defaults",
    ],
)
def test_invalid_snapshot_rolls_back_head_versions_and_cursor(tmp_path: Path, tamper: str) -> None:
    import json

    from ai_stp_cli.errors import CliFailure

    account, device, stable = new_id("account"), new_id("device"), new_id("component")
    with (
        closing(open_registry(tmp_path / "a.sqlite")) as a,
        closing(open_registry(tmp_path / "b.sqlite")) as b,
    ):
        draft = revisions.commit(a, _draft(account, stable, "component"), device_id=device)
        _release(a, draft, device, "1.0")
        event = sync_state.prepare(a, account_id=account, device_id=device, stored=draft).request
        payload = json.loads(json.dumps(event.payload))
        row = payload["sync_released_versions"][0]
        if tamper == "identity":
            row["snapshot"]["stable_id"] = new_id("component")
        elif tamper == "content":
            row["snapshot"]["description"] = "changed bytes"
        elif tamper == "digest":
            row["passport_digest"] = cache.digest_of({"different": True})
        elif tamper == "version":
            row["version"] = "2.0"
        elif tamper == "kind":
            row["snapshot"]["kind"] = "setup"
        elif tamper == "boolean_schema":
            row["snapshot"]["schema_version"] = True
        elif tamper == "missing_defaults":
            del row["snapshot"]["visibility"]
        else:
            row["snapshot"]["parent_revision_ids"] = [draft.revision_id]
        changed = _rebind(event, payload)
        before = b.serialize()
        with pytest.raises(CliFailure, match="snapshot") as refused:
            sync_state.apply_page(b, account_id=account, response=_page(changed, 1), at=AT)
        assert refused.value.code == "AI_STP_VALIDATION_ERROR"
        assert b.serialize() == before
        assert sync_state.cursor(b, account) is None


def test_command_delivers_new_release_after_resuming_an_uncertain_push(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    from ai_stp_cli import config
    from ai_stp_cli.cloud.client import Endpoint
    from ai_stp_cli.cloud.session import Session
    from ai_stp_cli.commands import cloud_auth, sync
    from ai_stp_cli.errors import CliFailure
    from ai_stp_contracts.sync import SyncPushRequest

    account, device, stable = new_id("account"), new_id("device"), new_id("component")
    path = tmp_path / "a.sqlite"
    config.set_values({"registry.path": str(path), "sync.enabled": "true"})
    with closing(open_registry(path)) as a:
        draft = revisions.commit(a, _draft(account, stable, "component"), device_id=device)
    held = Session(
        account_id=account,
        device_id=device,
        access_token="test",
        refresh_token="test",
        expires_at="2099-01-01T00:00:00.000Z",
    )
    events: list[SyncEvent] = []
    receipts: dict[str, SyncEventReceipt] = {}
    seen: list[SyncEvent] = []
    lose_response = True

    def route(request: httpx.Request) -> httpx.Response:
        nonlocal lose_response
        event = SyncPushRequest.model_validate_json(request.read()).events[0]
        seen.append(event)
        if event.event_id not in receipts:
            expected = events[-1].revision_id if events else None
            assert event.expected_head_revision_id == expected
            assert expected is None or expected in event.parent_revision_ids
            events.append(event)
            receipts[event.event_id] = _accepted(event)
        if lose_response:
            lose_response = False
            raise httpx.ReadError("lost response", request=request)
        return httpx.Response(
            200,
            json={
                "schema_version": 1,
                "receipts": [receipts[event.event_id].model_dump(mode="json")],
            },
        )

    def session_for(_purpose: str) -> Session:
        return held

    monkeypatch.setattr(cloud_auth, "required", session_for)
    monkeypatch.setattr(
        sync,
        "endpoint",
        lambda: Endpoint(
            "https://platform.example", max_attempts=1, transport=httpx.MockTransport(route)
        ),
    )
    with pytest.raises(CliFailure) as lost:
        sync.push({"id": stable, "confirm": True})
    assert lost.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"
    with closing(open_registry(path)) as a:
        snapshot, version = _release(a, draft, device, "1.0")
    result = sync.push({"id": stable, "confirm": True}).payload
    assert result.state == "accepted"
    assert seen[0] == seen[1]
    assert len(events) == 2
    calls = len(seen)
    assert sync.push({"id": stable, "confirm": True}).payload.state == "accepted"
    assert len(seen) == calls
    with closing(open_registry(tmp_path / "b.sqlite")) as b:
        for index, event in enumerate(events, 1):
            sync_state.apply_page(b, account_id=account, response=_page(event, index), at=AT)
        assert versions.line(b, stable) == (version,)
        assert revisions.get(b, snapshot.revision_id) is not None
        assert revisions.head(b, stable) == revisions.get(b, draft.revision_id)


def test_accepted_stream_resolves_own_uncertain_event_before_next_release(tmp_path: Path) -> None:
    account, device, stable = new_id("account"), new_id("device"), new_id("component")
    with closing(open_registry(tmp_path / "a.sqlite")) as a:
        draft = revisions.commit(a, _draft(account, stable, "component"), device_id=device)
        uncertain = sync_state.prepare(
            a, account_id=account, device_id=device, stored=draft
        ).request
        assert sync_state.saved_receipt(a, account_id=account, event_id=uncertain.event_id) is None
        assert sync_state.apply_page(a, account_id=account, response=_page(uncertain, 1), at=AT)[
            :2
        ] == (0, 1)
        receipt = sync_state.saved_receipt(a, account_id=account, event_id=uncertain.event_id)
        assert receipt is not None and receipt.state == "accepted"
        _release(a, draft, device, "1.0")
        changed = sync_state.prepare(a, account_id=account, device_id=device, stored=draft).request
        assert changed.event_id != uncertain.event_id
        assert changed.expected_head_revision_id == uncertain.revision_id
        assert changed.parent_revision_ids == [uncertain.revision_id]


def test_delayed_receipt_and_history_replay_do_not_regress_transport_head(tmp_path: Path) -> None:
    account, device, stable = new_id("account"), new_id("device"), new_id("component")
    with closing(open_registry(tmp_path / "a.sqlite")) as a:
        draft = revisions.commit(a, _draft(account, stable, "component"), device_id=device)
        first = sync_state.prepare(a, account_id=account, device_id=device, stored=draft).request
        sync_state.record_receipt(a, account_id=account, receipt=_accepted(first))
        _release(a, draft, device, "1.0")
        second = sync_state.prepare(a, account_id=account, device_id=device, stored=draft).request
        sync_state.record_receipt(a, account_id=account, receipt=_accepted(second))
        sync_state.record_receipt(a, account_id=account, receipt=_accepted(first))
        sync_state.apply_page(a, account_id=account, response=_page(first, 1), at=AT)
        _release(a, draft, device, "1.1")
        third = sync_state.prepare(a, account_id=account, device_id=device, stored=draft).request
        assert third.expected_head_revision_id == second.revision_id
        assert third.parent_revision_ids == [second.revision_id]


def test_pull_reports_partial_until_a_legacy_reference_is_materialized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    import httpx

    from ai_stp_cli import config
    from ai_stp_cli.cloud.client import Endpoint
    from ai_stp_cli.cloud.session import Session
    from ai_stp_cli.commands import cloud_auth, sync

    account, sender, receiver, stable = (
        new_id("account"),
        new_id("device"),
        new_id("device"),
        new_id("setup"),
    )
    target = tmp_path / "b.sqlite"
    config.set_values({"registry.path": str(target), "sync.enabled": "true"})
    with closing(open_registry(tmp_path / "a.sqlite")) as a:
        draft = revisions.commit(a, _draft(account, stable, "setup"), device_id=sender)
        snapshot, _ = _release(a, draft, sender, "1.0")
        original = sync_state.prepare(a, account_id=account, device_id=sender, stored=draft).request
        payload = json.loads(json.dumps(original.payload))
        del payload["sync_released_versions"][0]["snapshot"]
        legacy = _rebind(original, payload)
        a.execute(
            "UPDATE sync_event SET request_json = ?, remote_revision_id = ?, sync_key = ? "
            "WHERE event_id = ?",
            (legacy.model_dump_json(), legacy.revision_id, draft.revision_id, legacy.event_id),
        )
        sync_state.record_receipt(a, account_id=account, receipt=_accepted(legacy))
        repair = sync_state.prepare(a, account_id=account, device_id=sender, stored=draft).request
    pages = iter(
        [
            _page(legacy, 1),
            SyncPullResponse(items=[], page=PageInfo(next_cursor="1", page_size=1)),
            _page(repair, 2),
            SyncPullResponse(items=[], page=PageInfo(next_cursor="2", page_size=1)),
        ]
    )
    held = Session(
        account_id=account,
        device_id=receiver,
        access_token="test",
        refresh_token="test",
        expires_at="2099-01-01T00:00:00.000Z",
    )

    def session_for(_purpose: str) -> Session:
        return held

    def route(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(pages).model_dump(mode="json"))

    monkeypatch.setattr(cloud_auth, "required", session_for)
    monkeypatch.setattr(
        sync,
        "endpoint",
        lambda: Endpoint("https://platform.example", transport=httpx.MockTransport(route)),
    )
    first = sync.pull({"confirm": True}).payload
    assert (
        first.state == "partial" and first.pending_version_count == len(first.pending_versions) == 1
    )
    assert first.pending_versions[0].revision_id == snapshot.revision_id
    assert sync.pull({"confirm": True}).payload.state == "partial"
    repaired = sync.pull({"confirm": True}).payload
    assert repaired.pending_version_count == 0 and repaired.pending_versions == []
    assert sync.pull({"confirm": True}).payload.state == "up_to_date"


@pytest.mark.parametrize("kind", ["component", "setup"])
def test_real_catalog_passport_snapshot_keeps_its_complete_shape(
    tmp_path: Path, kind: Literal["component", "setup"]
) -> None:
    from ai_stp_contracts.first_party import versions as first_party_versions

    item = next(item for item in first_party_versions() if item.kind == kind)
    account, device = new_id("account"), new_id("device")
    stable = item.passport.stable_id
    body = item.passport.model_dump(mode="json")
    body["owner_id"] = account
    body["visibility"] = "private"
    with (
        closing(open_registry(tmp_path / "a.sqlite")) as a,
        closing(open_registry(tmp_path / "b.sqlite")) as b,
    ):
        draft = revisions.commit(a, _draft(account, stable, kind), device_id=device)
        stored = revisions.store_snapshot(a, cast(dict[str, JsonValue], body), device_id=device)
        typed = type(item.passport).model_validate(stored.envelope.model_dump(mode="json"))
        version = versions.record(
            a,
            stable_id=stable,
            version=typed.version,
            passport_digest=cache.digest_of(cast(JsonValue, typed.model_dump(mode="json"))),
            revision_id=stored.revision_id,
            at=AT,
        )
        event = sync_state.prepare(a, account_id=account, device_id=device, stored=draft).request
        sync_state.apply_page(b, account_id=account, response=_page(event, 1), at=AT)
        received = revisions.get(b, stored.revision_id)
        assert received is not None
        restored = type(typed).model_validate(received.envelope.model_dump(mode="json"))
        assert restored == typed
        assert versions.line(b, stable) == (version,)
        assert revisions.head(b, stable) == revisions.get(b, draft.revision_id)


def test_replay_page_query_growth_is_linear_in_history_length(tmp_path: Path) -> None:
    def measure(length: int) -> int:
        account, device, stable = new_id("account"), new_id("device"), new_id("component")
        with closing(open_registry(tmp_path / f"history-{length}.sqlite")) as db:
            events: list[SyncEvent] = []
            parents: list[JsonValue] = []
            for step in range(length):
                body = _draft(account, stable, "component")
                body["parent_revision_ids"] = parents
                body["step"] = step
                draft = revisions.commit(db, body, device_id=device)
                event = sync_state.prepare(
                    db, account_id=account, device_id=device, stored=draft
                ).request
                sync_state.record_receipt(db, account_id=account, receipt=_accepted(event))
                events.append(event)
                parents = [draft.revision_id]
            page = SyncPullResponse(
                items=[_page(event, position).items[0] for position, event in enumerate(events, 1)],
                page=PageInfo(next_cursor="end", page_size=length),
            )
            queries: list[str] = []
            db.set_trace_callback(queries.append)
            sync_state.apply_page(db, account_id=account, response=page, at=AT)
            db.set_trace_callback(None)
            return sum(query.lstrip().startswith("SELECT") for query in queries)

    small, large = 4, 16
    assert measure(large) < (large // small + 1) * measure(small)
