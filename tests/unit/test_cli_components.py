"""Discovery looks and adoption takes, and the gap between them is the design."""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import components, content, lifecycle, mcp_clients
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_contracts.sync_payload import check_sync_payload

SECRET = "AKIAIOSFODNN7EXAMPLE"


@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        yield connection


@pytest.fixture
def harness_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A home holding native layouts for every supported harness."""
    home = tmp_path / "home"
    claude = home / ".claude"
    (claude / "skills" / "reviewing").mkdir(parents=True)
    (claude / "agents").mkdir()
    (claude / "CLAUDE.md").write_bytes(b"# global instruction\n")
    (claude / "skills" / "reviewing" / "SKILL.md").write_bytes(b"# reviewing\n")
    (claude / "agents" / "planner.md").write_text("# planner\n", encoding="utf-8")
    (claude / "settings.json").write_text('{"model": "opus"}', encoding="utf-8")

    codex = home / ".codex"
    codex.mkdir()
    (codex / "AGENTS.md").write_text("# codex instruction\n", encoding="utf-8")
    (codex / "config.toml").write_text('model = "gpt"\n', encoding="utf-8")

    shared_skill = home / ".agents" / "skills" / "shared"
    shared_skill.mkdir(parents=True)
    (shared_skill / "SKILL.md").write_text("# shared\n", encoding="utf-8")

    pi = home / ".pi" / "agent"
    (pi / "skills" / "testing").mkdir(parents=True)
    (pi / "extensions").mkdir()
    (pi / "prompts").mkdir()
    (pi / "skills" / "testing" / "SKILL.md").write_text("# testing\n", encoding="utf-8")
    (pi / "extensions" / "trace.ts").write_text("export default {}\n", encoding="utf-8")
    (pi / "prompts" / "review.md").write_text("review\n", encoding="utf-8")
    (pi / "settings.json").write_text("{}\n", encoding="utf-8")

    opencode = home / ".config" / "opencode"
    (opencode / "agents").mkdir(parents=True)
    (opencode / "commands").mkdir()
    (opencode / "plugins").mkdir()
    (opencode / "skills" / "quality").mkdir(parents=True)
    (opencode / "agents" / "planner.md").write_text("# planner\n", encoding="utf-8")
    (opencode / "commands" / "ship.md").write_text("# ship\n", encoding="utf-8")
    (opencode / "plugins" / "audit.ts").write_text("export {}\n", encoding="utf-8")
    (opencode / "skills" / "quality" / "SKILL.md").write_text("# quality\n", encoding="utf-8")
    (opencode / "opencode.json").write_text("{}\n", encoding="utf-8")

    grok = home / ".grok"
    (grok / "skills" / "research").mkdir(parents=True)
    (grok / "plugins").mkdir()
    (grok / "plugins" / "marketplaces").mkdir()
    (grok / "hooks").mkdir()
    (grok / "skills" / "research" / "SKILL.md").write_text("# research\n", encoding="utf-8")
    (grok / "plugins" / "local.py").write_text("PLUGIN = True\n", encoding="utf-8")
    (grok / "hooks" / "guard.py").write_text("HOOK = True\n", encoding="utf-8")
    (grok / "config.toml").write_text("# grok\n", encoding="utf-8")

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    return home


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "work"
    (root / ".claude" / "commands").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# project rules\n", encoding="utf-8")
    (root / ".claude" / "commands" / "ship.md").write_text("# ship\n", encoding="utf-8")
    (root / ".mcp.json").write_text('{"servers": {}}', encoding="utf-8")
    (root / ".codex").mkdir()
    (root / ".codex" / "config.toml").write_text('model = "gpt"\n', encoding="utf-8")
    (root / ".pi" / "extensions").mkdir(parents=True)
    (root / ".pi" / "extensions" / "local.ts").write_text("export {}\n", encoding="utf-8")
    (root / ".opencode" / "agents").mkdir(parents=True)
    (root / ".opencode" / "agents" / "reviewer.md").write_text("# reviewer\n", encoding="utf-8")
    (root / ".grok" / "hooks").mkdir(parents=True)
    (root / ".grok" / "hooks" / "check.py").write_text("HOOK = True\n", encoding="utf-8")
    (root / ".agents" / "skills" / "project").mkdir(parents=True)
    (root / ".agents" / "skills" / "project" / "SKILL.md").write_text(
        "# project\n", encoding="utf-8"
    )
    return root


def test_the_declared_layouts_are_sound() -> None:
    # Every rule names one of the eight kinds, a harness a detector can find,
    # and the documentation the layout was read from. A rule for a harness
    # nothing detects would never be reached and nothing else would say so.
    assert components.declared_consistently() == ()


def test_discovery_finds_the_global_roots_and_writes_nothing(harness_home: Path) -> None:
    before = sorted(path for path in harness_home.rglob("*"))
    found = components.discover()

    kinds = {(item.harness_id, item.component_type) for item in found}
    assert ("claude-code", "instruction") in kinds
    assert ("claude-code", "skill") in kinds
    assert ("claude-code", "setting") in kinds
    assert ("codex", "instruction") in kinds
    assert ("codex", "setting") in kinds
    assert ("pi", "plugin") in kinds
    assert ("opencode", "agent") in kinds
    assert ("grok-build", "hook") in kinds
    assert ("", "skill") in kinds
    assert {item.harness_id for item in found if item.harness_id} == {
        "claude-code",
        "codex",
        "pi",
        "opencode",
        "grok-build",
    }
    assert all(item.scope == "global" for item in found)
    assert not any(item.source_path.endswith("/plugins/marketplaces") for item in found)

    # `REQ-518`: discovery changes nothing at all.
    assert sorted(path for path in harness_home.rglob("*")) == before


def test_a_claude_plugin_pack_is_a_project_inventory(tmp_path: Path) -> None:
    """A complete Claude setup does not have to put anything in `.claude/`.

    The canonical shape is a marketplace repository: `.claude-plugin/plugin.json`
    inside each `plugins/<name>/`, with the skills, agents, commands and hooks
    held there. The project rules for Claude were six paths under `.claude/`
    plus `CLAUDE.md`, so such a repository answered **zero** project-scoped
    components while the same family pack for Codex answered fifty-five
    (`#378`).
    """
    pack = tmp_path / "rldyour-claudecode"
    plugin = pack / "plugins" / "rldyour-flow"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text('{"name": "flow"}', encoding="utf-8")
    (plugin / "skills" / "ry-start").mkdir(parents=True)
    (plugin / "skills" / "ry-start" / "SKILL.md").write_text("# start\n", encoding="utf-8")
    (plugin / "agents").mkdir()
    (plugin / "agents" / "reviewer.md").write_text("# reviewer\n", encoding="utf-8")
    (plugin / "commands").mkdir()
    (plugin / "commands" / "ship.md").write_text("# ship\n", encoding="utf-8")
    (plugin / "hooks").mkdir()
    (plugin / "hooks" / "hooks.json").write_text("{}", encoding="utf-8")
    # Where a pack's MCP servers actually live. Measured on a real machine
    # before it was declared: eleven working servers sit in a plugin's own
    # `.mcp.json`, while `~/.claude.json`, `~/.claude/settings.json` and
    # `~/.claude/.mcp.json` carry no MCP key at all — which is how a machine
    # visibly running them answered `mcp: 0` (`#377`).
    (plugin / ".mcp.json").write_text('{"mcpServers": {"serena": {}}}', encoding="utf-8")

    found = [item for item in components.discover(project=pack) if item.scope == "project"]
    kinds = {(item.harness_id, item.component_type) for item in found}

    assert ("claude-code", "plugin") in kinds
    assert ("claude-code", "skill") in kinds
    assert ("claude-code", "agent") in kinds
    assert ("claude-code", "command") in kinds
    assert ("claude-code", "hook") in kinds
    assert ("claude-code", "mcp") in kinds

    # The role is what a consumer routes on, and discovery never opens the file
    # to decide it: nothing here reads a token, a URL or an `.env` body.
    mcp = [item for item in found if item.component_type == "mcp"]
    assert [item.native_role for item in mcp] == ["mcp_client_config"]


def test_a_cursor_plugin_pack_is_a_project_inventory(tmp_path: Path) -> None:
    """Cursor ships components inside `.cursor-plugin/plugin.json`, not beside it.

    The measured OpenNetwork nddev-builder pack declares rules, skills, agents
    and commands. It does not declare hooks or MCP, and discovery must not
    invent those kinds from a neighbouring directory name.
    """
    pack = tmp_path / "cursor-home"
    plugin = pack / "plugins" / "nddev-builder"
    (plugin / ".cursor-plugin").mkdir(parents=True)
    (plugin / ".cursor-plugin" / "plugin.json").write_text(
        '{"name": "nddev-builder", "rules": "./rules", "skills": "./skills",'
        ' "agents": "./agents", "commands": "./commands"}\n',
        encoding="utf-8",
    )
    (plugin / "rules").mkdir()
    (plugin / "rules" / "nddev-builder.mdc").write_text("# rule\n", encoding="utf-8")
    (plugin / "skills" / "nddev-builder").mkdir(parents=True)
    (plugin / "skills" / "nddev-builder" / "SKILL.md").write_text("# skill\n", encoding="utf-8")
    (plugin / "agents").mkdir()
    (plugin / "agents" / "nddev-builder.md").write_text("# agent\n", encoding="utf-8")
    (plugin / "commands").mkdir()
    (plugin / "commands" / "nddev-validate.md").write_text("# command\n", encoding="utf-8")
    (plugin / "hooks").mkdir()
    (plugin / "hooks" / "unrelated.sh").write_text("#!/bin/sh\n", encoding="utf-8")

    found = [item for item in components.discover(project=pack) if item.scope == "project"]
    cursor = [item for item in found if item.harness_id == "cursor"]
    kinds = {item.component_type for item in cursor}

    assert kinds == {"plugin", "skill", "agent", "command", "instruction"}
    assert any(item.absolute == plugin for item in cursor)
    assert any(item.absolute == plugin / "skills" / "nddev-builder" for item in cursor)
    assert any(item.absolute == plugin / "agents" / "nddev-builder.md" for item in cursor)
    assert any(item.absolute == plugin / "commands" / "nddev-validate.md" for item in cursor)
    assert any(item.absolute == plugin / "rules" / "nddev-builder.mdc" for item in cursor)
    assert not any(item.component_type in {"hook", "mcp"} for item in cursor)
    assert not any(item.absolute == plugin / "hooks" for item in cursor)


def test_a_plugins_directory_without_a_manifest_is_not_a_pack(tmp_path: Path) -> None:
    """Resembling a plugin is not being one, and the refusal is not silent."""
    pack = tmp_path / "looks-like-one"
    (pack / "plugins" / "not-a-plugin" / "skills" / "thing").mkdir(parents=True)
    (pack / "plugins" / "not-a-plugin" / "skills" / "thing" / "SKILL.md").write_text(
        "# thing\n", encoding="utf-8"
    )

    report = components.discover_report(project=pack)
    found = [item for item in report.components if item.scope == "project"]

    assert not [item for item in found if item.component_type == "plugin"]
    assert not [item for item in found if item.component_type == "skill"]
    assert any(
        item.code == "unsupported_manifest" and item.source == "project-plugins"
        for item in report.diagnostics
    )


def test_a_backup_copy_and_a_directory_listing_are_not_components(
    harness_home: Path,
) -> None:
    """A directory layout offers its members, not everything that sits in it.

    Both shapes were reported on a live machine: `component discover` named
    `ai-repo-safety.bak-20260801-103930` a skill beside the live one, and
    `index.json` a skill, a command and a plugin in three separate directories.
    An inventory that lists a user's archived copy as a component describes a
    machine nobody has (`#379`).
    """
    skills = harness_home / ".config" / "opencode" / "skills"
    (skills / "quality.bak-20260801-103930").mkdir(parents=True)
    (skills / "quality.bak-20260801-103930" / "SKILL.md").write_text("# old\n", encoding="utf-8")
    (skills / "index.json").write_text('{"skills": ["quality"]}', encoding="utf-8")
    commands = harness_home / ".config" / "opencode" / "commands"
    (commands / "ship.md.orig").write_text("# older ship\n", encoding="utf-8")
    (commands / "notes.md~").write_text("# editor leftover\n", encoding="utf-8")

    found = components.discover()
    offered = {Path(item.source_path).name for item in found}

    assert "quality" in offered, "the live skill has to survive the filter"
    assert "ship.md" in offered
    assert "quality.bak-20260801-103930" not in offered
    assert "index.json" not in offered
    assert "ship.md.orig" not in offered
    assert "notes.md~" not in offered


def test_discovery_reports_a_project_separately(harness_home: Path, project: Path) -> None:
    found = components.discover(project=project)
    inside = [item for item in found if item.scope == "project"]

    paths = {item.source_path for item in inside}
    assert any(path.endswith("AGENTS.md") for path in paths)
    assert any(path.endswith("ship.md") for path in paths)
    assert any(path.endswith(".mcp.json") for path in paths)
    assert {item.harness_id for item in inside if item.harness_id} >= {
        "claude-code",
        "codex",
        "pi",
        "opencode",
        "grok-build",
    }

    # A project `AGENTS.md` is the cross-harness convention and belongs to no
    # single harness, so it claims none rather than claiming one at random.
    agents = next(item for item in inside if Path(item.source_path).name == "AGENTS.md")
    assert agents.harness_id == ""


def test_portable_root_and_nested_skill_families_are_discovered_and_adoptable(
    registry: sqlite3.Connection, harness_home: Path, tmp_path: Path
) -> None:
    repository = tmp_path / "portable"
    repository.mkdir()
    root_manifest = repository / "SKILL.md"
    root_manifest.write_text("# root skill\n", encoding="utf-8")
    first = repository / "skills" / "review"
    nested = repository / "skills" / "families" / "security" / "audit"
    first.mkdir(parents=True)
    nested.mkdir(parents=True)
    (first / "SKILL.md").write_text("# review\n", encoding="utf-8")
    (nested / "SKILL.md").write_text("# audit\n", encoding="utf-8")

    report = components.discover_report(project=repository)
    portable = [
        item for item in report.components if item.layout_source == components.PORTABLE_SKILL_SOURCE
    ]

    assert {item.absolute for item in portable} == {root_manifest, first, nested}
    assert all(item.component_type == "skill" for item in portable)
    assert all(item.harness_id == "" for item in portable)
    assert all(item.provenance.state == "local" for item in portable)
    assert len({item.candidate_id for item in portable}) == 3
    stored = components.adopt(
        registry, next(item for item in portable if item.absolute == first), device_id="device_test"
    )
    facts = stored.envelope.model_dump(mode="json")["facts"]
    assert facts["component_type"]["value"] == "skill"
    assert facts["content_format"]["value"] == components.COMPONENT_TREE_FORMAT


def test_portable_skill_discovery_skips_vendor_fixtures_and_link_escapes(
    harness_home: Path, tmp_path: Path
) -> None:
    repository = tmp_path / "portable"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "SKILL.md").write_text("# outside\n", encoding="utf-8")
    for name in ("vendor", "fixtures", "node_modules", "cache"):
        hidden = repository / "skills" / name / "not-a-candidate"
        hidden.mkdir(parents=True)
        (hidden / "SKILL.md").write_text("# excluded\n", encoding="utf-8")
    (repository / "skills" / "linked").symlink_to(outside, target_is_directory=True)

    found = components.discover(project=repository)

    assert not any(item.layout_source == components.PORTABLE_SKILL_SOURCE for item in found)

    alias = tmp_path / "portable-alias"
    alias.symlink_to(repository, target_is_directory=True)
    report = components.discover_report(project=alias)
    assert not any(
        item.layout_source == components.PORTABLE_SKILL_SOURCE for item in report.components
    )
    assert any("root is a link" in item.reason for item in report.diagnostics)


def test_portable_skill_walk_reports_its_bound_without_reading_beyond_it(
    harness_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "portable"
    for name in ("a", "b", "c"):
        place = repository / "skills" / name / "nested"
        place.mkdir(parents=True)
        (place / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
    monkeypatch.setattr(components, "MAX_PORTABLE_SKILL_DIRECTORIES", 1)

    report = components.discover_report(project=repository)

    assert any(item.code == "bounded_limit" for item in report.diagnostics)
    assert (
        len(
            [
                item
                for item in report.components
                if item.layout_source == components.PORTABLE_SKILL_SOURCE
            ]
        )
        < 3
    )


def test_codex_project_hooks_agents_and_manifest_backed_plugins_are_bounded(
    registry: sqlite3.Connection, harness_home: Path, tmp_path: Path
) -> None:
    project = tmp_path / "codex-project"
    (project / ".codex" / "agents").mkdir(parents=True)
    (project / ".codex" / "agents" / "reviewer.toml").write_text(
        'name = "reviewer"\n', encoding="utf-8"
    )
    (project / ".codex" / "hooks.json").write_text('{"hooks": {}}\n', encoding="utf-8")
    plugin = project / "plugins" / "rldyour-flow"
    (plugin / ".codex-plugin").mkdir(parents=True)
    (plugin / ".codex-plugin" / "plugin.json").write_text(
        '{"name": "rldyour-flow"}\n', encoding="utf-8"
    )
    (plugin / "skills" / "flow").mkdir(parents=True)
    (plugin / "skills" / "flow" / "SKILL.md").write_text("# flow\n", encoding="utf-8")
    (plugin / "hooks").mkdir()
    (plugin / "hooks" / "hooks.json").write_text('{"hooks": {}}\n', encoding="utf-8")
    (plugin / "hooks" / "guard.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    frontend = project / "src" / "hooks"
    frontend.mkdir(parents=True)
    (frontend / "useFoo.ts").write_text("export const useFoo = () => 1\n", encoding="utf-8")

    report = components.discover_report(project=project)
    codex = [item for item in report.components if item.harness_id == "codex"]

    assert {(item.component_type, item.absolute) for item in codex} >= {
        ("agent", project / ".codex" / "agents" / "reviewer.toml"),
        ("hook", project / ".codex" / "hooks.json"),
        ("plugin", plugin),
        ("skill", plugin / "skills" / "flow"),
        ("hook", plugin / "hooks"),
    }
    assert not any(item.absolute == frontend or frontend in item.absolute.parents for item in codex)
    hook = next(item for item in codex if item.absolute == plugin / "hooks")
    stored = components.adopt(registry, hook, device_id="device_test")
    facts = stored.envelope.model_dump(mode="json")["facts"]
    expanded = components.expand(
        content.get(registry, facts["content_digest"]["value"]),
        facts["content_format"]["value"],
    )
    assert [item.path for item in expanded] == ["guard.sh", "hooks.json"]


def test_legacy_codex_markdown_is_explained_without_becoming_an_instruction(
    harness_home: Path, tmp_path: Path
) -> None:
    project = tmp_path / "legacy"
    project.mkdir()
    legacy = project / "CODEX.md"
    legacy.write_text("# legacy\n", encoding="utf-8")

    report = components.discover_report(project=project)

    assert not any(item.absolute == legacy for item in report.components)
    assert any(
        item.code == "unsupported_manifest" and "AGENTS.md" in item.reason
        for item in report.diagnostics
    )


def test_manifest_backed_mcp_server_is_adopted_with_role_and_capabilities(
    registry: sqlite3.Connection, harness_home: Path, tmp_path: Path
) -> None:
    project = tmp_path / "mcp-monorepo"
    package = project / "services" / "weather"
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

    server = next(
        item for item in components.discover(project=project) if item.native_role == "mcp_server"
    )
    stored = components.adopt(registry, server, device_id="device_test")
    facts = stored.envelope.model_dump(mode="json")["facts"]

    assert server.absolute == package
    assert server.harness_id == ""
    assert server.entry_points == ("weather.server:main",)
    assert server.transport_capabilities == ("stdio",)
    assert facts["native_role"]["value"] == "mcp_server"
    assert facts["entry_points"]["value"] == ["weather.server:main"]
    assert facts["transport_capabilities"]["value"] == ["stdio"]
    assert facts["evidence_refs"]["value"] == [
        "pyproject.toml",
        "src/weather/server.py",
    ]


def test_discovery_identity_and_layout_provenance_are_stable(harness_home: Path) -> None:
    first = components.discover()
    second = components.discover()

    assert [item.candidate_id for item in first] == [item.candidate_id for item in second]
    assert len({item.candidate_id for item in first}) == len(first)
    assert all(item.candidate_id.startswith("sha256:") for item in first)
    assert all(len(item.candidate_id) == 71 for item in first)
    assert all(item.layout_source for item in first)

    shared = next(item for item in first if item.source_path.endswith("/.agents/skills/shared"))
    assert shared.harness_id == ""
    assert shared.layout_source == "learn.chatgpt.com/docs/build-skills"


def test_global_discovery_honours_every_documented_root_override(tmp_path: Path) -> None:
    home = tmp_path / "home"
    environment = {"HOME": str(home)}
    expected: dict[str, tuple[str, str]] = {
        "codex": ("CODEX_HOME", "config.toml"),
        "pi": ("PI_CODING_AGENT_DIR", "settings.json"),
        "opencode": ("OPENCODE_CONFIG_DIR", "opencode.json"),
        "grok-build": ("GROK_HOME", "config.toml"),
    }
    for harness_id, (variable, filename) in expected.items():
        root = tmp_path / "moved" / harness_id
        root.mkdir(parents=True)
        (root / filename).write_text("{}\n", encoding="utf-8")
        environment[variable] = str(root)

    found = components.discover(environment=environment)
    assert {item.harness_id for item in found} >= set(expected)
    assert not any(str(home) in str(item.absolute) for item in found)


def test_discovery_never_opens_a_file_named_as_a_credential(
    harness_home: Path, project: Path
) -> None:
    planted = project / ".claude" / "commands" / ".env"
    planted.write_text(f"AWS_SECRET_ACCESS_KEY={SECRET}\n", encoding="utf-8")

    found = components.discover(project=project)
    flagged = next(item for item in found if item.source_path.endswith(".env"))

    assert flagged.holds_secret
    assert "never read" in flagged.reason
    # The whole listing carries nothing from inside it.
    assert SECRET not in str(found)


def test_an_absent_root_is_simply_not_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "empty"))
    assert components.discover() == ()
    assert components.discover(project=tmp_path / "nothing-here") == ()


def test_adoption_registers_the_component_and_stores_its_bytes(
    registry: sqlite3.Connection, harness_home: Path
) -> None:
    found = next(
        item
        for item in components.discover()
        if item.component_type == "instruction" and item.harness_id == "claude-code"
    )
    stored = components.adopt(registry, found, device_id="device_test")

    facts = stored.envelope.model_dump(mode="json")["facts"]
    assert set(facts) == set(components.ADOPTED_FIELDS)
    assert facts["component_type"]["value"] == "instruction"
    assert facts["scope"]["value"] == "global"

    # The passport records the address of the bytes, not the bytes.
    digest = facts["content_digest"]["value"]
    assert content.get(registry, digest) == b"# global instruction\n"
    assert "global instruction" not in str(facts)


def test_an_adopted_passport_carries_only_the_allowlist(
    registry: sqlite3.Connection, harness_home: Path
) -> None:
    found = next(item for item in components.discover() if item.component_type == "setting")
    stored = components.adopt(registry, found, device_id="device_test")
    facts = stored.envelope.model_dump(mode="json")["facts"]

    # Built by naming what goes in. A passport assembled by removing keys would
    # have to be right about every key a harness invents next.
    assert set(facts) == set(components.ADOPTED_FIELDS)
    assert "/home/" not in facts["source_path"]["value"]


def test_two_identical_components_share_one_stored_object(
    registry: sqlite3.Connection, harness_home: Path, project: Path
) -> None:
    (project / "CLAUDE.md").write_bytes(b"# global instruction\n")
    found = components.discover(project=project)
    same = [item for item in found if item.source_path.endswith("CLAUDE.md")]
    assert len(same) == 2

    digests = {
        components.adopt(registry, item, device_id="device_test").envelope.model_dump(mode="json")[
            "facts"
        ]["content_digest"]["value"]
        for item in same
    }
    # One object, two registrations: content addressing makes that automatic.
    assert len(digests) == 1
    assert registry.execute("SELECT COUNT(*) AS n FROM content").fetchone()["n"] == 1
    assert registry.execute("SELECT COUNT(*) AS n FROM entity").fetchone()["n"] == 2


def test_adopting_a_credential_file_is_refused_outright(
    registry: sqlite3.Connection, harness_home: Path, project: Path
) -> None:
    (project / ".claude" / "commands" / ".env").write_text(f"KEY={SECRET}\n", encoding="utf-8")
    flagged = next(
        item for item in components.discover(project=project) if item.source_path.endswith(".env")
    )

    # Not "adopted with its content skipped": a passport holding its path and
    # size still syncs, and that is not a promise worth making.
    with pytest.raises(CliFailure, match="named as a credential file") as raised:
        components.adopt(registry, flagged, device_id="device_test")
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    assert registry.execute("SELECT COUNT(*) AS n FROM entity").fetchone()["n"] == 0


def test_adopting_a_skill_directory_preserves_its_complete_tree(
    registry: sqlite3.Connection, harness_home: Path
) -> None:
    found = next(
        item
        for item in components.discover()
        if item.component_type == "skill" and item.harness_id == "claude-code"
    )
    (found.absolute / "references").mkdir()
    # write_bytes keeps LF even when the host default is CRLF (Windows).
    (found.absolute / "references" / "guide.md").write_bytes(b"guide\n")
    stored = components.adopt(registry, found, device_id="device_test")
    facts = stored.envelope.model_dump(mode="json")["facts"]
    digest = facts["content_digest"]["value"]
    expanded = components.expand(content.get(registry, digest), facts["content_format"]["value"])
    assert [(item.path, item.content) for item in expanded] == [
        ("SKILL.md", b"# reviewing\n"),
        ("references/guide.md", b"guide\n"),
    ]


def test_a_grok_build_plugin_root_is_a_complete_directory_artifact(tmp_path: Path) -> None:
    plugin = tmp_path / "nddev-builder"
    (plugin / "skills" / "review").mkdir(parents=True)
    (plugin / "plugin.json").write_text('{"name":"nddev-builder"}\n', encoding="utf-8")
    (plugin / "skills" / "review" / "SKILL.md").write_text("# Review\n", encoding="utf-8")

    held = components._read(plugin)  # pyright: ignore[reportPrivateUsage]

    assert held.format == components.COMPONENT_TREE_FORMAT
    assert [item.path for item in components.expand(held.payload, held.format)] == [
        "plugin.json",
        "skills/review/SKILL.md",
    ]


def test_directory_artifacts_are_deterministic_and_reject_links_and_secret_names(
    registry: sqlite3.Connection, harness_home: Path, tmp_path: Path
) -> None:
    skills = harness_home / ".claude" / "skills"
    first = skills / "deterministic"
    (first / "references").mkdir(parents=True)
    (first / "references" / "b.md").write_text("b\n", encoding="utf-8")
    (first / "SKILL.md").write_text("# deterministic\n", encoding="utf-8")
    before = components._read(first)  # pyright: ignore[reportPrivateUsage]
    (first / "SKILL.md").touch()
    (first / "references" / "b.md").touch()
    after = components._read(first)  # pyright: ignore[reportPrivateUsage]
    assert before == after

    linked = skills / "linked"
    linked.mkdir()
    (linked / "SKILL.md").write_text("# linked\n", encoding="utf-8")
    (linked / "outside").symlink_to(tmp_path / "outside")
    found = next(item for item in components.discover() if item.absolute == linked)
    with pytest.raises(CliFailure, match="contains a link"):
        components.adopt(registry, found, device_id="device_test")

    hard = skills / "hard"
    hard.mkdir()
    manifest = hard / "SKILL.md"
    manifest.write_text("# hard\n", encoding="utf-8")
    os.link(manifest, hard / "copy.md")
    found = next(item for item in components.discover() if item.absolute == hard)
    with pytest.raises(CliFailure, match="hard-linked"):
        components.adopt(registry, found, device_id="device_test")

    secret = skills / "secret"
    secret.mkdir()
    (secret / "SKILL.md").write_text("# secret\n", encoding="utf-8")
    (secret / ".env").write_text(f"KEY={SECRET}\n", encoding="utf-8")
    found = next(item for item in components.discover() if item.absolute == secret)
    with pytest.raises(CliFailure, match="credential-named"):
        components.adopt(registry, found, device_id="device_test")


def test_a_directory_with_no_manifest_and_an_oversized_file_are_named(
    registry: sqlite3.Connection, harness_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (harness_home / ".claude" / "skills" / "empty").mkdir()
    bare = next(item for item in components.discover() if item.source_path.endswith("empty"))
    with pytest.raises(CliFailure, match="no manifest to adopt"):
        components.adopt(registry, bare, device_id="device_test")

    monkeypatch.setattr(components, "MAX_COMPONENT_BYTES", 4)
    big = next(item for item in components.discover() if item.component_type == "instruction")
    with pytest.raises(CliFailure, match="larger than one may be"):
        components.adopt(registry, big, device_id="device_test")


def test_adopting_something_that_vanished_is_a_typed_refusal(
    registry: sqlite3.Connection, harness_home: Path
) -> None:
    found = next(item for item in components.discover() if item.component_type == "instruction")
    found.absolute.unlink()

    with pytest.raises(CliFailure, match="could not be read") as raised:
        components.adopt(registry, found, device_id="device_test")
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_a_failed_adoption_settles_the_journal(
    registry: sqlite3.Connection, harness_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_stp_cli.local import revisions

    def refuse(*_args: object, **_kwargs: object) -> revisions.StoredRevision:
        raise OSError("the disk went away mid-commit")

    found = next(item for item in components.discover() if item.component_type == "instruction")
    monkeypatch.setattr(revisions, "commit", refuse)

    with pytest.raises(OSError, match="mid-commit"):
        components.adopt(registry, found, device_id="device_test")
    rows = registry.execute("SELECT state FROM operation ORDER BY started_at DESC").fetchall()
    assert rows and rows[0]["state"] == "failed"


def test_an_adopted_component_can_be_marked_deleted(
    registry: sqlite3.Connection, harness_home: Path
) -> None:
    found = next(item for item in components.discover() if item.component_type == "instruction")
    stored = components.adopt(registry, found, device_id="device_test")
    assert lifecycle.registrable(registry, stored) is True

    lifecycle.entomb(
        registry, stored.stable_id, reason="no longer used", at="2026-08-07T10:00:00.000Z"
    )
    assert lifecycle.registrable(registry, stored) is False


# --- commands -------------------------------------------------------------


def test_the_discover_command_reports_the_project_it_searched(
    harness_home: Path, project: Path
) -> None:
    from ai_stp_cli.commands import component as command

    answer = command.discover({"root": str(project)}).payload
    assert answer.project == str(project)
    assert any(item.scope == "project" for item in answer.components)
    assert any(item.scope == "global" for item in answer.components)
    assert all(item.candidate_id.startswith("sha256:") for item in answer.components)
    assert all(item.layout_source for item in answer.components)

    without = command.discover({}).payload
    assert without.project is None
    assert all(item.scope == "global" for item in without.components)


def test_the_adopt_command_takes_a_path_and_refuses_an_unknown_one(
    harness_home: Path, project: Path
) -> None:
    from ai_stp_cli.commands import component as command

    view = command.adopt({"path": str(project / "AGENTS.md")}).payload
    assert view.kind == "component"
    assert view.stable_id.startswith("component_")

    with pytest.raises(CliFailure, match="no discovered component"):
        command.adopt({"path": str(project / "not-a-component.txt")})
    with pytest.raises(CliFailure, match="a component path is required"):
        command.adopt({})


def test_the_forget_command_marks_and_refuses_an_unknown_id(
    harness_home: Path, project: Path
) -> None:
    from ai_stp_cli.commands import component as command

    view = command.adopt({"path": str(project / "AGENTS.md")}).payload
    marked = command.forget({"id": view.stable_id, "reason": "done with it"}).payload
    assert marked.stable_id == view.stable_id

    with pytest.raises(CliFailure, match="nothing is registered"):
        command.forget({"id": "component_01J000000000000000000000ZZ"})
    with pytest.raises(CliFailure, match="a stable id is required"):
        command.forget({})


def test_the_consent_commands_record_list_and_withdraw() -> None:
    from ai_stp_cli.commands import component as command

    granted = command.consent_allow({"scope": "publisher", "target": "publisher/acme"}).payload
    assert granted.scope == "publisher"
    assert granted.revoked_at is None
    assert command.consent_list({}).payload.records == [granted]

    withdrawn = command.consent_revoke({"scope": "publisher", "target": "publisher/acme"}).payload
    assert withdrawn.revoked_at is not None
    assert command.consent_list({}).payload.records == []

    with pytest.raises(CliFailure, match="no consent record covers"):
        command.consent_revoke({"scope": "publisher", "target": "publisher/nobody"})


@pytest.mark.parametrize("missing", [{}, {"scope": "publisher"}, {"target": "publisher/acme"}])
def test_a_consent_command_without_both_halves_is_refused(missing: dict[str, str]) -> None:
    from ai_stp_cli.commands import component as command

    with pytest.raises(CliFailure, match="both a scope and a target"):
        command.consent_allow(missing)
    with pytest.raises(CliFailure, match="both a scope and a target"):
        command.consent_revoke(missing)


@pytest.mark.unprivileged
def test_an_unreadable_directory_or_entry_is_skipped_rather_than_fatal(
    harness_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pathlib import Path as RealPath

    closed = harness_home / ".claude" / "skills"
    closed.chmod(0o000)
    try:
        # A directory the user cannot list contributes nothing. Discovery is a
        # read of many places and one refusing is not a reason to answer with
        # none of the others.
        found = components.discover()
        assert not any(item.source_path.endswith("reviewing") for item in found)
        assert any(item.component_type == "instruction" for item in found)
    finally:
        closed.chmod(0o700)

    real_stat = RealPath.stat

    def refuse(self: RealPath, **named: object) -> object:
        if self.name == "CLAUDE.md":
            raise PermissionError("cannot stat")
        return real_stat(self, **named)  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(RealPath, "stat", refuse)
    # An entry that lists but will not measure is still reported, with the
    # reason, rather than dropped: it exists, and that is the fact discovery is
    # for.
    unmeasured = next(
        item for item in components.discover() if item.source_path.endswith("CLAUDE.md")
    )
    assert unmeasured.byte_length is None
    assert "not measurable" in unmeasured.reason


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        (components.Rule("marketplace", "x", "file", "claude-code", "d"), "unknown component type"),
        (components.Rule("skill", "x", "file", "not-a-harness", "d"), "no detector finds harness"),
        (components.Rule("skill", "x", "file", "claude-code", ""), "no documentation recorded"),
        (components.Rule("skill", "x", "file", "", "d", "somewhere"), "unknown global root"),
        (components.Rule("skill", "x", "file", "codex", "d", "home"), "shared home layout"),
    ],
)
def test_a_broken_layout_table_is_reported_by_the_checker(
    rule: components.Rule, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(components, "GLOBAL_RULES", (rule,))
    problems = components.declared_consistently()
    assert any(expected in problem for problem in problems)


def test_doctor_reports_a_broken_layout_table_as_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_stp_cli.commands import doctor

    monkeypatch.setattr(
        components, "GLOBAL_RULES", (components.Rule("skill", "x", "file", "nowhere", "d"),)
    )
    report = doctor.run({}).payload
    check = next(item for item in report.checks if item.name == "component_layouts")
    # A rule naming a harness nothing detects would never match, and discovery
    # would report one fewer kind with nothing saying why.
    assert check.state == "failed"
    assert "no detector finds harness" in check.detail


def test_forgetting_an_entity_with_no_revisions_says_so(
    registry: sqlite3.Connection,
) -> None:
    from ai_stp_cli.commands import component as command

    registry.execute(
        "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
        ("component_01J00000000000000000000020", "2026-08-07T10:00:00.000Z"),
    )
    registry.commit()

    with pytest.raises(CliFailure, match="no revisions to report"):
        command.forget({"id": "component_01J00000000000000000000020"})


def test_a_configuration_root_that_is_a_file_reports_nothing_rather_than_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A path whose parent is a regular file cannot hold anything, and `stat`
    # says so with `NotADirectoryError` rather than `FileNotFoundError`. Both
    # mean "nothing is here"; only one of them is the error people remember to
    # catch.
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").write_text("not a directory at all", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    assert components.discover() == ()


def test_a_project_component_is_adopted_by_naming_its_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guessing the root as the file's parent broke every directory rule.

    A component under `.claude/skills/` would have had its own directory taken
    as the project root, and discovery would then look for
    `.claude/skills/.claude/skills`. Only a component sitting directly in a
    project root — `AGENTS.md` — worked, which is one rule out of seven.
    """
    from ai_stp_cli.commands import component as command

    place = tmp_path / ".claude" / "skills"
    place.mkdir(parents=True)
    (place / "review.md").write_text("# review\n", encoding="utf-8")

    adopted = command.adopt({"path": str(place / "review.md"), "root": str(tmp_path)}).payload
    assert adopted.stable_id.startswith("component_")

    with pytest.raises(CliFailure) as raised:
        command.adopt({"path": str(place / "review.md")})
    assert raised.value.code == "AI_STP_NOT_FOUND"
    assert "root" in raised.value.details


