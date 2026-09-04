"""Content-addressed component adaptation identities (ADR-0143)."""

import re
from typing import Final

from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical

ADAPTATION_ID_PATTERN: Final[str] = r"^adaptation_[0-9a-f]{64}$"
_ADAPTATION_ID_RE: Final[re.Pattern[str]] = re.compile(ADAPTATION_ID_PATTERN)
_DOMAIN: Final[str] = "ai-stp:component-adaptation:v1"


def adaptation_id(payload: JsonValue) -> str:
    """Derive one adaptation identity from its complete immutable manifest."""
    digest = digest_canonical(_DOMAIN, payload)
    return f"adaptation_{digest.removeprefix('sha256:')}"


def is_valid_adaptation_id(value: str) -> bool:
    """Report whether a value has the canonical adaptation identity form."""
    return _ADAPTATION_ID_RE.fullmatch(value) is not None
