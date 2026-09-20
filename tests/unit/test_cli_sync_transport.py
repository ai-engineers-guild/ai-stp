"""Sync transport keeps exact events, cursors and revision graphs durable."""

import sqlite3
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import cast

import httpx
import pytest

from ai_stp_cli.application import cloud_auth
from ai_stp_cli.application import sync as sync_commands
from ai_stp_cli.cloud import session
from ai_stp_cli.cloud import sync as cloud_sync
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import lifecycle, revisions, sync_state, versions
from ai_stp_cli.local.database import open_registry
from ai_stp_contracts.http import PageInfo
from ai_stp_contracts.sync import (
    SyncConflictInfo,
    SyncEvent,
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
            passport_digest=digest_canonical(
                "ai-stp:passport:v1", cast(JsonValue, remote.envelope.model_dump(mode="json"))
            ),
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


def test_a_refused_second_identity_names_the_one_the_account_already_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh install makes its own developer passport, and the account has one.

    The server refuses the second and names the first, because a device that
    cannot see the account's identity cannot choose between adopting it and
    replacing it. Reporting only `rejected` hands the operator a dead end: the
    refusal is correct and the next move is unnameable.
    """
    registry_path = tmp_path / "registry.sqlite"
    with open_registry(registry_path) as registry:
        stable_id = new_id("developer")
        revisions.commit(registry, _content(stable_id), device_id=DEVICE_A)
    held_by_account = new_id("developer")
    held = session.Session(
        account_id=ACCOUNT,
        device_id=DEVICE_A,
        access_token="token",
        refresh_token="refresh",
        expires_at="2099-01-01T00:00:00.000Z",
    )

    def route(request: httpx.Request) -> httpx.Response:
        event = SyncPushRequest.model_validate_json(request.read()).events[0]
        receipt = SyncEventReceipt(
            event_id=event.event_id,
            state="rejected",
            revision_id=None,
            server_head_revision_id=None,
            cursor=None,
            conflict=None,
            conflicting_entity_id=held_by_account,
            error_code="AI_STP_CONFLICT",
        )
        return httpx.Response(
            200, json={"schema_version": 1, "receipts": [receipt.model_dump(mode="json")]}
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

    result = sync_commands.push({"id": stable_id, "confirm": True}).payload
    assert result.state == "rejected"
    assert result.conflicting_entity_id == held_by_account


def test_a_refusal_raised_while_applying_still_names_the_event(tmp_path: Path) -> None:
    """`--skip-event` takes an exact id, so every refusal has to supply one.

    The coordinates check names its event because it runs inside the applier.
    A refusal raised deeper does not: `revisions.commit` enforces one developer
    passport per installation and knows nothing about sync, so its `details`
    carried the entity and no event. Observed on production, where an account
    stream holding a second developer identity stopped every pull with a
    refusal naming a passport the operator could not translate into an id to
    walk past. Correct refusal, unusable answer.
    """
    source = open_registry(tmp_path / "source.sqlite")
    target = open_registry(tmp_path / "target.sqlite")
    try:
        # The target already holds one developer passport, which is the state
        # any installed device is in.
        revisions.commit(target, _content(new_id("developer")), device_id=DEVICE_B)
        second = new_id("developer")
        local = revisions.commit(source, _content(second), device_id=DEVICE_A)
        prepared = sync_state.prepare(
            source, account_id=ACCOUNT, device_id=DEVICE_A, stored=local
        ).request
        response = SyncPullResponse(
            items=[_stream(prepared, 1)],
            page=PageInfo(next_cursor="opaque-cursor", page_size=20),
        )
        with pytest.raises(CliFailure) as refused:
            sync_state.apply_page(target, account_id=ACCOUNT, response=response, at=AT)
        details = refused.value.details
        assert details["stable_id"] == second, details
        assert details["event_id"] == prepared.event_id, details
        assert sync_state.cursor(target, ACCOUNT) is None
        # And the named id is the one that actually walks the stream past it.
        applied, replayed, skipped = sync_state.apply_page(
            target,
            account_id=ACCOUNT,
            response=response,
            at=AT,
            skip_event_ids=frozenset({str(details["event_id"])}),
        )
        assert (applied, replayed, skipped) == (0, 0, [prepared.event_id])
    finally:
        source.close()
        target.close()


def test_preview_does_not_answer_up_to_date_against_a_server_head_it_lacks(
    tmp_path: Path,
) -> None:
    """Two surfaces must not tell the operator opposite things about one entity.

    Observed on production: `sync push` answered `conflict` and named the
    server head, `sync pull` answered `received: 0`, and `sync preview`
    answered `up_to_date`. All three were internally consistent — preview reads
    local heads, and the head the server named had never reached this device —
    and together they were unusable: the device was told it was current while
    every push was refused, with nothing naming the disagreement.

    A receipt this device already stored is enough to know better.
    """
    connection = open_registry(tmp_path / "registry.sqlite")
    stable_id = new_id("developer")
    try:
        local = revisions.commit(connection, _content(stable_id), device_id=DEVICE_A)
        prepared = sync_state.prepare(
            connection, account_id=ACCOUNT, device_id=DEVICE_A, stored=local
        )
        assert sync_commands._report(connection, stable_id).state == "up_to_date"  # pyright: ignore[reportPrivateUsage]
        unreachable = f"revision_{'c' * 64}"
        sync_state.record_receipt(
            connection,
            account_id=ACCOUNT,
            receipt=SyncEventReceipt(
                event_id=prepared.request.event_id,
                state="conflict",
                revision_id=None,
                server_head_revision_id=unreachable,
                cursor=None,
                conflict=None,
                conflicting_entity_id=None,
                error_code=None,
            ),
        )
        report = sync_commands._report(connection, stable_id)  # pyright: ignore[reportPrivateUsage]
        assert report.state == "conflict", report
        assert report.head_revision_ids == [local.revision_id]
        assert report.candidate_revision_id is None
    finally:
        connection.close()


def test_a_conflicted_ancestor_does_not_block_the_merge_that_resolves_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`sync push` after `sync merge` must ship the merge, not replay the refusal.

    The conflicted candidate's revision is already in the server ledger — the
    whole point of storing it there is that a merge can name it a parent. The
    push walk used to stop on the saved `conflict` receipt, so the merge event
    was never sent and `sync push` answered `conflict` forever. Found by the
    real-boundary suite; this test keeps the walk honest without Postgres.
    """
    registry_path = tmp_path / "registry.sqlite"
    stable_id = new_id("developer")
    with open_registry(registry_path) as registry:
        root = revisions.commit(registry, _content(stable_id), device_id=DEVICE_A)
    held = session.Session(
        account_id=ACCOUNT,
        device_id=DEVICE_A,
        access_token="token",
        refresh_token="refresh",
        expires_at="2099-01-01T00:00:00.000Z",
    )
    pushed: list[SyncEvent] = []
    remote_head: dict[str, str] = {}

    def route(request: httpx.Request) -> httpx.Response:
        event = SyncPushRequest.model_validate_json(request.read()).events[0]
        pushed.append(event)
        # The first event lands; anything naming a different expected head
        # afterwards conflicts, exactly as the server decides.
        expected = event.expected_head_revision_id
        if "root" in remote_head and expected != remote_head["server"]:
            receipt = SyncEventReceipt(
                event_id=event.event_id,
                state="conflict",
                revision_id=event.revision_id,
                server_head_revision_id=remote_head["server"],
                cursor=None,
                conflict=None,
                conflicting_entity_id=None,
                error_code=None,
            )
        else:
            remote_head.setdefault("root", event.revision_id)
            remote_head["server"] = event.revision_id
            receipt = _accepted(event.event_id, event.revision_id, "cursor")
        return httpx.Response(
            200, json={"schema_version": 1, "receipts": [receipt.model_dump(mode="json")]}
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

    assert sync_commands.push({"id": stable_id, "confirm": True}).payload.state == "accepted"

    # What the server holds instead: a divergent child another device pushed —
    # built by the same real stack on a second machine's registry, which learned
    # the root by pull exactly as this device published it.
    source = open_registry(tmp_path / "source.sqlite")
    try:
        sync_state.apply_page(
            source,
            account_id=ACCOUNT,
            response=SyncPullResponse(
                items=[_stream(pushed[0], 1)],
                page=PageInfo(next_cursor="cursor-1", page_size=20),
            ),
            at=AT,
        )
        # Disjoint divergence — the remote child adds a fact while this
        # device's child edits `role`, so the merge is mechanical.
        remote_document = _content(stable_id, parents=[root.revision_id])
        remote_document["facts"] = {
            **cast(dict[str, JsonValue], remote_document["facts"]),
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
        remote_stored = revisions.commit(source, remote_document, device_id=DEVICE_B)
        remote_event = _stream(
            sync_state.prepare(
                source, account_id=ACCOUNT, device_id=DEVICE_B, stored=remote_stored
            ).request,
            2,
        )
    finally:
        source.close()
    # The remote head is what the server's copy of that child sealed to —
    # this device learns it only when the conflicting push names it.
    remote_head["server"] = remote_event.revision_id

    # This device's own divergent child, committed only after the root landed.
    with open_registry(registry_path) as registry:
        revisions.commit(
            registry,
            _content(stable_id, parents=[root.revision_id], role="platform"),
            device_id=DEVICE_A,
        )
    conflict = sync_commands.push({"id": stable_id, "confirm": True}).payload
    assert conflict.state == "conflict"

    with open_registry(registry_path) as registry:
        # The remote head arrives by pull, then the merge resolves the fork.
        sync_state.apply_page(
            registry,
            account_id=ACCOUNT,
            response=SyncPullResponse(
                items=[remote_event],
                page=PageInfo(next_cursor="cursor-2", page_size=20),
            ),
            at=AT,
        )
        sync_commands.commit_merge(registry, stable_id=stable_id, device_id=DEVICE_A)

    result = sync_commands.push({"id": stable_id, "confirm": True}).payload
    assert result.state == "accepted", "the merge event must reach the server"
    assert len(pushed) == 3  # root, divergent child, merge


def test_a_server_reported_revocation_offers_the_same_recovery_as_a_local_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One code must not mean two different things depending on who noticed.

    `cloud_auth.required` refuses a locally-known revoked device and names the
    way back. The same code arriving from the server was mapped straight from
    the response body, which carries no `next_actions`, so the operator got
    `AI_STP_DEVICE_REVOKED` and an empty list. Observed on production right
    after revoking a device in the web: correct code, correct `retryable:
    false`, and nothing saying that re-login is the answer.

    The closed registry already records how each code is handled, so the
    recovery is derived from that rather than invented per call site.
    """
    registry_path = tmp_path / "registry.sqlite"
    with open_registry(registry_path) as registry:
        revisions.commit(registry, _content(new_id("developer")), device_id=DEVICE_A)
    held = session.Session(
        account_id=ACCOUNT,
        device_id=DEVICE_A,
        access_token="token",
        refresh_token="refresh",
        expires_at="2099-01-01T00:00:00.000Z",
    )

    def route(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "schema_version": 1,
                "ok": False,
                "error": {
                    "code": "AI_STP_DEVICE_REVOKED",
                    "message": "device is revoked",
                    "retryable": False,
                    "details": {},
                },
            },
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

    with pytest.raises(CliFailure) as refused:
        sync_commands.pull({"confirm": True})
    assert refused.value.code == "AI_STP_DEVICE_REVOKED"
    assert refused.value.retryable is False
    assert refused.value.next_actions, "a revoked device was given no way back"
    assert refused.value.next_actions[0] == "device reset --confirm --json"
    assert any("task start --intent account" in action for action in refused.value.next_actions)
    assert all("auth login" not in action for action in refused.value.next_actions)


def _component_content(
    stable_id: str, *, parents: list[str] | None = None, name: str = "probe"
) -> dict[str, JsonValue]:
    return {
        "schema_version": 1,
        "kind": "component",
        "stable_id": stable_id,
        "owner_id": ACCOUNT,
        "created_at": AT,
        "visibility": "private",
        "parent_revision_ids": cast(list[JsonValue], parents or []),
        "facts": {
            "component_type": {
                "value": "skill",
                "origin": "observed",
                "confirmation": "none",
                "source_refs": [],
                "observed_at": AT,
                "confirmed_at": None,
                "confidence": None,
            },
            "source_name": {
                "value": name,
                "origin": "observed",
                "confirmation": "none",
                "source_refs": [],
                "observed_at": AT,
                "confirmed_at": None,
                "confidence": None,
            },
        },
    }


def test_a_snapshot_missing_from_history_is_recovered_from_a_new_event(tmp_path: Path) -> None:
    from ai_stp_cli.local import sync_versions

    source = open_registry(tmp_path / "source.sqlite")
    target = open_registry(tmp_path / "target.sqlite")
    stable_id = new_id("component")
    try:
        first = revisions.commit(source, _component_content(stable_id), device_id=DEVICE_A)
        versions.record(
            source,
            stable_id=stable_id,
            version="1.0",
            passport_digest=digest_canonical(
                "ai-stp:passport:v1", cast(JsonValue, first.envelope.model_dump(mode="json"))
            ),
            revision_id=first.revision_id,
            at=AT,
        )
        second_root = revisions.commit(
            source, _component_content(stable_id, name="probe-2"), device_id=DEVICE_A
        )
        prepared = sync_state.prepare(
            source, account_id=ACCOUNT, device_id=DEVICE_A, stored=second_root
        ).request
        sync_state.apply_page(
            target,
            account_id=ACCOUNT,
            response=SyncPullResponse(
                items=[_stream(prepared, 1)], page=PageInfo(next_cursor="cursor", page_size=20)
            ),
            at=AT,
        )
        assert revisions.get(target, first.revision_id) is not None
        target_head = revisions.head(target, stable_id)
        assert target_head is not None and target_head.revision_id == second_root.revision_id
        assert versions.line(target, stable_id) == versions.line(source, stable_id)
        assert sync_versions.pending(target, account=ACCOUNT) == (0, [])
    finally:
        source.close()
        target.close()


def test_an_abandoned_event_is_remembered_and_the_refusal_names_the_way_past(
    tmp_path: Path,
) -> None:
    """Naming an abandoned event once is the decision; later pulls honour it unasked.

    Measured on a real account: five abandoned events had to travel as flags
    through every later invocation, and the refusal's next action was a
    template the caller had to complete from `details`. The id is recorded on
    the device the first time it is named, and the refusal that leads there
    carries the exact command.
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
        first_page = SyncPullResponse(
            items=[SyncStreamEvent(**event, sequence=1)],
            page=PageInfo(next_cursor="cursor-1", page_size=20),
        )

        with pytest.raises(CliFailure) as raised:
            sync_state.apply_page(target, account_id=ACCOUNT, response=first_page, at=AT)
        assert raised.value.next_actions[0] == (
            f"sync pull --skip-event {prepared.event_id} --confirm --json"
        )

        named = sync_state.apply_page(
            target,
            account_id=ACCOUNT,
            response=first_page,
            at=AT,
            skip_event_ids=frozenset({prepared.event_id}),
        )
        assert named == (0, 0, [prepared.event_id])
        assert sync_state.abandoned_events(target, ACCOUNT) == frozenset({prepared.event_id})

        # The same event again — a re-read page — with nothing named this time.
        again = SyncPullResponse(
            items=[SyncStreamEvent(**event, sequence=1)],
            page=PageInfo(next_cursor="cursor-2", page_size=20),
        )
        unasked = sync_state.apply_page(target, account_id=ACCOUNT, response=again, at=AT)
        assert unasked == (0, 0, [prepared.event_id])
        assert sync_state.cursor(target, ACCOUNT) == "cursor-2"
    finally:
        source.close()
        target.close()


def _stream_event(
    entity_kind: str,
    entity_id: str,
    payload: dict[str, object],
    *,
    operation: str = "upsert",
    sequence: int = 1,
    device_id: str = DEVICE_B,
    event_id: str | None = None,
) -> SyncStreamEvent:
    """A pulled event of a non-passport kind, sealed exactly as a sender does."""
    sealed: dict[str, JsonValue] = {
        "schema_version": 1,
        "entity_id": entity_id,
        "entity_kind": entity_kind,
        "parent_revision_ids": cast(list[JsonValue], []),
        "operation": operation,
        "payload": cast(JsonValue, payload),
        "device_id": device_id,
        "actor_id": ACCOUNT,
        "created_at": AT,
    }
    return SyncStreamEvent(
        event_id=event_id or f"event_{uuid.uuid4().hex}",
        entity_id=entity_id,
        entity_kind=entity_kind,  # pyright: ignore[reportArgumentType]
        revision_id=revision_id(sealed),
        parent_revision_ids=[],
        device_id=device_id,
        actor_id=ACCOUNT,
        operation=operation,  # pyright: ignore[reportArgumentType]
        content_digest=digest_canonical("ai-stp:revision:v1", cast(JsonValue, payload)),
        created_at=AT,
        payload=payload,
        sequence=sequence,
    )


def _summary_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "display_name": "studio-laptop",
        "operating_system": "linux",
        "architecture": "x86_64",
        "detected_harnesses": [{"harness_id": "claude-code", "version": "2.0.0"}],
        "toolchain_profile_version": "mvp-full/1",
        "summary_updated_at": AT,
    }


def _consent_payload(
    scope: str = "task", target: str = "full-auto", **overrides: object
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "scope": scope,
        "target": target,
        "fingerprint": {"network_permissions": ["api.example.test"]},
        "observed": ["component_01J000000000000000000000AA"],
        "decided_by": ACCOUNT,
        "origin": "component consent allow",
        "created_at": AT,
    }
    payload.update(overrides)
    return payload


def test_a_device_summary_pull_is_acknowledged_not_stored(tmp_path: Path) -> None:
    """Another device's summary advances the stream; it is never installed.

    Before the dispatch existed the same event refused the page as "not a
    passport envelope" and wedged every pull behind it.
    """
    connection = open_registry(tmp_path / "registry.sqlite")
    try:
        event = _stream_event("device_summary", DEVICE_B, _summary_payload())
        page = SyncPullResponse(items=[event], page=PageInfo(next_cursor="cursor-1", page_size=20))
        assert sync_state.apply_page(connection, account_id=ACCOUNT, response=page, at=AT) == (
            1,
            0,
            [],
        )
        assert sync_state.cursor(connection, ACCOUNT) == "cursor-1"
        # Acknowledged, not adopted: no local revision materialises for it.
        assert revisions.head(connection, DEVICE_B) is None

        replay = sync_state.apply_page(connection, account_id=ACCOUNT, response=page, at=AT)
        assert replay == (0, 1, [])
    finally:
        connection.close()


def test_a_malformed_device_summary_refuses_the_page_and_names_the_event(
    tmp_path: Path,
) -> None:
    connection = open_registry(tmp_path / "registry.sqlite")
    try:
        broken = _summary_payload()
        broken.pop("operating_system")
        event = _stream_event("device_summary", DEVICE_B, broken)
        page = SyncPullResponse(items=[event], page=PageInfo(next_cursor="cursor-1", page_size=20))
        with pytest.raises(CliFailure) as raised:
            sync_state.apply_page(connection, account_id=ACCOUNT, response=page, at=AT)
        assert raised.value.code == "AI_STP_VALIDATION_ERROR"
        assert raised.value.details["event_id"] == event.event_id
        # The refusal is transactional: the cursor stays behind the bad event.
        assert sync_state.cursor(connection, ACCOUNT) is None
    finally:
        connection.close()


def test_a_pulled_consent_grant_applies_and_replays(tmp_path: Path) -> None:
    from ai_stp_cli.local import consent

    connection = open_registry(tmp_path / "registry.sqlite")
    try:
        entity = consent.entity_id("task", "full-auto")
        event = _stream_event("unverified_consent", entity, _consent_payload())
        page = SyncPullResponse(items=[event], page=PageInfo(next_cursor="cursor-1", page_size=20))
        assert sync_state.apply_page(connection, account_id=ACCOUNT, response=page, at=AT) == (
            1,
            0,
            [],
        )
        held = consent.held(connection, scope="task", target="full-auto")
        assert held is not None and held.active
        assert held.consent_id == entity
        assert held.decided_by == ACCOUNT

        replay = sync_state.apply_page(connection, account_id=ACCOUNT, response=page, at=AT)
        assert replay == (0, 1, [])
    finally:
        connection.close()


def test_a_pulled_consent_tombstone_revokes(tmp_path: Path) -> None:
    from ai_stp_cli.local import consent

    connection = open_registry(tmp_path / "registry.sqlite")
    try:
        entity = consent.entity_id("task", "full-auto")
        upsert = _stream_event("unverified_consent", entity, _consent_payload())
        first = sync_state.apply_page(
            connection,
            account_id=ACCOUNT,
            response=SyncPullResponse(
                items=[upsert], page=PageInfo(next_cursor="c1", page_size=20)
            ),
            at=AT,
        )
        assert first == (1, 0, [])

        tombstone = _stream_event(
            "unverified_consent",
            entity,
            {"schema_version": 1, "scope": "task", "target": "full-auto", "revoked_at": AT},
            operation="tombstone",
            sequence=2,
        )
        second = sync_state.apply_page(
            connection,
            account_id=ACCOUNT,
            response=SyncPullResponse(
                items=[tombstone], page=PageInfo(next_cursor="c2", page_size=20)
            ),
            at=AT,
        )
        assert second == (1, 0, [])
        held = consent.held(connection, scope="task", target="full-auto")
        assert held is not None and not held.active
    finally:
        connection.close()


def test_a_pulled_consent_outside_the_closed_scopes_is_refused(tmp_path: Path) -> None:
    """A wildcard scope is exactly what the closed set exists to refuse."""
    connection = open_registry(tmp_path / "registry.sqlite")
    try:
        event = _stream_event(
            "unverified_consent",
            "consent_deadbeef",
            _consent_payload(scope="everything", target="*"),
        )
        page = SyncPullResponse(items=[event], page=PageInfo(next_cursor="c1", page_size=20))
        with pytest.raises(CliFailure) as raised:
            sync_state.apply_page(connection, account_id=ACCOUNT, response=page, at=AT)
        assert raised.value.code == "AI_STP_VALIDATION_ERROR"
        assert sync_state.cursor(connection, ACCOUNT) is None
    finally:
        connection.close()


def test_consent_entity_id_is_derived_from_scope_and_target() -> None:
    from ai_stp_cli.local import consent

    first = consent.entity_id("task", "full-auto")
    assert first == consent.entity_id("task", "full-auto")
    assert first.startswith("consent_")
    assert first != consent.entity_id("publisher", "account_x")
    assert first != consent.entity_id("task", "other")


def test_prepare_event_is_durable_deduplicated_and_head_aware(tmp_path: Path) -> None:
    connection = open_registry(tmp_path / "registry.sqlite")
    try:
        payload = _summary_payload()
        first = sync_state.prepare_event(
            connection,
            account_id=ACCOUNT,
            device_id=DEVICE_A,
            entity_id=DEVICE_A,
            entity_kind="device_summary",
            operation="upsert",
            payload=payload,
            created_at=AT,
        )
        # Durable before any network call, and the same content replays it.
        row = connection.execute(
            "SELECT state FROM sync_event WHERE event_id = ?", (first.request.event_id,)
        ).fetchone()
        assert row is not None and row[0] == "pending"
        again = sync_state.prepare_event(
            connection,
            account_id=ACCOUNT,
            device_id=DEVICE_A,
            entity_id=DEVICE_A,
            entity_kind="device_summary",
            operation="upsert",
            payload=payload,
            created_at=AT,
        )
        assert again.request == first.request

        sync_state.record_receipt(
            connection,
            account_id=ACCOUNT,
            receipt=_accepted(first.request.event_id, first.request.revision_id, "c1"),
        )
        # Equal content after acceptance reuses the accepted event — no second
        # row, no new idempotency key.
        repeat = sync_state.prepare_event(
            connection,
            account_id=ACCOUNT,
            device_id=DEVICE_A,
            entity_id=DEVICE_A,
            entity_kind="device_summary",
            operation="upsert",
            payload=payload,
            created_at="2026-09-20T00:00:00.000Z",
        )
        assert repeat.request.event_id == first.request.event_id
        assert repeat.state == "accepted"

        # Changed content fast-forwards off the accepted head.
        changed = dict(payload, display_name="renamed")
        nxt = sync_state.prepare_event(
            connection,
            account_id=ACCOUNT,
            device_id=DEVICE_A,
            entity_id=DEVICE_A,
            entity_kind="device_summary",
            operation="upsert",
            payload=changed,
            created_at="2026-09-20T00:00:00.000Z",
        )
        assert nxt.request.parent_revision_ids == [first.request.revision_id]
        assert nxt.request.expected_head_revision_id == first.request.revision_id
        assert nxt.request.event_id != first.request.event_id

        # A tombstone requires an accepted remote head — refuse one for an
        # entity that was never pushed.
        with pytest.raises(CliFailure, match="accepted remotely"):
            sync_state.prepare_event(
                connection,
                account_id=ACCOUNT,
                device_id=DEVICE_A,
                entity_id="consent_never_pushed",
                entity_kind="unverified_consent",
                operation="tombstone",
                payload={"schema_version": 1, "scope": "task", "target": "full-auto"},
                created_at=AT,
            )
    finally:
        connection.close()


def _wire_device_content(stable_id: str) -> dict[str, JsonValue]:
    def fact(value: JsonValue) -> dict[str, JsonValue]:
        return {"value": value, "origin": "observed", "confirmation": "none"}

    return {
        "schema_version": 1,
        "kind": "device",
        "stable_id": stable_id,
        "owner_id": ACCOUNT,
        "created_at": AT,
        "visibility": "private",
        "parent_revision_ids": [],
        "facts": {
            "operating_system": fact("linux"),
            "architecture": fact("x86_64"),
            "harness_installations": fact(
                [{"harness_id": "claude-code", "installations": [{"version": "2.0.0"}]}]
            ),
        },
    }


def _push_session(
    endpoint_route: Callable[[httpx.Request], httpx.Response],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held = session.Session(
        account_id=ACCOUNT,
        device_id=DEVICE_A,
        access_token="token",
        refresh_token="refresh",
        expires_at="2099-01-01T00:00:00.000Z",
    )

    def required_session(_purpose: str) -> session.Session:
        return held

    monkeypatch.setattr(sync_commands, "_enabled", lambda: None)  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(cloud_auth, "required", required_session)
    monkeypatch.setattr(
        sync_commands,
        "endpoint",
        lambda: Endpoint(
            "https://platform.example",
            max_attempts=1,
            transport=httpx.MockTransport(endpoint_route),
        ),
    )


def test_push_sends_the_device_summary_not_the_passport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`sync push --id` on the device passport emits `device_summary` only."""
    registry_path = tmp_path / "registry.sqlite"
    with open_registry(registry_path) as registry:
        stored = revisions.commit(registry, _wire_device_content(DEVICE_A), device_id=DEVICE_A)
    sent: list[SyncEvent] = []

    def route(request: httpx.Request) -> httpx.Response:
        event = SyncPushRequest.model_validate_json(request.read()).events[0]
        sent.append(event)
        receipt = _accepted(event.event_id, event.revision_id, "cursor-1")
        return httpx.Response(
            200, json={"schema_version": 1, "receipts": [receipt.model_dump(mode="json")]}
        )

    _push_session(route, monkeypatch)
    monkeypatch.setattr(sync_commands, "configured_path", lambda: registry_path)

    result = sync_commands.push({"id": DEVICE_A, "confirm": True}).payload
    assert result.state == "accepted"
    (event,) = sent
    assert event.entity_kind == "device_summary"
    assert event.entity_id == DEVICE_A
    assert event.operation == "upsert"
    payload = event.payload
    # The closed set, and nothing else: no facts, no paths, no passport.
    assert set(payload) == {
        "schema_version",
        "display_name",
        "operating_system",
        "architecture",
        "detected_harnesses",
        "toolchain_profile_version",
        "summary_updated_at",
    }
    assert payload["operating_system"] == "linux"
    assert payload["detected_harnesses"] == [{"harness_id": "claude-code", "version": "2.0.0"}]
    assert result.local_revision_id == stored.revision_id


def test_push_sends_the_consent_record_and_then_its_tombstone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_stp_cli.local import consent

    registry_path = tmp_path / "registry.sqlite"
    with open_registry(registry_path) as registry:
        consent.grant(
            registry,
            consent_id=new_id("request"),
            scope="task",
            target="full-auto",
            fingerprint={},
            observed=(),
            decided_by=ACCOUNT,
            origin="component consent allow",
            at=AT,
        )
    entity = consent.entity_id("task", "full-auto")
    sent: list[SyncEvent] = []

    def route(request: httpx.Request) -> httpx.Response:
        event = SyncPushRequest.model_validate_json(request.read()).events[0]
        sent.append(event)
        receipt = _accepted(event.event_id, event.revision_id, f"cursor-{len(sent)}")
        return httpx.Response(
            200, json={"schema_version": 1, "receipts": [receipt.model_dump(mode="json")]}
        )

    _push_session(route, monkeypatch)
    monkeypatch.setattr(sync_commands, "configured_path", lambda: registry_path)

    pushed = sync_commands.push({"id": entity, "confirm": True}).payload
    assert pushed.state == "accepted"
    assert sent[0].entity_kind == "unverified_consent"
    assert sent[0].entity_id == entity
    assert sent[0].operation == "upsert"
    assert sent[0].parent_revision_ids == []
    upsert_payload = sent[0].payload
    assert upsert_payload["scope"] == "task"
    assert upsert_payload["target"] == "full-auto"

    with open_registry(registry_path) as registry:
        consent.revoke(registry, scope="task", target="full-auto", at=AT)

    retracted = sync_commands.push({"id": entity, "confirm": True}).payload
    assert retracted.state == "accepted"
    assert sent[1].operation == "tombstone"
    assert sent[1].parent_revision_ids == [sent[0].revision_id]
    assert sent[1].expected_head_revision_id == sent[0].revision_id


def test_consent_allow_names_the_push_continuation_when_sync_is_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A granted consent is a sync entity; the answer says how to publish it."""
    from ai_stp_cli import config
    from ai_stp_cli.application.continuations import bind_continuation
    from ai_stp_cli.commands import component as component_command
    from ai_stp_cli.local import consent

    config.set_values({"sync.enabled": "true"})
    answer = component_command.consent_allow({"scope": "task", "target": "full-auto"})
    (step,) = answer.continuations
    entity = consent.entity_id("task", "full-auto")
    assert step.path == ["sync", "push"]
    assert step.arguments == {"id": entity, "confirm": True}
    bound = bind_continuation(step)
    assert bound.argv == ["sync", "push", "--id", entity, "--confirm", "--json"]

    # Sync off: no push step is offered for a record that does not sync.
    config.set_values({"sync.enabled": "false"})
    silent = component_command.consent_allow({"scope": "task", "target": "full-auto"})
    assert silent.continuations == ()
