"""Diagnostic packages cannot satisfy installed application or release admission."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
import yaml


def workflow(name: str) -> dict[str | bool, Any]:
    return cast(
        dict[str | bool, Any], yaml.safe_load(Path(f".github/workflows/{name}.yml").read_text())
    )


@pytest.mark.parametrize(
    ("event", "owner", "accepted"),
    [
        ("workflow_dispatch", "desktop", True),
        ("push", "desktop", False),
        ("pull_request", "desktop", False),
        ("workflow_dispatch", "desktop-release", False),
        ("workflow_dispatch", "check", False),
    ],
)
def test_package_diagnosis_refuses_to_replace_an_owning_release_or_main_run(
    event: str, owner: str, accepted: bool
) -> None:
    steps = workflow("desktop")["jobs"]["desktop"]["steps"]
    gate = next(step for step in steps if step["name"].startswith("Confine package-only"))
    result = subprocess.run(
        ["bash", "-c", gate["run"]],
        env={**os.environ, "GITHUB_EVENT_NAME": event, "GITHUB_WORKFLOW": owner},
        check=False,
        capture_output=True,
        timeout=5,
    )
    assert (result.returncode == 0) is accepted


def test_reusable_release_keeps_mandatory_application_acceptance() -> None:
    desktop = workflow("desktop")
    events = cast(dict[str, Any], desktop.get("on", desktop.get(True)))
    assert events["workflow_dispatch"]["inputs"]["packages_only"]["default"] is False
    reusable = cast(dict[str, Any], events["workflow_call"] or {})
    reusable_inputs = cast(dict[str, Any], reusable.get("inputs") or {})
    assert "packages_only" not in reusable_inputs
    release = workflow("desktop-release")
    assert "bundle" not in release["jobs"]
    check = workflow("check")
    assert check["jobs"]["desktop"]["uses"] == "./.github/workflows/desktop.yml"
    assert "packages_only" not in check["jobs"]["desktop"].get("with", {})
    assert "desktop" in check["jobs"]["qualification"]["needs"]
    steps = {step.get("name"): step for step in desktop["jobs"]["desktop"]["steps"]}
    for name in (
        "Install the release package on the disposable Linux runner",
        "Three installed Linux Desktop journeys with bundled CLI and native vault",
        "Installed corporate onboarding, lost reply and original binding recovery",
        "Retain the public installed corporate checkout result",
        "Retain public installed Desktop results",
    ):
        assert steps[name]["if"] == "runner.os == 'Linux' && !inputs.packages_only"
    assert "preflight-" in steps["Upload bundles"]["with"]["name"]
    assert (
        steps["Seal the platform installers after native acceptance"]["if"]
        == "${{ !inputs.packages_only }}"
    )
    order = list(steps)
    assert order.index("Seal the platform installers after native acceptance") > order.index(
        "Installed corporate onboarding, lost reply and original binding recovery"
    )
    assert steps["Upload bundles"]["with"]["if-no-files-found"] == "error"
    assert (
        '"application_acceptance":false'
        in steps["Record that diagnostic packages have no application acceptance"]["run"]
    )
