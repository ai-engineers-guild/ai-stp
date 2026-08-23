"""Sync transport keeps exact events, cursors and revision graphs durable."""

import sqlite3
from pathlib import Path
from typing import cast

import httpx
import pytest

from ai_stp_cli.cloud import session
from ai_stp_cli.cloud import sync as cloud_sync
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.commands import cloud_auth
from ai_stp_cli.commands import sync as sync_commands
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import lifecycle, revisions, sync_state, versions
from ai_stp_cli.local.database import open_registry
from ai_stp_contracts.http import PageInfo
from ai_stp_contracts.sync import (
    SyncConflictInfo,
    SyncEventReceipt,
    SyncPullQuery,
    SyncPullResponse,
    SyncPushRequest,
    SyncStreamEvent,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.revisions import revision_id

ACCOUNT = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
DEVICE_A = "device_01JQZK7B8N4M6P2R9T5V0X3Y7A"
DEVICE_B = "device_01JQZK7B8N4M6P2R9T5V0X3Y7B"
AT = "2026-08-13T00:00:00.000Z"


def _content(
    stable_id: str, *, parents: list[str] | None = None, role: str = "backend"
) -> dict[str, JsonValue]:
    return {
        "schema_version": 1,
        "kind": "developer",
        "stable_id": stable_id,
        "owner_id": ACCOUNT,
        "created_at": AT,
        "visibility": "private",
        "parent_revision_ids": cast(list[JsonValue], parents or []),
        "facts": {
            "role": {
                "value": role,
                "origin": "declared",
                "confirmation": "none",
                "source_refs": [],
                "observed_at": None,
                "confirmed_at": None,
                "confidence": None,
            }
        },
    }


def _accepted(event_id: str, revision_id: str, cursor: str) -> SyncEventReceipt:
    return SyncEventReceipt(
        event_id=event_id,
        state="accepted",
        revision_id=revision_id,
        server_head_revision_id=revision_id,
        cursor=cursor,
        conflict=None,
        conflicting_entity_id=None,
        error_code=None,
    )


def _stream(request: object, sequence: int) -> SyncStreamEvent:
    from ai_stp_contracts.sync import SyncEvent

    event = cast(SyncEvent, request)
    return SyncStreamEvent(
        **event.model_dump(exclude={"idempotency_key", "expected_head_revision_id"}, mode="python"),
        sequence=sequence,
    )


def test_prepare_replays_exact_event_and_child_uses_remote_parent(tmp_path: Path) -> None:
    connection = open_registry(tmp_path / "registry.sqlite")
    stable_id = new_id("developer")
    try:
        root = revisions.commit(connection, _content(stable_id), device_id=DEVICE_A)
        first = sync_state.prepare(connection, account_id=ACCOUNT, device_id=DEVICE_A, stored=root)
        replay = sync_state.prepare(connection, account_id=ACCOUNT, device_id=DEVICE_A, stored=root)
        assert replay.request == first.request
        sync_state.record_receipt(
            connection,
            account_id=ACCOUNT,
            receipt=_accepted(first.request.event_id, first.request.revision_id, "cursor-root"),
        )
        child = revisions.commit(
            connection,
            _content(stable_id, parents=[root.revision_id], role="platform"),
            device_id=DEVICE_A,
        )
        second = sync_state.prepare(
            connection, account_id=ACCOUNT, device_id=DEVICE_A, stored=child
        )
        assert second.request.parent_revision_ids == [first.request.revision_id]
        assert second.request.expected_head_revision_id == first.request.revision_id
        assert sync_state.cursor(connection, ACCOUNT) is None
    finally:
        connection.close()


def test_tombstone_is_a_distinct_replay_safe_child_of_remote_head(tmp_path: Path) -> None:
    connection = open_registry(tmp_path / "registry.sqlite")
    stable_id = new_id("developer")
    try:
        root = revisions.commit(connection, _content(stable_id), device_id=DEVICE_A)
        pushed = sync_state.prepare(connection, account_id=ACCOUNT, device_id=DEVICE_A, stored=root)
        sync_state.record_receipt(
            connection,
            account_id=ACCOUNT,
            receipt=_accepted(pushed.request.event_id, pushed.request.revision_id, "cursor-root"),
        )
        lifecycle.entomb(connection, stable_id, reason="owner deleted it", at=AT)
        tombstone = sync_state.prepare_tombstone(
            connection, account_id=ACCOUNT, device_id=DEVICE_A, stable_id=stable_id
        )
        replay = sync_state.prepare_tombstone(
            connection, account_id=ACCOUNT, device_id=DEVICE_A, stable_id=stable_id
        )
        assert replay.request == tombstone.request
        assert tombstone.request.operation == "tombstone"
        assert tombstone.request.payload == {}
        assert tombstone.request.parent_revision_ids == [pushed.request.revision_id]
        assert tombstone.request.expected_head_revision_id == pushed.request.revision_id
    finally:
        connection.close()


def test_forbidden_path_never_becomes_a_pending_network_event(tmp_path: Path) -> None:
    connection = open_registry(tmp_path / "registry.sqlite")
    stable_id = new_id("developer")
    content = _content(stable_id)
    content["facts"] = {
        "workspace": {
            "value": "/home/alice/private",
            "origin": "declared",
            "confirmation": "none",
        }
    }
    try:
        stored = revisions.commit(connection, content, device_id=DEVICE_A)
        with pytest.raises(CliFailure) as forbidden:
            sync_state.prepare(connection, account_id=ACCOUNT, device_id=DEVICE_A, stored=stored)
        assert forbidden.value.code == "AI_STP_VALIDATION_ERROR"
        assert connection.execute("SELECT COUNT(*) FROM sync_event").fetchone()[0] == 0
    finally:
        connection.close()


def test_secret_free_required_env_is_syncable_but_values_are_not(tmp_path: Path) -> None:
    connection = open_registry(tmp_path / "registry.sqlite")
    try:
        allowed_id = new_id("component")
        allowed = _content(allowed_id)
        allowed["kind"] = "component"
        allowed["required_env"] = [{"name": "GITHUB_TOKEN", "purpose": "test access"}]
        stored = revisions.commit(connection, allowed, device_id=DEVICE_A)
        pending = sync_state.prepare(
            connection, account_id=ACCOUNT, device_id=DEVICE_A, stored=stored
        )
        assert pending.request.payload["required_env"] == allowed["required_env"]

        refused_id = new_id("component")
        refused = _content(refused_id)
        refused["kind"] = "component"
        refused["required_env"] = [
            {"name": "GITHUB_TOKEN", "purpose": "test access", "value": "secret"}
        ]
        refused_stored = revisions.commit(connection, refused, device_id=DEVICE_A)
        with pytest.raises(CliFailure):
            sync_state.prepare(
                connection,
                account_id=ACCOUNT,
                device_id=DEVICE_A,
                stored=refused_stored,
            )
    finally:
        connection.close()


def test_pull_applies_page_and_cursor_atomically_then_replays(tmp_path: Path) -> None:
    source = open_registry(tmp_path / "source.sqlite")
    target = open_registry(tmp_path / "target.sqlite")
    stable_id = new_id("developer")
    try:
        local = revisions.commit(source, _content(stable_id), device_id=DEVICE_A)
        prepared = sync_state.prepare(
            source, account_id=ACCOUNT, device_id=DEVICE_A, stored=local
        ).request
        stream = SyncStreamEvent(
            **prepared.model_dump(
                exclude={"idempotency_key", "expected_head_revision_id"}, mode="python"
            ),
            sequence=1,
        )
        response = SyncPullResponse(
            items=[stream], page=PageInfo(next_cursor="opaque-cursor", page_size=20)
        )
        assert sync_state.apply_page(target, account_id=ACCOUNT, response=response, at=AT) == (
            1,
            0,
            [],
        )
        assert revisions.head(target, stable_id) is not None
        assert sync_state.cursor(target, ACCOUNT) == "opaque-cursor"
        assert sync_state.apply_page(target, account_id=ACCOUNT, response=response, at=AT) == (
            0,
            1,
            [],
        )
    finally:
        source.close()
        target.close()


def _pushed(source: sqlite3.Connection, sequence: int) -> SyncStreamEvent:
    """One server-shaped event for a fresh component, as this device would push it.

    A component rather than a developer passport: an installation holds exactly
    one of the latter, so a two-event walk of those could not be applied at all.
    """
    content = _content(new_id("component"))
    content["kind"] = "component"
    local = revisions.commit(source, content, device_id=DEVICE_A)
    prepared = sync_state.prepare(source, account_id=ACCOUNT, device_id=DEVICE_A, stored=local)
    return _stream(prepared.request, sequence)


def test_last_page_keeps_the_position_the_walk_reached(tmp_path: Path) -> None:
    # `next_cursor` is null on the last page by contract. Storing it would erase
    # the only position this device has, and because `pull` takes one page per
    # invocation the next call would restart the same walk — a loop that never
    # closes rather than one slow resync.
    source = open_registry(tmp_path / "source.sqlite")
    target = open_registry(tmp_path / "target.sqlite")
    try:
        first = _pushed(source, 1)
        last = _pushed(source, 2)

        walked = SyncPullResponse(
            items=[first], page=PageInfo(next_cursor="cursor-after-first", page_size=1)
        )
        assert sync_state.apply_page(target, account_id=ACCOUNT, response=walked, at=AT) == (
            1,
            0,
            [],
        )
        assert sync_state.cursor(target, ACCOUNT) == "cursor-after-first"

        terminal = SyncPullResponse(items=[last], page=PageInfo(next_cursor=None, page_size=1))
        assert sync_state.apply_page(target, account_id=ACCOUNT, response=terminal, at=AT) == (
            1,
            0,
            [],
        )

        # The next `pull` resumes from the page it already reached instead of
        # sending nothing and making the server start from sequence zero.
        assert sync_state.cursor(target, ACCOUNT) == "cursor-after-first"
    finally:
        source.close()
        target.close()


def test_pull_that_reached_the_end_of_an_empty_stream_invents_no_position(
    tmp_path: Path,
) -> None:
    target = open_registry(tmp_path / "target.sqlite")
    try:
        empty = SyncPullResponse(items=[], page=PageInfo(next_cursor=None, page_size=20))
        assert sync_state.apply_page(target, account_id=ACCOUNT, response=empty, at=AT) == (
            0,
            0,
            [],
        )
        # Nothing was walked, so there is no position to keep — and none is
        # fabricated: the cursor is signed and account-bound server-side.
        assert sync_state.cursor(target, ACCOUNT) is None
        assert sync_state.apply_page(target, account_id=ACCOUNT, response=empty, at=AT) == (
            0,
            0,
            [],
        )
        assert sync_state.cursor(target, ACCOUNT) is None
    finally:
        target.close()


def test_tampered_pull_rolls_back_without_advancing_cursor(tmp_path: Path) -> None:
    source = open_registry(tmp_path / "source.sqlite")
    target = open_registry(tmp_path / "target.sqlite")
    stable_id = new_id("developer")
    try:
        local = revisions.commit(source, _content(stable_id), device_id=DEVICE_A)
        prepared = sync_state.prepare(
            source, account_id=ACCOUNT, device_id=DEVICE_A, stored=local
        ).request
        stream = SyncStreamEvent(
            **prepared.model_dump(
                exclude={"idempotency_key", "expected_head_revision_id"}, mode="python"
            ),
            sequence=1,
        ).model_copy(update={"payload": {"changed": True}})
        response = SyncPullResponse(
            items=[stream], page=PageInfo(next_cursor="must-not-stick", page_size=20)
        )
        with pytest.raises(CliFailure):
            sync_state.apply_page(target, account_id=ACCOUNT, response=response, at=AT)
        assert sync_state.cursor(target, ACCOUNT) is None
    finally:
        source.close()
        target.close()


def test_version_collision_rolls_back_the_remote_revision_and_cursor(tmp_path: Path) -> None:
    source = open_registry(tmp_path / "source.sqlite")
    target = open_registry(tmp_path / "target.sqlite")
    stable_id = new_id("component")
    component = _content(stable_id)
    component["kind"] = "component"
    try:
        remote = revisions.commit(source, component, device_id=DEVICE_A)
        local = revisions.commit(target, component, device_id=DEVICE_B)
        versions.record(
            source,
            stable_id=stable_id,
            version="1.0",
            passport_digest="sha256:" + "a" * 64,
            revision_id=remote.revision_id,
            at=AT,
        )
        versions.record(
            target,
            stable_id=stable_id,
            version="1.0",
            passport_digest="sha256:" + "b" * 64,
            revision_id=local.revision_id,
            at=AT,
        )
        prepared = sync_state.prepare(
            source, account_id=ACCOUNT, device_id=DEVICE_A, stored=remote
        ).request
        stream = SyncStreamEvent(
            **prepared.model_dump(
                exclude={"idempotency_key", "expected_head_revision_id"}, mode="python"
            ),
            sequence=1,
        )
        response = SyncPullResponse(
            items=[stream], page=PageInfo(next_cursor="must-not-stick", page_size=20)
        )
        before = target.serialize()
        with pytest.raises(CliFailure) as collision:
            sync_state.apply_page(target, account_id=ACCOUNT, response=response, at=AT)
        assert collision.value.code == "AI_STP_CONFLICT"
        assert target.serialize() == before
        assert sync_state.cursor(target, ACCOUNT) is None
    finally:
        source.close()
        target.close()


def test_two_devices_fast_forward_diverge_and_commit_clean_merge(tmp_path: Path) -> None:
    left_db = open_registry(tmp_path / "left.sqlite")
    right_db = open_registry(tmp_path / "right.sqlite")
    stable_id = new_id("developer")
    try:
        root = revisions.commit(left_db, _content(stable_id), device_id=DEVICE_A)
        root_event = sync_state.prepare(
            left_db, account_id=ACCOUNT, device_id=DEVICE_A, stored=root
        ).request
        sync_state.record_receipt(
            left_db,
            account_id=ACCOUNT,
            receipt=_accepted(root_event.event_id, root_event.revision_id, "cursor-1"),
        )
        sync_state.apply_page(
            right_db,
            account_id=ACCOUNT,
            response=SyncPullResponse(
                items=[_stream(root_event, 1)],
                page=PageInfo(next_cursor="cursor-1", page_size=20),
            ),
            at=AT,
        )
        left_child = revisions.commit(
            left_db,
            _content(stable_id, parents=[root.revision_id], role="platform"),
            device_id=DEVICE_A,
        )
        right_document = _content(stable_id, parents=[root.revision_id])
        right_document["facts"] = {
            **cast(dict[str, JsonValue], right_document["facts"]),
            "autonomy": {
                "value": "full-auto",
                "origin": "declared",
                "confirmation": "none",
                "source_refs": [],
                "observed_at": None,
                "confirmed_at": None,
                "confidence": None,
            },
        }
        right_child = revisions.commit(right_db, right_document, device_id=DEVICE_B)
        left_event = sync_state.prepare(
            left_db, account_id=ACCOUNT, device_id=DEVICE_A, stored=left_child
        ).request
        right_event = sync_state.prepare(
            right_db, account_id=ACCOUNT, device_id=DEVICE_B, stored=right_child
        ).request
        sync_state.record_receipt(
            right_db,
            account_id=ACCOUNT,
            receipt=_accepted(right_event.event_id, right_event.revision_id, "cursor-2"),
        )
        conflict = SyncEventReceipt(
            event_id=left_event.event_id,
            state="conflict",
            revision_id=left_event.revision_id,
            server_head_revision_id=right_event.revision_id,
            cursor=None,
            conflict=SyncConflictInfo(
                server_head_revision_id=right_event.revision_id,
                client_head_revision_id=left_event.revision_id,
                common_ancestor_revision_id=root_event.revision_id,
                affected_fields=[],
            ),
            conflicting_entity_id=None,
            error_code=None,
        )
        sync_state.record_receipt(left_db, account_id=ACCOUNT, receipt=conflict)
        sync_state.apply_page(
            left_db,
            account_id=ACCOUNT,
            response=SyncPullResponse(
                items=[_stream(right_event, 2)],
                page=PageInfo(next_cursor="cursor-2", page_size=20),
            ),
            at=AT,
        )
        assert sync_commands._report(left_db, stable_id).state == "merge_ready"  # pyright: ignore[reportPrivateUsage]
        merged = sync_commands.commit_merge(left_db, stable_id=stable_id, device_id=DEVICE_A)
        assert len(merged.parents) == 2
        assert sync_commands._report(left_db, stable_id).state == "up_to_date"  # pyright: ignore[reportPrivateUsage]
        merged_event = sync_state.prepare(
            left_db, account_id=ACCOUNT, device_id=DEVICE_A, stored=merged
        ).request
        assert set(merged_event.parent_revision_ids) == {
            left_event.revision_id,
            right_event.revision_id,
        }
        assert merged_event.expected_head_revision_id == right_event.revision_id
    finally:
        left_db.close()
        right_db.close()


def test_http_transport_uses_exact_authenticated_routes(tmp_path: Path) -> None:
    seen: list[tuple[str, str, str | None]] = []

    def route(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.headers.get("Authorization")))
        if request.method == "POST":
            body = request.read()
            event = SyncPushRequest.model_validate_json(body).events[0]
            return httpx.Response(
                200,
                json={
                    "schema_version": 1,
                    "receipts": [
                        _accepted(event.event_id, event.revision_id, "cursor").model_dump(
                            mode="json"
                        )
                    ],
                },
            )
        return httpx.Response(
            200,
            json={
                "schema_version": 1,
                "items": [],
                "page": {"schema_version": 1, "next_cursor": None, "page_size": 7},
            },
        )

    endpoint = Endpoint("https://platform.example", transport=httpx.MockTransport(route))
    # Reuse a fully validated event created by the state layer.
    with open_registry(tmp_path / "registry.sqlite") as registry:
        stable_id = new_id("developer")
        stored = revisions.commit(registry, _content(stable_id), device_id=DEVICE_A)
        event = sync_state.prepare(
            registry, account_id=ACCOUNT, device_id=DEVICE_A, stored=stored
        ).request
        cloud_sync.push(endpoint, "token", SyncPushRequest(events=[event]))
    cloud_sync.pull(endpoint, "token", SyncPullQuery(cursor=None, page_size=7))
    assert seen == [
        ("POST", "/v1/sync/push", "Bearer token"),
        ("GET", "/v1/sync/pull", "Bearer token"),
    ]


