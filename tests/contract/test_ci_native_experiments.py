"""Exercise actual CI admission against omitted, failed and unexpectedly skipped owners."""

from __future__ import annotations

import json
import os
import subprocess
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@cache
def workflow() -> dict[str, Any]:
    return yaml.safe_load((ROOT / ".github/workflows/check.yml").read_text())


def accepted(results: dict[str, dict[str, str]], phase: str, private: bool, wasi: str) -> bool:
    script = workflow()["jobs"]["qualification"]["steps"][0]["run"]
    environment = {
        **os.environ,
        "RESULTS": json.dumps(results),
        "PHASE": phase,
        "PRIVATE_REPOSITORY": str(private).lower(),
        "WASI_SELECTED": wasi,
    }
    result = subprocess.run(
        ["bash", "-c", script],
        env=environment,
        capture_output=True,
        timeout=10,
        check=False,
    )
    return result.returncode == 0


def test_every_owning_job_is_joined_into_qualification() -> None:
    jobs = workflow()["jobs"]
    assert set(jobs["qualification"]["needs"]) == set(jobs) - {"qualification"}
    assert jobs["wasi-confinement"]["needs"] == "native-experiments"
    assert jobs["wasi-confinement"]["uses"] == "./.github/workflows/wasi-confinement.yml"
    assert jobs["qualification"]["if"] == "always()"
    experiment = yaml.safe_load((ROOT / ".github/workflows/wasi-confinement.yml").read_text())
    assert experiment["jobs"]["confinement"]["needs"] == "component"
    assert set(experiment["jobs"]["confinement"]["strategy"]["matrix"]["os"]) == {
        "ubuntu-24.04",
        "macos-15",
        "windows-2025",
    }


@pytest.mark.parametrize("phase", ["integration", "full"])
@pytest.mark.parametrize("private", [False, True])
@pytest.mark.parametrize("wasi", ["true", "false"])
def test_real_gate_refuses_each_wrong_result_and_missing_owner(
    phase: str, private: bool, wasi: str
) -> None:
    expected: dict[str, dict[str, str]] = {}
    for name in workflow()["jobs"]["qualification"]["needs"]:
        if name in {"secrets", "native-experiments"}:
            result = "success"
        elif name == "analysis":
            result = "skipped" if private else "success"
        elif name == "wasi-confinement":
            result = "success" if wasi == "true" else "skipped"
        elif name.startswith("integration-"):
            result = "success" if phase == "integration" else "skipped"
        else:
            result = "success" if phase == "full" else "skipped"
        expected[name] = {"result": result}
    assert accepted(expected, phase, private, wasi)
    for name, value in expected.items():
        for wrong in ["failure", "cancelled", "neutral", "skipped", "success"]:
            if wrong != value["result"]:
                changed = {**expected, name: {"result": wrong}}
                assert not accepted(changed, phase, private, wasi), (name, wrong)
        assert not accepted({k: v for k, v in expected.items() if k != name}, phase, private, wasi)
    for invalid in ["", "TRUE", "unknown"]:
        assert not accepted(expected, phase, private, invalid)
    assert not accepted({**expected, "unjoined": {"result": "success"}}, phase, private, wasi)
