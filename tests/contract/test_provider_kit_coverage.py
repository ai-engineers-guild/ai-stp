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

from ai_stp_cli.provider import bundle_corpus

#: Refusals the kit declares that the conformance run cannot drive today, each
#: with the reason. Emptying this map is the goal; growing it silently is the
#: failure it exists to prevent.
UNEXERCISED_REFUSALS: dict[str, str] = {
    "unsupported_component_kind": (
        "the kind lives in the setup passport, a separate archive member, so a "
        "hostile case has to rewrite that document and its digest in `documents` "
        "rather than a manifest field -- and the passport builder refuses to "
        "produce an invalid kind, so the case has to be patched after compilation"
    ),
    "unsupported_operation": (
        "a capability refusal, not a bundle one: it needs a surface that offers "
        "the provider an operation it never declared. `_rejections` only drives "
        "`validate-bundle`, so there is nowhere to put it yet"
    ),
    "projection_profile_mismatch": "capability refusal; no negotiation surface in the run",
    "unsupported_platform": "capability refusal; no negotiation surface in the run",
    "unsupported_architecture": "capability refusal; no negotiation surface in the run",
}


def _declared() -> set[str]:
    cases = json.loads(provider_kit.render()["conformance-cases.json"])
    return {case["expected_reason"] for case in cases["bundle_rejections"]} | {
        case["expected_reason"] for case in cases["capability_rejections"]
    }


def _exercised() -> set[str]:
    # `unknown_native_surface` is the v2 case name; the corpus maps it to the v3
    # reason, which is what a provider actually answers.
    return {
        "unsupported_native_surface" if refusal == "unknown_native_surface" else refusal
        for _name, refusal in bundle_corpus.CASE_REASONS_V3
    }


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
