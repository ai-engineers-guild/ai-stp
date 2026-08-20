"""The local and wire attestation models must not drift (`ADR-0092`)."""

from __future__ import annotations

from ai_stp_assurance.attestation import AuthorAttestation as LocalAttestation
from ai_stp_contracts.publication import AuthorAttestation as WireAttestation


def test_the_wire_attestation_carries_exactly_the_signed_record() -> None:
    """`#300` was the wire form being a lossy subset of what was signed.

    The fix makes the CLI send the record itself:
    `AuthorAttestation.model_validate(record.model_dump(mode="json"))`. That is
    correct only while the field sets match exactly, and both models forbid
    extras — so a drift is caught, but at run time, by whoever is publishing.

    Checked here instead, where a gate sees it. The two models live in separate
    packages on purpose: one is what a device signs locally, the other is what
    `/v1` accepts. Being equal is a property to prove, not an assumption.
    """
    assert set(LocalAttestation.model_fields) == set(WireAttestation.model_fields)


def test_neither_side_silently_accepts_unknown_fields() -> None:
    """`extra="forbid"` is what makes the round-trip fail loudly instead of leaking."""
    assert LocalAttestation.model_config.get("extra") == "forbid"
    assert WireAttestation.model_config.get("extra") == "forbid"
