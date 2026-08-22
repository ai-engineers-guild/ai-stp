"""Workflows must be parseable by the thing that runs them.

This tree checks its workflows by reading them as text and asserting strings.
Nothing checked that GitHub can *parse* them, and the day that mattered the
failure had no way to report itself: the broken file was the gate, so the run
came back with zero jobs, named after the file path instead of the workflow,
and every job-level assertion in the suite still passed.

What broke was one line — `PLAYWRIGHT_BROWSERS_PATH: ${{ runner.temp }}/…` in a
job's `env` block. The `runner` context exists inside steps and nowhere else,
and naming it at job level makes the whole workflow unreadable rather than that
one job unusable.

The structural rule below runs everywhere and needs no tool. `actionlint`
catches a wider class and runs when it is installed; a skip there is honest
because the rule that actually bit is asserted unconditionally above it.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

_OVERLAY = Path("release_scripts/public_overlay/.github/workflows")
WORKFLOWS = _OVERLAY if _OVERLAY.is_dir() else Path(".github/workflows")

#: Contexts that exist only inside a step. A job-level `env`, `if` or `name`
#: naming one of these is a parse error for the whole file.
STEP_ONLY = ("runner", "steps", "job", "env")


def _files() -> list[Path]:
    if not WORKFLOWS.is_dir():
        pytest.skip("this tree carries no workflows (ADR-0110)")
    found = sorted(WORKFLOWS.glob("*.yml"))
    assert found, "the workflow directory exists and is empty"
    return found


@pytest.mark.parametrize("workflow", _files(), ids=lambda p: p.name)
def test_no_job_level_field_names_a_step_only_context(workflow: Path) -> None:
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    for name, job in (document.get("jobs") or {}).items():
        for field in ("env", "if", "name", "runs-on", "timeout-minutes"):
            value = job.get(field)
            if value is None:
                continue
            for context in re.findall(r"\$\{\{\s*([a-z]+)\s*\.", str(value)):
                assert context not in STEP_ONLY, (
                    f"{workflow.name}: job {name!r} names `{context}` in `{field}`, "
                    "which exists only inside a step; GitHub refuses the whole file"
                )


def test_actionlint_accepts_every_workflow() -> None:
    binary = shutil.which("actionlint")
    if binary is None:
        pytest.skip("actionlint is not installed; the structural rule above still ran")
    result = subprocess.run(  # noqa: S603
        [binary, *[str(path) for path in _files()]],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout or result.stderr
