"""Two-integer ``X.Y`` versions (SPEC-015 REQ-1505, ADR-0004).

A version is stored as a string but compared as two non-negative integers.
Leading zeros are non-canonical and rejected.
"""

import re
from typing import Final

VERSION_PATTERN: Final[str] = r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"

_VERSION_RE: Final[re.Pattern[str]] = re.compile(VERSION_PATTERN)


class VersionError(ValueError):
    """A value is not a canonical two-integer version."""


def parse_version(text: str) -> tuple[int, int]:
    """Parse ``X.Y`` into ``(major, minor)``; reject non-canonical forms."""
    match = _VERSION_RE.fullmatch(text)
    if match is None:
        raise VersionError(f"not a canonical X.Y version: {text!r}")
    return int(match.group(1)), int(match.group(2))


def format_version(major: int, minor: int) -> str:
    """Format two non-negative integers as ``X.Y``."""
    if major < 0 or minor < 0:
        raise VersionError(f"version parts must be non-negative: {major}.{minor}")
    return f"{major}.{minor}"


def compare_versions(left: str, right: str) -> int:
    """Compare two versions numerically; return -1, 0 or 1."""
    parsed_left, parsed_right = parse_version(left), parse_version(right)
    if parsed_left < parsed_right:
        return -1
    if parsed_left > parsed_right:
        return 1
    return 0
