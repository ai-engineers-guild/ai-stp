"""Mechanical constraints: refused stays refused, and every refusal names why."""

import re
from pathlib import Path

import pytest

from ai_stp_cli.local import eligibility, search

CONTRACT = Path("docs/contracts/eligibility-constraints.md")
VOCABULARY = Path("docs/contracts/capability-vocabulary.md")

TARGET = eligibility.Target(
    harness_id="claude-code",
    os="linux",
    arch="x86_64",
    harness_version="2.1.224 (Claude Code)",
    capabilities=frozenset({"project.language.python", "project.vcs.git"}),
    entitlements=frozenset({"file:read"}),
    owner_id="account_me",
    provider_harnesses=frozenset({"claude-code", "codex"}),
)


def _candidate(**overrides: object) -> eligibility.CandidateFacts:
    """A candidate that passes everything, so a test changes exactly one thing."""
    facts: dict[str, object] = {
        "stable_id": "component_01J0000000000000000000000A",
        "revision_id": "revision_a",
        "version": "1.0",
        "harness_id": "claude-code",
        "owner_id": "account_other",
        "visibility": "public",
        "license_id": "MIT",
        "author_verified": True,
        "component_verified": True,
        "checks_current": True,
    }
    facts.update(overrides)
    return eligibility.CandidateFacts(**facts)  # pyright: ignore[reportArgumentType]


def _codes(assessment: eligibility.Assessment) -> tuple[str, ...]:
    return tuple(item.code for item in assessment.refusals)


def test_a_clean_candidate_is_admissible_and_selectable() -> None:
    verdict = eligibility.assess(_candidate(), TARGET)
    assert verdict.refusals == ()
    assert verdict.admissible
    assert verdict.auto_selectable
    assert verdict.lane == search.LANE_AUTHORITATIVE


# REQ-601: the mechanical stage runs before selection, so nothing it refuses can
# be chosen. Asserted over every single-constraint failure rather than one of
# them: the guarantee is about the set, not about a favourite member of it.
@pytest.mark.parametrize(
    ("override", "code"),
    [
        ({"harness_id": "codex"}, "harness_mismatch"),
        ({"harness_versions": ("9.0.0", "")}, "harness_version_unsupported"),
        ({"supported_os": frozenset({"darwin"})}, "os_unsupported"),
        ({"supported_arch": frozenset({"aarch64"})}, "arch_unsupported"),
        ({"requires_capabilities": ("no dots here",)}, "capability_malformed"),
        ({"requires_capabilities": ("tool.pytest",)}, "capability_unknown"),
        ({"requires_capabilities": ("project.language.rust",)}, "capability_missing"),
        ({"registrable": False}, "object_not_registrable"),
        ({"blocked": True}, "object_blocked"),
        ({"visibility": "private"}, "grant_missing"),
        ({"checks_current": False}, "evidence_stale"),
        ({"license_id": ""}, "license_undeclared"),
        ({"entitlements": ("network:outbound",)}, "entitlement_not_granted"),
    ],
)
def test_every_single_constraint_refuses_and_nothing_refused_is_selectable(
    override: dict[str, object], code: str
) -> None:
    verdict = eligibility.assess(_candidate(**override), TARGET)
    assert code in _codes(verdict)
    assert not verdict.admissible
    assert not verdict.auto_selectable
    assert eligibility.admissible((verdict,)) == ()
    assert eligibility.selectable((verdict,)) == ()


def test_a_refusal_never_carries_an_undeclared_code() -> None:
    """The family lookup is the guard; this proves it covers what is produced."""
    every = [
        eligibility.assess(_candidate(**case), TARGET)
        for case in (
            {"harness_id": "codex", "harness_versions": ("9.0", "")},
            {"visibility": "private", "license_id": "", "checks_current": False},
            {"requires_capabilities": ("tool.pytest", "project.language.rust", "bad")},
            {"entitlements": ("network:outbound",), "blocked": True, "registrable": False},
        )
    ]
    produced = {item.code for verdict in every for item in verdict.refusals}
    assert produced <= set(eligibility.REFUSALS)
    for verdict in every:
        for refusal in verdict.refusals:
            assert refusal.family == eligibility.REFUSALS[refusal.code]
            assert refusal.family in eligibility.FAMILIES


# REQ-602: `authoritative` needs both axes and current checks. Each of the three
# is removed on its own, because a lane that accepted any two would look correct
# on a candidate that has all three.
@pytest.mark.parametrize("missing", ["author_verified", "component_verified", "checks_current"])
def test_authoritative_needs_every_axis(missing: str) -> None:
    verdict = eligibility.assess(_candidate(**{missing: False}), TARGET)
    assert verdict.lane != search.LANE_AUTHORITATIVE
    assert not verdict.auto_selectable


