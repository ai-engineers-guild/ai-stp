"""What an attestation signature actually covers (`SPEC-015` REQ-1507).

`ai_stp_assurance` fixed the shape and deferred key handling to the CLI device
identity, which arrived in `#73`. The loop was never closed: the digest had a
golden vector, but nothing signed one and nothing proved the signature covers
the data and excludes its own envelope.

REQ-1507's oracle asks for mutation checks over both. That is the difference
between "the signature is 64 bytes in the right place" and "the signature means
this record was not altered".
"""

import base64
import json
from typing import cast

import pytest
from nacl.signing import VerifyKey

from ai_stp_assurance import AuthorAttestation, attestation_digest
from ai_stp_assurance.attestation import attestation_payload
from ai_stp_cli import identity
from ai_stp_foundation.canonical import JsonValue

GOLDEN = "tests/golden/passports/author-attestation.json"


def _record() -> AuthorAttestation:
    from pathlib import Path

    vector = cast(
        dict[str, JsonValue],
        json.loads(Path(GOLDEN).read_text(encoding="utf-8")),
    )
    return AuthorAttestation.model_validate(vector["value"])


def _sign(record: AuthorAttestation) -> tuple[bytes, VerifyKey]:
    """Sign the record's digest with a real device key."""
    current, _warning = identity.load_or_create()
    signed = attestation_digest(record).encode("utf-8")
    return current.sign(signed), current.public_key


def test_a_signature_over_the_digest_verifies() -> None:
    record = _record()
    signature, public_key = _sign(record)
    assert identity.verify(public_key, attestation_digest(record).encode("utf-8"), signature)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("result", "failed"),
        ("check_id", "another-check"),
        ("policy_version", "9.9"),
        ("harness_version", "0.0.1"),
    ],
)
def test_mutating_the_data_breaks_the_signature(field: str, value: str) -> None:
    # The mutation half of REQ-1507: a signature that survived an edit to the
    # result would attest to nothing.
    record = _record()
    altered = record.model_copy(update={field: value})
    assert attestation_digest(altered) != attestation_digest(record)

    signature, public_key = _sign(record)
    assert not identity.verify(public_key, attestation_digest(altered).encode("utf-8"), signature)


def test_the_signature_envelope_is_not_part_of_what_is_signed() -> None:
    # The other half: the signature must not cover itself, or no signature could
    # ever be produced.
    record = _record()
    assert "signature" not in cast(dict[str, JsonValue], attestation_payload(record))

    different = record.model_copy(update={"signature": base64.b64encode(b"x" * 64).decode()})
    assert attestation_digest(different) == attestation_digest(record)


def test_the_digest_is_domain_separated() -> None:
    # A bare hash of the canonical payload would collide with a passport digest
    # over the same bytes, and one domain's signature would verify in another.
    import hashlib

    from ai_stp_foundation.canonical import canonize

    record = _record()
    bare = hashlib.sha256(canonize(attestation_payload(record))).hexdigest()
    assert attestation_digest(record) != bare
    assert attestation_digest(record).startswith("sha256:")


def test_another_device_key_does_not_verify() -> None:
    record = _record()
    signature, _public_key = _sign(record)
    other, _warning = identity.reset()
    assert not identity.verify(
        other.public_key, attestation_digest(record).encode("utf-8"), signature
    )
