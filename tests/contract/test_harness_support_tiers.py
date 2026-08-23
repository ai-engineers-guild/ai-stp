"""The declared support tier has exactly one owner (SPEC-033 REQ-3315)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from ai_stp_cli.local import harness_catalog
from ai_stp_foundation.harnesses import (
    HARNESS_IDS,
    SUPPORT_TIERS,
    UNDEFINED_HARNESS,
    HarnessId,
)
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


def test_no_prose_names_the_members_of_a_tier() -> None:
    """The duplicate came back in Markdown, where the guard above never looked.

    `test_no_second_tier_table_exists_in_the_tree` scans `**/*.py` — it was
    written when the second table was a Python dict, and it did its job. Four
    documents kept their own copy in prose, and all four had drifted: README,
    `PRODUCT.md`, `docs/product/scope.md` and `SPEC-001` still placed Grok
    Build under beta after `SUPPORT_TIERS` promoted it to `primary`. A reader
    who starts at README — which is most readers — got the wrong answer.

    Written to fail in both directions. The first version of this check only
    read the clause claiming primary support, so restoring the exact defect —
    Grok Build back in the *beta* row — left it green. A guard that cannot
    catch the bug it was written for is worse than none, because it is also
    an argument against looking.
    """
    #: Spellings as the documents write them, not identifiers: prose says
    #: "Grok Build", never "grok-build".
    spelled: dict[str, HarnessId] = {
        "Claude Code": "claude-code",
        "Codex": "codex",
        "Grok Build": "grok-build",
        "OpenCode": "opencode",
        "Pi": "pi",
    }
    labels = ((re.compile(r"Основн\w+ поддержк\w+"), "primary"), (re.compile(r"Бета"), "beta"))
    wrong: list[str] = []
    for path in sorted(ROOT.glob("**/*.md")):
        if set(path.parts) & GENERATED_OR_VENDORED or not path.is_file():
            continue
        # Decision records are excluded because they argue about the *other*
        # axis. `ADR-0034` says the launch setups for Pi, OpenCode and Grok
        # Build "остаются бета-линиями" — that is corpus parity, not the
        # harness product tier, and the two are deliberately separate
        # (`SPEC-033`). Prose cannot be told apart by pattern, and a check that
        # forced ADR-0034 to say `primary` would merge the axes it is the
        # point of `SPEC-033` to keep apart. What is guarded here is the
        # surface a reader consults for the current split.
        if "adr" in path.parts:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            # A table row separates label from members with `|`; a sentence
            # uses `:` and `;`. Splitting on all three lets one pass read both,
            # and keeps a line that names two tiers from being read as one.
            clauses = [part for part in re.split(r"[|;:]", line) if part.strip()]
            carried: str | None = None
            for clause in clauses:
                here = next((tier for pattern, tier in labels if pattern.search(clause)), None)
                tier = here or carried
                # A clause that is only a label hands its tier to the next one,
                # which is how a table row spells the same thing.
                named = [name for name in spelled if name in clause]
                if tier and named:
                    for name in named:
                        if SUPPORT_TIERS[spelled[name]] != tier:
                            wrong.append(
                                f"{path.relative_to(ROOT)}: {name} under {tier} — "
                                f"the map says {SUPPORT_TIERS[spelled[name]]}\n    {line.strip()}"
                            )
                    carried = None
                else:
                    carried = here
    assert not wrong, "prose disagrees with SUPPORT_TIERS:\n" + "\n".join(sorted(set(wrong)))
