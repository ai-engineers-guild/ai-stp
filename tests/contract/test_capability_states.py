"""Native support and projection support are two facts, and every gap is named.

`#462`: `unsupported` was one word for three different situations — the harness
has no such surface, the harness has one at a scope no provider owns, and the
harness has one this compiler does not route yet. An agent reading the output
cannot tell them apart, and the difference decides whether waiting helps.

Two sources describe the same 56 cells and neither is the other's copy.
`harness_catalog.DEFINITIONS` records what each product natively reads, cited to
a vendor page or to the product's own bytes. `composition.PROVIDER_RULES`
records what this compiler will hand a provider. They answer different
questions, and this module holds them side by side so a disagreement is a
reviewed line rather than a discovery during an install.

The reasons below are not commentary. Each one is why a cell is not `supported`,
and a cell that becomes unexplained fails here rather than reaching a user as a
refusal with no cause.
"""

from __future__ import annotations

from typing import Final

import pytest

from ai_stp_cli.local import capability_reasons, composition, harness_catalog
from ai_stp_foundation.harnesses import HARNESS_ID_ORDER

pytestmark = pytest.mark.cli

COMPONENT_KINDS: Final[tuple[str, ...]] = (
    "instruction",
    "skill",
    "mcp",
    "hook",
    "command",
    "agent",
    "plugin",
    "setting",
)

#: The scopes a provider owns and may therefore project into. `project` is not
#: one: a project-scoped layout lives in somebody's repository, which discovery
#: may read and no provider writes. Calling such a cell `unsupported` says the
#: product cannot do it, which is false.
PROVIDER_OWNED_SCOPES: Final[frozenset[str]] = frozenset({"global", "user_root"})

# The reasons live in the product, because `#462` asks for a machine-readable
# one and a table only this test can read is not that. Imported rather than
# restated: a second copy agrees until somebody edits one.
PROJECTION_MISSING = capability_reasons.PROJECTION_MISSING
ROUTED_WITHOUT_A_CATALOGUE_ROW = capability_reasons.ROUTED_WITHOUT_A_CATALOGUE_ROW
PROJECT_SCOPE_ONLY = capability_reasons.PROJECT_SCOPE_ONLY


def _state(harness_id: str, kind: str) -> str:
    definition = harness_catalog.BY_ID[harness_id]
    scopes = {layout.scope for layout in definition.layouts if layout.component_type == kind}
    native_owned = bool(scopes & PROVIDER_OWNED_SCOPES)
    routed = any(
        rule.harness_id == harness_id and rule.component_type == kind
        for rule in composition.PROVIDER_RULES
    )
    if native_owned and routed:
        return "supported"
    if native_owned:
        return "projection_missing"
    if routed:
        return "routed_only"
    return "project_only" if scopes else "unsupported"


def test_every_cell_is_supported_or_named() -> None:
    """56 cells, and each one is either working or explained.

    The count is asserted rather than left to a loop that might examine nothing:
    a filter selecting no cells passes every assertion inside it.
    """
    examined = 0
    unexplained: list[str] = []
    for harness_id in HARNESS_ID_ORDER:
        for kind in COMPONENT_KINDS:
            examined += 1
            state = _state(harness_id, kind)
            key = (harness_id, kind)
            if state == "supported" or state == "unsupported":
                continue
            table = {
                "projection_missing": PROJECTION_MISSING,
                "routed_only": ROUTED_WITHOUT_A_CATALOGUE_ROW,
                "project_only": PROJECT_SCOPE_ONLY,
            }[state]
            if key not in table:
                unexplained.append(f"{harness_id}/{kind} is {state} and nothing says why")

    assert examined == len(HARNESS_ID_ORDER) * len(COMPONENT_KINDS) == 56
    assert not unexplained, unexplained


def test_no_reason_outlives_the_cell_it_explains() -> None:
    """The other direction, so a fixed gap does not keep its excuse.

    A reason that no longer applies is worse than none: it answers a question
    nobody is asking any more, and the next reader takes it for current.
    """
    stale: list[str] = []
    for state, table in (
        ("projection_missing", PROJECTION_MISSING),
        ("routed_only", ROUTED_WITHOUT_A_CATALOGUE_ROW),
        ("project_only", PROJECT_SCOPE_ONLY),
    ):
        for harness_id, kind in table:
            actual = _state(harness_id, kind)
            if actual != state:
                stale.append(f"{harness_id}/{kind} is now {actual}, not {state}")
    assert not stale, stale


def test_the_missing_projections_are_derived_and_each_belongs_to_an_issue() -> None:
    """`#456`'s scope derived from the tables rather than restated from its title.

    The set is empty now. It is still derived rather than deleted, because the
    property this holds is not "three cells are missing" but "every missing cell
    is explained" — and that survives the work landing.

    Two claims, kept apart because they answer to different work. The `mcp`
    cells are `#456` — codex, grok-build and opencode — and that set is not
    written here: it is what the two sources disagree about, and it changes when
    the work lands.

    The whole set is larger, and the fourth member is why this test is phrased
    this way. `codex/agent` joined on 2026-08-30, when a standalone
    `<name>.toml` under the configuration home turned out to be a role at the
    pinned `0.151.0` binary. An assertion naming exactly three would have failed
    on a correct new measurement and read as a regression.
    """
    missing = {
        (harness_id, kind)
        for harness_id in HARNESS_ID_ORDER
        for kind in COMPONENT_KINDS
        if _state(harness_id, kind) == "projection_missing"
    }
    # Empty since 2026-08-31, and empty is the point rather than an omission.
    # `#456` was exactly these three, and `ADR-0129` closed them: the landing is
    # a key inside a file the provider owns, so the component compiles into a
    # contribution to that file instead of asking for a surface that does not
    # exist. A cell reappearing here is a regression or a new harness, and
    # either way it must be explained before it passes.
    assert {pair for pair in missing if pair[1] == "mcp"} == set()
    # Every one of them is explained, which the first test also asserts; here it
    # is the set itself that must not grow silently.
    assert missing == set(PROJECTION_MISSING), missing
