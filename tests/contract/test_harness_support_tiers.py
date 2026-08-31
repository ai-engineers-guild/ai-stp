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
    "cursor": "beta",
    "antigravity": "beta",
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


#: How each harness is spelled in prose, so a document naming one can be found.
#: It is a map rather than `harness_catalog.BY_ID[...].title` on purpose: the
#: catalog titles are product names for a machine table (`Cursor CLI`,
#: `Antigravity CLI`), and the documents write the harness, not its executable.
#: Derived from `SUPPORT_TIERS` by an assertion below rather than by hand, so a
#: harness added to the enum without a spelling fails here instead of silently
#: leaving every document guard blind to it — which is exactly how `cursor` and
#: `antigravity` stayed unseen while four documents kept naming five.
SPELLED: Final[dict[str, HarnessId]] = {
    "Claude Code": "claude-code",
    "Codex": "codex",
    "Grok Build": "grok-build",
    "OpenCode": "opencode",
    "Pi": "pi",
    "Cursor": "cursor",
    "Antigravity": "antigravity",
}


#: Anchored, so a tier is read only where a cell *is* the label — not wherever
#: the word appears in a sentence inside one. Both languages are supported
#: because user documentation ships in both, and a pattern that knew only one
#: language would read the other page as if it declared one tier instead of two.
TIER_LABELS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (
        re.compile(
            r"^(?:\u041e\u0441\u043d\u043e\u0432\u043d\w+ "
            r"\u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\w+|primary(?: support)?)$",
            re.IGNORECASE,
        ),
        "primary",
    ),
    (
        re.compile(
            r"^(?:\u0411\u0435\u0442\u0430|beta)"
            r"(?:-\u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\w+| support)?$",
            re.IGNORECASE,
        ),
        "beta",
    ),
)


def test_every_harness_has_a_prose_spelling() -> None:
    """The document guards are only as wide as this map, so it must be complete."""
    assert set(SPELLED.values()) == set(SUPPORT_TIERS), (
        "a harness without a prose spelling cannot be found in any document"
    )


#: Directory names a tree walk must step over: dependencies it did not write
#: and output it produced. `public` holds the built public tree, which is a
#: complete copy of the sources — every table in it is the same table, so a
#: walk that counted it would report a duplicate of the file it just read
#: (`ADR-0108`).
GENERATED_OR_VENDORED: Final[frozenset[str]] = frozenset(
    {
        ".venv",
        "node_modules",
        "public",
        ".work",
        ".tmp",
        "dist",
        ".site",
        ".site-user-docs",
    }
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


def test_no_table_states_a_tier_that_disagrees_with_the_map() -> None:
    """The duplicate came back as a table, twice, where the guard never looked.

    `test_no_second_tier_table_exists_in_the_tree` scans `**/*.py` — it was
    written when the second table was a Python dict and it did its job. Four
    documents had already moved their copy to Markdown, and all four had
    drifted: README, `PRODUCT.md`, `docs/product/scope.md` and `SPEC-001` still
    placed Grok Build in beta eight days after `SUPPORT_TIERS` promoted it.

    Scoped to table rows deliberately, after a wider version failed twice in
    opposite directions. Reading only the clause claiming primary support let
    the exact defect back in — Grok Build in the *beta* row — and stayed green.
    Reading every sentence that says "beta" then flagged four correct documents,
    because prose mixes this axis with the evidence one: `release-evidence.md`
    talks about beta *lines of proof*, and `SPEC-001` REQ-109 about which
    evidence blocks a release. Those are different questions with the same
    words, and `SPEC-033` keeps them apart on purpose.

    A table row does not have that problem. The label is one cell and the
    members are another, which is why it is the one shape worth asserting on —
    and it is the shape that broke, both times.
    """
    spelled: dict[str, HarnessId] = dict(SPELLED)
    tiers = TIER_LABELS
    wrong: list[str] = []
    for path in sorted(ROOT.glob("**/*.md")):
        if set(path.parts) & GENERATED_OR_VENDORED or not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.lstrip().startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 2:
                continue
            # Both orientations occur and both have drifted. README and
            # `scope.md` put the tier first and list members after it;
            # `harnesses.md` gives each harness a row and the tier a column.
            # Reading only the first shape left the page whose whole job is
            # stating the tiers uncovered.
            for index, cell in enumerate(cells):
                tier = next((name for pattern, name in tiers if pattern.search(cell)), None)
                if tier is None:
                    continue
                elsewhere = " ".join(cells[:index] + cells[index + 1 :])
                wrong.extend(
                    f"{path.relative_to(ROOT)}: {key} under {tier} — "
                    f"the map says {SUPPORT_TIERS[spelled[key]]}\n    {line.strip()}"
                    for key in spelled
                    if key in elsewhere and SUPPORT_TIERS[spelled[key]] != tier
                )
    assert not wrong, "a support-tier table disagrees with SUPPORT_TIERS:\n" + "\n".join(
        sorted(set(wrong))
    )


def test_a_tier_table_names_every_harness() -> None:
    """The previous guard reads rows it finds; omission leaves no row to read.

    `test_no_table_states_a_tier_that_disagrees_with_the_map` catches a harness
    filed under the wrong label. It cannot catch a harness that is simply
    absent, because absence produces no cell — and absence is what actually
    happened: `SUPPORT_TIERS` grew to seven under `ADR-0120` while README,
    `PRODUCT.md` and `docs/product/scope.md` kept tables of five. All three
    stayed green, and `scope.md` is the document that owns the answer.

    Scoped to files that already state a tier, so this asks for completeness
    only where a claim is being made. A page that never mentions the axis is
    not required to start.

    ADRs are exempt: a decision records the set as it was when it was taken,
    and rewriting `ADR-0033` to name seven would falsify the history that
    `ADR-0120` exists to supersede.
    """
    tiers = tuple(pattern for pattern, _ in TIER_LABELS)
    incomplete: list[str] = []
    for path in sorted(ROOT.glob("**/*.md")):
        if set(path.parts) & GENERATED_OR_VENDORED or not path.is_file():
            continue
        if path.parent.name == "adr":
            continue
        named: set[HarnessId] = set()
        stated = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.lstrip().startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 2:
                continue
            for index, cell in enumerate(cells):
                if not any(pattern.search(cell) for pattern in tiers):
                    continue
                stated = True
                elsewhere = " ".join(cells[:index] + cells[index + 1 :])
                named.update(harness for key, harness in SPELLED.items() if key in elsewhere)
        if stated and named != set(SUPPORT_TIERS):
            missing = ", ".join(sorted(set(SUPPORT_TIERS) - named))
            incomplete.append(f"{path.relative_to(ROOT)}: table omits {missing}")
    assert not incomplete, "a support-tier table names fewer harnesses than exist:\n" + "\n".join(
        incomplete
    )
