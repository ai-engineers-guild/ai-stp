"""Canonical timestamps: UTC milliseconds, real calendar validation."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from ai_stp_foundation.timestamps import (
    TimestampError,
    format_timestamp,
    is_valid_timestamp,
    parse_timestamp,
)


def test_format_and_parse_round_trip() -> None:
    moment = datetime(2026, 8, 5, 12, 30, 45, 123000, tzinfo=UTC)
    wire = format_timestamp(moment)
    assert wire == "2026-08-05T12:30:45.123Z"
    assert parse_timestamp(wire) == moment


def test_naive_and_offset_datetimes_are_rejected() -> None:
    with pytest.raises(TimestampError):
        format_timestamp(datetime(2026, 8, 5, 12, 0, 0))
    with pytest.raises(TimestampError):
        format_timestamp(datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone(timedelta(hours=5))))


@pytest.mark.parametrize(
    "bad",
    [
        "2026-08-05T12:30:45Z",
        "2026-08-05T12:30:45.1234Z",
        "2026-08-05 12:30:45.123Z",
        "2026-08-05T12:30:45.123+00:00",
        "2026-13-05T12:30:45.123Z",
        "2026-02-30T12:30:45.123Z",
        "",
    ],
)
def test_non_canonical_forms_are_rejected(bad: str) -> None:
    assert not is_valid_timestamp(bad)


def test_valid_form_is_accepted() -> None:
    assert is_valid_timestamp("2026-01-31T23:59:59.999Z")
