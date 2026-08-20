"""Process-level adopted component passport enrichment lifecycle (`#253`)."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast


def _run(environment: dict[str, str], *arguments: str) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "-m", "ai_stp_cli", *arguments, "--json"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    envelope = cast(dict[str, object], json.loads(result.stdout))
    assert envelope["ok"] is True
    return cast(dict[str, object], envelope["data"])


def _refused(environment: dict[str, str], *arguments: str) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "-m", "ai_stp_cli", *arguments, "--json"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    assert result.returncode != 0
    envelope = cast(dict[str, object], json.loads(result.stdout))
    return cast(dict[str, object], envelope["error"])


def test_real_cli_adopts_enriches_and_validates_one_exact_revision(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    skill = project / ".agents" / "skills" / "quality"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# quality\n", encoding="utf-8")
    (skill / "pyproject.toml").write_text(
        """
[tool.ai-stp.component]
name = "quality"
description = "Checks quality."
tags = ["quality"]
harness_id = "codex"
component_type = "skill"
projection_kind = "native_files"
entry_points = ["SKILL.md"]
runtime_requirements = ["codex>=1"]

[tool.ai-stp.component.license]
spdx_id = "MIT"
redistribution_allowed = true
""".strip()
        + "\n",
        encoding="utf-8",
    )
    environment = {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "XDG_STATE_HOME": str(home / ".local" / "state"),
    }

    discovered = _run(environment, "component", "discover", "--root", str(project))
    candidates = cast(list[dict[str, object]], discovered["components"])
    candidate = next(item for item in candidates if str(item["source_path"]).endswith("quality"))
    adopted = _run(
        environment,
        "component",
        "adopt",
        "--path",
        str(candidate["source_path"]),
        "--root",
        str(project),
    )
    stable_id = str(adopted["stable_id"])
    original_revision = str(adopted["revision_id"])

    shown = _run(environment, "component", "passport", "show", "--id", stable_id)
    assert shown["revision_id"] == original_revision
    suggested = _run(environment, "component", "passport", "suggest", "--id", stable_id)
    suggestions = cast(list[dict[str, object]], suggested["suggestions"])
    assert suggested["revision_id"] == original_revision
    assert {item["field"] for item in suggestions} >= {
        "name",
        "license",
        "runtime_requirements",
    }
    assert all(item["requires_confirmation"] is True for item in suggestions)

    incomplete_patch = tmp_path / "incomplete.json"
    incomplete_patch.write_text(
        json.dumps({"name": "quality", "description": "Checks quality."}), encoding="utf-8"
    )
    enriched = _run(
        environment,
        "component",
        "passport",
        "update",
        "--id",
        stable_id,
        "--expected-revision",
        original_revision,
        "--from",
        str(incomplete_patch),
        "--confirm",
    )
    enriched_revision = str(enriched["revision_id"])
    incomplete = _run(
        environment,
        "component",
        "passport",
        "validate",
        "--id",
        stable_id,
        "--for-publication",
    )
    assert incomplete["ready"] is False
    assert "source" in cast(list[str], incomplete["missing_fields"])

    floating_source = tmp_path / "floating-source.json"
    floating_source.write_text(
        json.dumps(
            {
                "source": {
                    "repository": "https://github.com/example/quality",
                    "commit": "main",
                    "path": "skills/quality",
                }
            }
        ),
        encoding="utf-8",
    )
    floating = _refused(
        environment,
        "component",
        "passport",
        "update",
        "--id",
        stable_id,
        "--expected-revision",
        enriched_revision,
        "--from",
        str(floating_source),
        "--confirm",
    )
    assert floating["code"] == "AI_STP_VALIDATION_ERROR"

    secret_value = "must-never-reach-output"
    secret_patch = tmp_path / "secret.json"
    secret_patch.write_text(json.dumps({"access_token": secret_value}), encoding="utf-8")
    secret = _refused(
        environment,
        "component",
        "passport",
        "update",
        "--id",
        stable_id,
        "--expected-revision",
        enriched_revision,
        "--from",
        str(secret_patch),
        "--confirm",
    )
    assert secret["code"] == "AI_STP_VALIDATION_ERROR"
    assert secret_value not in json.dumps(secret)

    complete_patch = tmp_path / "complete.json"
    complete_patch.write_text(
        json.dumps(
            {
                "tags": ["quality"],
                "source": {
                    "repository": "https://github.com/example/quality",
                    "commit": "a" * 40,
                    "path": "skills/quality",
                },
                "harness_id": "codex",
                "component_type": "skill",
                "projection_kind": "native_files",
                "license": {"spdx_id": "MIT", "redistribution_allowed": True},
                "entry_points": ["SKILL.md"],
                "runtime_requirements": ["codex>=1"],
                "provides_capabilities": ["repository.safety"],
                "requires_components": [],
                "requires_capabilities": [],
                "requires_credentials": False,
                "requires_authorization": "none",
                "permissions": {"filesystem": [], "network": [], "process": []},
            }
        ),
        encoding="utf-8",
    )
    complete = _run(
        environment,
        "component",
        "passport",
        "update",
        "--id",
        stable_id,
        "--expected-revision",
        enriched_revision,
        "--from",
        str(complete_patch),
        "--confirm",
    )
    ready = _run(
        environment,
        "component",
        "passport",
        "validate",
        "--id",
        stable_id,
        "--for-publication",
    )
    assert ready == {
        "schema_version": 1,
        "stable_id": stable_id,
        "revision_id": complete["revision_id"],
        "for_publication": True,
        "ready": True,
        "missing_fields": [],
        "invalid_fields": [],
    }

    released = _run(environment, "component", "version", "release", "--id", stable_id)
    versions = cast(list[dict[str, object]], released["versions"])
    assert versions[0]["version"] == "1.0"
    assert versions[0]["revision_id"] == complete["revision_id"]

    later_patch = tmp_path / "later.json"
    later_patch.write_text(json.dumps({"description": "Checks quality safely."}), encoding="utf-8")
    later = _run(
        environment,
        "component",
        "passport",
        "update",
        "--id",
        stable_id,
        "--expected-revision",
        str(complete["revision_id"]),
        "--from",
        str(later_patch),
        "--confirm",
    )
    assert later["revision_id"] != complete["revision_id"]
    line = _run(environment, "component", "version", "list", "--id", stable_id)
    recorded = cast(list[dict[str, object]], line["versions"])
    assert recorded[0]["revision_id"] == complete["revision_id"]

    stale = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_stp_cli",
            "component",
            "passport",
            "update",
            "--id",
            stable_id,
            "--expected-revision",
            original_revision,
            "--from",
            str(complete_patch),
            "--confirm",
            "--json",
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    assert stale.returncode != 0
    failure = cast(dict[str, object], json.loads(stale.stdout))
    error = cast(dict[str, object], failure["error"])
    assert error["code"] == "AI_STP_PRECONDITION_FAILED"