# REQ-603: consent opens the section, never the automatic install.
def test_experimental_is_refused_without_consent() -> None:
    verdict = eligibility.assess(_candidate(component_verified=False), TARGET)
    assert verdict.lane == search.LANE_EXPERIMENTAL
    assert "unverified_without_consent" in _codes(verdict)
    assert not verdict.admissible


def test_experimental_with_consent_is_admissible_but_never_auto_selected() -> None:
    verdict = eligibility.assess(_candidate(component_verified=False, consented=True), TARGET)
    assert verdict.lane == search.LANE_EXPERIMENTAL
    assert verdict.admissible, "consent lets it be considered"
    assert not verdict.auto_selectable, "consent never lets it be chosen on its own"
    assert eligibility.selectable((verdict,)) == ()


def test_consent_cannot_move_a_candidate_out_of_experimental() -> None:
    """The lane is a reading of facts, so a flag cannot rewrite it."""
    without = eligibility.assess(_candidate(author_verified=False), TARGET)
    with_consent = eligibility.assess(_candidate(author_verified=False, consented=True), TARGET)
    assert without.lane == with_consent.lane == search.LANE_EXPERIMENTAL


# The first of the two traps: an unknown capability is a wrong passport and a
# missing one is a mismatch with this machine. One code for both would send the
# user to install something that does not exist.
def test_unknown_and_missing_capabilities_are_different_refusals() -> None:
    verdict = eligibility.assess(
        _candidate(requires_capabilities=("tool.pytest", "project.language.rust")), TARGET
    )
    assert set(_codes(verdict)) == {"capability_unknown", "capability_missing"}
    named = {item.code: item.details["capability"] for item in verdict.refusals}
    assert named["capability_unknown"] == "tool.pytest"
    assert named["capability_missing"] == "project.language.rust"


def test_a_malformed_capability_is_not_reported_as_unknown() -> None:
    verdict = eligibility.assess(_candidate(requires_capabilities=("Project..Language",)), TARGET)
    assert _codes(verdict) == ("capability_malformed",)


# The second trap: `SPEC-001` REQ-111 and `SPEC-008` REQ-816 both allow the
# install. Refusing here is the easy mistake and contradicts two requirements.
def test_a_missing_mandatory_variable_is_a_note_and_never_a_refusal() -> None:
    verdict = eligibility.assess(_candidate(required_env=("OPENAI_API_KEY", "AWS_REGION")), TARGET)
    assert verdict.refusals == ()
    assert verdict.admissible
    assert verdict.auto_selectable
    assert [item.code for item in verdict.notes] == [eligibility.NOTE_REQUIRED_ENV_MISSING]
    assert verdict.notes[0].details["names"] == "AWS_REGION, OPENAI_API_KEY"


def test_a_present_variable_produces_no_note() -> None:
    verdict = eligibility.assess(
        _candidate(required_env=("HOME",)),
        eligibility.Target(
            harness_id="claude-code",
            os="linux",
            arch="x86_64",
            env_present=frozenset({"HOME"}),
            provider_harnesses=frozenset({"claude-code"}),
        ),
    )
    assert verdict.notes == ()


def test_a_note_never_carries_a_value_only_a_name() -> None:
    verdict = eligibility.assess(_candidate(required_env=("SECRET_TOKEN",)), TARGET)
    assert verdict.notes[0].details == {"names": "SECRET_TOKEN"}


def test_authorization_and_credentials_are_notes_not_refusals() -> None:
    verdict = eligibility.assess(
        _candidate(requires_authorization="external_service", requires_credentials=True), TARGET
    )
    assert verdict.refusals == ()
    assert {item.code for item in verdict.notes} == {
        eligibility.NOTE_AUTHORIZATION_REQUIRED,
        eligibility.NOTE_CREDENTIALS_REQUIRED,
    }


# REQ-607: one canonical input, one answer. The order a passport happened to be
# written in is not part of the input.
def test_the_refusal_order_does_not_depend_on_how_a_passport_was_written() -> None:
    wanted = ("project.language.rust", "tool.pytest", "project.language.go")
    first = eligibility.assess(_candidate(requires_capabilities=wanted), TARGET)
    second = eligibility.assess(_candidate(requires_capabilities=tuple(reversed(wanted))), TARGET)
    assert _codes(first) == _codes(second)
    assert [item.details for item in first.refusals] == [item.details for item in second.refusals]


