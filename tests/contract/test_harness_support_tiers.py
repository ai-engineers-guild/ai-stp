"""The declared support tier has exactly one owner (SPEC-033 REQ-3315)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from ai_stp_cli.local import harness_catalog
from ai_stp_foundation.harnesses import HARNESS_IDS, SUPPORT_TIERS, UNDEFINED_HARNESS
from ai_stp_platform.catalog_support import support_tier_for_harness

ROOT = Path(__file__).resolve().parents[2]

EXPECTED: dict[str, str] = {
    "claude-code": "primary",
    "codex": "primary",
    "grok-build": "primary",
    "pi": "beta",
    "opencode": "beta",
}


def test_the_declared_tiers_are_exactly_what_the_specification_states() -> None:
    """SPEC-033 REQ-3315 names the split; this is the executable half of it."""
    assert SUPPORT_TIERS == EXPECTED
    assert set(SUPPORT_TIERS) == set(HARNESS_IDS), "every harness has a declared tier"


def test_both_surfaces_answer_from_the_same_owner() -> None:
    """The platform projection and the CLI catalog must never disagree.

    They used to hold one table each. Two copies of a product decision agree
    until the decision changes, and then exactly one of them is updated.
    """
    for harness_id, expected in EXPECTED.items():
        assert support_tier_for_harness(harness_id) == expected
        assert harness_catalog.BY_ID[harness_id].support == expected


def test_shared_conventions_are_portable_rather_than_a_tier() -> None:
    """`undefined` is not a harness, so it has no product tier."""
    assert UNDEFINED_HARNESS not in SUPPORT_TIERS
    assert harness_catalog.BY_ID[UNDEFINED_HARNESS].support == "portable"


#: Directory names a tree walk must step over: dependencies it did not write
#: and output it produced. `public` holds the built public tree, which is a
#: complete copy of the sources — every table in it is the same table, so a
#: walk that counted it would report a duplicate of the file it just read
#: (`ADR-0108`).
GENERATED_OR_VENDORED: Final[frozenset[str]] = frozenset(
    {".venv", "node_modules", "public", "dist", ".site", ".site-user-docs"}
)


def test_no_second_tier_table_exists_in_the_tree() -> None:
    """A guard, not a style rule: the duplicate is what this change removed.

    Without it the second table comes back the next time somebody needs the
    mapping in a hurry, and it will agree on the day it is written.
    """
    owner = ROOT / "packages/foundation/src/ai_stp_foundation/harnesses.py"
    pattern = re.compile(r'"(?:claude-code|codex|grok-build)"\s*:\s*"primary"')
    offenders = [
        path.relative_to(ROOT)
        for path in ROOT.glob("**/*.py")
        if not (set(path.parts) & GENERATED_OR_VENDORED)
        and path != owner
        and path != Path(__file__)
        and pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"a second support-tier table exists: {offenders}"
