"""Explicit-path inventory is passport-first and does not import global homes (`REQ-534`)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ai_stp_cli.local import authoring, components, setup_scaffold


def _write_tree(destination: Path, files: dict[str, bytes]) -> None:
    authoring.write_new_tree(destination, files)


def _mixed_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    skill_root = workspace / "review-kit"
    _plan, files = authoring.scaffold_plan(
        component_type="skill",
        name="review-kit",
        language="none",
        harness_variant="claude-code",
        output=skill_root,
    )
    _write_tree(skill_root, files)
    authoring.add_adaptation(skill_root, "codex")

    cli_root = workspace / "ship-tool"
    _cli_plan, cli_files = authoring.scaffold_plan(
        component_type="cli",
        name="ship-tool",
        language="python",
        harness_variant="portable",
        output=cli_root,
    )
    _write_tree(cli_root, cli_files)

    setup_root = workspace / "review-pack"
    _setup_plan, setup_files = setup_scaffold.setup_scaffold_plan(
        name="review-pack",
        harness="codex",
        output=setup_root,
        components="skill:nested-review,instruction:conventions",
    )
    _write_tree(setup_root, setup_files)

    portable = workspace / "skills" / "audit"
    portable.mkdir(parents=True)
    (portable / "SKILL.md").write_text("# audit\n", encoding="utf-8")

    package = workspace / "services" / "weather"
    source = package / "src" / "weather" / "server.py"
    source.parent.mkdir(parents=True)
    (package / "pyproject.toml").write_text(
        """[project]
name = "weather-mcp"
version = "1.0.0"
dependencies = ["mcp>=1"]

[project.scripts]
weather-mcp = "weather.server:main"
""",
        encoding="utf-8",
    )
    source.write_text(
        "from mcp.server.fastmcp import FastMCP\n"
        "server = FastMCP('weather')\n"
        "server.run(transport='stdio')\n",
        encoding="utf-8",
    )

    frontend = workspace / "src" / "hooks"
    frontend.mkdir(parents=True)
    (frontend / "useFoo.ts").write_text("export const useFoo = () => 1\n", encoding="utf-8")

    broken = workspace / "broken"
    broken.mkdir()
    (broken / "component-passport.json").write_text("{not-json", encoding="utf-8")

    (workspace / "AGENTS.md").write_text("# workspace rules\n", encoding="utf-8")
    return workspace


def test_named_project_discovery_does_not_list_global_homes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    skill = home / ".claude" / "skills" / "reviewing"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# reviewing\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))

    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text("# project\n", encoding="utf-8")

    report = components.discover_report(
        project=project,
        environment={**os.environ, "HOME": str(home), "USERPROFILE": str(home)},
    )

    assert all(item.scope != "global" for item in report.components)
    assert any(Path(item.source_path).name == "AGENTS.md" for item in report.components)
    assert not any("reviewing" in item.source_path for item in report.components)


def test_inventory_classifies_a_mixed_authoring_tree_without_home_or_minted_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    planted = home / ".claude" / "skills" / "reviewing"
    planted.mkdir(parents=True)
    (planted / "SKILL.md").write_text("# reviewing\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    from ai_stp_cli.local.path_inventory import inventory_root

    workspace = _mixed_workspace(tmp_path)
    first = inventory_root(workspace)
    second = inventory_root(workspace)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.complete is True
    assert all(item.stable_id is None for item in first.objects)

    independents = [item for item in first.objects if item.relation == "independent"]
    generated = [item for item in first.objects if item.relation == "generated_projection"]
    embedded = [item for item in first.objects if item.relation == "embedded_member"]

    kinds = {(item.object_kind, item.component_type, item.relative_path) for item in independents}
    assert ("component", "skill", "review-kit") in kinds
    assert ("component", "cli", "ship-tool") in kinds
    assert ("setup", None, "review-pack") in kinds
    assert any(item.relative_path.endswith("skills/audit") for item in independents)
    assert any(item.relative_path.endswith("services/weather") for item in independents)
    assert any(item.relative_path == "AGENTS.md" for item in independents)

    assert {item.relative_path for item in generated} >= {
        "review-kit/projections/claude-code",
        "review-kit/projections/codex",
    }
    assert any(item.relative_path.startswith("review-pack/components/") for item in embedded)
    assert not any(item.relative_path.endswith("useFoo.ts") for item in first.objects)
    assert not any("reviewing" in item.relative_path for item in first.objects)
    dumped = json.dumps(first.model_dump(mode="json"))
    assert str(home) not in dumped
    assert any(
        item.code == "invalid_manifest" and "broken" in item.reason for item in first.diagnostics
    )


def test_a_generated_projection_directory_is_not_an_independent_source(tmp_path: Path) -> None:
    skill_root = tmp_path / "review-kit"
    _plan, files = authoring.scaffold_plan(
        component_type="skill",
        name="review-kit",
        language="none",
        harness_variant="claude-code",
        output=skill_root,
    )
    _write_tree(skill_root, files)
    projection = skill_root / "projections" / "claude-code"

    from ai_stp_cli.local.path_inventory import inventory_root

    report = inventory_root(projection)

    assert [item.relation for item in report.objects] == ["generated_projection"]
    assert report.objects[0].relative_path == "."
    assert report.objects[0].object_kind == "component"
    assert report.objects[0].component_type == "skill"
    assert all(item.stable_id is None for item in report.objects)