def test_families_come_back_in_the_order_the_requirement_names_them() -> None:
    verdict = eligibility.assess(
        _candidate(
            harness_id="codex",
            visibility="private",
            checks_current=False,
            license_id="",
            entitlements=("network:outbound",),
        ),
        eligibility.Target(harness_id="claude-code", os="linux", arch="x86_64"),
    )
    seen = [item.family for item in verdict.refusals]
    assert seen == sorted(seen, key=eligibility.FAMILIES.index)


def test_many_candidates_come_back_in_a_stable_order() -> None:
    made = tuple(
        _candidate(stable_id=f"component_{suffix}", revision_id=f"revision_{suffix}")
        for suffix in ("c", "a", "b")
    )
    assert [item.stable_id for item in eligibility.assess_all(made, TARGET)] == [
        "component_a",
        "component_b",
        "component_c",
    ]
    assert eligibility.assess_all(made, TARGET) == eligibility.assess_all(
        tuple(reversed(made)), TARGET
    )


# ADR-0032: eligibility is derived from current evidence, and the user's own
# work has none to be stale.
def test_stale_evidence_blocks_a_third_party_object() -> None:
    verdict = eligibility.assess(_candidate(checks_current=False, consented=True), TARGET)
    assert "evidence_stale" in _codes(verdict)


def test_your_own_object_needs_no_evidence_no_licence_and_no_grant() -> None:
    verdict = eligibility.assess(
        _candidate(
            owner_id="account_me",
            visibility="private",
            license_id="",
            owned_or_pinned=True,
            author_verified=False,
            component_verified=False,
            checks_current=False,
        ),
        TARGET,
    )
    assert verdict.refusals == ()
    assert verdict.lane == search.LANE_LOCAL
    assert verdict.auto_selectable


def test_a_pinned_object_is_never_displayed_as_platform_confirmed() -> None:
    verdict = eligibility.assess(_candidate(owned_or_pinned=True), TARGET)
    assert verdict.lane == search.LANE_LOCAL
    assert "confirmed" not in verdict.lane_reason.replace("platform", "")


def test_a_private_object_of_another_owner_needs_a_grant_on_its_major_line() -> None:
    candidate = _candidate(visibility="private", version="2.3")
    assert "grant_missing" in _codes(eligibility.assess(candidate, TARGET))

    granted = eligibility.Target(
        harness_id="claude-code",
        os="linux",
        arch="x86_64",
        owner_id="account_me",
        grants=frozenset({f"{candidate.stable_id}:2"}),
        provider_harnesses=frozenset({"claude-code"}),
    )
    assert eligibility.assess(candidate, granted).refusals == ()


def test_a_grant_on_another_major_line_does_not_cover_this_one() -> None:
    candidate = _candidate(visibility="private", version="3.0")
    granted = eligibility.Target(
        harness_id="claude-code",
        os="linux",
        arch="x86_64",
        owner_id="account_me",
        grants=frozenset({f"{candidate.stable_id}:2"}),
        provider_harnesses=frozenset({"claude-code"}),
    )
    assert "grant_missing" in _codes(eligibility.assess(candidate, granted))


def test_redistribution_is_only_demanded_when_the_composition_is_for_it() -> None:
    candidate = _candidate(redistribution=False)
    assert eligibility.assess(candidate, TARGET).refusals == ()

    distributing = eligibility.Target(
        harness_id="claude-code",
        os="linux",
        arch="x86_64",
        provider_harnesses=frozenset({"claude-code"}),
        for_redistribution=True,
    )
    assert "redistribution_forbidden" in _codes(eligibility.assess(candidate, distributing))


def test_a_harness_no_provider_covers_is_refused_once() -> None:
    bare = eligibility.Target(harness_id="undefined", os="linux", arch="x86_64")
    codes = _codes(eligibility.assess(_candidate(harness_id="undefined"), bare))
    assert codes.count("provider_unavailable") == 1
    # Without a provider there is no platform list to be outside of; a second
    # refusal would read as a second thing to fix.
    assert "provider_platform_unsupported" not in codes


def test_a_declared_provider_platform_limit_is_enforced() -> None:
    limited = eligibility.Target(
        harness_id="claude-code",
        os="linux",
        arch="x86_64",
        provider_harnesses=frozenset({"claude-code"}),
        provider_platforms=frozenset({"darwin/arm64"}),
    )
    verdict = eligibility.assess(_candidate(), limited)
    assert "provider_platform_unsupported" in _codes(verdict)
    assert verdict.refusals[-1].details["platform"] == "linux/x86_64"


