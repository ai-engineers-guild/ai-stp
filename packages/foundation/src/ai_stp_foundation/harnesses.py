"""Closed identifiers for the seven supported harnesses.

undefined represents an observed unknown harness and cannot identify a managed
object. Extending the supported set changes the versioned contract."""

from typing import Final, Literal, get_args

type HarnessId = Literal[
    "claude-code",
    "codex",
    "pi",
    "opencode",
    "grok-build",
    "cursor",
    "antigravity",
]

#: Derived from ``HarnessId`` rather than restated. A second literal list would
#: agree today and drift the first time the enum changes, and this set is what
#: ``capabilities`` publishes to every agent.
HARNESS_IDS: Final[frozenset[HarnessId]] = frozenset(get_args(HarnessId.__value__))

#: The same set in declaration order, for the places that need a stable sequence
#: — option choices, generated tables and documentation. Restating either of
#: these as a literal is how a second copy of the set gets written, and a copy
#: agrees with the enum exactly until somebody changes the enum.
HARNESS_ID_ORDER: Final[tuple[HarnessId, ...]] = tuple(get_args(HarnessId.__value__))

UNDEFINED_HARNESS: Final[str] = "undefined"

type SupportTier = Literal["primary", "beta"]

#: Declared product support and observed evidence are independent.
#: Evidence never raises a support tier; an unmeasured run remains not_verified.
#: The shared declaration keeps catalog and CLI projections consistent.
SUPPORT_TIERS: Final[dict[HarnessId, SupportTier]] = {
    "claude-code": "beta",
    "codex": "beta",
    "grok-build": "beta",
    "pi": "beta",
    "opencode": "beta",
    "cursor": "beta",
    "antigravity": "beta",
}


def is_supported_harness(value: str) -> bool:
    """Report whether ``value`` is one of the supported harness IDs."""
    return value in HARNESS_IDS


def support_tier(harness_id: HarnessId) -> SupportTier:
    """Return the declared product support tier of a known harness."""
    return SUPPORT_TIERS[harness_id]
