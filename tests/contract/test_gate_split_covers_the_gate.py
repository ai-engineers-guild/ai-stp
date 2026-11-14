"""The complete verification tree is covered by pinned workflow command owners.

Use Just's real parser, including imports and parameterized recipes. CI keeps
platforms, services and acceptance evidence; project recipes own execution.
"""

from __future__ import annotations

import json
import re
import subprocess
import tomllib
from functools import cache
from pathlib import Path
from typing import Any, TypedDict, cast

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = ROOT / "justfile"
#: The gate this tree runs and publishes as its own.
WORKFLOW = ROOT / ".github/workflows/source.yml"
WORKFLOW_DIR = WORKFLOW.parent

#: One or more distinctive substrings per leaf recipe of `just verify`. A leaf
#: is covered by the gate exactly when every token appears in the workflow.
#: The mapping is deliberately explicit: when a recipe body changes its
#: command, updating this table is the review moment where drift is named.
_LEAF_TOKENS: dict[str, tuple[str, ...]] = {
    "infra-source": (
        "actionlint",
        "hadolint deploy/docker/Dockerfile.app deploy/docker/Dockerfile.web "
        "deploy/docker/Dockerfile.docs",
        "git ls-files -z -- '*.sh' | xargs -0 shellcheck -x -P SCRIPTDIR -S warning",
    ),
    "docs-static": ("rumdl check --no-cache --deny-config-warnings .",),
    "docs-source": (
        "docs_scripts/docs_lint.py",
        "docs_scripts/contract_lint.py",
        "ryl check --no-cache --strict . .repo-safety",
    ),
    "docs-test": ("unittest discover -s docs_scripts/tests",),
    "docs-build": (
        "-m mkdocs build --strict -f docs_scripts/mkdocs.yml",
        "mkdocs build --strict",
        "docs_scripts/user-mkdocs.yml",
    ),
    "docs-regress": ("docs_scripts/mermaid_check.py",),
    "back-dependencies": ("python -m release_scripts.python_dependencies",),
    "back-static": (
        "ruff format --check",
        "ruff check ",
        "bun run type-check:python",
        "-m ai_stp_contracts.schemas --check schemas/v1",
        "-m ai_stp_contracts.inventory_record --check",
        "-m ai_stp_contracts.web_projections --check",
        "-m ai_stp_contracts.technology_seed --check",
        "release_scripts/provider_kit.py --check provider-kit/v3",
        "release_scripts/first_party_corpus_digests.py --check",
        "release_scripts/safety_requirements.py --check",
        "-m release_scripts.update_component_fixture --check",
        "docs_scripts/skill_projections.py --check",
    ),
    # Not the worker count. `-n` is a tuning decision the gate is allowed to
    # make per leg — server shards use eight — and
    # pinning it here made raising it on the CLI legs look like the gate had
    # stopped running the suite at all. What identifies the leaf is that pytest
    # is distributed and that the coverage report and tracing core are the same.
    "back-test": (
        "pytest -n",
        "--dist=load",
        "coverage report --precision=2",
        "COVERAGE_CORE: sysmon",
    ),
    "back-build": ("uv build --all-packages",),
    "back-regress": ("clean_install_regress.sh",),
    "cli-source": ("cargo fmt --check",),
    "cli-static": (
        "-- resources --check",
        "cargo clippy --locked --all-targets -- -D warnings",
    ),
    "desktop-source": (
        "release_scripts/desktop_version.py --check",
        "release_scripts/desktop_tools.py",
        "scripts/generate-messages.mjs --check",
        "scripts/generate-theme.mjs --check",
        "scripts/generate-fonts.mjs --check",
        "scripts/generate-contracts.mjs --check",
        "bun run type-check",
        "cargo fmt --check",
        "bun run format:check",
        "bun run messages:check",
    ),
    "desktop-ui-build": ("vite build",),
    "desktop-build": ("desktop-stub",),
    "desktop-static": ("cargo clippy --locked --all-targets -- -D warnings",),
    "desktop-ui-test": ("vitest run",),
    "desktop-test": ("cargo nextest run --locked", "cargo test --locked --doc"),
    "desktop-core-test": ("cargo nextest run --locked", "cargo test --locked --doc"),
    "desktop-regress": ("desktop-build", "desktop-probe"),
    "just-fmt": ("just --fmt --check",),
    "cli-test": ("cargo nextest run --locked", "cargo test --locked --doc"),
    "rust-dependencies": (
        "cargo deny --frozen",
        "--manifest-path apps/cli/Cargo.toml check bans sources",
        "--manifest-path apps/cli/xtask/Cargo.toml check bans sources",
        "--manifest-path apps/desktop/core/Cargo.toml check bans sources",
        "--manifest-path apps/desktop/src-tauri/Cargo.toml check bans sources",
        "cd apps/cli && cargo shear --frozen --deny-warnings",
        "cd apps/cli/xtask && cargo shear --frozen --deny-warnings",
        "cd apps/desktop/core && cargo shear --frozen --deny-warnings",
        "cd apps/desktop/src-tauri && cargo shear --frozen --deny-warnings",
    ),
    "cli-build": ("cargo build --locked --release --bins --examples",),
    "cli-regress": ("cli-binary", 'tests/native_contract/verify.py "$binary"'),
    "security": ("bun run audit", "scan_lockfile.sh"),
    "web-build": ("AI_STP_WEB_PROFILE=public_saas bun run build",),
    "web-storybook": ("build-storybook",),
    "web-i18n": ("bun run i18n:check",),
    "web-source": (
        "bun run lint",
        "bun run format:check",
    ),
    "web-static": ("bun run type-check",),
    "web-test": ("bun run test:coverage", "bun run test:coverage:catalog"),
    "web-regress": ("ensure-chrome.sh", "bun run test:e2e"),
    "web-feature-profiles": ("ensure-chrome.sh", "bun run test:feature-profiles"),
}