def test_client_mcp_inside_a_setting_file_is_found_beside_the_setting(tmp_path: Path) -> None:
    """Three harnesses keep their servers in a file that is also a setting.

    Claude Code's `.mcp.json` proves itself by existing. `codex`, `grok-build`
    and `opencode` do not have such a file: their servers live inside
    `config.toml` and `opencode.json`, which are already declared as settings.
    Discovery answered `mcp: 0` for all three while they were running servers
    (`#377`). The setting does not stop being a setting — one file answers
    twice — and only the server names cross the boundary.
    """
    project = tmp_path / "workspace"
    (project / ".codex").mkdir(parents=True)
    (project / ".codex" / "config.toml").write_text(
        '[mcp_servers.github]\ncommand = "npx"\n\n'
        f'[mcp_servers.paid]\nheaders = {{ Authorization = "Bearer {SECRET}" }}\n',
        encoding="utf-8",
    )
    (project / ".grok").mkdir()
    (project / ".grok" / "config.toml").write_text(
        '[mcp_servers.codegraph]\ncommand = "codegraph"\n', encoding="utf-8"
    )
    (project / "opencode.json").write_text(
        '{"$schema": "https://opencode.ai/config.json",'
        ' "mcp": {"nx": {"type": "local", "command": ["npx", "nx", "mcp"]}}}',
        encoding="utf-8",
    )

    found = [item for item in components.discover(project=project) if item.scope == "project"]
    kinds = {(item.harness_id, item.component_type) for item in found}
    for harness in ("codex", "grok-build", "opencode"):
        assert (harness, "mcp") in kinds, harness
        assert (harness, "setting") in kinds, harness

    servers = {
        item.harness_id: item.evidence_refs for item in found if item.component_type == "mcp"
    }
    assert servers["codex"] == ("mcp_servers.github", "mcp_servers.paid")
    assert servers["grok-build"] == ("mcp_servers.codegraph",)
    assert servers["opencode"] == ("mcp.nx",)
    assert all(item.native_role == "mcp_client_config" for item in found if item.evidence_refs)
    # The name of a server is evidence; the credential written beside it is not.
    assert SECRET not in repr(found)


