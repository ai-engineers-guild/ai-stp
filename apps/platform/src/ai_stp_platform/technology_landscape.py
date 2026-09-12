"""Deterministic landscape activity policy (SPEC-080 REQ-8010)."""

from calendar import monthrange
from datetime import UTC, datetime
from typing import Literal


def project_activity(
    repository_activity_at: datetime | None,
    *,
    now: datetime,
    inactivity_months: int = 9,
    override: Literal["active", "inactive"] | None = None,
) -> Literal["active", "inactive", "unknown"]:
    """Compare calendar months, not a fixed number of thirty-day periods."""
    if not 1 <= inactivity_months <= 120:
        raise ValueError("inactivity months must be between 1 and 120")
    if now.tzinfo is None or (
        repository_activity_at is not None and repository_activity_at.tzinfo is None
    ):
        raise ValueError("activity timestamps must be timezone aware")
    if override is not None:
        return override
    if repository_activity_at is None:
        return "unknown"
    current = now.astimezone(UTC)
    month_number = current.year * 12 + current.month - 1 - inactivity_months
    year, month_index = divmod(month_number, 12)
    month = month_index + 1
    cutoff = current.replace(
        year=year, month=month, day=min(current.day, monthrange(year, month)[1])
    )
    return "inactive" if repository_activity_at.astimezone(UTC) < cutoff else "active"