type Expression = str | list[Expression]


class JustDependency(TypedDict):
    recipe: str


class JustRecipe(TypedDict):
    body: list[list[Expression]]
    dependencies: list[JustDependency]


class JustAssignment(TypedDict):
    value: Expression


class JustDocument(TypedDict):
    recipes: dict[str, JustRecipe]
    assignments: dict[str, JustAssignment]


@cache
def _parsed() -> JustDocument:
    result = subprocess.run(
        ["just", "--dump", "--dump-format=json"],
        cwd=ROOT,
        text=True,
        check=True,
        capture_output=True,
        timeout=15,
    )
    document = cast(JustDocument, json.loads(result.stdout))
    assert document["recipes"], "the real Just parser returned no command owners"
    return document


def _dependencies() -> dict[str, tuple[str, ...]]:
    return {
        name: tuple(item["recipe"] for item in recipe["dependencies"])
        for name, recipe in _parsed()["recipes"].items()
    }


def _render(value: Expression) -> str:
    if isinstance(value, str):
        return value
    if len(value) == 2 and value[0] == "variable" and isinstance(value[1], str):
        assignment = _parsed()["assignments"].get(value[1])
        return _render(assignment["value"]) if assignment else "{{" + value[1] + "}}"
    return "".join(_render(part) for part in value)


def _bodies() -> dict[str, str]:
    return {
        name: "\n".join(_render(line) for line in recipe["body"])
        for name, recipe in _parsed()["recipes"].items()
    }


def _leaves(recipe: str, graph: dict[str, tuple[str, ...]], seen: set[str]) -> set[str]:
    if recipe in seen:
        return set()
    assert recipe in graph, f"undeclared recipe owner: {recipe}"
    seen.add(recipe)
    covered: set[str] = {recipe} if _bodies().get(recipe) else set()
    for dependency in graph[recipe]:
        covered |= _leaves(dependency, graph, seen)
    # Literal nested calls retain a single owner while an enclosing script
    # sets the provider environment before delegating.
    for match in re.finditer(
        r"(?m)^\s*@?just ([a-z][a-z0-9-]*(?: +[a-z][a-z0-9-]*)*)\s*$", _bodies().get(recipe, "")
    ):
        for dependency in match.group(1).split():
            covered |= _leaves(dependency, graph, seen)
    return covered


