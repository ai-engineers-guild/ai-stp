"""Every named conflict class has a fixture, and the reports stay stable."""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Final

import pytest

from ai_stp_cli.local import composition

CONTRACT = Path("docs/contracts/composition-reports.md")

CLAUDE = composition.Target(harness_id="claude-code", os="linux", arch="x86_64")


def _surface(stable_id: str, **overrides: object) -> composition.Surface:
    """One component that conflicts with nothing, so a fixture changes one thing."""
    facts: dict[str, object] = {
        "stable_id": stable_id,
        "version": "1.0",
        "component_type": "skill",
        "harness_id": "claude-code",
    }
    facts.update(overrides)
    return composition.Surface(**facts)  # pyright: ignore[reportArgumentType]


def _codes(report: composition.CompositionReport) -> tuple[str, ...]:
    return tuple(item.code for item in report.conflicts)


def test_a_composition_with_nothing_wrong_is_not_blocked() -> None:
    report = composition.compose((_surface("component_a"), _surface("component_b")), CLAUDE)
    assert not report.blocked
    assert [item.stable_id for item in report.chosen] == ["component_a", "component_b"]


def test_an_empty_composition_is_a_composition_not_an_absence() -> None:
    """`ADR-0124`: managed emptiness is a graph of zero, not a missing graph."""
    report = composition.compose((), CLAUDE)
    assert not report.blocked
    assert report.chosen == ()
    assert report.rejected == ()
    assert report.conflicts == ()
    assert "deterministic_report_generation" in report.operations
    assert composition.convert((), CLAUDE).complete
    contract = CONTRACT.read_text(encoding="utf-8")
    assert "Пустой состав" in contract
    assert "Пустого состава не бывает" not in contract


def test_a_nested_managed_path_is_the_same_claim_as_its_root() -> None:
    """Disjoint union is about ownership, not string equality.

    A passport names roots. `skills/foo` already owns `skills/foo/SKILL.md`, so
    a second component declaring the child is the same conflict as declaring
    the root twice. `skills/review` does not own `skills/review.md`.
    """
    nested = composition.compose(
        (
            _surface("component_a", managed_paths=("skills/foo",)),
            _surface("component_b", managed_paths=("skills/foo/SKILL.md",)),
        ),
        CLAUDE,
    )
    assert "managed_path_owned_twice" in _codes(nested)
    neighbour = composition.compose(
        (
            _surface("component_a", managed_paths=("skills/review",)),
            _surface("component_b", managed_paths=("skills/review.md",)),
        ),
        CLAUDE,
    )
    assert "managed_path_owned_twice" not in _codes(neighbour)
    assert composition.path_covers("skills/foo", "skills/foo/SKILL.md")
    assert not composition.path_covers("skills/review", "skills/review.md")


def test_a_hook_manifest_owns_its_sibling_handler_directory() -> None:
    """`hooks.json` is the discovered file; handlers live next to it.

    A second component claiming `config/hooks/h01.py` is the same collision as
    claiming the manifest: they are one native surface. Handlers under that
    sibling are also inside the file-shaped projection, not outside it.
    """
    antigravity = composition.Target(harness_id="antigravity", os="linux", arch="x86_64")
    overlap = composition.compose(
        (
            _surface(
                "component_a",
                component_type="hook",
                harness_id="antigravity",
                managed_paths=("config/hooks.json",),
            ),
            _surface(
                "component_b",
                component_type="hook",
                harness_id="antigravity",
                managed_paths=("config/hooks/h01.py",),
            ),
        ),
        antigravity,
    )
    assert "managed_path_owned_twice" in _codes(overlap)
    inside = composition.compose(
        (
            _surface(
                "component_a",
                component_type="hook",
                harness_id="antigravity",
                managed_paths=("config/hooks.json", "config/hooks/h01.py"),
            ),
        ),
        antigravity,
    )
    assert "managed_path_outside_projection" not in _codes(inside)
    assert composition.hook_sibling_directory("config/hooks.json") == "config/hooks"
    assert composition.claimed_paths("config/hooks.json") == (
        "config/hooks.json",
        "config/hooks",
    )