def test_a_setting_that_declares_no_server_is_only_a_setting(tmp_path: Path) -> None:
    """Presence is not evidence, so nothing here may answer as a client config.

    `"mcp": {}` is how a project switches the feature off, an unrelated setting
    carries no such key at all, and a broken or oversized file says nothing
    that can be trusted. Reporting any of them would be the file-name heuristic
    the discovery contract forbids.
    """
    for name, body in (
        ("empty", '{"mcp": {}}'),
        ("absent", '{"model": "sonnet"}'),
        ("broken", '{"mcp": {"a"'),
        ("oversized", '{"mcp": {"a": {}}}' + " " * (mcp_clients.MAX_CLIENT_BYTES + 1)),
    ):
        project = tmp_path / name
        project.mkdir()
        (project / "opencode.json").write_text(body, encoding="utf-8")

        found = components.discover(project=project)
        kinds = {(item.harness_id, item.component_type) for item in found}

        assert ("opencode", "setting") in kinds, name
        assert ("opencode", "mcp") not in kinds, name


def test_jsonc_comments_and_trailing_commas_do_not_hide_servers(tmp_path: Path) -> None:
    """OpenCode accepts a commented config, so reading it must accept one too.

    A `//` inside a URL and a comma inside a description are content, not
    syntax; stepping over strings rather than scanning them is what keeps the
    two apart.
    """
    project = tmp_path / "workspace"
    project.mkdir()
    (project / "opencode.jsonc").write_text(
        "{\n"
        "  // the entry below is deliberately commented\n"
        '  "mcp": {\n'
        '    "context7": {"type": "remote", "url": "https://mcp.context7.com//mcp",'
        ' "note": "a, b"},\n'
        "  },\n"
        "  /* and a block comment */\n"
        "}\n",
        encoding="utf-8",
    )

    found = [item for item in components.discover(project=project) if item.component_type == "mcp"]

    assert [item.evidence_refs for item in found] == [("mcp.context7",)]


