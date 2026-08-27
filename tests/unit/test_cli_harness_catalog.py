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
        "cursor",
        "antigravity",
        "undefined",
    )
    for definition in harness_catalog.DEFINITIONS:
        assert definition.layouts
        assert definition.native_authoring
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
    # The oracles are migration artefacts: they hold the hand-written rules the
    # generated ones replaced, and they prove generation reproduced them. They
    # say nothing about a harness added after the migration, so the comparison
    # is scoped to the harnesses each oracle actually covers — widening the
    # oracle instead would turn a record of what was into a second place to
    # declare what is.
    global_oracle = components._MIGRATION_GLOBAL_ORACLE  # pyright: ignore[reportPrivateUsage]
    project_oracle = components._MIGRATION_PROJECT_ORACLE  # pyright: ignore[reportPrivateUsage]
    migrated = {rule.harness_id for rule in global_oracle} | {
        rule.harness_id for rule in project_oracle
    }
    # A row withdrawn after the migration is subtracted rather than deleted from
    # the oracle. The oracle records what the hand table held; deleting from a
    # record makes it stop proving anything, and the withdrawal has its own
    # reason written beside it.
    withdrawn = set(
        components._WITHDRAWN_GLOBAL_SINCE_MIGRATION  # pyright: ignore[reportPrivateUsage]
    )
    assert withdrawn <= set(global_oracle), (
        "a withdrawal must name a row the global oracle actually recorded"
    )
    # And a surface the catalog learned *after* the migration, on a harness the
    # oracle already covers, is added rather than folded into the record. The
    # comment above anticipated a new harness and not a new surface on an old
    # one, which is what `tui.json` turned out to be.
    added = set(
        components._ADDED_BOTH_SCOPES_SINCE_MIGRATION  # pyright: ignore[reportPrivateUsage]
    )
    added_global = set(
        components._ADDED_GLOBAL_SINCE_MIGRATION  # pyright: ignore[reportPrivateUsage]
    )
    assert not ((added | added_global) & (set(global_oracle) | set(project_oracle))), (
        "an addition must name a row the oracles never recorded"
    )
    assert not (added & added_global), (
        "a surface is documented at both scopes or at one, and never declared twice"
    )
    assert {rule for rule in components.GLOBAL_RULES if rule.harness_id in migrated} == (
        (set(global_oracle) - withdrawn) | added | added_global
    )
    # The project oracle is untouched by a *global* withdrawal. `Rule` carries no
    # scope, so the two rows for one kind are equal objects in different tuples;
    # subtracting from both would take a project surface that is real.
    #
    # Additions are scoped the same way, and were not until a global-only one
    # arrived. `tui.json` is documented at both scopes, so a single unscoped set
    # was indistinguishable from a correct one — and the first global-only
    # addition would have been asserted into the project table, where the file
    # does not exist. Same defect as the withdrawal, opposite direction.
    assert {rule for rule in components.PROJECT_RULES if rule.harness_id in migrated} == (
        set(project_oracle) | added
    )


def test_machine_table_exposes_support_layouts_capabilities_and_gaps() -> None:
    rows = toolchain.harness_capabilities({}).payload.harnesses
    assert [row.harness_id for row in rows] == [
        item.harness_id for item in harness_catalog.DEFINITIONS
    ]
    by_id = {row.harness_id: row for row in rows}
    assert by_id["claude-code"].support == "primary"
    assert "plugin_manifest" in by_id["codex"].native_authoring
    assert ".grok/skills" in by_id["grok-build"].project_layouts
    assert by_id["undefined"].gaps == ["no_single_harness_owner"]
    pi = next(item for item in harness_catalog.DEFINITIONS if item.harness_id == "pi")
    assert pi.npm_packages[0] == "@earendil-works/pi-coding-agent"
    plugin_roots = {
        layout.relative
        for layout in pi.layouts
        if layout.component_type == "plugin" and layout.scope == "global"
    }
    assert plugin_roots == {"extensions"}


def test_every_harness_either_declares_client_mcp_or_states_a_verified_gap() -> None:
    """A missing layout is reported, not left as silence.

    Five harnesses declare where their client servers live. Two do not, for
    different reasons, and the difference is why the gap is named rather than
    counted.

    Pi has no documented location at all: the `mcp.json` files under its root
    are written by a community extension rather than by Pi, they disagree on
    the key, and its documentation index carries no MCP page to declare one
    from (`#377`).

    Cursor has MCP, but not as a global file: `mcpServers` is a key inside a
    plugin manifest, so what a provider installs is the plugin. Declaring a
    global layout for it would state a location the product does not have.

    Inventing a layout in either case would be the guess the discovery contract
    forbids, so the table says so instead.
    """
    rows = {row.harness_id: row for row in toolchain.harness_capabilities({}).payload.harnesses}
    declaring = {
        definition.harness_id
        for definition in harness_catalog.DEFINITIONS
        for layout in definition.layouts
        if layout.component_type == "mcp"
    }

    assert declaring == {"claude-code", "codex", "opencode", "grok-build", "antigravity"}
    assert "no_documented_mcp_client_config" in rows["pi"].gaps
    assert "components_are_plugin_declared" in rows["cursor"].gaps
    assert all("no_documented_mcp_client_config" not in rows[harness].gaps for harness in declaring)
