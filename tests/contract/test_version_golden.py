"""Version-passport and attestation golden vectors reproduce byte for byte."""

import json
from pathlib import Path
from typing import cast

import pytest

from ai_stp_assurance import AuthorAttestation, attestation_digest
from ai_stp_foundation import canonize, digest_bytes
from ai_stp_foundation.canonical import JsonValue
from ai_stp_passports import (
    ComponentVersionPassport,
    SetupVersionPassport,
    derive_revision_id,
)

GOLDEN = Path(__file__).parents[1] / "golden" / "passports"


@pytest.mark.parametrize(
    ("stem", "model"),
    [("component-version", ComponentVersionPassport), ("setup-version", SetupVersionPassport)],
)
def test_version_passport_vectors(stem: str, model: type[object]) -> None:
    vector = cast(
        dict[str, JsonValue], json.loads((GOLDEN / f"{stem}.json").read_text(encoding="utf-8"))
    )
    value = cast(dict[str, JsonValue], vector["value"])
    canonical = canonize(value)
    assert canonical.decode("utf-8") == vector["canonical"]
    assert digest_bytes("ai-stp:passport:v1", canonical) == vector["passport_digest"]
    assert derive_revision_id(value) == vector["revision_id"]
    assert cast(type[ComponentVersionPassport], model).model_validate(value)


def test_attestation_vector() -> None:
    vector = cast(
        dict[str, JsonValue],
        json.loads((GOLDEN / "author-attestation.json").read_text(encoding="utf-8")),
    )
    record = AuthorAttestation.model_validate(vector["value"])
    assert attestation_digest(record) == vector["attestation_digest"]
