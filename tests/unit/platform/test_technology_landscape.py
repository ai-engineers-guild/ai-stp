"""Calendar-month, unknown and explicit-override landscape oracle."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from ai_stp_platform.technology_landscape import project_activity


def test_calendar_cutoff_unknown_and_overrides() -> None:
    now = datetime(2026, 11, 30, 12, tzinfo=UTC)
    cutoff = datetime(2026, 2, 28, 12, tzinfo=UTC)
    assert project_activity(cutoff, now=now) == "active"
    assert project_activity(cutoff - timedelta(microseconds=1), now=now) == "inactive"
    assert project_activity(None, now=now) == "unknown"
    assert project_activity(None, now=now, override="inactive") == "inactive"
    assert project_activity(cutoff - timedelta(days=1), now=now, override="active") == "active"
    assert project_activity(cutoff, now=now, inactivity_months=1) == "inactive"
    assert project_activity(cutoff.astimezone(timezone(timedelta(hours=3))), now=now) == "active"
    leap_now = datetime(2024, 3, 31, tzinfo=UTC)
    assert (
        project_activity(datetime(2024, 2, 29, tzinfo=UTC), now=leap_now, inactivity_months=1)
        == "active"
    )
    for months in (0, 121):
        with pytest.raises(ValueError, match="inactivity months"):
            project_activity(None, now=now, inactivity_months=months)
    with pytest.raises(ValueError, match="timezone aware"):
        project_activity(None, now=now.replace(tzinfo=None))
