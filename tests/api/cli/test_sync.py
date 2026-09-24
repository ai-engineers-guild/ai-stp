# pyright: reportUnusedFunction=false

"""Private sync journeys against the real `/v1/sync` push and pull routes.

`tests/unit/test_cli_sync_transport.py` exercises the local half — event
preparation, page application, cursors and merge mechanics on real SQLite —
which is where those guarantees live. What it could not exercise is the
server half: a real outbox, real conflict detection against another device's
head, real idempotency replay, and the singleton-identity refusal. This file
drives the CLI's own `sync_state`/`sync_commands` code against the deployed
surface over `SyncAsgiTransport`.

A second device on the same account is seeded directly (`Device` row plus a
device-bound session token): its pushes and pulls are real HTTP, while its
local registry is a scratch file — exactly what a second machine is.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from tests.support.asgi_sync import SyncAsgiServer

from ai_stp_cli.application import sync as sync_commands
from ai_stp_cli.cloud import sync as cloud_sync
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.cloud.session import Session as CliSession
from ai_stp_cli.commands import config_show
from ai_stp_cli.commands import task as task_command
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import passports, revisions, sync_state
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_contracts.machine_help import SyncPushView
from ai_stp_contracts.sync import SyncEvent, SyncPullQuery, SyncPushRequest
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Device

AT = "2026-08-13T00:00:00.000Z"


def _enable(monkeypatch: pytest.MonkeyPatch, endpoint: Endpoint) -> None:
    """The real config gate plus the real endpoint — no patched seams inside."""
    config_show.set_({"set": ("sync.enabled=true",)})
    monkeypatch.setattr(sync_commands, "endpoint", lambda: endpoint)


def _content(
    stable_id: str,
    *,
    owner_id: str,
    kind: str = "component",
    parents: list[str] | None = None,
    name: str = "probe",
    extra_facts: dict[str, JsonValue] | None = None,
) -> dict[str, JsonValue]:
    if kind == "developer":
        # `developer init` ships empty facts, so any fact a revision declares
        # is an addition — divergence stays disjoint when each child names a
        # different key.
        facts: dict[str, JsonValue] = {}
    else:
        facts = {
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
        }
    if extra_facts:
        facts.update(extra_facts)
    return {
        "schema_version": 1,
        "kind": kind,
        "stable_id": stable_id,
        "owner_id": owner_id,
        "created_at": AT,
        "visibility": "private",
        "parent_revision_ids": cast(list[JsonValue], parents or []),
        "facts": facts,
    }


def _second_device(cli_server: SyncAsgiServer, account_id: str) -> tuple[str, str]:
    """A second active device on the same account, plus its bearer token."""
    device_id = new_id("device")
    sessionmaker = cli_server.app.state.sessionmaker

    async def seed() -> str:
        from ai_stp_api.session import issue_session

        async with sessionmaker() as db:
            db.add(
                Device(
                    id=device_id,
                    account_id=account_id,
                    public_key=f"ed25519:{device_id}",
                )
            )
            issued = await issue_session(
                db, account_id=account_id, device_id=device_id, ttl_seconds=3600
            )
            await db.commit()
            return issued.raw_token

    return device_id, cli_server.call(seed)


def _event_for(
    registry_path: Path,
    *,
    account_id: str,
    device_id: str,
    stable_id: str,
    name: str = "probe",
    parents: list[str] | None = None,
    kind: str = "component",
    extra_facts: dict[str, JsonValue] | None = None,
) -> SyncEvent:
    """One prepared sync event, built by the real local stack on its own registry."""
    with open_registry(registry_path) as connection:
        stored = revisions.commit(
            connection,
            _content(
                stable_id,
                owner_id=account_id,
                kind=kind,
                parents=parents,
                name=name,
                extra_facts=extra_facts,
            ),
            device_id=device_id,
        )
        return sync_state.prepare(
            connection, account_id=account_id, device_id=device_id, stored=stored
        ).request


def test_push_then_pull_round_trips_the_event_to_a_second_device(
    cli_endpoint: Endpoint,
    cli_server: SyncAsgiServer,
    device_session: CliSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An account task writes the outbox; a second device reads exact bytes."""
    _enable(monkeypatch, cli_endpoint)
    account_id = device_session.account_id
    stable_id = new_id("component")

    # The device's own registry is the configured one — the same file
    # `developer init` created during sign-in.
    with open_registry(configured_path()) as connection:
        revisions.commit(
            connection,
            _content(stable_id, owner_id=account_id),
            device_id=device_session.device_id,
        )

    facts = tmp_path / "account-push.json"
    facts.write_text(json.dumps({"action": "sync", "scope": "push", "stable_id": stable_id}))
    started = task_command.start(
        {
            "intent": "account",
            "idempotency-key": "account-real-push-0001",
            "input": str(facts),
        }
    )
    assert started.payload.goal_satisfied
    outcome = started.payload.outcome
    assert outcome is not None and outcome.kind == "account"
    pushed = outcome.sync_result
    assert isinstance(pushed, SyncPushView)
    assert pushed.state == "accepted"
    assert pushed.stable_id == stable_id
    replay = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert replay.payload == started.payload

    device_b, token_b = _second_device(cli_server, account_id)
    del device_b
    page = cloud_sync.pull(cli_endpoint, token_b, SyncPullQuery(cursor=None, page_size=20))
    # Event ids round-trip exactly; the event's revision_id seals the sync
    # envelope, so it is not the local revision id the push view reports.
    assert [item.event_id for item in page.items] == [pushed.event_id]
    assert page.page.next_cursor is not None

    # The received page applies cleanly to a fresh machine's empty registry.
    other = tmp_path / "device-b.sqlite"
    with open_registry(other) as connection:
        applied, replayed, skipped = sync_state.apply_page(
            connection, account_id=account_id, response=page, at=AT
        )
        assert (applied, replayed, skipped) == (1, 0, [])
        assert revisions.head(connection, stable_id) is not None

    drained = cloud_sync.pull(
        cli_endpoint,
        token_b,
        SyncPullQuery(cursor=page.page.next_cursor, page_size=20),
    )
    assert drained.items == []


