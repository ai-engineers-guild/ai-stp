"""A refusal asserted without naming which refusal is `is_err()` in Python.

An external audit of the provider repository found tests there that asserted
`result.is_err()` and nothing else: the code raised, the test passed, and *why*
it raised was never checked. Applying the same question here found the same
shape — 45 `pytest.raises(CliFailure)` blocks that name no code, no message,
and never read the captured exception.

Tightening five of them exposed one real defect immediately. A case built to
prove that a status binding itself to no operation is refused had omitted
`provider_id`, so it was refused one line earlier at the identity check and
never reached the binding at all. It had been passing for the wrong reason
since it was written, and only naming the expected refusal revealed it.

This is a ratchet rather than an allowlist. An allowlist of the current
offenders would be a place to add the next one; a count can only be lowered.
The number is debt, recorded so it is visible, and every reduction is a test
that now says which refusal it expects.

Not every loose assertion is wrong: a pure function with one failure mode says
everything by its type. The ratchet does not claim the remainder are defects —
it claims nobody may add another without lowering one.
"""

from __future__ import annotations

import ast
from pathlib import Path

#: Measured on 2026-08-28, after naming the refusal in the five that the
#: provider-trust and v3-conformance work had just written. Lower it when you
#: tighten one; it may never be raised.
BUDGET = 40


def _loose(path: Path) -> list[int]:
    """`pytest.raises(CliFailure)` blocks that never say which failure.

    Three earlier versions of this detector were wrong — 552, then 292, then
    45 — and each was wrong by being too broad. The narrowing that mattered
    last is the pattern below, where the assertion sits *after* the block:

        with pytest.raises(CliFailure) as caught:
            ...
        assert caught.value.code == "..."

    Inspecting only the `with` body reports every one of those as loose. So the
    check walks the enclosing function and asks whether the bound name is read
    anywhere after the block ends.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[int] = []
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for node in ast.walk(function):
            if not isinstance(node, ast.With):
                continue
            for item in node.items:
                call = item.context_expr
                if not (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "raises"
                ):
                    continue
                raised = {getattr(arg, "id", getattr(arg, "attr", "")) for arg in call.args}
                if "CliFailure" not in raised:
                    # Only this repository's typed refusal. `pytest.raises(ValueError)`
                    # on a narrow pure function is the type *being* the assertion,
                    # and counting those is what produced the 552.
                    continue
                if any(keyword.arg == "match" for keyword in call.keywords):
                    continue
                bound = getattr(item.optional_vars, "id", None)
                end = node.end_lineno or node.lineno
                if bound and any(
                    isinstance(name, ast.Name)
                    and name.id == bound
                    and getattr(name, "lineno", 0) > end
                    for name in ast.walk(function)
                ):
                    continue
                found.append(node.lineno)
    return found


def test_no_new_refusal_is_asserted_without_naming_it() -> None:
    sites = sorted(
        f"{path}:{line}" for path in Path("tests").rglob("*.py") for line in _loose(path)
    )
    assert len(sites) <= BUDGET, (
        f"{len(sites)} refusals assert only that something raised, budget {BUDGET}. "
        f"Name the code with `match=` or read `caught.value.code`:\n" + "\n".join(sites)
    )


def test_the_budget_tracks_the_measurement_rather_than_trailing_it() -> None:
    """A budget left above the real count is a slot for a silent addition."""
    actual = sum(len(_loose(path)) for path in Path("tests").rglob("*.py"))
    assert actual == BUDGET, f"{actual} loose refusals; set BUDGET to {actual}"
