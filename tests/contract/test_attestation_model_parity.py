"""The local and wire attestation models must not drift (`ADR-0092`)."""

from __future__ import annotations

import json
from pathlib import Path

from ai_stp_assurance import attestation_digest
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
    vector = json.loads(Path("tests/golden/passports/author-attestation.json").read_text())
    local = LocalAttestation.model_validate(
        {
            **vector["value"],
            "adaptation_id": "adaptation_" + "a" * 64,
            "projection_digest": "sha256:" + "b" * 64,
            "scope": "project",
            "provider_profile_digest": "sha256:" + "c" * 64,
            "os": "linux",
            "arch": "x86_64",
        }
    )
    wire = WireAttestation.model_validate(local.model_dump(mode="json"))
    returned = LocalAttestation.model_validate(wire.model_dump(mode="json"))
    assert returned == local
    assert attestation_digest(returned) == attestation_digest(local)


def test_neither_side_silently_accepts_unknown_fields() -> None:
    """`extra="forbid"` is what makes the round-trip fail loudly instead of leaking."""
    assert LocalAttestation.model_config.get("extra") == "forbid"
    assert WireAttestation.model_config.get("extra") == "forbid"