#: One fixture per named conflict class. Held as a constant rather than inline,
#: so the coverage check below reads the same list the parametrisation does — an
#: introspected list would drift the first time the decorator changed shape.
FIXTURES: list[tuple[tuple[composition.Surface, ...], composition.Target, str]] = [
    (
        (
            _surface("component_a", managed_paths=("skills/review.md",)),
            _surface("component_b", managed_paths=("skills/review.md",)),
        ),
        CLAUDE,
        "managed_path_owned_twice",
    ),
    (
        (
            _surface("component_a", native_ids=("/review",)),
            _surface("component_b", native_ids=("/review",)),
        ),
        CLAUDE,
        "native_id_collision",
    ),
    (
        (
            _surface("component_a", component_type="instruction", precedence=1),
            _surface("component_b", component_type="instruction", precedence=1),
        ),
        CLAUDE,
        "instruction_precedence_conflict",
    ),
    (
        (
            _surface("component_a", component_type="hook", hook_event="pre_write", hook_order=1),
            _surface("component_b", component_type="hook", hook_event="pre_write", hook_order=1),
        ),
        CLAUDE,
        "hook_order_conflict",
    ),
    (
        (_surface("component_a", component_type="plugin"),),
        composition.Target(harness_id="codex", os="linux", arch="x86_64"),
        "native_surface_lost",
    ),
    (
        (_surface("component_a", managed_paths=("../outside.md",)),),
        CLAUDE,
        "path_escapes_bundle",
    ),
    (
        (_surface("component_a", required_env=("OPENAI_API_KEY",)),),
        CLAUDE,
        "undeclared_environment",
    ),
    (
        (_surface("component_a", permissions=("network:outbound",)),),
        CLAUDE,
        "permission_escalation",
    ),
    (
        (_surface("component_a", redistribution=False),),
        composition.Target(
            harness_id="claude-code", os="linux", arch="x86_64", for_redistribution=True
        ),
        "redistribution_forbidden",
    ),
    (
        (_surface("component_a", permissions=("file:write",)),),
        composition.Target(
            harness_id="claude-code",
            os="linux",
            arch="x86_64",
            granted_entitlements=frozenset({"file:write"}),
        ),
        "entitlement_missing",
    ),
    (
        (_surface("component_a", lane="experimental"),),
        CLAUDE,
        "unverified_without_consent",
    ),
    (
        # A path relative to `$HOME` where the rule's root is the config home:
        # correct against a root nobody wrote down, which is the whole class.
        (_surface("component_a", managed_paths=(".agents/skills/x",), source_name="x"),),
        CLAUDE,
        "managed_path_outside_projection",
    ),
    (
        (_surface("component_a"),),
        composition.Target(
            harness_id="claude-code",
            os="windows",
            arch="x86_64",
            supported_platforms=frozenset({"linux/x86_64"}),
        ),
        "unsupported_platform",
    ),
]


# REQ-606: every named class is detected, and the list above is the claim.
@pytest.mark.parametrize(("surfaces", "target", "code"), FIXTURES)
def test_every_named_conflict_class_has_a_fixture(
    surfaces: tuple[composition.Surface, ...], target: composition.Target, code: str
) -> None:
    report = composition.compose(surfaces, target)
    assert code in _codes(report)
    assert report.blocked


def test_the_fixtures_cover_the_whole_closed_set() -> None:
    """A class with no fixture is a class nothing proves is detected."""
    assert {code for _, _, code in FIXTURES} == composition.CONFLICTS


# Each pair below is two codes for two situations with two different fixes.
def test_an_escalation_and_a_missing_entitlement_are_different_codes() -> None:
    """One is narrowed by changing the composition, the other by granting."""
    ungranted = composition.compose((_surface("component_a", permissions=("net",)),), CLAUDE)
    granted = composition.compose(
        (_surface("component_a", permissions=("net",)),),
        composition.Target(
            harness_id="claude-code",
            os="linux",
            arch="x86_64",
            granted_entitlements=frozenset({"net"}),
        ),
    )
    assert _codes(ungranted) == ("permission_escalation",)
    assert _codes(granted) == ("entitlement_missing",)


def test_an_allowed_permission_conflicts_with_nothing() -> None:
    report = composition.compose(
        (_surface("component_a", permissions=("file:read",)),),
        composition.Target(
            harness_id="claude-code",
            os="linux",
            arch="x86_64",
            allowed_permissions=frozenset({"file:read"}),
        ),
    )
    assert not report.blocked


def test_a_consented_unverified_component_is_allowed_in_a_named_composition() -> None:
    """Consent opens the composition; `select confirm` is where the user decides."""
    report = composition.compose(
        (_surface("component_a", lane="experimental", consented=True),), CLAUDE
    )
    assert "unverified_without_consent" not in _codes(report)


def test_one_component_owning_its_own_path_twice_is_not_a_conflict() -> None:
    report = composition.compose(
        (_surface("component_a", managed_paths=("skills/a.md", "skills/a.md")),), CLAUDE
    )
    assert not report.blocked


@pytest.mark.parametrize(
    "path", ["/etc/passwd", "~/notes.md", "../up.md", "a//b.md", "./here.md", ""]
)
def test_a_path_that_leaves_the_bundle_is_refused(path: str) -> None:
    report = composition.compose((_surface("component_a", managed_paths=(path,)),), CLAUDE)
    assert "path_escapes_bundle" in _codes(report)


def test_an_optional_component_without_a_surface_is_a_loss_not_a_conflict() -> None:
    """`unsupported` is not automatically fatal; a *required* one is."""
    codex = composition.Target(harness_id="codex", os="linux", arch="x86_64")
    optional_surface = _surface("component_a", component_type="plugin", required=False)
    optional = composition.compose((optional_surface,), codex)
    assert not optional.blocked

    converted = composition.convert((optional_surface,), codex)
    assert converted.entries[0].state == composition.STATE_UNSUPPORTED
    assert converted.losses


