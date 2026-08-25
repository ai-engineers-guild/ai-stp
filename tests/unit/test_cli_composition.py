"""Every named conflict class has a fixture, and the reports stay stable."""

import re
from pathlib import Path

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
    assert composition.native_surface("skill", "codex") == ".agents/skills"
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
        == "extension"
    )


# Documentation and code are two statements of one closed set.
def test_the_conflict_registry_matches_the_contract() -> None:
    written = set(re.findall(r"^\| `([a-z_]+)` \|", CONTRACT.read_text("utf-8"), re.MULTILINE))
    states = {composition.STATE_COMPLETE, composition.STATE_PARTIAL, composition.STATE_UNSUPPORTED}
    assert written - states == composition.CONFLICTS


def test_the_operation_registry_matches_the_contract() -> None:
    text = CONTRACT.read_text("utf-8")
    for name in composition.OPERATIONS:
        assert name in text