def _expand(recipes: list[str]) -> set[str]:
    graph = _dependencies()
    covered: set[str] = set()
    for recipe in recipes:
        covered |= _leaves(recipe, graph, set())
    return covered


RECIPE_ACTION = "NDDev-Technocracy-OpenNetwork/nddev-ci/actions/recipe@"
RECIPE_WORKFLOW = "NDDev-Technocracy-OpenNetwork/nddev-ci/.github/workflows/recipe.yml@"


def _command_owners(entry: dict[str, Any]) -> list[str]:
    target = str(entry.get("uses", ""))
    if not target.startswith((RECIPE_ACTION, RECIPE_WORKFLOW)):
        return []
    assert re.fullmatch(r".+@[0-9a-f]{40}", target), "shared execution must pin a full commit"
    values = cast(dict[str, Any], entry.get("with") or {})
    if target.startswith(RECIPE_ACTION):
        assert "prepare" not in values, "The recipe action needs a separate preparation step"
    recipes = [values[key] for key in ("prepare", "recipe") if values.get(key)]
    assert recipes, "a shared recipe call has no project owner"
    assert all(recipe in _dependencies() for recipe in recipes), "a recipe call has no declaration"
    return recipes


def _script_commands(body: str, seen: set[Path]) -> str:
    """Follow only invoked literal project Bash owners, retaining cycle bounds."""
    parts = [body]
    for match in re.finditer(r"(?m)^\s*@?bash (\.github/scripts/[a-z0-9-]+\.sh)(?:\s|$)", body):
        path = ROOT / match.group(1)
        if path in seen:
            continue
        seen.add(path)
        parts.append(_script_commands(path.read_text(encoding="utf-8"), seen))
    return "\n".join(parts)


def command_text(job: dict[str, Any]) -> str:
    entries = [job, *job.get("steps", [])]
    owners = [owner for entry in entries for owner in _command_owners(entry)]
    body = "\n".join(
        [entry.get("run", "") for entry in entries]
        + [_bodies()[owner] for owner in _expand(owners)]
    )
    return _script_commands(body, set())


def workflow_text() -> str:
    parts: list[str] = []
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        source = path.read_text(encoding="utf-8")
        document = yaml.safe_load(source)
        parts.extend([source, *(command_text(job) for job in document["jobs"].values())])
    return "\n".join(parts)


def test_every_recipe_leaf_of_full_verification_appears_in_the_gate() -> None:
    """No check disappears when the gate is split, across jobs or across trees.

    Splitting is worth having right up to the moment a check falls out of the
    union, and nothing fails when it does: the run stays green and the check
    simply stops running. The split is across multiple trees as well as
    across jobs, so the union is asserted over the whole published
    workflow directory rather than one file.
    """
    required = _expand(["verify"])
    assert required, "the `verify` recipe resolved to nothing; the parser is wrong"
    unmapped = required - set(_LEAF_TOKENS)
    assert not unmapped, f"a leaf of `just verify` has no command tokens mapped: {sorted(unmapped)}"
    gate = workflow_text()
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
    assert graph["check"] == (
        "docs-static",
        "back-static",
        "cli-source",
        "desktop-source",
        "web-source",
        "infra-source",
        "just-fmt",
    )
    assert graph["verify"] == (
        "check",
        "docs-check",
        "back-check",
        "cli-check",
        "web-check",
        "desktop-check",
        "rust-dependencies",
        "security",
    )
    assert "back-test" in _expand(["back-check"])
    assert _expand(["security"]) == {"security"}


def test_source_checks_cannot_build_install_or_execute_test_suites() -> None:
    bodies = _bodies()
    forbidden = re.compile(
        r"cargo (?:run|build|check|clippy|test)|bun (?:install|x)|"
        r"bun run (?:build|test|i18n:check|audit)|pytest|unittest|uv (?:sync|build)"
    )
    for recipe in _expand(["check"]):
        assert not forbidden.search(bodies[recipe]), f"{recipe} is not a source-only check"
    assert _expand(["pre-commit"]) == _expand(["check"])
    assert {"docs-test", "cli-static", "cli-test", "web-test", "desktop-test"} <= _expand(["test"])


