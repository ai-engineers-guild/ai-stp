"""Passport golden vector: canonical bytes, passport digest and revision ID
must reproduce exactly from the committed envelope value."""

import json
from pathlib import Path
from typing import cast

from ai_stp_foundation import canonize, digest_bytes
from ai_stp_foundation.canonical import JsonValue
from ai_stp_passports import PassportEnvelope, derive_revision_id, verify_revision_id

VECTOR = Path(__file__).parents[1] / "golden" / "passports" / "developer-envelope.json"


def test_passport_golden_vector_reproduces() -> None:
    vector = cast(dict[str, JsonValue], json.loads(VECTOR.read_text(encoding="utf-8")))
    value = cast(dict[str, JsonValue], vector["value"])
    canonical = canonize(value)
    assert canonical.decode("utf-8") == vector["canonical"]
    assert digest_bytes("ai-stp:passport:v1", canonical) == vector["passport_digest"]
    assert derive_revision_id(value) == vector["revision_id"]
    envelope = PassportEnvelope.model_validate(value)
    assert verify_revision_id(envelope)