def test_push_resumes_after_unknown_result_with_the_same_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    with open_registry(registry_path) as registry:
        stable_id = new_id("developer")
        root = revisions.commit(registry, _content(stable_id), device_id=DEVICE_A)
        revisions.commit(
            registry,
            _content(stable_id, parents=[root.revision_id], role="platform"),
            device_id=DEVICE_A,
        )
    held = session.Session(
        account_id=ACCOUNT,
        device_id=DEVICE_A,
        access_token="token",
        refresh_token="refresh",
        expires_at="2099-01-01T00:00:00.000Z",
    )
    seen: list[tuple[str, str]] = []
    receipts: dict[str, dict[str, object]] = {}
    lose_first = True

    def route(request: httpx.Request) -> httpx.Response:
        nonlocal lose_first
        event = SyncPushRequest.model_validate_json(request.read()).events[0]
        seen.append((event.event_id, event.idempotency_key))
        receipt = _accepted(event.event_id, event.revision_id, f"cursor-{len(receipts) + 1}")
        receipts.setdefault(event.event_id, receipt.model_dump(mode="json"))
        if lose_first:
            lose_first = False
            raise httpx.ReadError("response was lost", request=request)
        return httpx.Response(
            200, json={"schema_version": 1, "receipts": [receipts[event.event_id]]}
        )

    monkeypatch.setattr(sync_commands, "_enabled", lambda: None)  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(sync_commands, "configured_path", lambda: registry_path)

    def required_session(_purpose: str) -> session.Session:
        return held

    monkeypatch.setattr(cloud_auth, "required", required_session)
    monkeypatch.setattr(
        sync_commands,
        "endpoint",
        lambda: Endpoint(
            "https://platform.example", max_attempts=1, transport=httpx.MockTransport(route)
        ),
    )

    with pytest.raises(CliFailure) as lost:
        sync_commands.push({"id": stable_id, "confirm": True})
    assert lost.value.retryable

    result = sync_commands.push({"id": stable_id, "confirm": True}).payload
    assert result.state == "accepted"
    assert result.processed_events == 2
    assert seen[0] == seen[1]
    assert len({event_id for event_id, _key in seen}) == 2


