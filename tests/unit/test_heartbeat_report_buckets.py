"""The report counts expected signals at the policy effective for each interval."""

from datetime import UTC, datetime, timedelta

from ai_stp_api.slices.corporate.heartbeat_report import heartbeat_buckets
from ai_stp_platform.heartbeat_models import (
    InstallationHeartbeatEvent,
    InstallationHeartbeatPolicyEvent,
)


def _event(at: datetime, state: str = "active") -> InstallationHeartbeatEvent:
    return InstallationHeartbeatEvent(
        organization_id="org",
        account_id="account",
        device_id="device",
        checked_at=at,
        received_at=at,
        reported_state=state,
        interval_seconds=3600,
        policy_version=1,
    )


def test_history_counts_signals_and_policy_change_without_marking_disabled_as_missing() -> None:
    start = datetime(2026, 9, 25, tzinfo=UTC)
    end = start + timedelta(hours=4)
    policy = InstallationHeartbeatPolicyEvent(
        organization_id="org",
        version=2,
        effective_from=start + timedelta(hours=2),
        enabled=True,
        interval_seconds=7200,
        stale_after_seconds=86400,
    )
    events = [_event(start), _event(start + timedelta(hours=1)), _event(start + timedelta(hours=2))]
    buckets, coverage = heartbeat_buckets(
        events=events,
        policies=[policy],
        start=start,
        end=end,
        default_interval=3600,
        first_seen=start,
    )
    assert sum(bucket.expected for bucket in buckets) == 3
    assert sum(bucket.received for bucket in buckets) == 3
    assert coverage == 100

    disabled = _event(start + timedelta(hours=2), "disabled")
    buckets, _ = heartbeat_buckets(
        events=[_event(start), _event(start + timedelta(hours=1)), disabled],
        policies=[],
        start=start,
        end=end,
        default_interval=3600,
        first_seen=start,
    )
    assert sum(bucket.expected for bucket in buckets) == 2
    assert buckets[-1].state == "not_expected"


def test_history_before_first_stored_signal_is_not_measured() -> None:
    start = datetime(2026, 9, 25, tzinfo=UTC)
    buckets, coverage = heartbeat_buckets(
        events=[],
        policies=[],
        start=start,
        end=start + timedelta(days=1),
        default_interval=3600,
    )
    assert coverage is None
    assert all(bucket.state == "not_expected" for bucket in buckets)
