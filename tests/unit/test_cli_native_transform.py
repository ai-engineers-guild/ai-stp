"""Native recast transforms rewrite target syntax or refuse."""

from __future__ import annotations

from ai_stp_cli.local import composition, native_transform


def test_cursor_mcp_becomes_opencode_local_command_array() -> None:
    target = composition.rule_for("mcp", "opencode")
    assert target is not None
    encoded = native_transform.encode_mcp_servers(
        {"docs": {"command": "npx", "args": ["docs-mcp"]}}, target
    )
    assert encoded is not None
    payload, _losses = encoded
    text = payload.decode("utf-8")
    assert '"type": "local"' in text
    assert '"npx"' in text
    assert '"docs-mcp"' in text


def test_a_url_only_mcp_server_has_no_stdio_encoding() -> None:
    target = composition.rule_for("mcp", "cursor")
    assert target is not None
    assert (
        native_transform.encode_mcp_servers(
            {"docs": {"url": "https://example.invalid/mcp"}}, target
        )
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
