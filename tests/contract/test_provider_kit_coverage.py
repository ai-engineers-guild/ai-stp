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

from release_scripts import provider_kit

from ai_stp_cli.provider import bundle_corpus, conformance_v3

#: Refusals the kit declares that the conformance run cannot drive today, each
#: with the reason. Emptying this map is the goal; growing it silently is the
#: failure it exists to prevent.
UNEXERCISED_REFUSALS: dict[str, str] = {
    # These three describe a disagreement between what the caller expects and
    # what the provider is, and v3 argv carries no platform, architecture or
    # projection profile from the caller: `plan-operation` takes the operation,
    # the release digest, an operation id, an expiry and the bundle binding, and
    # nothing else. There is nothing for the provider to disagree with, so the
    # pure surface cannot provoke them at all — a stronger statement than "no
    # surface yet", and one that makes driving them a protocol question rather
    # than a missing driver.
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
