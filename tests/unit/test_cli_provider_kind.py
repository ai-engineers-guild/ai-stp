"""A component's kind and the kind its provider is told can differ (`#454`).

Pi declares no `mcp` kind, and says why in its own documentation: it
"intentionally does not include built-in MCP, sub-agents, permission popups,
plan mode, to-dos, or background bash. You can build or install those workflows
as extensions or packages." So an MCP adapter for Pi *is* an extension, and the
component failed twice — `provider_surface_unavailable` because no route
existed, then `unsupported_component_kind: mcp` once a route was added naively.

The passport keeps `mcp`. Only the word spoken at the provider boundary changes.
"""

from __future__ import annotations

from ai_stp_cli.local import composition


def test_pi_routes_an_mcp_component_to_its_extension_surface() -> None:
    rule = composition.rule_for("mcp", "pi")
    assert rule is not None
    assert rule.relative == "extensions"
    assert rule.projection_kind == "package"
    assert composition.native_surface("mcp", "pi") == "extensions"


def test_the_provider_is_told_a_kind_it_declares() -> None:
    """The second failure, and the one a route alone does not fix."""
    rule = composition.rule_for("mcp", "pi")
    assert rule is not None
    assert rule.provider_kind == "plugin"


def test_no_other_harness_translates_its_kinds() -> None:
    """`#454` asks for exactly one mapping and no other route to change.

    A translation is a claim that a product has no kind of its own for
    something, and one that spread quietly would hide a missing declaration
    behind a rename.
    """
    translated = {
        (rule.harness_id, rule.component_type, rule.provider_kind)
        for rule in composition.PROVIDER_RULES
        if rule.provider_kind and rule.provider_kind != rule.component_type
    }
    assert translated == {("pi", "mcp", "plugin")}


def test_every_translation_names_a_kind_its_harness_declares_a_route_for() -> None:
    """A translation must land somewhere the compiler can also reach.

    Naming a provider kind this table cannot itself route would move the
    refusal to the provider, which is the shape this repository has already
    paid for: closed, but late.
    """
    for rule in composition.PROVIDER_RULES:
        if not rule.provider_kind or rule.provider_kind == rule.component_type:
            continue
        target = composition.rule_for(rule.provider_kind, rule.harness_id)
        assert target is not None, f"{rule.harness_id}: {rule.provider_kind} has no route"
        assert target.relative == rule.relative, (
            f"{rule.harness_id}: {rule.component_type} lands on {rule.relative} "
            f"but {rule.provider_kind} lands on {target.relative}"
        )
