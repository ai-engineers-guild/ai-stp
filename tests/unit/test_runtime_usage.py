"""Focused checks for the corporate runtime usage boundary (SPEC-088).

The contract is the privacy mechanism: a closed field set, `extra="forbid"`,
and a payload guard that refuses anything outside `EVENT_FIELDS`. These tests
prove the boundary locally - no server, no session.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from ai_stp_cli import runtime_usage
from ai_stp_cli.application import usage_outbox
from ai_stp_cli.provider import usage_reporting
from ai_stp_contracts.runtime_usage import RuntimeUsageEvent, RuntimeUsageIngestResult
from ai_stp_foundation.ids import new_id

DIGEST = "sha256:" + "ab" * 32
INVOKED_AT = "2026-01-01T00:00:00.000Z"


def _event_kwargs(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "organization_id": new_id("organization"),
        "employee_id": new_id("account"),
        "device_id": new_id("device"),
        "project_id": new_id("remote_project"),
        "harness": "claude-code",
        "setup_stable_id": "setup_billing",
        "setup_version": "1.2",
        "setup_passport_digest": DIGEST,
        "component_kind": "skill",
        "component_stable_id": "skill_review",
        "component_version": "3.1",
        "component_passport_digest": DIGEST,
        "invoked_at": INVOKED_AT,
        "outcome": "succeeded",
    }
    values.update(overrides)
    return values


def _outbox(tmp_path: Path) -> sqlite3.Connection:
    return usage_outbox.connect(tmp_path / "outbox.sqlite3")


class TestClosedContract:
    def test_event_round_trips_the_closed_field_set(self) -> None:
        event = runtime_usage.build_event(**_event_kwargs())
        payload = runtime_usage.event_payload(event)
        assert tuple(payload) == runtime_usage.EVENT_FIELDS
        assert payload["setup"] == {
            "stable_id": "setup_billing",
            "version": "1.2",
            "passport_digest": DIGEST,
        }
        component = cast("dict[str, Any]", payload["component"])
        assert component["kind"] == "skill"
        assert payload["outcome"] == "succeeded"

    def test_direct_component_has_no_setup_coordinate(self) -> None:
        event = runtime_usage.build_event(
            **_event_kwargs(
                setup_stable_id=None,
                setup_version=None,
                setup_passport_digest=None,
            )
        )
        assert runtime_usage.event_payload(event)["setup"] is None
        with pytest.raises(ValueError, match="complete or absent"):
            runtime_usage.build_event(**_event_kwargs(setup_version=None))

    def test_extra_field_is_refused(self) -> None:
        payload = runtime_usage.event_payload(runtime_usage.build_event(**_event_kwargs()))
        with pytest.raises(ValidationError):
            RuntimeUsageEvent.model_validate({**payload, "prompt": "secret text"})

    def test_forbidden_names_have_no_field(self) -> None:
        fields = set(RuntimeUsageEvent.model_fields)
        assert runtime_usage.FORBIDDEN_FIELDS.isdisjoint(fields)

    def test_unknown_outcome_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            runtime_usage.build_event(**_event_kwargs(outcome="exploded"))

    def test_unknown_component_kind_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            runtime_usage.build_event(**_event_kwargs(component_kind="database"))

    def test_malformed_digest_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            runtime_usage.build_event(**_event_kwargs(component_passport_digest="not-a-digest"))

    def test_event_id_pattern_is_enforced(self) -> None:
        with pytest.raises(ValidationError):
            runtime_usage.build_event(**_event_kwargs(event_id="has spaces"))
        with pytest.raises(ValidationError):
            runtime_usage.build_event(**_event_kwargs(event_id="short"))

    def test_payload_guard_refuses_a_widened_model(self) -> None:
        class Widened(RuntimeUsageEvent):
            arguments: str = ""

        widened = Widened(
            **json.loads(runtime_usage.build_event(**_event_kwargs()).model_dump_json())
        )
        with pytest.raises(ValueError, match="closed set"):
            runtime_usage.event_payload(widened)


class TestOutbox:
    def test_native_confirmation_promotes_fallback_during_delivery(self, tmp_path: Path) -> None:
        connection = _outbox(tmp_path)
        kwargs = _event_kwargs(event_id="usage_event_promoted")
        fallback = runtime_usage.event_payload(
            runtime_usage.build_event(**kwargs, source="agent_reported")
        )
        native = runtime_usage.event_payload(
            runtime_usage.build_event(**kwargs, source="native_hook")
        )
        usage_outbox.enqueue(connection, "usage_event_promoted", fallback)
        delivered: list[str] = []

        def send(batch: list[dict[str, object]]) -> RuntimeUsageIngestResult:
            delivered.append(str(batch[0]["source"]))
            if len(delivered) == 1:
                assert (
                    usage_outbox.enqueue(connection, "usage_event_promoted", native) == "duplicate"
                )
            return RuntimeUsageIngestResult(
                accepted=1, duplicates=0, rejected=0, accepted_ids=["usage_event_promoted"]
            )

        assert usage_outbox.flush(connection, send) == (1, 0)
        assert delivered == ["agent_reported", "native_hook"]

    def test_reused_event_id_cannot_change_component(self, tmp_path: Path) -> None:
        connection = _outbox(tmp_path)
        kwargs = _event_kwargs(event_id="usage_event_collision")
        assert usage_reporting.record_invocation(**kwargs, outbox=connection) == "queued"
        kwargs["component_stable_id"] = "skill_other"
        assert usage_reporting.record_invocation(**kwargs, outbox=connection) == "dropped"
        assert usage_outbox.due(connection)[0][1]["component"] == {
            "kind": "skill",
            "stable_id": "skill_review",
            "version": "3.1",
            "passport_digest": DIGEST,
        }

    def test_scoped_paths_separate_accounts_and_organizations(self) -> None:
        first = usage_outbox.scoped_path("account_1", "organization_1")
        assert first != usage_outbox.scoped_path("account_2", "organization_1")
        assert first != usage_outbox.scoped_path("account_1", "organization_2")

    def test_enqueue_then_duplicate_is_a_noop(self, tmp_path: Path) -> None:
        connection = _outbox(tmp_path)
        payload = {"event_id": "evt_one", "outcome": "succeeded"}
        assert usage_outbox.enqueue(connection, "evt_one", payload) == "queued"
        assert usage_outbox.enqueue(connection, "evt_one", payload) == "duplicate"
        assert usage_outbox.stats(connection)["pending"] == 1

    def test_full_outbox_refuses_new_events(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(usage_outbox, "MAX_ROWS", 2)
        connection = _outbox(tmp_path)
        assert usage_outbox.enqueue(connection, "a", {}) == "queued"
        assert usage_outbox.enqueue(connection, "b", {}) == "queued"
        assert usage_outbox.enqueue(connection, "c", {}) == "full"
        # A duplicate id is still a no-op even when the queue is full.
        assert usage_outbox.enqueue(connection, "a", {}) == "duplicate"

    def test_failed_send_backs_off_then_dead(self, tmp_path: Path) -> None:
        connection = _outbox(tmp_path)
        usage_outbox.enqueue(connection, "evt", {"x": 1}, now=100.0)
        for attempt in range(usage_outbox.MAX_ATTEMPTS):
            usage_outbox.mark_failed(connection, "evt", error="boom", now=200.0 + attempt)
        assert usage_outbox.stats(connection)["dead"] == 1
        assert usage_outbox.due(connection, now=10**10) == []

    def test_backoff_delays_redelivery(self, tmp_path: Path) -> None:
        connection = _outbox(tmp_path)
        usage_outbox.enqueue(connection, "evt", {"x": 1}, now=0.0)
        usage_outbox.mark_failed(connection, "evt", error="boom", now=0.0)
        # Backoff schedules the next attempt 60s out; the event resurfaces
        # after it elapses but well inside MAX_AGE_SECONDS.
        assert usage_outbox.due(connection, now=1.0) == []
        assert [event_id for event_id, _ in usage_outbox.due(connection, now=61.0)] == ["evt"]

    def test_expired_events_become_dead(self, tmp_path: Path) -> None:
        connection = _outbox(tmp_path)
        usage_outbox.enqueue(connection, "old", {"x": 1}, now=0.0)
        usage_outbox.enqueue(connection, "new", {"x": 1}, now=10**8)
        assert usage_outbox.expire(connection, now=10**8) == 1
        assert [event_id for event_id, _ in usage_outbox.due(connection, now=10**8)] == ["new"]

    def test_flush_sends_due_events_and_clears_them(self, tmp_path: Path) -> None:
        connection = _outbox(tmp_path)
        for index in range(3):
            usage_outbox.enqueue(connection, f"event_{index:04d}", {"n": index}, now=0.0)
        sent_batches: list[list[dict[str, object]]] = []

        def send(batch: list[dict[str, object]]) -> RuntimeUsageIngestResult:
            sent_batches.append(batch)
            return RuntimeUsageIngestResult(
                accepted=3,
                duplicates=0,
                rejected=0,
                accepted_ids=[f"event_{index:04d}" for index in range(3)],
            )

        sent, remaining = usage_outbox.flush(connection, send, now=1.0)
        assert (sent, remaining) == (3, 0)
        assert len(sent_batches) == 1 and len(sent_batches[0]) == 3

    def test_flush_keeps_rejected_events(self, tmp_path: Path) -> None:
        connection = _outbox(tmp_path)
        for event_id in ("accepted_1", "rejected_1"):
            usage_outbox.enqueue(connection, event_id, {"event_id": event_id}, now=0.0)

        def send(_batch: list[dict[str, object]]) -> RuntimeUsageIngestResult:
            return RuntimeUsageIngestResult(
                accepted=1,
                duplicates=0,
                rejected=1,
                accepted_ids=["accepted_1"],
                rejected_ids=["rejected_1"],
            )

        assert usage_outbox.flush(connection, send, now=1.0) == (1, 1)
        assert connection.execute("SELECT event_id FROM usage_outbox").fetchall() == [
            ("rejected_1",)
        ]

    def test_flush_keeps_events_without_a_matching_receipt(self, tmp_path: Path) -> None:
        connection = _outbox(tmp_path)
        usage_outbox.enqueue(connection, "event_0001", {"event_id": "event_0001"}, now=0.0)

        def send(_batch: list[dict[str, object]]) -> RuntimeUsageIngestResult:
            return RuntimeUsageIngestResult(accepted=1, duplicates=0, rejected=0)

        assert usage_outbox.flush(connection, send, now=1.0) == (0, 1)
        assert connection.execute("SELECT attempts FROM usage_outbox").fetchone() == (1,)

    def test_flush_failure_marks_batch_failed_once(self, tmp_path: Path) -> None:
        connection = _outbox(tmp_path)
        usage_outbox.enqueue(connection, "evt", {"x": 1}, now=0.0)

        def fail(_batch: list[dict[str, object]]) -> RuntimeUsageIngestResult:
            raise OSError("offline")

        sent, remaining = usage_outbox.flush(connection, fail, now=0.0)
        assert (sent, remaining) == (0, 1)
        row = connection.execute(
            "SELECT attempts, state FROM usage_outbox WHERE event_id = 'evt'"
        ).fetchone()
        assert row == (1, "pending")


def test_disabled_policy_keeps_pending_events_without_sending(tmp_path: Path) -> None:
    with usage_outbox.connect(tmp_path / "o.sqlite3") as connection:
        usage_outbox.enqueue(connection, "event_0001", {"event_id": "event_0001"})
        usage_outbox.save_policy(connection, enabled=False, required=True)

        def send(_batch: list[dict[str, object]]) -> RuntimeUsageIngestResult:
            raise AssertionError("disabled collection must not send")

        assert usage_outbox.flush(connection, send) == (0, 1)


class TestRecordInvocation:
    def test_cached_policy_disables_collection(self, tmp_path: Path) -> None:
        path = tmp_path / "o.sqlite3"
        with usage_outbox.connect(path) as connection:
            usage_outbox.save_policy(connection, enabled=False, required=True)
            assert usage_outbox.cached_policy(connection) == (False, True)
        assert usage_reporting.record_invocation(**_event_kwargs(), outbox_path=path) == "disabled"
        with usage_outbox.connect(path) as connection:
            assert usage_outbox.stats(connection)["pending"] == 0
            usage_outbox.save_policy(connection, enabled=True, required=False)
        assert usage_reporting.record_invocation(**_event_kwargs(), outbox_path=path) == "queued"

    def test_valid_invocation_is_queued(self, tmp_path: Path) -> None:
        assert (
            usage_reporting.record_invocation(**_event_kwargs(), outbox_path=tmp_path / "o.sqlite3")
            == "queued"
        )
        connection = usage_outbox.connect(tmp_path / "o.sqlite3")
        stored = usage_outbox.due(connection)
        assert len(stored) == 1
        # Only the closed field set was stored - nothing else can be in the row.
        # The outbox serializes with sorted keys, so membership is the check.
        assert frozenset(stored[0][1]) == frozenset(runtime_usage.EVENT_FIELDS)

    def test_bad_outcome_is_dropped_not_raised(self, tmp_path: Path) -> None:
        assert (
            usage_reporting.record_invocation(
                **_event_kwargs(outcome="exploded"), outbox_path=tmp_path / "o.sqlite3"
            )
            == "dropped"
        )
        connection = usage_outbox.connect(tmp_path / "o.sqlite3")
        assert usage_outbox.stats(connection)["pending"] == 0

    def test_same_event_id_is_a_duplicate(self, tmp_path: Path) -> None:
        kwargs = _event_kwargs(event_id="usage_event_repeatable1")
        path = tmp_path / "o.sqlite3"
        assert usage_reporting.record_invocation(**kwargs, outbox_path=path) == "queued"
        assert usage_reporting.record_invocation(**kwargs, outbox_path=path) == "duplicate"


def test_fallback_command_records_load_separately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_stp_cli.cloud.session import Session
    from ai_stp_cli.commands import usage

    account, device = new_id("account"), new_id("device")
    held = Session(account, device, "test-access", "test-refresh", "2030-01-01T00:00:00.000Z")
    monkeypatch.setattr(usage, "_session", Mock(return_value=held))
    path = tmp_path / "outbox.sqlite3"
    monkeypatch.setattr(usage_outbox, "scoped_path", Mock(return_value=path))
    result = usage.record(
        {
            "organization": new_id("organization"),
            "project": new_id("remote_project"),
            "harness": "codex",
            "kind": "instruction",
            "component": "instruction_example",
            "component-version": "1.0",
            "component-digest": DIGEST,
            "invoked-at": INVOKED_AT,
            "outcome": "succeeded",
            "activity-kind": "load",
        }
    )
    assert result.payload.state == "queued"
    with usage_outbox.connect(path) as connection:
        [(event_id, payload)] = usage_outbox.due(connection)
    assert event_id == result.payload.event_id
    assert payload["source"] == "agent_reported"
    assert payload["activity_kind"] == "load"