def test_an_adopted_passport_carries_no_home_path_and_can_therefore_sync(
    registry: sqlite3.Connection, harness_home: Path
) -> None:
    """A passport that records where it was found must still be able to leave.

    `redact_home` exists because "a passport, a log or an agent transcript"
    must not carry home-path material, and adoption already applies it. Nothing
    pinned the consequence, though, and the two halves live far apart: the
    redaction is in `local/components.py`, the refusal is
    `check_sync_payload` in the contracts package, and neither mentions the
    other. Reading only the refusal, it is easy to conclude that adopted
    components cannot sync at all — which is what I concluded, from a component
    I had put in a scratch directory outside the home.

    An absolute path outside the home directory does stay refused, and should:
    shortening it would hide rather than redact, and it means nothing on
    another machine either. That is the boundary this test draws, so the next
    reader does not mistake it for a defect.
    """
    found = next(
        item
        for item in components.discover()
        if item.component_type == "instruction" and item.harness_id == "claude-code"
    )
    stored = components.adopt(registry, found, device_id="device_test")
    document = stored.envelope.model_dump(mode="json")

    recorded = document["facts"]["source_path"]["value"]
    assert not recorded.startswith(str(harness_home)), recorded
    assert recorded.startswith("~/"), recorded
    # The point of the redaction, not a restatement of it.
    check_sync_payload(document)