# Version reading. Both real harnesses on a developer machine print the version
# inside a sentence, and a stricter reader would refuse every ranged candidate.
@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        ("2.1.224 (Claude Code)", ((2, 1, 224), 1)),
        ("codex-cli 0.146.0", ((0, 146, 0), 1)),
        ("v1.4.0", ((1, 4, 0), 1)),
        ("1.2.3-beta", ((1, 2, 3), 0)),
        ("unknown", None),
        ("", None),
        ("2", None),
    ],
)
def test_a_version_is_read_out_of_whatever_a_harness_printed(
    printed: str, expected: tuple[tuple[int, ...], int] | None
) -> None:
    assert eligibility._reading(printed) == expected  # pyright: ignore[reportPrivateUsage]


def test_a_prerelease_does_not_satisfy_the_floor_written_to_exclude_it() -> None:
    target = eligibility.Target(
        harness_id="claude-code",
        os="linux",
        arch="x86_64",
        harness_version="1.2.3-beta",
        provider_harnesses=frozenset({"claude-code"}),
    )
    assert "harness_version_unsupported" in _codes(
        eligibility.assess(_candidate(harness_versions=("1.2.3", "")), target)
    )


def test_a_shorter_version_is_the_same_version_as_its_padded_form() -> None:
    target = eligibility.Target(
        harness_id="claude-code",
        os="linux",
        arch="x86_64",
        harness_version="1.2",
        provider_harnesses=frozenset({"claude-code"}),
    )
    assert (
        eligibility.assess(_candidate(harness_versions=("1.2.0", "1.2.0")), target).refusals == ()
    )


def test_an_unreadable_version_is_not_reported_as_an_unsupported_one() -> None:
    silent = eligibility.Target(
        harness_id="claude-code",
        os="linux",
        arch="x86_64",
        harness_version="unknown",
        provider_harnesses=frozenset({"claude-code"}),
    )
    codes = _codes(eligibility.assess(_candidate(harness_versions=("1.0", "")), silent))
    assert codes == ("harness_version_unknown",)


def test_a_candidate_declaring_no_range_never_asks_about_the_version() -> None:
    silent = eligibility.Target(
        harness_id="claude-code",
        os="linux",
        arch="x86_64",
        harness_version="",
        provider_harnesses=frozenset({"claude-code"}),
    )
    assert eligibility.assess(_candidate(), silent).refusals == ()


def test_observed_capabilities_never_leave_the_vocabulary() -> None:
    held = eligibility.observed_capabilities(
        languages=("python", "cobol"),
        surfaces=("AGENTS.md", "README.md"),
        git=True,
        tools_current=("ruff", "invented"),
    )
    assert held == {
        "project.language.python",
        "project.surface.agents_md",
        "project.vcs.git",
        "toolchain.ruff",
    }
    assert held <= eligibility.CAPABILITIES


def test_the_capability_shape_rules_are_the_ones_the_contract_states() -> None:
    assert eligibility.well_formed("project.language.python")
    assert eligibility.well_formed("toolchain.ruff")
    assert not eligibility.well_formed("python")
    assert not eligibility.well_formed("a.b.c.d.e")
    assert not eligibility.well_formed("project..python")
    assert not eligibility.well_formed("project.-python")
    assert not eligibility.well_formed("project.python-")
    assert not eligibility.well_formed("project.py thon")
    assert not eligibility.well_formed("p." + "x" * eligibility.CAPABILITY_MAX_LENGTH)


def test_normalisation_folds_case_and_form_before_comparison() -> None:
    assert eligibility.normalise_capability("  Project.Language.PYTHON ") == (
        "project.language.python"
    )


# Documentation and code are two statements of one closed set, and the failure
# mode is that they agree today and drift the first time somebody adds a code to
# one of them.
def test_the_refusal_registry_matches_the_contract() -> None:
    written = set(re.findall(r"^\| `([a-z_]+)` \|", CONTRACT.read_text("utf-8"), re.MULTILINE))
    assert written - eligibility.NOTES == set(eligibility.REFUSALS)


def test_the_capability_vocabulary_matches_the_contract() -> None:
    written = set(
        re.findall(r"^\| `([a-z][a-z0-9_.]+)` \|", VOCABULARY.read_text("utf-8"), re.MULTILINE)
    )
    assert written == eligibility.CAPABILITIES


def test_every_declared_family_is_reachable() -> None:
    assert set(eligibility.REFUSALS.values()) == set(eligibility.FAMILIES)


