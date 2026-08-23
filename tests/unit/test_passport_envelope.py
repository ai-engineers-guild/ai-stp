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


def test_sealing_a_document_that_omits_a_defaulted_field_still_verifies() -> None:
    """`seal_envelope` hashed its input; `verify_revision_id` hashes the model.

    Those are the same document only when the caller spells out every field
    that has a default. `_base` above does, which is why every test here
    passed while the defect was live: `visibility` defaults to `private`, and
    a caller that leaves it out gets an id derived over a document without it,
    then a validated envelope that has it. The two never agree again.

    Found on production. `passport developer update` omits `visibility`, so
    every developer passport written by an update carried an id that fails its
    own verification — invisible locally, because nothing verifies a revision
    it just wrote, and fatal on `sync pull`, which does exactly that and
    refused the payload as not matching its event coordinates. Two devices
    could push and conflict, and neither could ever pull.
    """
    data = _base("developer")
    del data["visibility"]
    sealed = seal_envelope(data)
    assert sealed.visibility == "private", "the default is still applied"
    assert verify_revision_id(sealed), "a sealed envelope must verify against itself"


def test_an_omitted_default_seals_to_the_same_id_as_the_spelled_one() -> None:
    """Otherwise the same passport has two ids depending on how it was written."""
    spelled = _base("developer")
    omitted = {key: value for key, value in spelled.items() if key != "visibility"}
    assert seal_envelope(omitted).revision_id == seal_envelope(spelled).revision_id
