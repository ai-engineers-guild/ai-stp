"""One table owns harness detection, layouts, projections and support labels."""

from ai_stp_cli.commands import toolchain
from ai_stp_cli.local import components, harness_catalog, harnesses


def test_catalog_is_closed_complete_and_has_no_duplicate_layouts() -> None:
    assert tuple(item.harness_id for item in harness_catalog.DEFINITIONS) == (
        "claude-code",
        "codex",
        "pi",
        "opencode",
        "grok-build",
        "undefined",
    )
    for definition in harness_catalog.DEFINITIONS:
        assert definition.layouts
        assert definition.projection_capabilities
        keys = [
            (layout.scope, layout.root, layout.relative, layout.component_type)
            for layout in definition.layouts
        ]
        assert len(keys) == len(set(keys))
        assert all(layout.source for layout in definition.layouts)


def test_detection_and_discovery_are_derived_from_the_catalog() -> None:
    assert [item.harness_id for item in harnesses.DETECTORS] == [
        item.harness_id for item in harness_catalog.DEFINITIONS if item.executable
    ]
    assert set(components.GLOBAL_RULES) == set(components._MIGRATION_GLOBAL_ORACLE)  # pyright: ignore[reportPrivateUsage]
    assert set(components.PROJECT_RULES) == set(components._MIGRATION_PROJECT_ORACLE)  # pyright: ignore[reportPrivateUsage]


def test_machine_table_exposes_support_layouts_capabilities_and_gaps() -> None:
    rows = toolchain.harness_capabilities({}).payload.harnesses
    assert [row.harness_id for row in rows] == [
        item.harness_id for item in harness_catalog.DEFINITIONS
    ]
    by_id = {row.harness_id: row for row in rows}
    assert by_id["claude-code"].support == "primary"
    assert "plugin_manifest" in by_id["codex"].projection_capabilities
    assert ".grok/skills" in by_id["grok-build"].project_layouts
    assert by_id["undefined"].gaps == ["no_single_harness_owner"]


def test_every_harness_either_declares_client_mcp_or_states_a_verified_gap() -> None:
    """A missing layout is reported, not left as silence.

    Four harnesses declare where their client servers live. Pi does not: the
    `mcp.json` files under its root are written by a community extension rather
    than by Pi, they disagree on the key, and its documentation index carries no
    MCP page to declare one from. Inventing a layout would be the guess the
    discovery contract forbids, so the table says so instead (`#377`).
    """
    rows = {row.harness_id: row for row in toolchain.harness_capabilities({}).payload.harnesses}
    declaring = {
        definition.harness_id
        for definition in harness_catalog.DEFINITIONS
        for layout in definition.layouts
        if layout.component_type == "mcp"
    }

    assert declaring == {"claude-code", "codex", "opencode", "grok-build"}
    assert "no_documented_mcp_client_config" in rows["pi"].gaps
    assert all("no_documented_mcp_client_config" not in rows[harness].gaps for harness in declaring)