# REQ-607: the reports are stable.
def test_the_conflict_order_does_not_depend_on_the_input_order() -> None:
    surfaces = (
        _surface("component_c", managed_paths=("a.md",)),
        _surface("component_a", native_ids=("/x",)),
        _surface("component_b", native_ids=("/x",)),
    )
    forward = composition.compose(surfaces, CLAUDE)
    backward = composition.compose(tuple(reversed(surfaces)), CLAUDE)
    assert _codes(forward) == _codes(backward)
    assert [item.details for item in forward.conflicts] == [
        item.details for item in backward.conflicts
    ]


def test_the_chosen_list_is_ordered_by_identifier() -> None:
    surfaces = (_surface("component_c"), _surface("component_a"), _surface("component_b"))
    report = composition.compose(surfaces, CLAUDE)
    assert [item.stable_id for item in report.chosen] == [
        "component_a",
        "component_b",
        "component_c",
    ]


# REQ-625: only the allowed operations, and only the ones actually applied.
def test_the_report_names_only_allowed_operations() -> None:
    report = composition.compose((_surface("component_a", managed_paths=("a.md",)),), CLAUDE)
    assert set(report.operations) <= set(composition.OPERATIONS)
    assert "disjoint_managed_path_union" in report.operations


def test_an_operation_that_was_not_applied_is_not_claimed() -> None:
    report = composition.compose((_surface("component_a"),), CLAUDE)
    assert "disjoint_managed_path_union" not in report.operations
    assert "exact_reference_deduplication" not in report.operations


def test_an_exact_duplicate_reference_is_rejected_not_chosen_twice() -> None:
    """`REQ-625` names the operation. Claiming it while keeping both is a lie."""
    report = composition.compose((_surface("component_a"), _surface("component_a")), CLAUDE)
    assert [item.stable_id for item in report.chosen] == ["component_a"]
    assert [item.reason for item in report.rejected] == [
        "exact reference already in the composition"
    ]
    assert "exact_reference_deduplication" in report.operations
    assert not report.blocked


def test_the_chosen_reason_is_the_recorded_lane_reason() -> None:
    report = composition.compose(
        (
            _surface(
                "component_a",
                lane_reason="your own or exactly pinned; installable after local checks",
            ),
        ),
        CLAUDE,
    )
    assert report.chosen[0].reason == ("your own or exactly pinned; installable after local checks")


def test_the_operations_come_back_in_the_declared_order() -> None:
    report = composition.compose(
        (_surface("component_a", managed_paths=("a.md",)), _surface("component_a")), CLAUDE
    )
    assert report.operations == tuple(
        name for name in composition.OPERATIONS if name in report.operations
    )


# The conversion report: three reachable states, every loss named.
def test_a_directory_surface_takes_several_components_completely() -> None:
    report = composition.convert((_surface("component_a"), _surface("component_b")), CLAUDE)
    assert [item.state for item in report.entries] == ["complete", "complete"]
    assert report.complete
    assert report.losses == ()


def test_a_file_surface_shared_by_two_components_loses_their_separate_identity() -> None:
    codex = composition.Target(harness_id="codex", os="linux", arch="x86_64")
    report = composition.convert(
        (
            _surface("component_a", component_type="instruction"),
            _surface("component_b", component_type="instruction"),
        ),
        codex,
    )
    assert [item.state for item in report.entries] == ["partial", "partial"]
    assert not report.complete
    assert all("AGENTS.md" in loss for loss in report.losses)


def test_a_file_surface_with_one_component_is_complete() -> None:
    codex = composition.Target(harness_id="codex", os="linux", arch="x86_64")
    report = composition.convert((_surface("component_a", component_type="instruction"),), codex)
    assert report.entries[0].state == "complete"
    assert report.complete


def test_every_declared_conversion_state_is_reachable() -> None:
    """A state nothing can produce is a state nobody has to handle."""
    codex = composition.Target(harness_id="codex", os="linux", arch="x86_64")
    seen = {
        composition.convert((_surface("component_a"),), CLAUDE).entries[0].state,
        composition.convert(
            (
                _surface("component_a", component_type="instruction"),
                _surface("component_b", component_type="instruction"),
            ),
            codex,
        )
        .entries[0]
        .state,
        composition.convert((_surface("component_a", component_type="plugin"),), codex)
        .entries[0]
        .state,
    }
    assert seen == {
        composition.STATE_COMPLETE,
        composition.STATE_PARTIAL,
        composition.STATE_UNSUPPORTED,
    }


def test_a_loss_is_always_named() -> None:
    """ "Something was lost" is a sentence nobody can act on."""
    codex = composition.Target(harness_id="codex", os="linux", arch="x86_64")
    report = composition.convert((_surface("component_a", component_type="plugin"),), codex)
    assert report.entries[0].losses
    assert all(loss.strip() for loss in report.losses)


def test_an_unsupported_entry_names_no_surface() -> None:
    codex = composition.Target(harness_id="codex", os="linux", arch="x86_64")
    entry = composition.convert((_surface("component_a", component_type="plugin"),), codex).entries[
        0
    ]
    assert entry.native_surface == ""


