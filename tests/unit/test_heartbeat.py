# pyright: reportPrivateUsage=false
"""Heartbeat contract, ordering, and health projection (t-heartbeat, #215)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from pydantic import ValidationError

from ai_stp_cli import heartbeat as heartbeat_rules
from ai_stp_cli.application import heartbeat as heartbeat_app
from ai_stp_cli.cloud.session import Session
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.heartbeat import (
    InstallationHeartbeatPolicy,
    InstallationHeartbeatRequest,
    InstallationHeartbeatStatus,
)
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform import heartbeat_service
from ai_stp_platform.heartbeat_models import InstallationHeartbeat as HeartbeatRow

NOW = datetime(2026, 9, 22, 12, 0, 0, tzinfo=UTC)


def _request(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "account_id": new_id("account"),
        "device_id": new_id("device"),
        "cli_version": "1.4.2",
        "capabilities": ["cli.heartbeat", "provider.github@2.1.0"],
        "last_sync_at": "2026-09-22T11:00:00.000Z",
        "health_state": "active",
        "checked_at": format_timestamp(NOW),
    }
    payload.update(overrides)
    return payload


def _session() -> Session:
    return Session(
        account_id=new_id("account"),
        device_id=new_id("device"),
        access_token="opaque",
        refresh_token="opaque-refresh",
        expires_at=format_timestamp(NOW + timedelta(hours=1)),
    )


def _row(**overrides: object) -> SimpleNamespace:
    row = SimpleNamespace(
        organization_id=new_id("organization"),
        account_id=new_id("account"),
        device_id=new_id("device"),
        cli_version="1.4.2",
        capabilities=["cli.heartbeat"],
        last_sync_at=None,
        reported_state="active",
        checked_at=NOW,
        received_at=NOW,
        revision=1,
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def test_request_accepts_the_closed_field_set() -> None:
    request = InstallationHeartbeatRequest.model_validate(_request())
    assert request.health_state == "active"
    assert request.schema_version == 1
    assert (
        InstallationHeartbeatRequest.model_validate(_request(health_state="partial")).health_state
        == "partial"
    )


def test_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        InstallationHeartbeatRequest.model_validate(_request(project_path="C:/repo"))


def test_request_rejects_noncanonical_checked_at() -> None:
    with pytest.raises(ValidationError):
        InstallationHeartbeatRequest.model_validate(_request(checked_at="now"))


def test_request_rejects_reported_states_outside_the_closed_set() -> None:
    with pytest.raises(ValidationError):
        InstallationHeartbeatRequest.model_validate(_request(health_state="stale"))
    with pytest.raises(ValidationError):
        InstallationHeartbeatRequest.model_validate(_request(health_state="unknown"))


def test_capability_token_rejects_paths_and_arguments() -> None:
    for value in ("/home/user/repo", "C:\\work", "token=abc", "a b", "..", ""):
        with pytest.raises(ValueError):
            heartbeat_rules.capability_token(value)


def test_capability_token_accepts_name_and_versioned_forms() -> None:
    assert heartbeat_rules.capability_token("provider.github@2.1.0") == ("provider.github@2.1.0")
    assert heartbeat_rules.capability_token("cli.heartbeat") == "cli.heartbeat"


def test_request_rejects_capability_that_is_not_a_token() -> None:
    with pytest.raises(ValidationError):
        InstallationHeartbeatRequest.model_validate(_request(capabilities=["C:/Users/name/.ssh"]))


def test_request_rejects_cli_version_with_whitespace_or_path() -> None:
    with pytest.raises(ValidationError):
        InstallationHeartbeatRequest.model_validate(_request(cli_version="1.0 /etc"))


def test_evaluate_health_is_deterministic_over_the_closed_state_set() -> None:
    fresh = NOW - timedelta(hours=1)
    old = NOW - timedelta(hours=25)
    threshold = heartbeat_service.DEFAULT_STALE_AFTER
    cases = [
        (("active", fresh), "active"),
        (("active", old), "stale"),
        (("failing", fresh), "failing"),
        (("failing", old), "stale"),
        (("partial", fresh), "partial"),
        (("partial", old), "stale"),
        (("disabled", fresh), "disabled"),
        (("disabled", old), "disabled"),
    ]
    for (reported, received_at), expected in cases:
        assert (
            heartbeat_service.evaluate_health(reported, received_at, now=NOW, stale_after=threshold)
            == expected
        )


def test_health_state_for_missing_row_is_unknown() -> None:
    assert (
        heartbeat_service.health_state_for(None, now=NOW, stale_after=timedelta(hours=1))
        == "unknown"
    )


def test_staleness_threshold_is_injectable() -> None:
    received = NOW - timedelta(minutes=30)
    short = timedelta(minutes=10)
    assert (
        heartbeat_service.evaluate_health("active", received, now=NOW, stale_after=short) == "stale"
    )


def test_policy_rejects_a_retry_cap_below_its_base() -> None:
    with pytest.raises(ValidationError):
        InstallationHeartbeatPolicy(
            organization_id=new_id("organization"),
            retry_base_seconds=120,
            retry_max_seconds=60,
        )


def test_subscription_claim_lease_and_retry_backoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "registry.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE heartbeat_subscription ("
            "organization_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, "
            "device_id TEXT NOT NULL, next_attempt_at TEXT NOT NULL, "
            "attempts INTEGER NOT NULL DEFAULT 0, last_attempt_at TEXT, "
            "last_success_at TEXT, attempt_token TEXT)"
        )
        connection.execute(
            "INSERT INTO heartbeat_subscription "
            "(organization_id, account_id, device_id, next_attempt_at) VALUES (?, ?, ?, ?)",
            (
                "org_due",
                new_id("account"),
                new_id("device"),
                format_timestamp(NOW - timedelta(seconds=1)),
            ),
        )
    monkeypatch.setattr(heartbeat_app, "configured_path", lambda: path)

    claimed = heartbeat_app._claim_due_subscription(NOW)
    assert claimed is not None
    organization_id, _account_id, _device_id, token = claimed
    assert organization_id == "org_due"
    assert heartbeat_app._claim_due_subscription(NOW) is None

    heartbeat_app._finish_attempt(
        organization_id,
        token,
        now=NOW,
        retry_base_seconds=60,
        retry_max_seconds=90,
    )
    with sqlite3.connect(path) as connection:
        attempts, next_attempt, token = connection.execute(
            "SELECT attempts, next_attempt_at, attempt_token FROM heartbeat_subscription"
        ).fetchone()
    assert attempts == 1
    assert next_attempt == format_timestamp(NOW + timedelta(seconds=60))
    assert token is None
    assert heartbeat_app._claim_due_subscription(NOW + timedelta(seconds=59)) is None

    claimed = heartbeat_app._claim_due_subscription(NOW + timedelta(seconds=60))
    assert claimed is not None
    heartbeat_app._finish_attempt(
        claimed[0],
        claimed[3],
        now=NOW + timedelta(seconds=60),
        retry_base_seconds=60,
        retry_max_seconds=90,
    )
    with sqlite3.connect(path) as connection:
        attempts, next_attempt = connection.execute(
            "SELECT attempts, next_attempt_at FROM heartbeat_subscription"
        ).fetchone()
    assert attempts == 2
    assert next_attempt == format_timestamp(NOW + timedelta(seconds=150))


def test_local_subscription_is_explicit_idempotent_and_device_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "registry.sqlite"
    organization_id = new_id("organization")
    account_id = new_id("account")
    device_id = new_id("device")
    monkeypatch.setattr(heartbeat_app, "configured_path", lambda: path)

    enabled = heartbeat_app.enable_subscription(
        organization_id, account_id=account_id, device_id=device_id, now=NOW
    )
    repeated = heartbeat_app.enable_subscription(
        organization_id,
        account_id=account_id,
        device_id=device_id,
        now=NOW + timedelta(hours=1),
    )
    assert enabled.enabled and repeated.enabled
    assert repeated.next_attempt_at == format_timestamp(NOW)

    next_account_id = new_id("account")
    next_device_id = new_id("device")
    heartbeat_app.enable_subscription(
        organization_id,
        account_id=next_account_id,
        device_id=next_device_id,
        now=NOW + timedelta(hours=1),
    )
    with sqlite3.connect(path) as connection:
        account_id, device_id, next_attempt = connection.execute(
            "SELECT account_id, device_id, next_attempt_at FROM heartbeat_subscription"
        ).fetchone()
    assert (account_id, device_id) == (next_account_id, next_device_id)
    assert next_attempt == format_timestamp(NOW + timedelta(hours=1))

    disabled = heartbeat_app.disable_subscription(organization_id)
    assert not disabled.enabled


def test_accepts_update_orders_on_checked_at() -> None:
    assert heartbeat_service.accepts_update(None, NOW)
    assert heartbeat_service.accepts_update(NOW, NOW + timedelta(seconds=1))
    assert not heartbeat_service.accepts_update(NOW, NOW)
    assert not heartbeat_service.accepts_update(NOW, NOW - timedelta(hours=1))


def test_build_report_binds_session_identity_and_closed_fields() -> None:
    session = _session()
    report = heartbeat_app.build_report(
        session,
        health_state="active",
        last_sync_at="2026-09-22T11:00:00.000Z",
        clock=lambda: NOW,
    )
    assert report.account_id == session.account_id
    assert report.device_id == session.device_id
    assert report.checked_at == format_timestamp(NOW)
    assert set(type(report).model_fields) == {
        "schema_version",
        "account_id",
        "device_id",
        "cli_version",
        "capabilities",
        "last_sync_at",
        "health_state",
        "checked_at",
    }


def test_build_report_rejects_unknown_state_and_bad_sync_timestamp() -> None:
    session = _session()
    with pytest.raises(CliFailure, match="a supplied value is not valid for this command"):
        heartbeat_app.build_report(session, health_state="broken")
    with pytest.raises(CliFailure, match="a supplied value is not valid for this command"):
        heartbeat_app.build_report(session, last_sync_at="yesterday")


def test_collect_capabilities_rejects_smuggled_content() -> None:
    tokens = heartbeat_app.collect_capabilities(["provider.github@2.1.0"])
    assert "provider.github@2.1.0" in tokens
    assert "cli.heartbeat" in tokens
    with pytest.raises(ValueError):
        heartbeat_app.collect_capabilities(["C:/secrets/id_rsa"])


def test_status_view_reports_unknown_for_a_first_run() -> None:
    view = heartbeat_service.status_view(
        organization_id=new_id("organization"),
        device_id=new_id("device"),
        row=None,
        now=NOW,
        stale_after=timedelta(hours=24),
    )
    assert isinstance(view, InstallationHeartbeatStatus)
    assert view.health_state == "unknown"
    assert view.heartbeat is None


def test_to_view_carries_no_local_paths_or_secrets() -> None:
    view = heartbeat_service.to_view(
        cast(HeartbeatRow, _row()), now=NOW, stale_after=timedelta(hours=24)
    )
    dumped = view.model_dump()
    assert view.health_state == "active"
    for field in ("cli_version", "capabilities"):
        value = dumped[field]
        text = value if isinstance(value, str) else " ".join(value)
        assert "/" not in text and "\\" not in text and " " not in text
