"""Content-addressed revision identifiers (ADR-0036, SPEC-015 REQ-1502).

A revision ID is not a logical stable ID: it is derived deterministically from
the canonical revision content in the ``ai-stp:revision:v1`` domain, so equal
revision bytes produce the same ID on every device. The wire form is
``revision_<64 lowercase hex>``. There is no random mint path.
"""

import re
from typing import Final

from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical

REVISION_ID_PATTERN: Final[str] = r"^revision_[0-9a-f]{64}$"

_REVISION_ID_RE: Final[re.Pattern[str]] = re.compile(REVISION_ID_PATTERN)
_DOMAIN: Final[str] = "ai-stp:revision:v1"


def revision_id(payload: JsonValue) -> str:
    """Derive the revision ID from canonical revision content."""
    digest = digest_canonical(_DOMAIN, payload)
    return f"revision_{digest.removeprefix('sha256:')}"


def is_valid_revision_id(value: str) -> bool:
    """Report whether ``value`` has the canonical revision ID form."""
    return _REVISION_ID_RE.fullmatch(value) is not None