def test_sync_transport_commands_are_explicit_and_machine_described() -> None:
    from ai_stp_cli.registry import COMMANDS

    commands = {item.name: item for item in COMMANDS}
    assert commands["sync preview"].descriptor.mutability == "read"
    for name in ("sync push", "sync pull", "sync merge"):
        assert commands[name].descriptor.confirmation == "explicit_flag"
        assert commands[name].descriptor.result_schema is not None


def test_a_refused_pull_names_the_event_and_the_condition(tmp_path: Path) -> None:
    """A page is applied atomically, so one bad event stops the account forever.

    The refusal used to carry neither the event nor the reason — an empty
    `details` and a sentence naming three conditions without saying which. Two
    events with a `revision_id` that does not derive from their payload reached
    production before `seal_envelope` was corrected, and from the client there
    was no way to learn which of the three checks refused them, or which event
    to repair. Finding out meant reimplementing the check outside the CLI.

    Everything the answer needs is already in hand at the point of refusal.
    """
    source = open_registry(tmp_path / "source.sqlite")
    target = open_registry(tmp_path / "target.sqlite")
    stable_id = new_id("developer")
    try:
        local = revisions.commit(source, _content(stable_id), device_id=DEVICE_A)
        prepared = sync_state.prepare(
            source, account_id=ACCOUNT, device_id=DEVICE_A, stored=local
        ).request
        event = prepared.model_dump(
            exclude={"idempotency_key", "expected_head_revision_id"}, mode="python"
        )
        # Exactly the shape production carried: a payload whose stated revision
        # id is not the one its own content derives, inside an event whose own
        # account binding is intact. Both have to hold — the binding is checked
        # first, and a payload edited without resealing the event never reaches
        # the coordinates check at all.
        payload = dict(cast(dict[str, object], event["payload"]))
        payload["revision_id"] = f"revision_{'0' * 64}"
        event["payload"] = payload
        sealed: dict[str, JsonValue] = {
            "schema_version": 1,
            "entity_id": event["entity_id"],
            "entity_kind": event["entity_kind"],
            "parent_revision_ids": event["parent_revision_ids"],
            "operation": event["operation"],
            "payload": cast(JsonValue, payload),
            "device_id": event["device_id"],
            "actor_id": event["actor_id"],
            "created_at": event["created_at"],
        }
        event["revision_id"] = revision_id(sealed)
        event["content_digest"] = digest_canonical("ai-stp:revision:v1", cast(JsonValue, payload))
        response = SyncPullResponse(
            items=[SyncStreamEvent(**event, sequence=1)],
            page=PageInfo(next_cursor="opaque-cursor", page_size=20),
        )
        with pytest.raises(CliFailure) as refused:
            sync_state.apply_page(target, account_id=ACCOUNT, response=response, at=AT)
        details = refused.value.details
        assert refused.value.message == (
            "a pulled sync payload does not match its exact event coordinates"
        ), refused.value.message
        assert details["entity_id"] == stable_id
        assert details["event_id"] == prepared.event_id
        assert details["reason"] == "revision_id is not derived from the payload"
        # The cursor must not move past an event that was never applied.
        assert sync_state.cursor(target, ACCOUNT) is None
    finally:
        source.close()
        target.close()


