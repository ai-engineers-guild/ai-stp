"""The gate split across jobs covers exactly what `just check` covers.

Splitting by required capability (`ADR-0105`) is worth having right up to the
moment one recipe silently falls out of the union. Nothing fails when it does:
the run stays green and the check simply stops running, and the only trace is a
line missing from a log nobody reads.

So the union is checked mechanically. The `just check` dependency tree is
expanded to its leaves, every `just` invocation in the workflow is expanded the
same way, and the first has to be contained in the second.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = ROOT / "justfile"
#: The gate this tree runs. The working copy runs none of its own any more, so
#: the file it holds is the one it publishes; the built tree holds that same
#: file as its actual gate.
_OVERLAY = ROOT / "release_scripts/public_overlay/.github/workflows/check.yml"
WORKFLOW = _OVERLAY if _OVERLAY.is_file() else ROOT / ".github/workflows/check.yml"

#: `name: dep dep` at the start of a line. No recipe in the `check` tree takes
#: parameters, so everything to the right of the colon is a dependency list.
_RECIPE = re.compile(r"^([a-z][a-z0-9-]*):(?:\s+([a-z0-9\- ]*))?$", re.MULTILINE)


def _dependencies() -> dict[str, tuple[str, ...]]:
    text = JUSTFILE.read_text(encoding="utf-8")
    found: dict[str, tuple[str, ...]] = {}
    for match in _RECIPE.finditer(text):
        name = match.group(1)
        deps = tuple((match.group(2) or "").split())
        found[name] = deps
    return found


def _leaves(recipe: str, graph: dict[str, tuple[str, ...]], seen: set[str]) -> set[str]:
    if recipe in seen:
        return set()
    seen.add(recipe)
    deps = graph.get(recipe, ())
    if not deps:
        return {recipe}
    covered: set[str] = set()
    for dep in deps:
        covered |= _leaves(dep, graph, seen)
    return covered


def _expand(recipes: list[str]) -> set[str]:
    graph = _dependencies()
    covered: set[str] = set()
    for recipe in recipes:
        covered |= _leaves(recipe, graph, set())
    return covered


def _recipes_in(path: Path) -> list[str]:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    invoked: list[str] = []
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            script = step.get("run")
            if not isinstance(script, str):
                continue
            for line in script.splitlines():
                stripped = line.strip()
                if not stripped.startswith("just "):
                    continue
                invoked.extend(stripped.removeprefix("just ").split())
    return invoked


def _invoked_in_ci() -> set[str]:
    return _expand(_recipes_in(WORKFLOW))


def test_the_split_jobs_cover_every_recipe_the_gate_runs() -> None:
    """No check disappears when the gate is split, across jobs or across trees.

    Splitting is worth having right up to the moment a recipe falls out of the
    union, and nothing fails when it does: the run stays green and the check
    simply stops running. Since `ADR-0110` the split is across two workflows as
    well as across jobs, so the union is taken over both — the one that runs
    here and the one this copy publishes. Dropping a recipe from either is
    allowed; dropping it from both is what this refuses.
    """
    required = _expand(["check"])
    assert required, "the `check` recipe resolved to nothing; the parser is wrong"
    missing = required - _invoked_in_ci()
    assert not missing, f"no gate runs these parts of `just check`: {sorted(missing)}"


def test_the_parser_sees_the_shape_it_claims_to_see() -> None:
    """A gate nobody has watched fail is a gate of unknown shape."""
    graph = _dependencies()
    assert graph["check"] == ("docs-check", "back-check", "web-check", "security")
    assert "back-test" in _expand(["back-check"])
    assert _expand(["security"]) == {"security"}


def test_setup_is_split_and_each_job_prepares_only_its_own_part() -> None:
    """`just setup` stays whole locally while CI prepares one part per job."""
    graph = _dependencies()
    assert graph["setup"] == ("setup-python", "setup-docs", "setup-web")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    # A job running the full preparation would bring back the Node and bun
    # minutes exactly where only Python is needed.
    assert "run: just setup\n" not in workflow