def test_a_retried_push_replays_one_stored_receipt(
    cli_endpoint: Endpoint,
    cli_server: SyncAsgiServer,
    device_session: CliSession,
    tmp_path: Path,
) -> None:
    """Same idempotency key, same event: the stored receipt, not a second row."""
    account_id = device_session.account_id
    stable_id = new_id("component")
    event = _event_for(
        tmp_path / "sender.sqlite",
        account_id=account_id,
        device_id=device_session.device_id,
        stable_id=stable_id,
    )

    first = cloud_sync.push(
        cli_endpoint, device_session.access_token, SyncPushRequest(events=[event])
    )
    again = cloud_sync.push(
        cli_endpoint, device_session.access_token, SyncPushRequest(events=[event])
    )
    assert first.receipts[0].state == "accepted"
    assert again.receipts[0].model_dump() == first.receipts[0].model_dump()

    page = cloud_sync.pull(
        cli_endpoint, device_session.access_token, SyncPullQuery(cursor=None, page_size=20)
    )
    assert len(page.items) == 1, "a replayed push must not enqueue the event twice"


def test_a_second_developer_identity_is_rejected_naming_the_held_one(
    cli_endpoint: Endpoint,
    cli_server: SyncAsgiServer,
    device_session: CliSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A fresh install pushes its own developer passport; the account holds one."""
    _enable(monkeypatch, cli_endpoint)
    account_id = device_session.account_id

    with open_registry(configured_path()) as connection:
        held_id = passports.developer_stable_id(connection)
    assert held_id is not None

    accepted = sync_commands.push({"id": held_id, "confirm": True}).payload
    assert accepted.state == "accepted"

    # A second machine's own `passport developer init` — a different entity on
    # the same account, pushed from its own device.
    device_b, token_b = _second_device(cli_server, account_id)
    foreign = _event_for(
        tmp_path / "device-b.sqlite",
        account_id=account_id,
        device_id=device_b,
        stable_id=new_id("developer"),
        kind="developer",
    )
    response = cloud_sync.push(cli_endpoint, token_b, SyncPushRequest(events=[foreign]))
    receipt = response.receipts[0]
    assert receipt.state == "rejected"
    assert receipt.error_code == "AI_STP_CONFLICT"
    assert receipt.conflicting_entity_id == held_id


def test_divergent_heads_conflict_then_an_explicit_merge_is_accepted(
    cli_endpoint: Endpoint,
    cli_server: SyncAsgiServer,
    device_session: CliSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The whole production shape: two devices diverge, the merge lands.

    Device A pushes a root; device B fast-forwards it; device A's own child
    meets the moved head and comes back `conflict` naming the server head.
    Pull applies B's event; `sync merge` writes the two-parent revision; the
    push is accepted — and B's pull then receives A's undelivered conflict
    candidate ahead of the merge, because a page has to be applicable.
    """
    _enable(monkeypatch, cli_endpoint)
    account_id = device_session.account_id
    device_a = device_session.device_id
    registry_a = configured_path()

    # The developer passport sign-in created is the entity: only developer
    # passports merge mechanically, and this one exists on both sides.
    with open_registry(registry_a) as connection:
        held = passports.developer_stable_id(connection)
    assert held is not None
    stable_id = held

    root = sync_commands.push({"id": stable_id, "confirm": True}).payload
    assert root.state == "accepted"
    root_revision = root.local_revision_id

    device_b, token_b = _second_device(cli_server, account_id)
    registry_b = tmp_path / "device-b.sqlite"
    # B's registry must know the root before its child can name it a parent.
    with open_registry(registry_b) as connection:
        page = cloud_sync.pull(cli_endpoint, token_b, SyncPullQuery(cursor=None, page_size=20))
        sync_state.apply_page(connection, account_id=account_id, response=page, at=AT)

    # Divergence must be on disjoint facts for a mechanical merge: B adds one
    # fact, A changes another — the unit suite's mergeable shape.
    child_b = _event_for(
        registry_b,
        account_id=account_id,
        device_id=device_b,
        stable_id=stable_id,
        kind="developer",
        parents=[root_revision],
        extra_facts={
            "autonomy": {
                "value": "full-auto",
                "origin": "declared",
                "confirmation": "none",
                "source_refs": [],
                "observed_at": None,
                "confirmed_at": None,
                "confidence": None,
            }
        },
    )
    pushed_b = cloud_sync.push(cli_endpoint, token_b, SyncPushRequest(events=[child_b]))
    assert pushed_b.receipts[0].state == "accepted"

    # A diverges from the same parent on a disjoint fact while B's child is
    # already the head — the mechanical-merge case. The push goes through the
    # command so the conflict receipt is recorded locally.
    with open_registry(registry_a) as connection:
        revisions.commit(
            connection,
            _content(
                stable_id,
                owner_id=account_id,
                kind="developer",
                parents=[root_revision],
                extra_facts={
                    "role": {
                        "value": "platform",
                        "origin": "declared",
                        "confirmation": "none",
                        "source_refs": [],
                        "observed_at": None,
                        "confirmed_at": None,
                        "confidence": None,
                    }
                },
            ),
            device_id=device_a,
        )
    child_a_view = sync_commands.push({"id": stable_id, "confirm": True}).payload
    assert child_a_view.state == "conflict"
    assert child_a_view.server_head_revision_id == child_b.revision_id

    pulled = sync_commands.pull({"confirm": True}).payload
    assert pulled.applied >= 1
    report = sync_commands.preview({"id": stable_id}).payload
    assert report.state == "merge_ready"

    merged = sync_commands.merge({"id": stable_id, "confirm": True}).payload
    assert merged.state == "up_to_date"

    merge_push = sync_commands.push({"id": stable_id, "confirm": True}).payload
    assert merge_push.state == "accepted"

    # B's next pull re-reads its own event, then gets A's conflict candidate
    # ahead of the merge — the undelivered-ancestors guarantee, end to end.
    for_b = cloud_sync.pull(
        cli_endpoint,
        token_b,
        SyncPullQuery(cursor=page.page.next_cursor, page_size=20),
    )
    delivered = [item.event_id for item in for_b.items]
    assert delivered == [child_b.event_id, child_a_view.event_id, merge_push.event_id]


def test_a_revoked_device_is_refused_and_the_answer_names_the_way_back(
    cli_endpoint: Endpoint,
    cli_server: SyncAsgiServer,
    device_session: CliSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Server-reported revocation carries the same recovery as a local one."""
    _enable(monkeypatch, cli_endpoint)
    sessionmaker = cli_server.app.state.sessionmaker
    device_id = device_session.device_id

    async def revoke() -> None:
        async with sessionmaker() as db:
            device = await db.get(Device, device_id)
            assert device is not None
            device.state = "revoked"
            await db.commit()

    cli_server.call(revoke)

    with pytest.raises(CliFailure) as refused:
        sync_commands.pull({"confirm": True})
    assert refused.value.code == "AI_STP_DEVICE_REVOKED"
    assert refused.value.retryable is False
    assert refused.value.next_actions[0] == "device reset --confirm --json"


def test_an_event_bound_to_another_device_is_refused(
    cli_endpoint: Endpoint,
    device_session: CliSession,
    tmp_path: Path,
) -> None:
    """The session's device is authoritative: an event naming another is a 400."""
    foreign_device = new_id("device")
    event = _event_for(
        tmp_path / "forged.sqlite",
        account_id=device_session.account_id,
        device_id=foreign_device,
        stable_id=new_id("component"),
    )
    with pytest.raises(CliFailure) as refused:
        cloud_sync.push(
            cli_endpoint,
            device_session.access_token,
            SyncPushRequest(events=[event]),
        )
    assert refused.value.code == "AI_STP_VALIDATION_ERROR"


def _device_passport_content(stable_id: str, *, owner_id: str) -> dict[str, JsonValue]:
    def fact(value: JsonValue) -> dict[str, JsonValue]:
        return {
            "value": value,
            "origin": "observed",
            "confirmation": "none",
            "source_refs": [],
            "observed_at": AT,
            "confirmed_at": None,
            "confidence": None,
        }

    return {
        "schema_version": 1,
        "kind": "device",
        "stable_id": stable_id,
        "owner_id": owner_id,
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


def _sealed_event(
    *,
    account_id: str,
    device_id: str,
    entity_id: str,
    entity_kind: str,
    operation: str,
    payload: dict[str, object],
    parents: list[str] | None = None,
    expected_head: str | None = None,
) -> SyncEvent:
    from ai_stp_cli.cloud import login
    from ai_stp_foundation.digests import digest_canonical
    from ai_stp_foundation.revisions import revision_id

    sealed: dict[str, JsonValue] = {
        "schema_version": 1,
        "entity_id": entity_id,
        "entity_kind": entity_kind,
        "parent_revision_ids": cast(list[JsonValue], parents or []),
        "operation": operation,
        "payload": cast(JsonValue, payload),
        "device_id": device_id,
        "actor_id": account_id,
        "created_at": AT,
    }
    return SyncEvent(
        event_id=f"event_{new_id('request').removeprefix('request_')}",
        entity_id=entity_id,
        entity_kind=entity_kind,  # pyright: ignore[reportArgumentType]
        revision_id=revision_id(sealed),
        parent_revision_ids=parents or [],
        device_id=device_id,
        actor_id=account_id,
        operation=operation,  # pyright: ignore[reportArgumentType]
        content_digest=digest_canonical("ai-stp:revision:v1", cast(JsonValue, payload)),
        created_at=AT,
        idempotency_key=login.new_idempotency_key(),
        expected_head_revision_id=expected_head,
        payload=payload,
    )


def test_device_summary_publishes_through_sync_and_reads_back_on_devices(
    cli_endpoint: Endpoint,
    cli_server: SyncAsgiServer,
    device_session: CliSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`sync push` on the device passport emits only the closed summary, and
    `GET /v1/devices` serves that stored document instead of a fabricated one."""
    _enable(monkeypatch, cli_endpoint)
    account_id = device_session.account_id
    device_stable = new_id("device")

    with open_registry(configured_path()) as connection:
        revisions.commit(
            connection,
            _device_passport_content(device_stable, owner_id=account_id),
            device_id=device_session.device_id,
        )

    pushed = sync_commands.push({"id": device_stable, "confirm": True}).payload
    assert pushed.state == "accepted"

    # The wire event is the summary entity bound to the session device — never
    # the passport, which stays local (REQ-911).
    page = cloud_sync.pull(
        cli_endpoint, device_session.access_token, SyncPullQuery(cursor=None, page_size=20)
    )
    (item,) = [event for event in page.items if event.entity_kind == "device_summary"]
    assert item.entity_id == device_session.device_id
    payload = item.payload
    assert payload["operating_system"] == "linux"
    assert payload["architecture"] == "x86_64"
    assert "facts" not in payload and "harness_installations" not in payload

    # The read side serves what was stored, not a fabricated linux/x86_64.
    import httpx

    assert cli_server.transport is not None
    with httpx.Client(transport=cli_server.transport, base_url="http://127.0.0.1") as web:
        listed = web.get(
            "/v1/devices",
            headers={"Authorization": f"Bearer {device_session.access_token}"},
        )
    assert listed.status_code == 200, listed.text
    (record,) = [
        row for row in listed.json()["items"] if row["device_id"] == device_session.device_id
    ]
    summary = cast(dict[str, object], record["summary"])
    assert summary["operating_system"] == "linux"
    assert summary["architecture"] == "x86_64"
    assert summary["toolchain_profile_version"] == payload["toolchain_profile_version"]


def test_consent_round_trips_through_the_real_ledger_to_a_second_device(
    cli_endpoint: Endpoint,
    cli_server: SyncAsgiServer,
    device_session: CliSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Grant on one device → pull applies it on another; revoke → tombstone."""
    from ai_stp_cli.commands import component as component_command
    from ai_stp_cli.local import consent

    _enable(monkeypatch, cli_endpoint)
    account_id = device_session.account_id

    granted = component_command.consent_allow({"scope": "task", "target": "full-auto"})
    entity = granted.payload.sync_entity_id
    # The continuation names the exact entity and the real push command.
    (step,) = granted.continuations
    assert step.path == ["sync", "push"]
    assert step.arguments == {"id": entity, "confirm": True}

    pushed = sync_commands.push({"id": entity, "confirm": True}).payload
    assert pushed.state == "accepted"

    # A second device pulls the account stream and the consent lands locally.
    _device_b, token_b = _second_device(cli_server, account_id)
    page = cloud_sync.pull(cli_endpoint, token_b, SyncPullQuery(cursor=None, page_size=20))
    other = tmp_path / "device-b.sqlite"
    with open_registry(other) as connection:
        applied, _replayed, _skipped = sync_state.apply_page(
            connection, account_id=account_id, response=page, at=AT
        )
        assert applied >= 1
        held = consent.held(connection, scope="task", target="full-auto")
        assert held is not None and held.active
        assert held.consent_id == entity

    # Revocation pushes the tombstone, fast-forwarding off the accepted head.
    component_command.consent_revoke({"scope": "task", "target": "full-auto"})
    retracted = sync_commands.push({"id": entity, "confirm": True}).payload
    assert retracted.state == "accepted"

    page2 = cloud_sync.pull(cli_endpoint, token_b, SyncPullQuery(cursor=None, page_size=20))
    tombstones = [
        event
        for event in page2.items
        if event.entity_kind == "unverified_consent" and event.operation == "tombstone"
    ]
    assert len(tombstones) == 1
    fresh = tmp_path / "device-c.sqlite"
    with open_registry(fresh) as connection:
        sync_state.apply_page(connection, account_id=account_id, response=page2, at=AT)
        held = consent.held(connection, scope="task", target="full-auto")
        assert held is not None and not held.active


def test_a_malformed_consent_event_is_rejected_at_intake(
    cli_endpoint: Endpoint,
    cli_server: SyncAsgiServer,
    device_session: CliSession,
) -> None:
    """Intake refuses a scope the contract never declared, before the ledger.

    Without the shape check this event would be accepted, then refuse every
    pulling device on the page boundary — a wedge with no client-side remedy
    that names it. The receipt is `rejected`, durably.
    """
    account_id = device_session.account_id
    event = _sealed_event(
        account_id=account_id,
        device_id=device_session.device_id,
        entity_id="consent_deadbeef",
        entity_kind="unverified_consent",
        operation="upsert",
        payload={
            "schema_version": 1,
            "scope": "everything",
            "target": "*",
            "fingerprint": {},
            "observed": [],
            "decided_by": account_id,
            "origin": "planted",
            "created_at": AT,
        },
    )
    response = cloud_sync.push(
        cli_endpoint, device_session.access_token, SyncPushRequest(events=[event])
    )
    receipt = response.receipts[0]
    assert receipt.state == "rejected"

    # And nothing entered the stream: a second device pulls an empty account.
    _device_b, token_b = _second_device(cli_server, account_id)
    page = cloud_sync.pull(cli_endpoint, token_b, SyncPullQuery(cursor=None, page_size=20))
    assert page.items == []