def test_a_named_event_can_be_walked_past_and_is_reported(tmp_path: Path) -> None:
    """The only way out of a poisoned outbox, and it cannot be used blind.

    An event that fails validation stops the account's pulls on every device,
    and no page size gets past it: observed on production, where the walk
    stopped on the same event id eight times running while `--page-size 1`
    made no difference. Nothing client-side could move the cursor beyond it.

    Walking past one abandons a revision, so the caller names the exact id the
    refusal answered. There is deliberately no "skip whatever is broken": that
    would silently drop a real revision the first time a different defect made
    one unreadable. The skipped ids come back in the answer for the same
    reason — an abandoned revision is not a quiet outcome.
    """
    source = open_registry(tmp_path / "source.sqlite")
    target = open_registry(tmp_path / "target.sqlite")
    stable_id = new_id("developer")
    try:
        local = revisions.commit(source, _content(stable_id), device_id=DEVICE_A)
        prepared = sync_state.prepare(
            source, account_id=ACCOUNT, device_id=DEVICE_A, stored=local
        ).request
        event = prepared.model_dump(
            exclude={"idempotency_key", "expected_head_revision_id"}, mode="python"
        )
        payload = dict(cast(dict[str, object], event["payload"]))
        payload["revision_id"] = f"revision_{'0' * 64}"
        event["payload"] = payload
        sealed: dict[str, JsonValue] = {
            "schema_version": 1,
            "entity_id": event["entity_id"],
            "entity_kind": event["entity_kind"],
            "parent_revision_ids": event["parent_revision_ids"],
            "operation": event["operation"],
            "payload": cast(JsonValue, payload),
            "device_id": event["device_id"],
            "actor_id": event["actor_id"],
            "created_at": event["created_at"],
        }
        event["revision_id"] = revision_id(sealed)
        event["content_digest"] = digest_canonical("ai-stp:revision:v1", cast(JsonValue, payload))
        response = SyncPullResponse(
            items=[SyncStreamEvent(**event, sequence=1)],
            page=PageInfo(next_cursor="opaque-cursor", page_size=20),
        )

        # Without the id, the page is refused and the cursor never moves.
        with pytest.raises(CliFailure):
            sync_state.apply_page(target, account_id=ACCOUNT, response=response, at=AT)
        assert sync_state.cursor(target, ACCOUNT) is None

        # A different id is not "close enough": it must be the exact one.
        with pytest.raises(CliFailure):
            sync_state.apply_page(
                target,
                account_id=ACCOUNT,
                response=response,
                at=AT,
                skip_event_ids=frozenset({f"event_{'f' * 32}"}),
            )

        applied, replayed, skipped = sync_state.apply_page(
            target,
            account_id=ACCOUNT,
            response=response,
            at=AT,
            skip_event_ids=frozenset({prepared.event_id}),
        )
        assert (applied, replayed, skipped) == (0, 0, [prepared.event_id])
        assert sync_state.cursor(target, ACCOUNT) == "opaque-cursor"
        # The revision was abandoned, not quietly written.
        assert revisions.head(target, stable_id) is None
    finally:
        source.close()
        target.close()
