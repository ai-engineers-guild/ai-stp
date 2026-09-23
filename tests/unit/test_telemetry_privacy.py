"""Telemetry privacy boundary and contract tests (SPEC-089, ADR-0203)."""

from typing import Any, cast

import pytest
from pydantic import ValidationError

from ai_stp_contracts.telemetry_privacy import (
    CorporateTelemetryEventBatchRequest,
    CorporateTelemetryEventRequest,
    CorporateTelemetryHeartbeatEvent,
    CorporateTelemetryInvocationEvent,
    CorporateTelemetryPolicyRequest,
)
from ai_stp_foundation.ids import new_id
from ai_stp_platform.telemetry_privacy_service import (
    TELEMETRY_PERMISSIONS,
    TelemetryBoundaryError,
    event_columns,
    validate_event_fields,
)


def _heartbeat(**overrides: object) -> dict[str, Any]:
    event: dict[str, Any] = {
        "kind": "heartbeat",
        "event_id": "evt-heartbeat-0001",
        "device_id": "dev-001",
        "harness": "codex",
        "harness_version": "0.140.1",
        "provider_name": "codex-cli",
        "provider_version": "0.140.1",
        "capabilities": ["apply", "status"],
        "last_sync_at": "2026-09-21T10:00:00.000Z",
        "health": "active",
        "occurred_at": "2026-09-21T10:00:01.000Z",
    }
    event.update(overrides)
    return event


def _invocation(**overrides: object) -> dict[str, Any]:
    event: dict[str, Any] = {
        "kind": "invocation",
        "event_id": "evt-invocation-0001",
        "account_id": new_id("account"),
        "device_id": "dev-001",
        "project_id": "proj-001",
        "harness": "claude",
        "setup_id": "setup-001",
        "component_kind": "skill",
        "component_stable_id": "component-001",
        "component_version": "1.0",
        "outcome": "succeeded",
        "occurred_at": "2026-09-21T10:00:01.000Z",
    }
    event.update(overrides)
    return event


def test_heartbeat_contract_accepts_closed_field_set() -> None:
    event = CorporateTelemetryHeartbeatEvent(**_heartbeat())
    assert event.kind == "heartbeat"
    assert event.health == "active"


def test_heartbeat_contract_rejects_forbidden_fields() -> None:
    for forbidden in (
        {"prompt": "fix this"},
        {"repository": "org/private"},
        {"email": "dev@example.com"},
        {"target_path": "C:\\Users\\dev"},
        {"environment": {"TOKEN": "abc"}},
    ):
        with pytest.raises(ValidationError):
            CorporateTelemetryHeartbeatEvent(**_heartbeat(**forbidden))


def test_invocation_contract_has_no_content_fields() -> None:
    event = CorporateTelemetryInvocationEvent(**_invocation())
    assert event.outcome == "succeeded"
    with pytest.raises(ValidationError):
        CorporateTelemetryInvocationEvent(**_invocation(output="secret output"))


def test_ingest_request_discriminates_on_kind() -> None:
    request = CorporateTelemetryEventRequest(
        event=cast(Any, _heartbeat()),
        authorization_revision=1,
        idempotency_key="telemetry-ingest-0001",
    )
    assert request.event.kind == "heartbeat"
    with pytest.raises(ValidationError):
        CorporateTelemetryEventRequest(
            event=cast(Any, {"event_id": "evt-x", "occurred_at": "2026-09-21T10:00:00.000Z"}),
            authorization_revision=1,
            idempotency_key="telemetry-ingest-0002",
        )


def test_boundary_accepts_complete_legal_heartbeat() -> None:
    validate_event_fields("heartbeat", _heartbeat())


def test_boundary_rejects_unknown_kind_and_keys() -> None:
    with pytest.raises(TelemetryBoundaryError):
        validate_event_fields("runtime", _heartbeat())
    with pytest.raises(TelemetryBoundaryError):
        validate_event_fields("heartbeat", _heartbeat(debug_flag=True))


def test_boundary_rejects_nested_forbidden_names() -> None:
    with pytest.raises(TelemetryBoundaryError):
        validate_event_fields("invocation", _invocation(component_stable_id={"prompt": "hi"}))


def test_boundary_rejects_absolute_paths_and_env_values() -> None:
    with pytest.raises(TelemetryBoundaryError):
        validate_event_fields("heartbeat", _heartbeat(harness="C:\\tools\\harness"))
    with pytest.raises(TelemetryBoundaryError):
        validate_event_fields("heartbeat", _heartbeat(harness="/usr/local/bin/x"))
    with pytest.raises(TelemetryBoundaryError):
        validate_event_fields("heartbeat", _heartbeat(capabilities=["apply", "SECRET_KEY=abc123"]))


def test_event_columns_returns_only_allowlisted_keys() -> None:
    fields = _heartbeat()
    columns = event_columns("heartbeat", fields)
    assert set(columns) == set(fields)
    assert "kind" in columns and columns["kind"] == "heartbeat"


def test_policy_request_enforces_retention_bounds() -> None:
    with pytest.raises(ValidationError):
        CorporateTelemetryPolicyRequest(
            raw_retention_days=0,
            legal_basis="legitimate_interest",
            notice_revision=1,
            expected_policy_revision=0,
            authorization_revision=1,
            idempotency_key="telemetry-policy-0001",
        )
    request = CorporateTelemetryPolicyRequest(
        raw_retention_days=30,
        legal_basis="consent",
        notice_revision=2,
        expected_policy_revision=0,
        authorization_revision=1,
        idempotency_key="telemetry-policy-0002",
    )
    assert request.legal_basis == "consent"


def test_batch_request_rejects_repeated_event_ids() -> None:
    with pytest.raises(ValidationError):
        CorporateTelemetryEventBatchRequest(
            events=cast(Any, [_heartbeat(), _heartbeat()]),
            authorization_revision=1,
            idempotency_key="telemetry-batch-0001",
        )
    batch = CorporateTelemetryEventBatchRequest(
        events=cast(Any, [_heartbeat(), _invocation()]),
        authorization_revision=1,
        idempotency_key="telemetry-batch-0002",
    )
    assert len(batch.events) == 2


def test_telemetry_permissions_are_a_closed_named_set() -> None:
    assert (
        frozenset(
            {
                "telemetry.write",
                "telemetry.read",
                "telemetry.list",
                "telemetry.export",
                "telemetry.manage",
                "telemetry.delete",
            }
        )
        == TELEMETRY_PERMISSIONS
    )
    assert all(permission.startswith("telemetry.") for permission in TELEMETRY_PERMISSIONS)