def test_a_kind_the_provider_cannot_project_is_refused_before_selection() -> None:
    """Found by running the whole pipeline, not by reading it.

    A `setting` component for `claude-code` discovers, adopts, versions and was
    reported admissible — and only `select bundle` said `claude-code has no
    native surface for setting`, by which point an immutable SetupVersion had
    already been frozen. `REQ-601` puts the mechanical stage before selection
    precisely so an impossibility is not learned that late.

    Not `harness_mismatch`: the object does name this harness. A familiar
    refusal accurate about the wrong thing costs more than a new code, which is
    the same argument that kept `unsupported_platform` from carrying a second
    meaning.

    The kinds are read from the projection table rather than spelled here, so
    the test states the rule instead of today's contents of the table.

    Half of that was true and the untrue half let this narrow without a word.
    The *filter* read the table; the two candidate lists were written by hand,
    and `("setting", "hook", "plugin")` was the absent set when it was written.
    Both `setting` and `plugin` gained claude-code routes since — the first
    declared by a released provider, the second by `0.0.30` — so `absent`
    quietly went from three members to one while `assert projectable and absent`
    stayed green, because a non-empty list is all it ever asked for.

    Every kind is partitioned now, and the sizes are asserted. A kind moving
    between the two halves is a reviewed line rather than a silent narrowing.
    """
    from typing import get_args

    from ai_stp_cli.local.composition import native_surface
    from ai_stp_passports.versions import ComponentType

    kinds = get_args(ComponentType.__value__)
    projectable = [kind for kind in kinds if native_surface(kind, "claude-code")]
    absent = [kind for kind in kinds if not native_surface(kind, "claude-code")]

    assert len(projectable) + len(absent) == len(kinds) == 8
    assert projectable and absent, "the fixture harness must have both, or this proves nothing"
    # Named, so the partition is the assertion rather than its precondition.
    # `hook` left on 2026-08-31: `ADR-0129` gives it a surface, the `hooks` key
    # inside the owned `settings.json`, and a component landing inside a file
    # the provider owns compiles into a contribution to that file. `mcp` stays
    # absent for the reason that has always been its own — `.mcp.json` is a
    # project file and the user scope lives in `~/.claude.json`, which the
    # provider holds in `never_touch`, so there is no owned host here to
    # contribute to.
    assert set(absent) == {"mcp"}, absent

    for kind in projectable:
        verdict = eligibility.assess(
            _candidate(harness_id="claude-code", component_type=kind, owned_or_pinned=True),
            TARGET,
        )
        assert "provider_surface_unavailable" not in {r.code for r in verdict.refusals}, kind

    for kind in absent:
        verdict = eligibility.assess(
            _candidate(harness_id="claude-code", component_type=kind, owned_or_pinned=True),
            TARGET,
        )
        codes = {r.code for r in verdict.refusals}
        assert "provider_surface_unavailable" in codes, kind
        assert "harness_mismatch" not in codes, kind
        assert not verdict.admissible, kind

    # A setup names no kind, and must not be caught by a constraint about kinds.
    setup = eligibility.assess(
        _candidate(harness_id="claude-code", owned_or_pinned=True),
        TARGET,
    )
    assert "provider_surface_unavailable" not in {r.code for r in setup.refusals}


def test_a_portable_component_fits_every_harness_with_a_surface_for_its_kind() -> None:
    """`#64`: the portable claim is proposable, not four fake harness claims.

    A repository-root `AGENTS.md` answers to the cross-product convention and
    to no single harness, so its adopted component names none. `harness_mismatch`
    compared that empty name to the target and refused it everywhere, leaving an
    author with no path from a project file to a harness-bound instruction. A
    portable component fits any harness whose provider declares a surface for
    its kind; where none does, the refusal names the surface, exactly as it does
    for a harness-bound object of that kind.
    """
    from ai_stp_cli.local.composition import native_surface

    assert native_surface("instruction", TARGET.harness_id)
    portable = eligibility.assess(
        _candidate(harness_id="", component_type="instruction", owned_or_pinned=True), TARGET
    )
    assert "harness_mismatch" not in _codes(portable)
    assert "provider_surface_unavailable" not in _codes(portable)
    assert portable.admissible

    assert not native_surface("mcp", TARGET.harness_id)
    surfaceless = eligibility.assess(
        _candidate(harness_id="", component_type="mcp", owned_or_pinned=True), TARGET
    )
    assert "provider_surface_unavailable" in _codes(surfaceless)
    assert "harness_mismatch" not in _codes(surfaceless)
    assert not surfaceless.admissible

    # A named harness other than the target is still a mismatch, unchanged.
    foreign = eligibility.assess(
        _candidate(harness_id="codex", component_type="instruction", owned_or_pinned=True), TARGET
    )
    assert "harness_mismatch" in _codes(foreign)
