"""Process-level component discovery across layout and source adapters (`#231`)."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _snapshot(root: Path) -> dict[str, bytes | None]:
    return {
        path.relative_to(root).as_posix(): None if path.is_dir() else path.read_bytes()
        for path in sorted(root.rglob("*"))
    }


def test_real_cli_combines_project_layout_and_global_github_provenance(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    extension = project / ".pi" / "extensions" / "review.ts"
    extension.parent.mkdir(parents=True)
    extension.write_text("export default {}\n", encoding="utf-8")
    codex_plugin = project / "plugins" / "rldyour-flow"
    _write(codex_plugin / ".codex-plugin" / "plugin.json", {"name": "rldyour-flow"})
    _write(codex_plugin / "hooks" / "hooks.json", {"hooks": {}})
    (codex_plugin / "hooks" / "guard.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (project / "src" / "hooks").mkdir(parents=True)
    (project / "src" / "hooks" / "useFoo.ts").write_text(
        "export const useFoo = () => 1\n", encoding="utf-8"
    )
    (project / ".mcp.json").write_text(
        '{"mcpServers":{"docs":{"command":"npx","args":["docs-mcp"]}}}',
        encoding="utf-8",
    )
    (project / ".codex").mkdir(parents=True)
    (project / ".codex" / "config.toml").write_text(
        '[mcp_servers.docs]\ncommand = "npx"\n',
        encoding="utf-8",
    )
    mcp_package = project / "services" / "review-mcp"
    mcp_source = mcp_package / "src" / "review_mcp" / "server.py"
    mcp_source.parent.mkdir(parents=True)
    (mcp_package / "pyproject.toml").write_text(
        """[project]
name = "review-mcp"
version = "1.0.0"
dependencies = ["mcp>=1"]

