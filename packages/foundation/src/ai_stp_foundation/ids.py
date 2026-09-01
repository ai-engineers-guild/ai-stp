"""Typed stable identifiers (SPEC-015 REQ-1501).

A stable ID is opaque, path-independent and never reused. The wire form is
``<prefix>_<ULID>`` where the prefix comes from a closed immutable registry
and the suffix is a canonical uppercase 26-character Crockford ULID. Unknown
prefixes and out-of-range suffixes fail closed. Revision IDs are not stable
IDs: they are content-addressed (ADR-0036) and live in ``revisions.py``.
"""

import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from ulid import ULID

ID_PREFIXES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "account": "platform account",
        "acceptance": "legal policy acceptance",
        # A reference to bytes the provider holds (`REQ-814`). Typed and
        # never reused like the rest, and deliberately not part of any
        # setup's identity: deleting a backup must not delete a setup.
        "backup": "provider backup reference",
        "complaint": "public complaint intake",
        "component": "component logical entity",
        "developer": "developer passport",
        "device": "device passport",
        "grant": "major-line access grant",
        "invite": "access grant invitation",
        "operation": "durable mutating operation",
        "plan": "publication plan",
        "prevision": "profile revision",
        "project": "project passport",
        "report": "private report case",
        # Valid only inside one recommendation session (`ADR-0027`). Typed and
        # never reused like the rest, but naming no durable object: a proposal
        # has no entity, no revision and no head, and confirming it is what
        # creates something the registry holds.
        "proposal": "ephemeral composition proposal",
        "request": "machine request",
        "scan": "platform safety scan run",
        "snapshot": "validation snapshot",
        "setup": "setup logical entity",
        "sub": "external provider subject",
        "variant": "native component realization",
    }
)

# 26 Crockford characters encode 130 bits while a ULID is 128 bits: the first
# character carries only three bits and must stay in [0-7]. Anything starting
# with 8-Z overflows the ULID domain and is rejected, not normalized.
_ULID_BODY: Final[str] = r"[0-7][0-9A-HJKMNP-TV-Z]{25}"
_SUFFIX_RE: Final[re.Pattern[str]] = re.compile(rf"^{_ULID_BODY}$")


class StableIdError(ValueError):
    """A value is not a valid typed stable identifier."""


def stable_id_pattern(prefix: str) -> str:
    """Return the anchored wire regex for one registered prefix."""
    if prefix not in ID_PREFIXES:
        raise StableIdError(f"unknown id prefix: {prefix!r}")
    return rf"^{prefix}_{_ULID_BODY}$"


def new_id(prefix: str) -> str:
    """Mint a new stable ID for a known prefix."""
    if prefix not in ID_PREFIXES:
        raise StableIdError(f"unknown id prefix: {prefix!r}")
    return f"{prefix}_{ULID()}"


def parse_id(value: str) -> tuple[str, str]:
    """Split and validate a stable ID; return ``(prefix, suffix)``."""
    prefix, separator, suffix = value.partition("_")
    if not separator:
        raise StableIdError(f"stable id has no prefix separator: {value!r}")
    if prefix not in ID_PREFIXES:
        raise StableIdError(f"unknown id prefix: {prefix!r}")
    if _SUFFIX_RE.fullmatch(suffix) is None:
        raise StableIdError(f"stable id suffix is not a canonical ULID: {value!r}")
    return prefix, suffix


def is_valid_id(value: str, prefix: str | None = None) -> bool:
    """Report whether ``value`` is a valid stable ID, optionally of one prefix."""
    try:
        parsed_prefix, _ = parse_id(value)
    except StableIdError:
        return False
    return prefix is None or parsed_prefix == prefix