def test_the_native_surface_matches_provider_targets() -> None:
    """Composition paths are relative to each explicit provider target."""
    assert composition.native_surface("skill", "claude-code") == "skills"
    assert composition.native_surface("instruction", "codex") == "AGENTS.md"
    # `skills` relative to the `user_root` target `~/.agents`, not
    # `.agents/skills` relative to codex's configuration home. Resolved the old
    # way it landed in `~/.codex/.agents/skills`, a sibling of what codex reads
    # rather than a child, and the install said `verified` (`ADR-0127`).
    assert composition.native_surface("skill", "codex") == "skills"
    assert composition.rule_for("skill", "codex").target_scope == "user_root"  # pyright: ignore[reportOptionalMemberAccess]
    # Pi's target is `~/.pi/agent`, so `agent` is the last segment of the home
    # and not a directory inside it. This line asserted the prefix while the
    # docstring above stated the rule the prefix breaks.
    assert composition.native_surface("instruction", "pi") == "AGENTS.md"
    assert composition.native_surface("plugin", "pi") == "extensions"
    assert composition.native_surface("plugin", "grok-build") == "plugins"
    assert (
        composition.convert(
            (_surface("component_a", component_type="plugin"),),
            composition.Target(harness_id="grok-build", os="linux", arch="x86_64"),
        )
        .entries[0]
        .projection_kind
        == "plugin"
    )
    assert (
        composition.convert(
            (_surface("component_a", component_type="plugin"),),
            composition.Target(harness_id="pi", os="linux", arch="x86_64"),
        )
        .entries[0]
        .projection_kind
        == "package"
    )


def test_a_harness_whose_mcp_lives_inside_a_settings_file_has_no_surface() -> None:
    """Absent is the honest answer, and the only one that fails closed.

    `codex` and `grok-build` both spell their MCP servers as an `mcp_servers`
    table inside `config.toml`, which the harness catalog records with a cited
    source. There is no separate file for a provider to write, so a rule naming
    one would send the projection somewhere the harness never reads: install
    verified, MCP absent. With no rule, `native_surface_lost` blocks the bundle.

    `grok-build` used to name `.mcp.json` — claude-code's spelling, which reads
    as correct sitting one line below claude-code's own row. It is checked here
    against the catalog rather than against a remembered filename, because the
    catalog is where the researched fact lives.
    """
    from ai_stp_cli.local import harness_catalog

    for harness in ("codex", "grok-build", "opencode", "claude-code"):
        assert composition.native_surface("mcp", harness) == "", harness

    # `pi` left this list on 2026-08-29, and it had been here for the wrong
    # reason: its MCP does not live inside a settings file, it does not exist.
    # The product says so itself — "intentionally does not include built-in MCP
    # … you can build or install those workflows as extensions or packages" —
    # so an MCP adapter for Pi is an extension package, and refusing it was
    # refusing something the product supports (`#454`). The passport still says
    # `mcp`; only the kind named to the provider is `plugin`.
    assert composition.native_surface("mcp", "pi") == "extensions"
    pi_rule = composition.rule_for("mcp", "pi")
    assert pi_rule is not None and pi_rule.provider_kind == "plugin"

    # `cursor` left this list on 2026-08-28, and by measurement rather than by
    # argument: a server written straight to `~/.cursor/mcp.json` is listed and
    # dialled by the product, with both controls holding — the file removed
    # reports no servers, and the same file one directory to the side reports
    # no servers. So there *is* a separate file here, and refusing to name it
    # would be the mirror defect: `native_surface_lost` blocking a bundle for a
    # surface the harness reads.
    assert composition.native_surface("mcp", "cursor") == "mcp.json"
    lost = composition.compose(
        (_surface("component_a", component_type="mcp", harness_id="codex"),),
        composition.Target(harness_id="codex", os="linux", arch="x86_64"),
    )
    hint = next(item for item in lost.conflicts if item.code == "native_surface_lost")
    assert "setting" in hint.details["hint"]

    # `claude-code` joined that list on 2026-08-27, and for a third reason
    # rather than the same one. Its MCP does not live inside a settings file —
    # `code.claude.com/docs/en/mcp` lists three scopes, `local` and `user` both
    # in `~/.claude.json` and `project` as `.mcp.json` at a repository root, and
    # the provider lists `~/.claude.json` in `never_touch`. So nothing MCP-shaped
    # is ownable inside the target. The global row had taken the project scope's
    # filename, which is why both tables agreed and both were wrong: they cited
    # the same page, and the page is *about* scopes.

    # And where a surface *is* claimed, the catalog has to agree it exists.
    for harness in ("antigravity",):
        relative = composition.native_surface("mcp", harness)
        assert relative, harness
        declared = {
            item.relative
            for item in harness_catalog.BY_ID[harness].layouts
            if item.component_type == "mcp" and item.scope == "global"
        }
        assert relative in declared, (harness, relative, declared)


