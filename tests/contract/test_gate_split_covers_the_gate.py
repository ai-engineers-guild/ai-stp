"""The gate split across jobs covers exactly what `just check` covers.

Splitting by required capability (`ADR-0105`) is worth having right up to the
moment one check silently falls out of the union. Nothing fails when it does:
the run stays green and the check simply stops running, and the only trace is a
line missing from a log nobody reads.

So the union is checked mechanically. The `just check` dependency tree is
expanded to its leaves, every leaf is mapped to the distinctive commands of its
recipe body, and those commands have to appear in the workflow. The workflow,
in turn, must not invoke `just` at all: the local task runner is a convenience
for the maintainer's machine, not a dependency of the published gate.
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
WORKFLOW_DIR = WORKFLOW.parent

#: `name: dep dep` at the start of a line. No recipe in the `check` tree takes
#: parameters, so everything to the right of the colon is a dependency list.
_RECIPE = re.compile(r"^([a-z][a-z0-9-]*):(?:\s+([a-z0-9\- ]*))?$", re.MULTILINE)

#: One or more distinctive substrings per leaf recipe of `just check`. A leaf
#: is covered by the gate exactly when every token appears in the workflow.
#: The mapping is deliberately explicit: when a recipe body changes its
#: command, updating this table is the review moment where drift is named.
_LEAF_TOKENS: dict[str, tuple[str, ...]] = {
    "docs-static": (
        "docs_scripts/docs_lint.py",
        "docs_scripts/spec_lint.py",
        "docs_scripts/contract_lint.py",
        "docs_scripts/run_markdownlint.py",
        "-m yamllint -c docs_scripts/.yamllint.yml .",
    ),
    "docs-test": ("unittest discover -s docs_scripts/tests",),
    "docs-build": (
        "-m mkdocs build --strict -f docs_scripts/mkdocs.yml",
        "mkdocs build --strict",
        "docs_scripts/user-mkdocs.yml",
    ),
    "docs-regress": ("docs_scripts/mermaid_check.py",),
    "back-static": (
        "ruff format --check",
        "ruff check ",
        "pyright",
        "-m release_scripts.public_export --report",
        "-m ai_stp_contracts.schemas --check schemas/v1",
        "-m ai_stp_contracts.web_projections --check",
        "release_scripts/provider_kit.py --check provider-kit/v3",
        "docs_scripts/skill_projections.py --check",
    ),
    "back-test": ("pytest -n 4 --dist=load", "--fail-under=90", "COVERAGE_CORE: sysmon"),
    "back-resource": ("tests/contract/test_cli_resource_lifecycle.py",),
    "back-build": ("uv build --all-packages",),
    "back-regress": ("clean_install_regress.sh",),
    "security": ("bun run audit",),
    "web-build": ("AI_STP_WEB_PROFILE=public_saas bun run build",),
    "web-storybook": ("build-storybook",),
    "web-i18n": ("bun run i18n:check",),
    "web-static": (
        "bun run lint",
        "bun run format:check",
        "bun run type-check",
    ),
    "web-test": ("bun run test:coverage", "bun run test:coverage:catalog"),
    "web-regress": ("bunx playwright install chromium", "bun run test:e2e"),
    "web-feature-profiles": ("bun run test:feature-profiles",),
}


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


def _workflow_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(WORKFLOW_DIR.glob("*.yml"))
    )


def test_every_recipe_leaf_of_just_check_appears_in_the_gate() -> None:
    """No check disappears when the gate is split, across jobs or across trees.

    Splitting is worth having right up to the moment a check falls out of the
    union, and nothing fails when it does: the run stays green and the check
    simply stops running. Since `ADR-0110` the split is across two trees as
    well as across jobs, so the union is asserted over the whole published
    workflow directory rather than one file.
    """
    required = _expand(["check"])
    assert required, "the `check` recipe resolved to nothing; the parser is wrong"
    unmapped = required - set(_LEAF_TOKENS)
    assert not unmapped, f"a leaf of `just check` has no command tokens mapped: {sorted(unmapped)}"
    gate = _workflow_text()
    missing = [
        (leaf, token)
        for leaf in sorted(required & set(_LEAF_TOKENS))
        for token in _LEAF_TOKENS[leaf]
        if token not in gate
    ]
    assert not missing, f"no gate runs these recipe commands: {missing}"


def test_the_parser_sees_the_shape_it_claims_to_see() -> None:
    """A gate nobody has watched fail is a gate of unknown shape."""
    graph = _dependencies()
    assert graph["check"] == ("docs-check", "back-check", "web-check", "security")
    assert "back-test" in _expand(["back-check"])
    assert _expand(["security"]) == {"security"}


def test_the_published_gate_never_invokes_the_local_task_runner() -> None:
    """`just` stays on the maintainer's machine; CI runs the commands directly.

    A runner installed into the gate is one more downloaded binary per job, and
    it hides the real commands behind an indirection the reader cannot see.
    Every published workflow runs its steps directly.
    """
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            assert not stripped.startswith("just "), f"{path.name}:{number} invokes just"


def test_setup_is_split_and_each_job_prepares_only_its_own_part() -> None:
    """The full preparation stays local while CI prepares one part per job."""
    graph = _dependencies()
    assert graph["setup"] == ("setup-python", "setup-docs", "setup-web")
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # A job running the full preparation would bring back the Node and bun
    # minutes exactly where only Python is needed.
    python_only = {"package", "tests", "coverage"}
    for name, job in workflow["jobs"].items():
        scripts = "\n".join(
            step["run"] for step in job.get("steps", []) if isinstance(step.get("run"), str)
        )
        if name in python_only:
            assert "npm_ci.py" not in scripts, f"{name} installs documentation Node tools"
            assert "bun install" not in scripts, f"{name} installs web dependencies"


def test_cli_and_web_tests_run_on_three_os_and_backend_stays_on_linux() -> None:
    """ADR-0116: client tests see three operating systems; the server does not."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    three = {"ubuntu-latest", "macos-latest", "windows-latest"}
    jobs = workflow["jobs"]
    for name in ("cli", "web-unit", "web-e2e", "web-profiles"):
        assert set(jobs[name]["strategy"]["matrix"]["os"]) == three, name
    assert jobs["tests"]["runs-on"] == "ubuntu-latest"
    shards = [row["shard"] for row in jobs["tests"]["strategy"]["matrix"]["include"]]
    assert shards == [
        "api",
        "integration",
        "unit-platform",
        "unit-api",
        "unit",
        "contract",
        "property",
    ]
    assert jobs["cli"]["strategy"]["matrix"]["suite"] == ["unit", "contract", "process"]
    assert "-n 8" in "\n".join(
        step["run"] for step in jobs["tests"]["steps"] if isinstance(step.get("run"), str)
    )
