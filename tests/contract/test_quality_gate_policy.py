"""Repository-native gates must obey the same privilege boundary as the product."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[2]
JUSTFILE = ROOT / "justfile"
QUICKSTART = ROOT / "QUICKSTART.md"
#: Where the workflows this tree runs actually live. The working copy stopped
#: running any of its own (`ADR-0110` made it a mirror, and the fleet is not
#: spent on proving a mirror), so what it holds is the overlay it publishes. In
#: the built tree the overlay is absent and the workflows are local, and the
#: same assertions then describe the gate that really runs there.
OVERLAY = ROOT / "release_scripts" / "public_overlay" / ".github" / "workflows"
WORKFLOWS = OVERLAY if OVERLAY.is_dir() else ROOT / ".github" / "workflows"

CHECK_WORKFLOW = WORKFLOWS / "check.yml"
MACOS_WORKFLOW = WORKFLOWS / "macos-evidence.yml"
PROVIDER_SAFE_PATH = ROOT / ".github" / "scripts" / "provider-safe-path.sh"


def test_web_regression_never_installs_system_packages_with_sudo() -> None:
    recipes = JUSTFILE.read_text(encoding="utf-8")
    quickstart = QUICKSTART.read_text(encoding="utf-8")

    assert "playwright install --with-deps" not in recipes
    assert "bunx playwright install chromium" in recipes
    assert "никогда не вызывает `sudo`" in quickstart


def test_python_ci_jobs_do_not_reuse_a_persistent_checkout_venv() -> None:
    """Every job that runs `uv` isolates its environment, and no two share one.

    Counted jobs rather than occurrences, because the count changed the moment
    the gate was split into five (`ADR-0105`) and a hard-coded `== 2` fails for
    a reason that has nothing to do with the property. What has to hold is that
    a job running `uv` never resolves the checkout's `.venv`, and that two jobs
    never write to the same environment — a shared path is how a 3.12 run ends
    up executing what a 3.14 run installed.
    """
    workflow = yaml.safe_load(CHECK_WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]

    environments: list[str] = []
    for name, job in jobs.items():
        scripts = "\n".join(
            step["run"] for step in job.get("steps", []) if isinstance(step.get("run"), str)
        )
        if "uv" not in scripts and "just setup-python" not in scripts:
            continue
        assert "UV_PYTHON=${python_path}" in scripts, f"{name} does not pin its interpreter"
        marker = "UV_PROJECT_ENVIRONMENT=${RUNNER_TEMP}/"
        assert marker in scripts, f"{name} would resolve the checkout .venv"
        environments.append(scripts.split(marker, 1)[1].split('"', 1)[0].strip())
        assert "ai_stp_use_provider_safe_path" in scripts, f"{name} keeps the fixture path"

    assert len(environments) >= 2, "the Python matrix lost a job"
    assert len(set(environments)) == len(environments), f"two jobs share one env: {environments}"


@pytest.mark.skipif(os.name == "nt", reason="provider-safe-path gate is a bash script for Linux CI")
def test_provider_fixture_path_deprioritizes_interpreters_but_keeps_tools(
    tmp_path: Path,
) -> None:
    project_bin = tmp_path / "job" / "venv" / "bin"
    python_root = tmp_path / "tool" / "Python" / "3.14" / "x64"
    python_bin = python_root / "bin"
    safe_bin = tmp_path / "safe-bin"
    fixture_bin = tmp_path / "fixture-bin"
    for directory in (project_bin, python_bin, safe_bin, fixture_bin):
        directory.mkdir(parents=True)
    for executable in (python_bin / "python", python_bin / "python3", python_bin / "uv"):
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)
    for executable in (safe_bin / "just", fixture_bin / "python3"):
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)

    original_path = ":".join(
        str(part)
        for part in (
            project_bin,
            python_bin,
            python_root,
            safe_bin,
            fixture_bin,
            "/usr/bin",
            "/bin",
        )
    )
    result = subprocess.run(
        [
            "/bin/bash",
            "-c",
            (
                f'source "{PROVIDER_SAFE_PATH}"; ai_stp_use_provider_safe_path; '
                'printf "%s\\n%s" "$PATH" "$AI_STP_TEST_PROVIDER_PATH"'
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
        env={
            "PATH": original_path,
            "UV_PYTHON": str(python_bin / "python"),
            "UV_PROJECT_ENVIRONMENT": str(project_bin.parent),
        },
    )

    expected_path = ":".join(
        str(part)
        for part in (
            safe_bin,
            fixture_bin,
            "/usr/bin",
            "/bin",
            project_bin,
            python_bin,
            python_root,
        )
    )
    assert result.stdout == f"{expected_path}\n{expected_path}"


def test_clean_wheel_regression_ignores_the_outer_matrix_interpreter() -> None:
    recipes = JUSTFILE.read_text(encoding="utf-8")

    assert 'uv pip install --python "$work/venv"' in recipes
    assert 'uv pip list --python "$work/venv"' in recipes
    assert 'VIRTUAL_ENV="$work/venv" uv pip install' not in recipes


def test_primary_quality_gates_do_not_require_bash_on_windows() -> None:
    result = subprocess.run(
        ["just", "--dry-run", "setup", "docs-check", "back-gen", "back-static"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    output = result.stdout + result.stderr
    assert "#!/usr/bin/env bash" not in output
    assert "ruff format --check" in output

    if os.name == "nt":
        regression = subprocess.run(
            ["just", "--dry-run", "back-regress"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        output = regression.stdout + regression.stderr
        assert "back-regress requires bash" in output
        assert "uv build" not in output


def test_macos_matrix_proves_its_selected_python_and_exact_candidate() -> None:
    workflow = MACOS_WORKFLOW.read_text(encoding="utf-8")

    assert "UV_PROJECT_ENVIRONMENT=${RUNNER_TEMP}/ai-stp-python-${{ matrix.python }}" in workflow
    assert "just release-candidate" in workflow
    assert "release_scripts.verify_candidate_install" in workflow
    assert '--expected-python "${{ matrix.python }}"' in workflow
    assert '> ".evidence/release-candidate-python-${{ matrix.python }}.json"' in workflow
    assert workflow.count("ai_stp_use_provider_safe_path") == 1