def test_grok_has_no_provider_projection_for_mcp_or_command() -> None:
    """Both were claude-code's rows copied down, and neither surface exists.

    Named explicitly rather than left to the general guards, because
    `ai_stp#434` asks for exactly this pair and an issue answered by "a broader
    test covers it" is answered by nobody.

    MCP is real for Grok and lives under `[mcp_servers.<name>]` inside the
    owned `config.toml`; there is no standalone file for a provider to write,
    and promising one would mean promising a partial-TOML rollback. Slash
    commands are skills — `/<skill-name>`, qualified on collision — so there is
    no `commands/` directory either. The provider declares neither, and fails
    closed for the same reasons.

    `setting -> config.toml` stays: that file is genuinely owned. Discovery
    keeps measuring the nested `mcp_servers` table for inventory, which is a
    different question from whether a provider may install one.
    """
    for kind in ("mcp", "command"):
        assert composition.native_surface(kind, "grok-build") == "", kind
    assert composition.native_surface("setting", "grok-build") == "config.toml"


def test_where_the_two_tables_both_speak_they_name_the_same_path() -> None:
    """Two tables, two questions, one shared fact — and nothing checked it.

    `PROVIDER_RULES` answers *where does a provider write this kind*. The
    catalog's `Layout` answers *where might a person have written it*, which is
    why the catalog is deliberately incomplete: its own comment says importing
    only what is declared would silently drop configuration somebody wrote. So
    an absence on either side proves nothing, and this deliberately does not
    require either table to be complete.

    What it does require is agreement wherever both name the same kind for the
    same harness at global scope. That is one fact recorded twice, and it drifted
    exactly once: grok-build's MCP said `.mcp.json` here — claude-code's spelling
    — against the catalog's cited `config.toml`. A component would have been
    projected into a file the harness never reads.

    Only `root="config"` layouts are compared, because those are the ones
    relative to the target a provider is handed. `undefined` is the shared
    conventions entry rather than a harness and has no provider at all.
    """
    from ai_stp_cli.local import harness_catalog
    from ai_stp_foundation.harnesses import UNDEFINED_HARNESS

    rules = {(rule.harness_id, rule.component_type): rule for rule in composition.PROVIDER_RULES}
    disagreements: list[str] = []
    for definition in harness_catalog.DEFINITIONS:
        if definition.harness_id == UNDEFINED_HARNESS:
            continue
        for kind in {item.component_type for item in definition.layouts}:
            rule = rules.get((definition.harness_id, kind))
            if rule is None:
                continue
            declared = {
                item.relative
                for item in definition.layouts
                if item.component_type == kind and item.scope == "global" and item.root == "config"
            }
            if declared and rule.relative not in declared:
                disagreements.append(
                    f"{definition.harness_id}/{kind}: rule says {rule.relative!r}, "
                    f"catalog says {sorted(declared)}"
                )

    assert not disagreements, sorted(disagreements)


#: A rule may rest on a shared convention rather than on a product's own
#: documented surface, so a kind the catalog does not list for that harness is
#: not automatically wrong. What is wrong is not saying which. Each entry names
#: the basis; a rule that cannot name one is a guess about somebody's product.
#:
#: **Naming a basis does not make the surface discoverable, and this list held
#: two entries where those came apart.** `opencode/instruction` and
#: `grok-build/instruction` both cited the agents.md convention, which was true
#: and which quietly excused a real gap: each product reads its *own* global
#: `AGENTS.md` — `~/.config/opencode/AGENTS.md`, `~/.grok/AGENTS.md` — a
#: provider was already writing there, and discovery could find neither. The
#: repair was the catalog row, not the entry. Before adding one here, ask
#: whether the honest answer is a row instead.
_CONVENTION_BACKED: Final[dict[tuple[str, str], str]] = {
    ("codex", "skill"): (
        "`.agents/skills`, the shared skills convention the catalog records "
        "under `undefined` with source learn.chatgpt.com/docs/build-skills"
    ),
    ("grok-build", "agent"): (
        "declared in the provider's own grok-baseline native_discovery, which "
        "the catalog's cited vendor page does not enumerate"
    ),
    ("pi", "mcp"): (
        "declared by the product rather than by the provider: Pi states it "
        '"intentionally does not include built-in MCP … you can build or '
        'install those workflows as extensions or packages", so an MCP adapter '
        "is an extension package. The provider is told `plugin`, which it "
        "declares, and `extensions`, which it owns; the passport keeps `mcp`"
    ),
    ("claude-code", "plugin"): (
        "declared by the released provider: `0.0.30` carries `plugin` in "
        "`component_kinds` with `skills` among its namespaces, read from the "
        "downloaded binary. The catalog has no plugin layout for claude-code "
        "and must not gain one until a directory rule can carry a marker test: "
        "the product separates the two kinds by a manifest inside the child, "
        "and discovery reports every child of a directory rule as its kind"
    ),
    ("antigravity", "instruction"): (
        "declared by the released provider: `0.0.29` carries `instruction` in "
        "`component_kinds` and `config/rules` in `native_namespaces`, read from "
        "the downloaded binary. `0.0.28` declared neither, and the catalog's "
        "cited vendor page does not enumerate rules among the customization "
        "elements although the product's own reference does"
    ),
}


