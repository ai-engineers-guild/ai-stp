"""Repository-native gates must obey the same privilege boundary as the product."""

import os
import re
import shutil
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
_REQUIRED_WORKFLOWS = {"check.yml", "platform-evidence.yml", "codeql.yml"}
WORKFLOWS = (
    OVERLAY
    if OVERLAY.is_dir() and {path.name for path in OVERLAY.iterdir()} >= _REQUIRED_WORKFLOWS
    else ROOT / ".github" / "workflows"
)

CHECK_WORKFLOW = WORKFLOWS / "check.yml"
CODEQL_WORKFLOW = WORKFLOWS / "codeql.yml"
PLATFORM_WORKFLOW = WORKFLOWS / "platform-evidence.yml"
PROVIDER_SAFE_PATH = ROOT / ".github" / "scripts" / "provider-safe-path.sh"
ENSURE_CHROME = ROOT / ".github" / "scripts" / "ensure-chrome.sh"


def test_web_regression_never_installs_system_packages_with_sudo() -> None:
    """Browser bytes go to the user's cache; OS packages are not this gate's to
    install.

    The browser install moved out of the recipes and into a script both the
    recipes and the gate call, so the property is asserted over the script as
    well — checking only the justfile would have gone quiet the moment the
    command moved one file over.
    """
    quickstart = QUICKSTART.read_text(encoding="utf-8")
    sources = {
        "justfile": JUSTFILE.read_text(encoding="utf-8"),
        "ensure-chrome.sh": ENSURE_CHROME.read_text(encoding="utf-8"),
    }
    for name, text in sources.items():
        assert "--with-deps" not in text, f"{name} installs OS packages"
        # Comments stripped first: both files explain in prose that they must
        # not call `sudo`, and matching the word anywhere would fail on the
        # sentence that states the rule.
        commands = "\n".join(line for line in text.split("\n") if not line.strip().startswith("#"))
        assert not re.search(r"(^|[\s;&|(])sudo\s", commands), f"{name} invokes sudo"
    assert "playwright install chrome" in sources["ensure-chrome.sh"]
    assert "ensure-chrome.sh" in sources["justfile"]
    assert "never invokes `sudo`" in quickstart


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
        if "uv" not in scripts:
            continue
        assert "UV_PYTHON=${python_path}" in scripts, f"{name} does not pin its interpreter"
        marker = "UV_PROJECT_ENVIRONMENT=${RUNNER_TEMP}/"
        assert marker in scripts, f"{name} would resolve the checkout .venv"
        environments.append(scripts.split(marker, 1)[1].split('"', 1)[0].strip())
        if "pytest" in scripts:
            # Only the jobs that actually run the pytest provider fixtures
            # depend on the de-prioritized interpreter path; a bun-only job
            # gains nothing from sourcing a bash helper.
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
    (fixture_bin / "python3").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (fixture_bin / "python3").chmod(0o755)

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
    script = (ROOT / "release_scripts" / "clean_install_regress.sh").read_text(encoding="utf-8")

    assert 'uv pip install --python "$work/venv"' in script
    assert 'uv pip list --python "$work/venv"' in script
    assert 'VIRTUAL_ENV="$work/venv" uv pip install' not in script


def test_primary_quality_gates_do_not_require_bash_on_windows() -> None:
    """What `just` expands the primary recipes to, when `just` is here to ask.

    Skipped rather than failed when it is not. CI stopped installing `just` on
    purpose — the workflow writes the recipe bodies out, so `just` is a local
    convenience — and this test kept invoking it, which turned every contract
    shard red with `No such file or directory: 'just'` about a tree that was
    fine.

    A skip is honest here because the property is about what the *recipes* say,
    and the recipes are read by `test_gate_split_covers_the_gate.py` against the
    workflow without any tool at all. This one adds the expansion, which needs
    the expander.
    """
    if shutil.which("just") is None:
        pytest.skip("just is not installed; the gate does not depend on it (ADR-0116)")
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
        # PATH bash on Windows is frequently WSL. The recipe locates Git bash
        # through the helper and still builds the wheels; it does not refuse
        # the OS and it does not invoke unqualified bash.
        assert "back-regress requires bash" not in output
        assert "run_bash.py" in output
        assert "clean_install_regress.sh" in output
        assert "just back-build" in output
        assert "bash release_scripts/clean_install_regress.sh" not in output


def test_platform_matrix_installs_one_exact_candidate_on_six_native_targets() -> None:
    text = PLATFORM_WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    verify_job = workflow["jobs"]["verify"]
    rows = verify_job["strategy"]["matrix"]["include"]
    verify_scripts = "\n".join(
        step["run"] for step in verify_job["steps"] if isinstance(step.get("run"), str)
    )
    observed = {(row["os"], row["arch"], row["runner"]) for row in rows}
    expected = {
        ("linux", "x86_64", "ubuntu-24.04"),
        ("linux", "arm64", "ubuntu-24.04-arm"),
        ("darwin", "x86_64", "macos-15-intel"),
        ("darwin", "arm64", "macos-15"),
        ("windows", "x86_64", "windows-2025"),
        ("windows", "arm64", "windows-11-arm"),
    }
    assert observed == expected
    assert sum(row["python"] == "3.12" for row in rows) == 1
    assert text.count("release_scripts/build_candidate.py --replace") == 1
    assert "actions/download-artifact" in text
    assert "release_scripts.verify_candidate_install" in text
    assert '--expected-python "${EXPECTED_PYTHON}"' in text
    assert "RUNNER_ARCH" in text
    assert "--network-report" in verify_scripts
    assert "release_scripts.verify_network_evidence" in verify_scripts
    assert "uv sync" not in verify_scripts
    assert "ai-stp provider network --json" not in verify_scripts
    assert not (WORKFLOWS / "macos-evidence.yml").exists()


def test_codeql_is_public_github_hosted_security_and_not_the_gate() -> None:
    """Findings must not look like a broken check, and must not take the fleet."""
    text = CODEQL_WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    executable = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    job = workflow["jobs"]["analyse"]

    assert workflow["name"] == "codeql"
    assert workflow["permissions"]["contents"] == "read"
    assert job["if"] == "github.event.repository.private == false"
    assert job["runs-on"] == "ubuntu-latest"
    assert job["permissions"]["contents"] == "read"
    assert job["permissions"]["security-events"] == "write"
    assert "queries: security-extended" in executable
    assert "security-and-quality" not in executable
    assert "persist-credentials: false" in executable
    assert "nddev-linux" not in executable
    assert "secrets." not in executable
