"""The kit must not promise providers more than the conformance run checks.

`provider-kit/v3/conformance-cases.json` is what a provider vendors and builds
against — five public setup-systems carry it byte for byte — so a refusal it
declares is a refusal somebody implements. When the run exercised ten of the
nineteen, an implementation could be wrong in six distinct reasons and still be
told it conformed.

This file is deliberately public. The guard first lived in
`tests/unit/test_provider_kit.py`, which the export manifest withholds for
naming a private repository, so it never ran in the gate that decides a
deployment — a guard that guards nothing, which is the shape of defect it was
written to prevent.
"""

from __future__ import annotations

import json
from pathlib import Path

from release_scripts import provider_kit

from ai_stp_cli.provider import bundle_corpus, conformance_v3, protocol_v3

#: Refusals the kit declares that the conformance run cannot drive today, each
#: with the reason. Emptying this map is the goal; growing it silently is the
#: failure it exists to prevent.
UNEXERCISED_REFUSALS: dict[str, str] = {
    # These three describe a disagreement between what the caller expects and
    # what the provider is. v3 argv still carries no platform, architecture or
    # projection profile from the caller. Permission profile is on the wire and
    # is driven; these three are not.
    "projection_profile_mismatch": "the caller states no expected profile in v3 argv",
    "unsupported_platform": "the caller states no expected platform in v3 argv",
    "unsupported_architecture": "the caller states no expected architecture in v3 argv",
}


def _declared() -> set[str]:
    cases = json.loads(provider_kit.render()["conformance-cases.json"])
    return {case["expected_reason"] for case in cases["bundle_rejections"]} | {
        case["expected_reason"] for case in cases["capability_rejections"]
    }


def _exercised() -> set[str]:
    # `unknown_native_surface` is the v2 case name; the corpus maps it to the v3
    # reason, which is what a provider actually answers.
    corpus = {
        "unsupported_native_surface" if refusal == "unknown_native_surface" else refusal
        for _name, refusal in bundle_corpus.CASE_REASONS_V3
    }
    # Two sources, because there are two surfaces: the corpus drives bundle
    # refusals through `validate-bundle`, and the run drives capability refusals
    # through `plan-operation`.
    return corpus | set(conformance_v3.DRIVEN_CAPABILITY_REJECTIONS)


def test_every_refusal_the_kit_declares_is_exercised_or_named() -> None:
    unchecked = sorted(_declared() - _exercised() - UNEXERCISED_REFUSALS.keys())
    assert not unchecked, (
        f"the kit declares {unchecked} and nothing exercises them. Add a corpus case, "
        f"or name the refusal in UNEXERCISED_REFUSALS with the reason it cannot be driven."
    )


def test_every_named_exemption_is_still_a_refusal_the_kit_declares() -> None:
    """An exemption for a refusal that no longer exists hides a stale decision."""
    stale = sorted(UNEXERCISED_REFUSALS.keys() - _declared())
    assert not stale, f"exemptions name refusals the kit no longer declares: {stale}"


def test_every_command_the_run_will_not_invoke_is_declared_forbidden() -> None:
    """The kit named two forbidden commands while three are not pure.

    `pure_commands` is derived from `READ_COMMANDS`, but
    `forbidden_in_safe_conformance` was a hand-written
    `["apply-operation", "launch"]`. That leaves `recover-operation` in neither
    list, and it is a mutating command — `APPLY_COMMANDS` holds it next to
    `apply-operation`.

    A provider author reads this file and nothing else. Two lists that do not
    partition the command set tell them a mutating command *might* be invoked
    during safe conformance, so they must either make it safe to call or be
    surprised. The run never invokes it: `conformance_v3.py` does not mention
    `recover-operation` anywhere. The behaviour was right and the promise was
    narrower than the behaviour.

    Asserted as a partition rather than as a literal, because the literal is
    exactly what drifted. A command added to the protocol now lands on one side
    or fails here.
    """
    kit = json.loads(provider_kit.render()["conformance-cases.json"])
    pure = set(kit["pure_commands"])
    forbidden = set(kit["forbidden_in_safe_conformance"])

    assert pure | forbidden == set(protocol_v3.COMMANDS), (
        "every v3 command is either pure or forbidden in safe conformance"
    )
    assert not pure & forbidden, "a command cannot be both pure and forbidden"
    assert forbidden >= protocol_v3.APPLY_COMMANDS, (
        "a mutating command the run will not invoke must say so"
    )


#: Kit versions whose bytes are pinned by somebody else. The ledger beside this
#: file is the record; this is the code that makes it mean something.
_LEDGER = Path(__file__).resolve().parents[1] / "golden" / "provider-kit" / "identity-ledger.json"


def _ledger() -> dict[str, str]:
    document = json.loads(_LEDGER.read_text(encoding="utf-8"))
    return {item["kit_version"]: item["aggregate_digest"] for item in document["released"]}


def test_a_released_kit_version_never_changes_its_bytes() -> None:
    """A version whose contents moved is a republished immutable `X.Y`.

    Providers vendor the kit and pin its aggregate digest — the provider side
    pins `0.2.3` at `sha256:2bf26243…` in work that is already merged. Editing
    a released version's files while leaving `KIT_VERSION` alone gives that pin
    two possible failures, and the quieter one is worse: it keeps matching a
    name that now means something else.

    **The ledger existed and nothing read it.** It was written as a record of
    released versions and no code compared anything against it, so it drifted
    at the first release nobody added — `0.2.3` was pinned by a provider and
    never entered the file. A record with no guard is the same shape as a guard
    with no path: it reads as protection and protects nothing.

    Found by nearly committing the defect: adding `user_root` to the scope set
    changed `0.2.3`'s aggregate in place, and nothing said so.
    """
    released = _ledger()
    current = provider_kit.KIT_VERSION
    identity = json.loads(
        (
            Path(provider_kit.__file__).resolve().parents[1]
            / "provider-kit"
            / "v3"
            / "KIT-IDENTITY.json"
        ).read_text(encoding="utf-8")
    )
    assert identity["kit_version"] == current

    if current in released:
        assert identity["aggregate_digest"] == released[current], (
            f"kit {current} is released and its bytes moved; bump KIT_VERSION instead"
        )


def test_the_ledger_names_each_version_and_each_digest_once() -> None:
    """Two names for one digest means a version that did not change.

    And one name with two digests is the defect above, recorded rather than
    caught. Either way the ledger stops being a record of distinct releases.
    """
    document = json.loads(_LEDGER.read_text(encoding="utf-8"))
    versions = [item["kit_version"] for item in document["released"]]
    digests = [item["aggregate_digest"] for item in document["released"]]

    assert len(versions) == len(set(versions)), sorted(versions)
    assert len(digests) == len(set(digests)), "two kit versions share an aggregate digest"