def test_every_rule_the_catalog_does_not_know_names_why_it_exists() -> None:
    """Agreement by omission is not agreement (`grok-setup-system#36`).

    The neighbouring guard only compares rows where *both* tables speak, which
    is right: the catalog is deliberately incomplete, so an absence there
    proves nothing about a provider. The cost is that a rule the catalog has
    never heard of passes in silence — and that is exactly where the defects
    have been.

    Four of them were claude-code's block copied down onto `grok-build`:
    `mcp -> .mcp.json`, and `command -> commands` beside `agent` and
    `instruction`. The first was removed when a cited source contradicted it.
    The second was removed when the provider measured the vendor's own
    documentation: Grok surfaces slash commands as **skills**, `/<skill-name>`,
    and there is no `~/.grok/commands` for anyone to write to. Both tables are
    silent about it now, which is agreement rather than omission.

    So a rule whose kind the catalog does not list for that harness has to say
    what it rests on instead. It may be a shared convention or a provider's own
    declaration — both are real sources — but it may not be nothing.
    """
    from ai_stp_cli.local import harness_catalog

    unexplained: list[str] = []
    for rule in composition.PROVIDER_RULES:
        definition = harness_catalog.BY_ID.get(rule.harness_id)
        if definition is None:
            continue
        declared = {item.component_type for item in definition.layouts}
        if rule.component_type in declared:
            continue
        if (rule.harness_id, rule.component_type) in _CONVENTION_BACKED:
            continue
        unexplained.append(f"{rule.harness_id}/{rule.component_type} -> {rule.relative}")

    assert not unexplained, sorted(unexplained)


def test_the_stated_bases_are_all_still_load_bearing() -> None:
    """An allowlist nobody prunes becomes a place to hide the next one."""
    from ai_stp_cli.local import harness_catalog

    rules = {(rule.harness_id, rule.component_type) for rule in composition.PROVIDER_RULES}
    stale: list[str] = []
    for harness_id, kind in _CONVENTION_BACKED:
        definition = harness_catalog.BY_ID.get(harness_id)
        if (harness_id, kind) not in rules:
            stale.append(f"{harness_id}/{kind}: no such rule any more")
        elif definition is not None and kind in {
            item.component_type for item in definition.layouts
        }:
            stale.append(f"{harness_id}/{kind}: the catalog declares it now")

    assert not stale, sorted(stale)


#: Surfaces the catalog anchors to `$HOME` that `PROVIDER_RULES` still names,
#: with what closes each. A provider owns only its `--target`, so a rule naming
#: a home-anchored path resolves under the target instead and lands one
#: directory across from where the product reads.
#:
#: Empty is the goal. An entry here is a defect with a due date, not a decision.
_HOME_ANCHORED_DEBT: dict[tuple[str, str], str] = {}


def test_a_provider_rule_never_names_a_surface_anchored_outside_its_target() -> None:
    """A path is only a path together with what it is relative to.

    Five defects in one day were this sentence: three filenames copied across
    scopes, one scope misresolved, and one root dropped. This guards the last
    kind, which is the one with published victims.

    `Rule` carries a `root` that means something in discovery — `config` for a
    harness configuration home, `home` for a cross-product convention under
    `$HOME` — and means nothing in projection, because a provider owns exactly
    one directory and it is the `--target` it was handed. So a projection rule
    naming a surface the catalog anchors to `$HOME` is not merely undeclared;
    it is unrepresentable, and it resolves under the target instead.

    Measured: codex's `.agents/skills` resolves to `~/.codex/.agents/skills`
    while the documented directory is `$HOME/.agents/skills` — a sibling, not a
    child. An install writes twenty-nine files, answers `verified`, and the
    product reads none of them. The provider is truthful and conformance cannot
    see it: its cases are refusals, and none asks whether the harness reads what
    was written.

    Stated as a general rule rather than as one row, because the shared
    conventions the catalog knows — `.agents/skills` and `.agents/commands` —
    are exactly the paths most likely to be copied into a projection table by
    someone reading the string and not the anchor.

    **A rule that declares a non-global `target_scope` is exempt, and that is
    the repair rather than a hole in the guard.** The defect was never the path;
    it was a path with no statement of what it hangs off, resolved against the
    only root the rule could reach. A `user_root` rule names its root, so
    `skills` under it is `~/.agents/skills` and nothing about it is ambiguous.
    The list is empty now because the one entry was paid that way.
    """
    from ai_stp_cli.local import harness_catalog

    home_anchored = {
        item.relative
        for definition in harness_catalog.DEFINITIONS
        for item in definition.layouts
        if item.root == "home"
    }
    assert home_anchored, "the catalog must still know at least one shared convention"

    offending = {
        (rule.harness_id, rule.component_type)
        for rule in composition.PROVIDER_RULES
        if rule.relative in home_anchored and rule.target_scope == "global"
    }
    assert offending <= set(_HOME_ANCHORED_DEBT), sorted(offending - set(_HOME_ANCHORED_DEBT))