def test_recipe_action_rejects_unsupported_preparation() -> None:
    with pytest.raises(AssertionError, match="separate preparation step"):
        _command_owners(
            {
                "uses": RECIPE_ACTION + "9fead1382c452a6b791a0a9e464ac6ac66537ac3",
                "with": {"recipe": "ci-native-corporate", "prepare": "ci-native-corporate-prepare"},
            }
        )


def test_published_execution_uses_pinned_declared_command_owners() -> None:
    calls: list[str] = []
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        document = yaml.safe_load(path.read_text())
        for job in document["jobs"].values():
            for entry in [job, *job.get("steps", [])]:
                calls.extend(_command_owners(entry))
    assert calls, "the workflows bypass every shared command owner"
    assert any(name.startswith("ci-tests-") for name in calls)
    assert any(name.startswith("ci-desktop-") for name in calls)


def test_setup_is_split_and_each_job_prepares_only_its_own_part() -> None:
    """Only source-analysis owners prepare the small root Node tool set."""
    graph = _dependencies()
    assert graph["setup"] == ("setup-python-source", "setup-docs", "setup-web", "setup-desktop")
    assert graph["setup-python-source"] == ("setup-python", "setup-analysis")
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    runtime_only = {"tests", "coverage"}
    analysis_owners = {"package", "integration-python"}
    for name, job in workflow["jobs"].items():
        scripts = command_text(job)
        if name in runtime_only | analysis_owners:
            assert "docs_scripts && bun install" not in scripts, (
                f"{name} installs documentation Node tools"
            )
            assert "apps/web && bun install" not in scripts, f"{name} installs Web dependencies"
            assert "apps/desktop && bun install" not in scripts, (
                f"{name} installs Desktop dependencies"
            )
        if name in runtime_only:
            assert "bun install" not in scripts, f"{name} installs source-analysis dependencies"
            assert not any(
                "node-version" in step.get("with", {}) for step in job.get("steps", [])
            ), f"{name} prepares a Node SDK"
        if name in analysis_owners:
            assert "bun install --frozen-lockfile" in scripts, f"{name} omits analysis preparation"
            assert "bun run type-check:python" in scripts, f"{name} omits Python type analysis"


def test_python_analysis_preserves_product_and_tooling_coverage() -> None:
    document = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "pyright" not in document["tool"], "the superseded type configuration remains"
    config = document["tool"]["basedpyright"]
    assert set(config["include"]) >= {
        "packages",
        "apps",
        "tests",
        "docs_scripts",
        "release_scripts",
    }
    assert config["typeCheckingMode"] in {"standard", "strict"}
    if config["typeCheckingMode"] != "strict":
        assert set(config["strict"]) >= {"packages", "apps", "tests"}


