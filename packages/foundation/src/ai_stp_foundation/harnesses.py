"""Closed harness identifiers (ADR-0003, ADR-0033, ADR-0120, SPEC-001 REQ-105).

Seven supported harnesses form the complete MVP set; ``undefined`` marks an
observed unknown harness and never appears in managed objects (SPEC-011
REQ-1109). Expanding the enum requires a new ADR and a schema version.
"""

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

#: The declared product support tier of each harness (SPEC-033).
#:
#: This is a product decision, not a claim about evidence. SPEC-033 keeps the
#: two apart on purpose: `REQ-3306` says evidence never raises a tier, and
#: `REQ-3307` says a line without a recorded run is reported honestly as
#: `not_verified` without blocking a release. So a harness is `primary` because
#: it is supported as a first-class target, and whether its end-to-end run has
#: been recorded is answered by support *state*, separately.
#:
#: It lives here, next to `HarnessId`, because it was previously written twice —
#: in the platform catalog projection and in the CLI harness catalog. The copies
#: agreed while nobody changed them, which is the only state in which duplicated
#: facts ever agree.
SUPPORT_TIERS: Final[dict[HarnessId, SupportTier]] = {
    "claude-code": "primary",
    "codex": "primary",
    "grok-build": "primary",
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