def test_the_home_anchored_debt_is_still_owed() -> None:
    """An entry that has been paid must leave, or the list becomes a hiding place."""
    from ai_stp_cli.local import harness_catalog

    home_anchored = {
        item.relative
        for definition in harness_catalog.DEFINITIONS
        for item in definition.layouts
        if item.root == "home"
    }
    live = {
        (rule.harness_id, rule.component_type)
        for rule in composition.PROVIDER_RULES
        if rule.relative in home_anchored
    }
    assert set(_HOME_ANCHORED_DEBT) <= live, sorted(set(_HOME_ANCHORED_DEBT) - live)


def test_provider_rule_projection_kinds_are_the_protocol_closed_set() -> None:
    """A typo here becomes `the exact native package family exceeds provider capabilities`."""
    from ai_stp_cli.provider.protocol_v3 import ProjectionKind

    allowed = {kind.value for kind in ProjectionKind}
    illegal = [
        (rule.harness_id, rule.component_type, rule.projection_kind)
        for rule in composition.PROVIDER_RULES
        if rule.projection_kind not in allowed
    ]
    assert not illegal, illegal


# Documentation and code are two statements of one closed set.
def test_the_conflict_registry_matches_the_contract() -> None:
    written = set(re.findall(r"^\| `([a-z_]+)` \|", CONTRACT.read_text("utf-8"), re.MULTILINE))
    states = {composition.STATE_COMPLETE, composition.STATE_PARTIAL, composition.STATE_UNSUPPORTED}
    assert written - states == composition.CONFLICTS


def test_the_operation_registry_matches_the_contract() -> None:
    text = CONTRACT.read_text("utf-8")
    for name in composition.OPERATIONS:
        assert name in text


#: Projection rules a released provider does not accept, and why each may stay.
#:
#: Empty is the goal. An entry means a component of that kind cannot be
#: installed on that harness by the provider people actually have.
_UNDECLARED_BY_PROVIDER: dict[tuple[str, str], str] = {
    ("codex", "skill"): (
        "`ADR-0127`. The provider withdrew `skill` from codex's declaration at "
        "0.0.7 exactly as that record predicted, so the 62 corpus skills — 61 "
        "published — now refuse rather than installing where codex cannot read. "
        "The refusal is the improvement; removing the rule first would leave "
        "nothing to install once corrected versions exist. Closes with the "
        "corpus re-seed."
    ),
}