def test_cli_and_web_tests_run_on_three_os_and_backend_stays_on_linux() -> None:
    """Client tests see three operating systems; server tests run on Linux."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    three = {"ubuntu-26.04", "macos-26", "windows-latest"}
    jobs = workflow["jobs"]
    for name in ("cli", "web-unit", "web-e2e", "web-profiles"):
        assert set(jobs[name]["strategy"]["matrix"]["os"]) == three, name
    assert jobs["tests"]["runs-on"] == "ubuntu-26.04"
    native = command_text(jobs["cli"])
    assert "cargo test --locked" in native
    assert "--package ai-stp-cli " not in native
    assert "-n 8" in command_text(jobs["tests"])


def test_pr_native_checks_cover_platform_specific_code_and_real_vault_processes() -> None:
    """Platform-only native defects must be observed before main promotion."""
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    native = jobs["integration-native"]
    assert native["if"] == "github.event_name == 'pull_request'"
    assert native["strategy"]["fail-fast"] is False
    assert set(native["strategy"]["matrix"]["os"]) == {
        "ubuntu-26.04",
        "macos-26",
        "windows-latest",
    }
    scripts = command_text(native)
    assert "cargo clippy --locked --all-targets -- -D warnings" in scripts
    vault = next(
        step
        for step in native["steps"]
        if step.get("name") == "Existing native vault and independent CLI processes"
    )
    assert vault["if"] == "runner.os != 'Linux'"
    assert "cargo test --locked --test enrollments_native" in command_text(vault)
    assert "--ignored" not in command_text(vault)
    pr_linux = next(
        step
        for step in native["steps"]
        if step.get("name") == "Fresh concurrent Linux clients and independent CLI processes"
    )
    assert pr_linux["if"] == "runner.os == 'Linux'"
    assert pr_linux["env"]["AI_STP_NATIVE_VAULT_ROUNDS"] == "10"
    assert "bash .github/scripts/check-native-secret-service.sh" in command_text(pr_linux)
    linux = next(
        step
        for step in jobs["cli"]["steps"]
        if step.get("name") == "Actual Linux Secret Service enrollment and recovery"
    )
    assert linux["if"] == "runner.os == 'Linux'"
    assert "bash .github/scripts/check-native-secret-service.sh" in command_text(linux)
    assert linux["env"]["AI_STP_NATIVE_VAULT_ROUNDS"] == (
        "${{ inputs.native_vault_rounds || '100' }}"
    )


def _shard_selection(arguments: list[str]) -> tuple[set[Path], set[Path]]:
    """Split one shard's pytest arguments into selected and ignored trees."""
    selected: set[Path] = set()
    ignored: set[Path] = set()
    for token in arguments:
        if token.startswith("--ignore="):
            ignored.add(ROOT / token.removeprefix("--ignore="))
        elif token.startswith("-"):
            raise AssertionError(f"unrecognised pytest argument in a shard: {token}")
        else:
            selected.add(ROOT / token)
    return selected, ignored


def _files_under(paths: set[Path]) -> set[Path]:
    found: set[Path] = set()
    for path in paths:
        if path.is_file():
            found.add(path)
            continue
        assert path.is_dir(), f"a shard names a path that does not exist: {path}"
        found |= set(path.rglob("test_*.py"))
    return found


def test_the_test_shards_cover_the_whole_tree_exactly_once() -> None:
    """Every test file runs on exactly one shard — none twice, none dropped.

    Asserted as a property rather than as a literal list of shard names,
    because the list is a tuning decision and the property is the requirement.
    A shard split for wall-clock is a good change; a split that silently drops
    a file is the failure the literal list was there to catch, and it catches
    it whatever the shards end up being called.
    """
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    rows = workflow["jobs"]["tests"]["strategy"]["matrix"]["include"]
    covered: dict[Path, list[str]] = {}
    for row in rows:
        selected, ignored = _shard_selection(row["arguments"])
        for path in _files_under(selected) - _files_under(ignored):
            covered.setdefault(path, []).append(row["shard"])

    twice = {path: shards for path, shards in covered.items() if len(shards) > 1}
    assert not twice, f"these files run on more than one shard: {twice}"

    everything = _files_under({ROOT / "tests"})
    missing = sorted(str(path.relative_to(ROOT)) for path in everything - set(covered))
    assert not missing, f"no shard of the gate runs these test files: {missing}"


def test_the_combined_coverage_names_every_shard_and_only_those() -> None:
    """Splitting a shard must reach the combine step, or coverage silently drops.

    The combine names its inputs one by one rather than globbing, so a shard
    that passed without writing coverage fails loudly instead of quietly
    lowering the total. That is worth keeping — and it is also why the list has
    to be checked against the matrix: adding a shard and forgetting this line
    loses that shard's coverage while the gate stays green.
    """
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    shards = {row["shard"] for row in workflow["jobs"]["tests"]["strategy"]["matrix"]["include"]}
    combine = command_text(workflow["jobs"]["coverage"])
    assert "coverage combine" in combine, "the coverage job no longer combines anything"
    named = set(re.findall(r"\.coverage\.([a-z0-9-]+)", combine))
    assert named == shards, f"combined {sorted(named)} but the matrix runs {sorted(shards)}"