[project.scripts]
review-mcp = "review_mcp.server:main"
""",
        encoding="utf-8",
    )
    mcp_source.write_text(
        "from mcp.server.fastmcp import FastMCP\n"
        "server = FastMCP('review')\n"
        "server.run(transport='stdio')\n",
        encoding="utf-8",
    )

    plugins = home / ".claude" / "plugins"
    cache = plugins / "cache" / "acme" / "reviewer" / "1.0.0"
    (cache / ".claude-plugin").mkdir(parents=True)
    _write(cache / ".claude-plugin" / "plugin.json", {"name": "reviewer"})
    _write(
        plugins / "known_marketplaces.json",
        {"acme": {"source": {"source": "github", "repo": "acme/tools"}}},
    )
    _write(
        plugins / "marketplaces" / "acme" / ".claude-plugin" / "marketplace.json",
        {
            "name": "acme",
            "plugins": [{"name": "reviewer", "source": "./plugins/reviewer"}],
        },
    )
    _write(
        plugins / "installed_plugins.json",
        {
            "version": 2,
            "plugins": {
                "reviewer@acme": [
                    {
                        "scope": "user",
                        "installPath": str(cache),
                        "gitCommitSha": "a" * 40,
                        "version": "1.0.0",
                    }
                ]
            },
        },
    )
    before = _snapshot(tmp_path)
    environment = {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
    }

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_stp_cli",
            "component",
            "discover",
            "--root",
            str(project),
            "--json",
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    envelope = cast(dict[str, object], json.loads(result.stdout))
    data = cast(dict[str, object], envelope["data"])
    found = cast(list[dict[str, object]], data["components"])
    github = next(item for item in found if item["component_type"] == "plugin")
    provenance = cast(dict[str, object], github["provenance"])
    assert provenance["kind"] == "github"
    assert provenance["state"] == "exact"
    assert provenance["repository"] == "https://github.com/acme/tools"
    assert provenance["revision"] == "a" * 40
    assert any(
        item["harness_id"] == "pi"
        and item["scope"] == "project"
        and str(item["source_path"]).endswith("review.ts")
        for item in found
    )
    assert any(
        item["harness_id"] == "codex"
        and item["component_type"] == "plugin"
        and str(item["source_path"]).endswith("plugins/rldyour-flow")
        for item in found
    )
    assert any(
        item["harness_id"] == "codex"
        and item["component_type"] == "hook"
        and str(item["source_path"]).endswith("plugins/rldyour-flow/hooks")
        for item in found
    )
    assert not any(str(item["source_path"]).endswith("useFoo.ts") for item in found)
    mcp = next(item for item in found if item.get("native_role") == "mcp_server")
    assert str(mcp["source_path"]).endswith("services/review-mcp")
    assert mcp["entry_points"] == ["review_mcp.server:main"]
    assert mcp["transport_capabilities"] == ["stdio"]
    assert mcp["evidence_refs"] == ["pyproject.toml", "src/review_mcp/server.py"]
    clients = [item for item in found if item.get("native_role") == "mcp_client_config"]
    assert any(item["harness_id"] == "claude-code" for item in clients)
    assert any(
        item["harness_id"] == "codex" and item.get("evidence_refs") == ["mcp_servers.docs"]
        for item in clients
    )
    assert "npx" not in result.stdout
    assert data["diagnostics"] == []
    assert _snapshot(tmp_path) == before


def test_project_instructions_are_found_at_both_claude_placements(tmp_path: Path) -> None:
    """Claude Code reads project instructions from the root and from `.claude/`.

    Only the root placement was declared, so a repository that keeps its
    instructions at `.claude/CLAUDE.md` had them invisible to discovery — this
    repository is one, which is how the gap was found. Observed directly: a
    Claude Code session opened here reports `.claude/CLAUDE.md` as "project
    instructions, checked into the codebase".
    """
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    (project / ".claude").mkdir(parents=True)
    (project / "CLAUDE.md").write_text("# root\n", encoding="utf-8")
    (project / ".claude" / "CLAUDE.md").write_text("# nested\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_stp_cli",
            "component",
            "discover",
            "--root",
            str(project),
            "--json",
        ],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
        },
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = cast(dict[str, object], json.loads(result.stdout))
    data = cast(dict[str, object], payload["data"])
    found = {
        Path(cast(str, row["source_path"])).relative_to(project).as_posix()
        for row in cast(list[dict[str, object]], data["components"])
        if row["component_type"] == "instruction" and row["scope"] != "global"
    }
    assert found == {"CLAUDE.md", ".claude/CLAUDE.md"}, found


def test_every_declared_component_kind_is_discovered_in_one_project(tmp_path: Path) -> None:
    """All eight kinds, in one tree, through the real CLI.

    `COMPONENT_TYPES` is a closed vocabulary of eight, and each kind is
    declared by its own rules. What nothing asserted is that the eight
    *together* come back from a project that holds all of them — the existing
    coverage checks one adapter, or one placement, at a time.

    The gap that motivated this was found by hand: `.claude/CLAUDE.md` was
    absent from the catalogue of placements, so this repository was invisible
    to its own discovery. Finding that took a sandbox and a person. Nothing
    stops the next omitted placement, and a kind that no rule reaches produces
    no error — it produces silence, which is why the assertion is on the set.

    Written against the live catalogue at a moment when the published corpus
    held six of the eight: `mcp` and `hook` had never been published, so the
    path for them had never run end to end. It runs here.
    """
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"

    (project / ".claude" / "skills" / "demo").mkdir(parents=True)
    (project / ".claude" / "skills" / "demo" / "SKILL.md").write_text(
        "---\nname: demo\ndescription: A demo skill.\n---\n# Demo\n", encoding="utf-8"
    )
    (project / ".claude" / "agents").mkdir(parents=True)
    (project / ".claude" / "agents" / "reviewer.md").write_text(
        "---\nname: reviewer\ndescription: A demo agent.\n---\nReview.\n", encoding="utf-8"
    )
    (project / ".claude" / "commands").mkdir(parents=True)
    (project / ".claude" / "commands" / "ship.md").write_text(
        "---\ndescription: A demo command.\n---\nShip.\n", encoding="utf-8"
    )
    (project / ".claude" / "CLAUDE.md").write_text("# instructions\n", encoding="utf-8")
    _write(project / ".claude" / "settings.json", {"permissions": {"allow": ["Bash(ls:*)"]}})
    _write(project / ".mcp.json", {"mcpServers": {"demo": {"command": "demo", "args": []}}})
    _write(
        project / ".codex" / "hooks.json",
        {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": cast(list[object], [])}]}},
    )
    # A plugin is a manifest under `plugins/<name>/`, not at the project root.
    # Getting that wrong is what an unwritten fixture costs: the first attempt
    # put the manifest in the root and read the empty result as a defect.
    _write(project / "plugins" / "demo-pack" / ".claude-plugin" / "plugin.json", {"name": "demo"})

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_stp_cli",
            "component",
            "discover",
            "--root",
            str(project),
            "--json",
        ],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
        },
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = cast(dict[str, object], json.loads(result.stdout))
    data = cast(dict[str, object], payload["data"])
    rows = cast(list[dict[str, object]], data["components"])
    kinds = {cast(str, row["component_type"]) for row in rows if row["scope"] == "project"}
    declared = {"instruction", "skill", "mcp", "hook", "command", "agent", "plugin", "setting"}
    assert kinds == declared, f"discovery missed {sorted(declared - kinds)}; rows={rows!r}"