def test_a_projection_rule_names_a_kind_the_released_provider_accepts() -> None:
    """The one table that is not ours, asked directly instead of remembered.

    Every other guard here compares two of our own tables, so both can be wrong
    together — and twice now they were, agreeing on a surface no product reads.
    `provider-info` is the provider's own declaration of what it will accept and
    where it writes, so it settles those cases from outside.

    It found cursor's `instruction -> AGENTS.md`: the released provider declares
    `plugin` and `setting` only, because `cursor.com/docs/rules` puts AGENTS.md
    at a project root and there is no global `~/.cursor/AGENTS.md`. Our rule and
    the catalog row both cited that page. The kind-level guard above could not
    see it, since cursor's project `.cursor/rules` makes `instruction` a
    declared kind for the harness — a kind without a scope is not a surface.

    Skipped unless real providers are wired, because it is evidence rather than
    a unit: what it asserts is a property of built binaries, not of this file.
    """
    directory = os.environ.get("AI_STP_PROVIDER_V3_DIR")
    if directory is None:
        pytest.skip("set AI_STP_PROVIDER_V3_DIR to a directory of v3 provider binaries")

    from ai_stp_cli.local import harness_catalog

    binaries = {
        definition.harness_id: name
        for definition in harness_catalog.DEFINITIONS
        for name in [
            f"{definition.harness_id.removesuffix('-code').removesuffix('-build')}-setup-system"
        ]
        if (Path(directory) / name).is_file()
    }
    assert binaries, f"no provider binaries found under {directory}"

    undeclared: list[str] = []
    unnamed: list[str] = []
    for harness_id, binary in sorted(binaries.items()):
        completed = subprocess.run(
            [str(Path(directory) / binary), "provider-info"],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        answer: dict[str, Any] = json.loads(completed.stdout)
        profile: dict[str, Any] = answer.get("projection_profile") or {}
        kinds = {str(item) for item in profile.get("component_kinds", [])}
        namespaces = {str(item) for item in profile.get("native_namespaces", [])}
        for rule in composition.PROVIDER_RULES:
            if rule.harness_id != harness_id:
                continue
            if rule.component_type not in kinds:
                undeclared.append(f"{harness_id}/{rule.component_type} -> {rule.relative}")
            elif rule.relative not in namespaces:
                unnamed.append(f"{harness_id}/{rule.component_type} -> {rule.relative}")

    allowed = {f"{h}/{k}" for h, k in _UNDECLARED_BY_PROVIDER}
    named = {item.split(" ->")[0] for item in undeclared}
    assert named <= allowed, sorted(undeclared)
    # And the other direction, without which this list outlives its reasons.
    # Every other exception register here has this pair; this one shipped
    # without it, so a `codex/skill` entry would have sat unopposed the day the
    # corpus re-seed paid the debt. An allowlist nobody prunes is a hiding
    # place — the same sentence that removed two entries from
    # `_CONVENTION_BACKED` when the catalog learned their rows.
    assert allowed <= named, sorted(allowed - named)
    # A declared kind written to a path the provider does not own is the same
    # defect one level down, and has no standing exception.
    assert not unnamed, sorted(unnamed)


#: Kinds a released provider accepts that this program cannot compose.
#:
#: Not defects — nothing is written to a wrong place — but capability a person
#: cannot reach, and invisible until measured. The guard above catches a
#: provider *dropping* a kind we project; nothing caught a provider *gaining*
#: one, so a surface could be installable for months with no rule to reach it.
#:
#: An inventory rather than a threshold: adding a rule needs the vendor page and
#: the provider's agreement, so the value here is that a change arrives as a
#: reviewed diff and asks the question out loud.
_PROVIDER_OFFERS_UNUSED: dict[str, tuple[str, ...]] = {
    "claude-code": ("plugin", "setting"),
    "codex": ("command", "hook"),
    "pi": ("command",),
}


def test_the_capability_this_program_leaves_unused_is_the_measured_set() -> None:
    """What the providers can install and nothing here can ask for."""
    directory = os.environ.get("AI_STP_PROVIDER_V3_DIR")
    if directory is None:
        pytest.skip("set AI_STP_PROVIDER_V3_DIR to a directory of v3 provider binaries")

    from ai_stp_cli.local import harness_catalog

    unused: dict[str, tuple[str, ...]] = {}
    for definition in harness_catalog.DEFINITIONS:
        harness_id = definition.harness_id
        stem = harness_id.removesuffix("-code").removesuffix("-build")
        binary = Path(directory) / f"{stem}-setup-system"
        if not binary.is_file():
            continue
        completed = subprocess.run(
            [str(binary), "provider-info"],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        answer: dict[str, Any] = json.loads(completed.stdout)
        profile: dict[str, Any] = answer.get("projection_profile") or {}
        kinds = {str(item) for item in profile.get("component_kinds", [])}
        projected = {
            rule.component_type
            for rule in composition.PROVIDER_RULES
            if rule.harness_id == harness_id
        }
        if kinds - projected:
            unused[harness_id] = tuple(sorted(kinds - projected))

    assert unused == _PROVIDER_OFFERS_UNUSED


def test_a_managed_path_outside_its_kinds_projection_root_is_refused() -> None:
    """The published path and the computed one were unioned, never compared.

    A component declares `managed_paths` and the rule for its kind names a root.
    Both went into one set and the composition carried whichever it was given,
    so a path relative to the wrong root produced a second, silently wrong
    surface beside the right one. Against a `~/.agents` target, a codex skill
    declaring `.agents/skills/x` projects into `~/.agents/.agents/skills/x`.

    `install.py` does refuse a native surface the provider never declared, but
    it refuses the whole bundle after selection and names provider capabilities.
    This names the component and the path while a person can still act on it.
    """
    report = composition.compose(
        (_surface("component_a", managed_paths=(".agents/skills/x",), source_name="x"),),
        CLAUDE,
    )
    assert report.blocked
    assert "managed_path_outside_projection" in _codes(report)
    detail = next(
        item for item in report.conflicts if item.code == "managed_path_outside_projection"
    )
    # The root, not only the offending path: the two are only comparable
    # together, and a message with one of them asks the reader to guess.
    assert detail.details["path"] == ".agents/skills/x"
    assert detail.details["projection_root"] == "skills"


def test_a_managed_path_at_or_under_its_projection_root_is_accepted() -> None:
    """Both shapes: a directory rule's child, and a file rule's exact path."""
    directory = composition.compose(
        (_surface("component_a", managed_paths=("skills/x",), source_name="x"),), CLAUDE
    )
    assert "managed_path_outside_projection" not in _codes(directory)
    exact = composition.compose(
        (
            _surface(
                "component_b",
                component_type="setting",
                harness_id="cursor",
                managed_paths=("cli-config.json",),
            ),
        ),
        composition.Target(harness_id="cursor", os="linux", arch="x86_64"),
    )
    assert "managed_path_outside_projection" not in _codes(exact)


def test_a_kind_with_no_rule_makes_no_claim_about_its_paths() -> None:
    """Absence of a rule is not a rule that everything is wrong.

    Cursor has no `agent` row: the sweep that found five user-scope surfaces in
    its bundle found no directory for that kind, so the gap narrowed to exactly
    one rather than disappearing. `instruction` was the example here until
    2026-08-28, when the User Rule scope at `~/.cursor/rules` was confirmed and
    routed. Refusing its paths here would be inventing a projection
    from the fact that none exists, and the honest refusal for a kind this
    compiler cannot place belongs to eligibility, not to path arithmetic.
    """
    report = composition.compose(
        (
            _surface(
                "component_a",
                component_type="agent",
                harness_id="cursor",
                managed_paths=("agents/reviewer.md",),
            ),
        ),
        composition.Target(harness_id="cursor", os="linux", arch="x86_64"),
    )
    assert "managed_path_outside_projection" not in _codes(report)
