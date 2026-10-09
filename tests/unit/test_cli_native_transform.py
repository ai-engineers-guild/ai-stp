"""Native recast transforms rewrite target syntax or refuse."""

from __future__ import annotations

import json

import pytest

from ai_stp_cli.local import composition, native_transform
from ai_stp_foundation.canonical import JsonValue


@pytest.mark.parametrize(
    "server",
    [
        {"command": "npx", "args": ["docs-mcp"], "env": {"MODE": "read"}},
        {"type": "local", "command": ["npx", "docs-mcp"], "environment": {"MODE": "read"}},
    ],
)
def test_mcp_command_and_literal_environment_survive_conversion(
    server: dict[str, JsonValue],
) -> None:
    target = composition.rule_for("mcp", "opencode")
    assert target is not None
    encoded = native_transform.encode_mcp_servers({"docs": server}, target)
    assert encoded is not None
    payload, losses = encoded
    assert not losses
    assert json.loads(payload) == {
        "docs": {
            "type": "local",
            "command": ["npx", "docs-mcp"],
            "environment": {"MODE": "read"},
        }
    }


def test_a_url_only_mcp_server_has_no_stdio_encoding() -> None:
    target = composition.rule_for("mcp", "cursor")
    assert target is not None
    assert (
        native_transform.encode_mcp_servers(
            {"docs": {"url": "https://example.invalid/mcp"}}, target
        )
        is None
    )


@pytest.mark.parametrize(
    "extra",
    [
        {"enabled": False},
        {"disabled_tools": ["delete"]},
        {"enabled_tools": ["read"]},
        {"cwd": "/synthetic/project"},
        {"tool_timeout_sec": 60},
        {"unknown": "setting"},
        {"type": "http"},
        {"url": "https://example.invalid/mcp"},
        {"args": [1]},
        {"args": None},
        {"env": {"MODE": True}},
        {"env": {"MODE": "one"}, "environment": {"MODE": "two"}},
        {"command": ["server", "one"], "args": ["two"]},
        {"env": {"MODE": "${MODE}"}},
        {"args": ["{env:MODE}"]},
    ],
)
def test_mcp_conversion_refuses_lost_controls_and_ambiguous_values(
    extra: dict[str, JsonValue],
) -> None:
    target = composition.rule_for("mcp", "opencode")
    assert target is not None
    assert (
        native_transform.encode_mcp_servers({"docs": {"command": "server", **extra}}, target)
        is None
    )


def test_claude_agent_markdown_becomes_codex_toml() -> None:
    target = composition.rule_for("agent", "codex")
    assert target is not None
    result = native_transform.transform(
        component_type="agent",
        source_harness="claude-code",
        target=target,
        files={"agents/review.md": b"# review\n\nReview the change.\n"},
        modes={"agents/review.md": 0o644},
        source_paths={"agents/review.md": "agents/review.md"},
    )
    assert result is not None
    assert "agents/review.toml" in result.files
    text = result.files["agents/review.toml"].decode("utf-8")
    assert 'name = "review"' in text
    assert "Review the change." in text


def test_a_hook_document_moves_onto_the_target_surface() -> None:
    target = composition.rule_for("hook", "codex")
    assert target is not None
    result = native_transform.transform(
        component_type="hook",
        source_harness="claude-code",
        target=target,
        files={"hooks.json": b'{"hooks":{}}\n'},
        modes={"hooks.json": 0o644},
        source_paths={"hooks.json": "hooks.json"},
    )
    assert result is not None
    assert "hooks.json" in result.files


def test_a_plugin_manifest_is_retargeted_for_cursor() -> None:
    target = composition.rule_for("plugin", "cursor")
    assert target is not None
    result = native_transform.transform(
        component_type="plugin",
        source_harness="claude-code",
        target=target,
        files={".claude-plugin/plugin.json": b'{"name":"pack"}\n'},
        modes={".claude-plugin/plugin.json": 0o644},
        source_paths={".claude-plugin/plugin.json": ".claude-plugin/plugin.json"},
    )
    assert result is not None
    assert ".cursor-plugin/plugin.json" in result.files


def test_an_agent_name_with_quotes_still_produces_valid_toml() -> None:
    """A heading breaking out of the basic string would corrupt the agent file."""
    import tomlkit

    target = composition.rule_for("agent", "codex")
    assert target is not None
    result = native_transform.transform(
        component_type="agent",
        source_harness="claude-code",
        target=target,
        files={"agents/reviewer.md": b'# say "hi" \\ now\n\nDescribe it.\n'},
        modes={"agents/reviewer.md": 0o644},
        source_paths={"agents/reviewer.md": "agents/reviewer.md"},
    )
    assert result is not None
    text = result.files["agents/reviewer.toml"].decode("utf-8")
    parsed = tomlkit.parse(text)
    assert parsed["name"] == 'say "hi" \\ now'


def test_an_agent_name_with_high_control_chars_still_produces_valid_toml() -> None:
    """json stops escaping at U+001F, but TOML requires U+007F escaped too —
    and strict readers refuse the C1 block entirely."""
    import tomlkit

    target = composition.rule_for("agent", "codex")
    assert target is not None
    result = native_transform.transform(
        component_type="agent",
        source_harness="claude-code",
        target=target,
        files={"agents/reviewer.md": "# re\x7fview\x85er\n\nDescribe it.\n".encode()},
        modes={"agents/reviewer.md": 0o644},
        source_paths={"agents/reviewer.md": "agents/reviewer.md"},
    )
    assert result is not None
    text = result.files["agents/reviewer.toml"].decode("utf-8")
    assert "\\u007f" in text and "\\u0085" in text
    assert tomlkit.parse(text)["name"] == "re\x7fview\x85er"
