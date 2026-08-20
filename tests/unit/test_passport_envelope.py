"""Passport envelope: five kinds, content-addressed sealing, preservation."""

from typing import cast

import pytest
from pydantic import ValidationError

from ai_stp_foundation import new_id
from ai_stp_foundation.canonical import JsonValue
from ai_stp_passports import (
    IMMUTABLE_KINDS,
    MUTABLE_KINDS,
    PASSPORT_KINDS,
    PassportEnvelope,
    derive_revision_id,
    seal_envelope,
    verify_revision_id,
)

CREATED = "2026-08-05T10:00:00.000Z"


def _base(kind: str) -> dict[str, JsonValue]:
    return {
        "schema_version": 1,
        "kind": kind,
        "stable_id": new_id(kind),
        "parent_revision_ids": [],
        "owner_id": new_id("account"),
        "created_at": CREATED,
        "visibility": "private",
        "facts": {},
    }


def test_every_kind_seals_and_verifies() -> None:
    assert MUTABLE_KINDS | IMMUTABLE_KINDS == PASSPORT_KINDS
    for kind in sorted(PASSPORT_KINDS):
        sealed = seal_envelope(_base(kind))
        assert sealed.kind == kind
        assert verify_revision_id(sealed)


def test_sealing_is_content_addressed() -> None:
    data = _base("developer")
    left = derive_revision_id(data)
    reordered = dict(reversed(list(data.items())))
    assert derive_revision_id(reordered) == left
    changed = dict(data)
    changed["visibility"] = "public"
    assert derive_revision_id(changed) != left


def test_kind_and_stable_id_prefix_must_agree() -> None:
    data = _base("developer")
    data["stable_id"] = new_id("device")
    with pytest.raises(ValidationError):
        seal_envelope(data)


def test_unknown_kind_fails_closed() -> None:
    data = _base("developer")
    data["kind"] = "marketplace"
    with pytest.raises(ValidationError):
        seal_envelope(data)


def test_component_envelope_can_carry_local_draft_parent_revision() -> None:
    data = _base("component")
    parent_revision_id = derive_revision_id(_base("component"))
    data["parent_revision_ids"] = [parent_revision_id]

    sealed = seal_envelope(data)

    assert sealed.parent_revision_ids == [parent_revision_id]


def test_unknown_optional_fields_are_preserved_and_hashed() -> None:
    data = _base("project")
    data["future_optional"] = {"nested": [1, 2]}
    sealed = seal_envelope(data)
    dumped = cast(dict[str, JsonValue], sealed.model_dump(mode="json"))
    assert dumped["future_optional"] == {"nested": [1, 2]}
    assert verify_revision_id(sealed)
    without = dict(data)
    del without["future_optional"]
    assert derive_revision_id(without) != sealed.revision_id


def test_tampered_revision_id_fails_verification() -> None:
    sealed = seal_envelope(_base("device"))
    tampered = PassportEnvelope.model_validate(
        {**sealed.model_dump(mode="json"), "revision_id": derive_revision_id(_base("device"))}
    )
    assert not verify_revision_id(tampered)
