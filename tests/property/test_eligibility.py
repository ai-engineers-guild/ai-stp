"""Eligibility properties: what is refused is never chosen, whatever the facts.

`SPEC-006` asks for REQ-601 to be proven by a property check rather than by
examples, and the reason is the shape of the guarantee: the example tests fix
one constraint at a time, and the thing that must hold is that *no* combination
of facts produces a candidate that was refused and is selectable anyway.
"""

from hypothesis import given
from hypothesis import strategies as st

from ai_stp_cli.local import eligibility, search

_names = st.sampled_from(["claude-code", "codex", "pi", "opencode", "grok-build", "undefined", ""])
_systems = st.sampled_from(["linux", "darwin", "windows"])
_machines = st.sampled_from(["x86_64", "aarch64", "arm64"])
_versions = st.sampled_from(["", "1.0", "2.1.224 (Claude Code)", "codex-cli 0.146.0", "unknown"])
_ranges = st.tuples(
    st.sampled_from(["", "1.0", "2.0.0", "9.9"]), st.sampled_from(["", "1.5", "3.0", "99.0"])
)
_capabilities = st.lists(
    st.sampled_from(
        [
            "project.language.python",
            "project.language.rust",
            "toolchain.ruff",
            "tool.pytest",
            "not a capability",
            "one",
        ]
    ),
    max_size=4,
).map(tuple)
_permissions = st.lists(
    st.sampled_from(["file:read", "file:write", "network:outbound"]), max_size=3
)

_targets = st.builds(
    eligibility.Target,
    harness_id=_names,
    os=_systems,
    arch=_machines,
    harness_version=_versions,
    capabilities=_capabilities.map(lambda held: frozenset(held) & eligibility.CAPABILITIES),
    entitlements=_permissions.map(frozenset),
    env_present=st.just(frozenset[str]()),
    owner_id=st.sampled_from(["account_me", ""]),
    grants=st.just(frozenset[str]()),
    provider_harnesses=st.sets(_names, max_size=3).map(frozenset),
    provider_platforms=st.sets(st.just("linux/x86_64"), max_size=1).map(frozenset),
    for_redistribution=st.booleans(),
)

_candidates = st.builds(
    eligibility.CandidateFacts,
    stable_id=st.sampled_from(["component_a", "component_b"]),
    revision_id=st.just("revision_a"),
    version=st.sampled_from(["1.0", "2.3", ""]),
    harness_id=_names,
    adaptation_harnesses=st.sets(_names, max_size=3).map(frozenset),
    owner_id=st.sampled_from(["account_me", "account_other"]),
    visibility=st.sampled_from(["private", "public"]),
    supported_os=st.sets(_systems, max_size=2).map(frozenset),
    supported_arch=st.sets(_machines, max_size=2).map(frozenset),
    harness_versions=_ranges,
    requires_capabilities=_capabilities,
    required_env=st.lists(st.sampled_from(["A", "B"]), max_size=2).map(tuple),
    requires_credentials=st.booleans(),
    requires_authorization=st.sampled_from(["none", "user_account", "external_service"]),
    license_id=st.sampled_from(["", "MIT", "Apache-2.0"]),
    redistribution=st.booleans(),
    entitlements=_permissions.map(tuple),
    registrable=st.booleans(),
    blocked=st.booleans(),
    author_verified=st.booleans(),
    component_verified=st.booleans(),
    checks_current=st.booleans(),
    owned_or_pinned=st.booleans(),
    consented=st.booleans(),
)


# REQ-601: the mechanical stage runs before selection, so a refused candidate
# has no path to being chosen. This is the property the whole ordering exists
# to provide.
@given(_candidates, _targets)
def test_a_refused_candidate_is_never_selectable(
    candidate: eligibility.CandidateFacts, target: eligibility.Target
) -> None:
    verdict = eligibility.assess(candidate, target)
    assert verdict.admissible is (verdict.refusals == ())
    if not verdict.admissible:
        assert not verdict.auto_selectable
        assert eligibility.selectable((verdict,)) == ()
        assert eligibility.admissible((verdict,)) == ()


# REQ-603: consent widens what may be shown, never what may be installed on its
# own. No combination of facts turns an experimental candidate into one.
@given(_candidates, _targets)
def test_experimental_is_never_automatically_selectable(
    candidate: eligibility.CandidateFacts, target: eligibility.Target
) -> None:
    verdict = eligibility.assess(candidate, target)
    if verdict.lane == search.LANE_EXPERIMENTAL:
        assert not verdict.auto_selectable


@given(_candidates, _targets)
def test_every_refusal_carries_a_declared_code_and_its_own_family(
    candidate: eligibility.CandidateFacts, target: eligibility.Target
) -> None:
    for refusal in eligibility.assess(candidate, target).refusals:
        assert eligibility.REFUSALS[refusal.code] == refusal.family
        assert refusal.summary
        assert refusal.details


@given(_candidates, _targets)
def test_a_note_is_never_counted_as_a_refusal(
    candidate: eligibility.CandidateFacts, target: eligibility.Target
) -> None:
    """`SPEC-001` REQ-111 and `SPEC-008` REQ-816: an advisory does not block."""
    verdict = eligibility.assess(candidate, target)
    codes = {item.code for item in verdict.notes}
    assert codes <= eligibility.NOTES
    assert codes.isdisjoint({item.code for item in verdict.refusals})


# REQ-607: one canonical input, one answer.
@given(_candidates, _targets)
def test_assessing_twice_gives_the_same_answer(
    candidate: eligibility.CandidateFacts, target: eligibility.Target
) -> None:
    assert eligibility.assess(candidate, target) == eligibility.assess(candidate, target)
