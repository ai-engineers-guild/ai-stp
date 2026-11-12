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
    check = workflow("source")
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
        "Prepare the exact installed performance baseline",
        "Compare installed startup and repeated navigation on the same worker",
        "Retain the exact same-worker performance observations",
    ):
        assert steps[name]["if"] == "runner.os == 'Linux' && !inputs.packages_only"
    assert "preflight-" in steps["Upload bundles"]["with"]["name"]
    assert steps["Seal the exact platform installers"]["if"] == "${{ !inputs.packages_only }}"
    order = list(steps)
    assert order.index("Seal the exact platform installers") > order.index(
        "Installed corporate onboarding, lost reply and original binding recovery"
    )
    assert order.index("Seal the exact platform installers") > order.index(
        "Retain the exact same-worker performance observations"
    )
    personal = "Qualify personal workspace on installed macOS and Windows"
    retained = "Retain installed macOS and Windows personal results"
    condition = "(runner.os == 'macOS' || runner.os == 'Windows') && !inputs.packages_only"
    assert steps[personal]["if"] == steps[retained]["if"] == condition
    assert steps[personal]["with"]["recipe"] == "ci-desktop-installed-personal-workspace"
    assert order.index("Seal the exact platform installers") < order.index(personal)
    assert order.index(personal) < order.index(retained) < order.index("Upload bundles")
    assert steps["Upload bundles"]["with"]["if-no-files-found"] == "error"
    assert (
        '"application_acceptance":false'
        in steps["Record that diagnostic packages have no application acceptance"]["run"]
    )


def test_native_corporate_diagnosis_preserves_ordinary_application_acceptance() -> None:
    desktop = workflow("desktop")
    events = cast(dict[str, Any], desktop.get("on", desktop.get(True)))
    selected = "diagnostic_native_corporate"
    assert events["workflow_dispatch"]["inputs"][selected]["default"] is False
    reusable = cast(dict[str, Any], events["workflow_call"] or {})
    assert selected not in reusable.get("inputs", {})
    jobs = desktop["jobs"]
    for owner in ["desktop", "native-diagnostic"]:
        assert f"!inputs.{selected}" in jobs[owner]["if"]
    corporate = jobs["native-corporate-diagnostic"]
    assert corporate["if"] == f"github.event_name == 'workflow_dispatch' && inputs.{selected}"
    assert corporate["permissions"] == {
        "contents": "read",
        "actions": "read",
        "security-events": "read",
    }
    assert corporate["uses"] == "./.github/workflows/native-corporate-checks.yml"
    assert corporate["with"]["diagnostic_only"] is True
    owner = workflow("native-corporate-checks")["jobs"]["journeys"]
    steps = {step.get("name"): step for step in owner["steps"]}
    order = list(steps)
    admit = "Admit the exact current Dev qualification"
    archive = "Read the exact qualified native CLI archive"
    preparation = "Prepare the actual API fixture"
    consumer = "Run native corporate journeys against actual API/PostgreSQL"
    database = "Admit native PostgreSQL startup and SCRAM authentication"
    assert (
        order.index(admit) < order.index(archive) < order.index(preparation) < order.index(consumer)
    )
    assert steps[admit]["if"] == "inputs.diagnostic_only"
    assert steps[admit]["with"]["recipe"] == "ci-desktop-admit-native-diagnostic"
    assert (
        steps[archive]["with"]["run-id"]
        == "${{ inputs.diagnostic_source_run_id || github.run_id }}"
    )
    assert "inputs.diagnostic_app_source" in steps[archive]["with"]["name"]
    assert steps[consumer]["env"]["AI_STP_REQUIRE_ENGINE"] == "true"
    assert not {"GH_TOKEN", "GITHUB_TOKEN"} & steps[consumer]["env"].keys()
    assert steps[preparation]["with"] == {"recipe": "ci-native-corporate-prepare"}
    assert order.index(preparation) < order.index(database)
    assert steps[database]["with"] == {"recipe": "ci-native-corporate-postgresql-preflight"}
    assert steps[consumer]["with"] == {"recipe": "ci-native-corporate"}

    assert any(step.get("uses") == "./.github/actions/project-rust" for step in owner["steps"])
    for name in [
        "Build the immutable previous schema58 native writer",
        "Build the qualified previous schema59 binding writer",
        "Verify the immutable released schema60 native writer",
        "Verify the immutable released schema61 native writer",
    ]:
        assert order.index(database) < order.index(name) < order.index(consumer)
        assert "if" not in steps[name]


def test_native_corporate_consumer_refuses_before_provisioning_on_a_developer_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.native_contract.verify_native_corporate import main

    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(AssertionError, match="Native fixtures require hosted CI"):
        main()
