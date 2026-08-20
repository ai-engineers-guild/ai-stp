"""Canonical timestamps (SPEC-015 REQ-1505, docs/contracts/canonical-data.md).

Time is recorded as RFC 3339 UTC with exactly millisecond precision and the
``Z`` suffix. The pattern is shared with generated schemas; full validation
also parses the value so ``2026-13-40...`` cannot slip through the regex.
"""

import re
from datetime import UTC, datetime
from typing import Final

TIMESTAMP_PATTERN: Final[str] = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"

_TIMESTAMP_RE: Final[re.Pattern[str]] = re.compile(TIMESTAMP_PATTERN)
_PARSE_FORMAT: Final[str] = "%Y-%m-%dT%H:%M:%S.%fZ"


class TimestampError(ValueError):
    """A value is not a canonical UTC millisecond timestamp."""


def format_timestamp(moment: datetime) -> str:
    """Format an aware UTC datetime as the canonical wire string."""
    if moment.tzinfo is None or moment.utcoffset() != UTC.utcoffset(None):
        raise TimestampError(f"timestamp must be timezone-aware UTC: {moment!r}")
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def parse_timestamp(value: str) -> datetime:
    """Parse a canonical wire string into an aware UTC datetime."""
    if _TIMESTAMP_RE.fullmatch(value) is None:
        raise TimestampError(f"not a canonical UTC millisecond timestamp: {value!r}")
    try:
        parsed = datetime.strptime(value, _PARSE_FORMAT)
    except ValueError as error:
        raise TimestampError(f"not a real calendar moment: {value!r}") from error
    return parsed.replace(tzinfo=UTC)


def is_valid_timestamp(value: str) -> bool:
    """Report whether ``value`` is a canonical UTC millisecond timestamp."""
    try:
        parse_timestamp(value)
    except TimestampError:
        return False
    return True
