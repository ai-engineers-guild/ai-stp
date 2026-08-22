"""Domain-separated SHA-256 digests (docs/contracts/canonical-data.md).

Every object class hashes in its own domain so equal bytes never produce an
interchangeable identifier across classes: ``sha256(domain || 0x00 || bytes)``.
Unknown domains fail closed.
"""

import hashlib
import re
from typing import Final

from ai_stp_foundation.canonical import JsonValue, canonize

DIGEST_DOMAINS: Final[frozenset[str]] = frozenset(
    {
        "ai-stp:artifact:v1",
        "ai-stp:attestation:v1",
        "ai-stp:bundle:v1",
        "ai-stp:native-discovery:v1",
        "ai-stp:passport:v1",
        "ai-stp:plan:v1",
        "ai-stp:publication-set:v1",
        "ai-stp:provider-plan:v3",
        "ai-stp:provider-projection:v3",
        "ai-stp:project-configuration:v1",
        "ai-stp:project-index:v1",
        "ai-stp:project-toolchain:v1",
        "ai-stp:revision:v1",
        "ai-stp:scaffold-plan:v1",
        "ai-stp:selection-snapshot:v1",
        "ai-stp:setup-eval-plan:v1",
        "ai-stp:setup-eval-result:v1",
        "ai-stp:store-port-plan:v1",
    }
)

DIGEST_PATTERN: Final[str] = r"^sha256:[0-9a-f]{64}$"

_DIGEST_RE: Final[re.Pattern[str]] = re.compile(DIGEST_PATTERN)


class DigestError(ValueError):
    """A digest input or representation is invalid."""


def digest_bytes(domain: str, payload: bytes) -> str:
    """Hash exact bytes inside one domain; return ``sha256:<hex>``."""
    if domain not in DIGEST_DOMAINS:
        raise DigestError(f"unknown digest domain: {domain!r}")
    digest = hashlib.sha256(domain.encode("ascii") + b"\x00" + payload)
    return f"sha256:{digest.hexdigest()}"


def digest_canonical(domain: str, value: JsonValue) -> str:
    """Hash the canonical JSON bytes of ``value`` inside one domain."""
    return digest_bytes(domain, canonize(value))


def is_digest(value: str) -> bool:
    """Report whether ``value`` has the canonical digest form."""
    return _DIGEST_RE.fullmatch(value) is not None
