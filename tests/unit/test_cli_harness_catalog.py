"""One table owns harness detection, layouts, projections and support labels."""

import json
from pathlib import Path

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
    added_project = set(
        components._ADDED_PROJECT_SINCE_MIGRATION  # pyright: ignore[reportPrivateUsage]
    )
    assert not (
        (added | added_global | added_project) & (set(global_oracle) | set(project_oracle))
    ), "an addition must name a row the oracles never recorded"
    assert not (added & (added_global | added_project)), (
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
        set(project_oracle) | added | added_project
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

    Cursor was the second until 2026-08-28, on the reading that `mcpServers` is
    a key inside a plugin manifest and there is no global file. The product
    disagrees, and it was settled by running it rather than by reading: a server
    written straight to `~/.cursor/mcp.json` is listed and dialled, the file
    removed reports no servers, and the same file one directory to the side
    reports no servers. The CLI's own help names the global path unprompted.

    So the gap was true of `cursor.com/docs` and false of the product. It is
    withdrawn rather than softened, and what remains of it is `no_global_agent`
    — the one kind the same sweep found no user-scope directory for.

    Inventing a layout would be the guess the discovery contract forbids. So
    would keeping a gap after the thing it denies has been observed.
    """
    rows = {row.harness_id: row for row in toolchain.harness_capabilities({}).payload.harnesses}
    declaring = {
        definition.harness_id
        for definition in harness_catalog.DEFINITIONS
        for layout in definition.layouts
        if layout.component_type == "mcp"
    }

    assert declaring == {
        "claude-code",
        "codex",
        "opencode",
        "grok-build",
        "antigravity",
        "cursor",
    }
    assert "no_documented_mcp_client_config" in rows["pi"].gaps
    assert "no_global_agent" in rows["cursor"].gaps
    assert all("no_documented_mcp_client_config" not in rows[harness].gaps for harness in declaring)


#: Harnesses the migration oracles cannot cover, pinned instead.
#:
#: The oracles record the hand-written tables that existed before the catalog,
#: so a harness added afterwards has nothing to be compared against and cannot
#: be given one retroactively. That left `cursor` and `antigravity` — 17 layout
#: rows — where a row could be added, changed or deleted and no test would say
#: anything. Measured while removing a cursor row that was genuinely wrong:
#: nothing noticed, correctly, and that silence is the hole.
#:
#: A golden rather than a second oracle, because the question differs. The
#: oracles ask whether centralising the facts changed the released discovery
#: contract. This asks whether a row changed at all, and its whole value is that
#: the answer arrives as a reviewed diff.
UNMIGRATED_GOLDEN = Path(__file__).parents[1] / "golden" / "cli" / "harness-catalog-unmigrated.json"


def _oracle_harnesses() -> set[str]:
    """Harnesses either oracle covers, spelled the way the catalog spells them.

    The oracles call the shared conventions `""` and the catalog calls that
    harness `undefined`; `components._declared_rules` maps between them. The
    same mapping belongs here, or `undefined` reads as unguarded and the golden
    grows a row that another test already pins.
    """
    covered = {rule.harness_id for rule in components._MIGRATION_GLOBAL_ORACLE} | {  # pyright: ignore[reportPrivateUsage]
        rule.harness_id
        for rule in components._MIGRATION_PROJECT_ORACLE  # pyright: ignore[reportPrivateUsage]
    }
    return {"undefined" if harness_id == "" else harness_id for harness_id in covered}


def _unmigrated_rows() -> dict[str, list[dict[str, object]]]:
    return {
        definition.harness_id: [
            {
                "component_type": item.component_type,
                "relative": item.relative,
                "shape": item.shape,
                "scope": item.scope,
                "root": item.root,
                "source": item.source,
                "declared_key": item.declared_key,
            }
            for item in definition.layouts
        ]
        for definition in harness_catalog.DEFINITIONS
        if definition.harness_id not in _oracle_harnesses()
    }


def test_every_catalog_harness_is_guarded_by_an_oracle_or_by_the_golden() -> None:
    """A harness added later must not arrive in the blind spot silently.

    Without this the next one joins `cursor` and `antigravity` unguarded, and
    the golden's share of the catalog shrinks while every test stays green.
    """
    guarded = _oracle_harnesses() | set(_unmigrated_rows())
    assert guarded >= {definition.harness_id for definition in harness_catalog.DEFINITIONS}


def test_the_unmigrated_catalog_rows_match_their_golden() -> None:
    """A layout row for these harnesses changes as a reviewed diff or not at all."""
    expected = json.loads(UNMIGRATED_GOLDEN.read_text(encoding="utf-8"))
    assert _unmigrated_rows() == expected


def test_cursor_ignores_xdg_because_seven_of_its_eight_surfaces_do() -> None:
    """A resolver is not a statement about a home, and this row proved it.

    Cursor's configuration resolver really does rename the leaf —
    `CURSOR_CONFIG_DIR`, then `$XDG_CONFIG_HOME/cursor` without the dot, else
    `~/.cursor`. Reading that and turning XDG on here was a fix that broke the
    thing it was fixing: of the eight namespaces the provider owns, exactly one
    — `cli-config.json` — is built by calling that resolver. `commands`,
    `rules`, `hooks.json`, `mcp.json`, `plugins` and `plugins/local` are literal
    `join(homedir(), ".cursor", …)` and move for no variable at all.

    So with the variable set, discovery, projection and the target survey looked
    under `$XDG_CONFIG_HOME/cursor` for six of the seven surfaces this catalogue
    carries. Unconditional `~/.cursor` could not be wrong, because config and
    data coincide there; the correction is what split them.

    Asserted with the variable *set*, since that is the branch the mistake lived
    in and the one a passing test would otherwise never enter.

    The next correction split the root per surface: the harness root is now
    literal `~/.cursor` under every variable — a whole-harness override moved
    the six literal surfaces whenever `CURSOR_CONFIG_DIR` was set — and the
    one resolver-built surface (`cli-config.json`) carries its own layout root,
    resolved override-first exactly as the pinned bundle does.
    """
    from pathlib import Path

    from ai_stp_cli.local import components, harnesses

    cursor = next(item for item in harnesses.DETECTORS if item.harness_id == "cursor")
    home = {"HOME": "/home/u"}

    assert harnesses.config_root(cursor, home) == Path("/home/u/.cursor")
    assert harnesses.config_root(cursor, {**home, "XDG_CONFIG_HOME": "/elsewhere"}) == Path(
        "/home/u/.cursor"
    )
    assert harnesses.config_root(cursor, {**home, "CURSOR_CONFIG_DIR": "/opt/c"}) == Path(
        "/home/u/.cursor"
    )

    resolver = components.cursor_config_root
    assert resolver({**home, "CURSOR_CONFIG_DIR": "/opt/c"}, Path("/home/u")) == Path("/opt/c")
    assert resolver({**home, "XDG_CONFIG_HOME": "/elsewhere"}, Path("/home/u")) == Path(
        "/elsewhere/cursor"
    )
    assert resolver(home, Path("/home/u")) == Path("/home/u/.cursor")

    catalog_cursor = harness_catalog.BY_ID["cursor"]
    resolver_rooted = [
        layout.relative for layout in catalog_cursor.layouts if layout.root == "cursor_config"
    ]
    assert resolver_rooted == ["cli-config.json"]
    assert catalog_cursor.root_override is None


def test_opencode_is_xdg_on_every_system_including_windows() -> None:
    """The harness that genuinely is XDG, and has no `%APPDATA%` branch.

    Vendor pages claiming otherwise are about third-party plugins rather than
    the product's own `Global` module. Kept beside cursor's row because the two
    together are the reason a single flag was never enough: one product honours
    the variable everywhere, the other names it in a resolver almost nothing
    calls.
    """
    from pathlib import Path

    from ai_stp_cli.local import harnesses

    opencode = next(item for item in harnesses.DETECTORS if item.harness_id == "opencode")
    home = {"HOME": "/home/u"}

    assert harnesses.config_root(opencode, home) == Path("/home/u/.config/opencode")
    assert harnesses.config_root(opencode, {**home, "XDG_CONFIG_HOME": "/elsewhere"}) == Path(
        "/elsewhere/opencode"
    )


def test_the_evidence_default_is_the_weakest_value_and_the_set_is_closed() -> None:
    """A column that graded generously would make the catalogue look measured.

    `page` marks a row whose wrong answer is **undetectable by anything in this
    repository** — a property of the tooling, not a verdict on whoever wrote the
    row. Most `page` rows are correct and several were carefully reasoned. But
    every projection defect found this week sat on a real, live vendor page:
    `antigravity-cli/plugins` was the directory the CLI manages itself, cursor's
    `plugins` was one level short of `plugins/local`, and `.mcp.json` was called
    global on two harnesses. A ranking that put a page above a measurement would
    have promoted exactly those.

    So the default is the weakest value. Absence of a record of measurement is
    not evidence of measurement, and the alternative — defaulting to the middle
    and letting somebody argue a row up — is how a column becomes decoration.
    """
    from dataclasses import fields

    from ai_stp_cli.local import harness_catalog

    default = next(item for item in fields(harness_catalog.Layout) if item.name == "evidence")
    assert default.default == "page"

    values = {layout.evidence for item in harness_catalog.DEFINITIONS for layout in item.layouts}
    assert values <= {"ran", "bytes", "page"}, sorted(values)


def test_every_exercised_row_is_one_somebody_actually_exercised() -> None:
    """The claim, pinned, so a promotion is a reviewed diff rather than a habit.

    Each exercised row was established by running the product or by reading its
    shipped bytes, and each is named below so that raising one requires saying
    which. The number being small is the finding, and the counts are computed
    rather than written: the sentence said "seven of ninety-three, five
    harnesses with none" and went stale the first time a row was added — a typed
    total beside a list nobody recounts, which is the defect this file exists to
    prevent one level up.
    """
    from ai_stp_cli.local import harness_catalog

    rows = [
        (item.harness_id, layout) for item in harness_catalog.DEFINITIONS for layout in item.layouts
    ]
    exercised = {
        (harness_id, layout.component_type, layout.relative, layout.evidence)
        for harness_id, layout in rows
        if layout.evidence != "page"
    }
    # Reported, not asserted against a literal: the shape of the estate is what
    # a reader wants and a number typed here would be wrong on the next row.
    covered = {harness_id for harness_id, layout in rows if layout.evidence != "page"}
    assert len(exercised) < len(rows) // 4, (
        f"{len(exercised)} of {len(rows)} rows exercised across {len(covered)} harnesses; "
        "if this stops being a minority the sentence above needs rewriting"
    )
    assert exercised == {
        # Read from the shipped `2.1.251` bytes, with two invented key names as
        # controls returning zero: "require hooks configured in settings.json —
        # the harness executes these", "Change settings: hooks, permissions,
        # environment variables", and `disableAllHooks` "in your user settings".
        ("claude-code", "hook", "settings.json", "bytes"),
        # Planted under a temporary `CODEX_HOME` and read back through `codex
        # doctor` on the pinned `0.151.0` binary: a complete `<name>.toml` is
        # accepted silently, one missing `description` is refused by name, a
        # file in an invented directory is ignored, and the same content as
        # `.md` is ignored because the scan filters on `.toml`. That last
        # control is why the earlier measurement concluded the opposite — it
        # planted a `.md` and could not have failed.
        ("codex", "agent", "agents", "ran"),
        # A server written straight to `~/.cursor/mcp.json` is listed and
        # dialled; the file removed, and the same file one directory to the
        # side, both report no servers.
        ("cursor", "mcp", "mcp.json", "ran"),
        # Confirmed at the line in the pinned bundle: the joins, the `user`
        # scope tags, and the product's own User Rule picker.
        ("cursor", "command", "commands", "bytes"),
        ("cursor", "hook", "hooks.json", "bytes"),
        ("cursor", "instruction", "rules", "bytes"),
        # `antigravity plugin install` creates `~/.gemini/config/plugins/` and
        # validates the plugin; no `antigravity-cli/plugins` is created at all.
        ("antigravity", "plugin", "config/plugins", "ran"),
        # Global workflows invoked as `/workflow-name` across every workspace.
        ("antigravity", "command", "config/global_workflows", "ran"),
        # Measured against a real codex install: skills land under the shared
        # convention root rather than the product's configuration home.
        ("undefined", "skill", ".agents/skills", "ran"),
    }