def test_a_provider_rule_lands_inside_the_harness_home_it_is_relative_to() -> None:
    """Provider projection is relative to the target, and the target is the home.

    The comment above `PROVIDER_RULES` says a provider writes the isolated
    harness home, and for four of the five harnesses the rule is the catalog's
    own global layout, spelled identically. Pi carried an extra `agent/`, which
    is not a directory inside its home — it is the last segment *of* the home,
    `~/.pi/agent`. So the rule resolved to `~/.pi/agent/agent/AGENTS.md`.

    Reported by the provider implementation, whose `declared_native_route_is_
    compilable` case failed against it, and which correctly refused to add the
    doubled segment on its side to make our check pass.

    This is the third place the same off-by-one-directory surfaced for Pi. The
    other two were the first-party corpus `managed_paths` and the
    `builder_surfaces` notation both were read from.
    """
    from ai_stp_cli.local import composition, harness_catalog

    roots = {name: item.config_root for name, item in harness_catalog.BY_ID.items()}
    assert roots["pi"] == ".pi/agent", roots["pi"]

    doubled = [
        rule
        for rule in composition.PROVIDER_RULES
        if rule.harness_id == "pi" and rule.relative.split("/")[0] == "agent"
    ]
    assert not doubled, (
        f"{[rule.relative for rule in doubled]} are relative to the target, and the target "
        f"already is {roots['pi']!r}, so each resolves one directory too deep"
    )
