"""Revision IDs: content-addressed, deterministic, no random mint path."""

import pytest

from ai_stp_foundation import StableIdError, is_valid_id, new_id
from ai_stp_foundation.revisions import is_valid_revision_id, revision_id


def test_equal_content_gives_equal_id_regardless_of_key_order() -> None:
    left = revision_id({"a": 1, "b": {"x": "é"}})
    right = revision_id({"b": {"x": "é"}, "a": 1})
    assert left == right
    assert is_valid_revision_id(left)


def test_single_field_mutation_changes_the_id() -> None:
    base = revision_id({"a": 1, "b": 2})
    assert revision_id({"a": 1, "b": 3}) != base
    assert revision_id({"a": 1}) != base


def test_wire_form_is_prefixed_lowercase_hex() -> None:
    value = revision_id({"k": "v"})
    prefix, _, suffix = value.partition("_")
    assert prefix == "revision"
    assert len(suffix) == 64
    assert set(suffix) <= set("0123456789abcdef")


def test_random_mint_path_is_gone() -> None:
    with pytest.raises(StableIdError):
        new_id("revision")


def test_revision_id_is_not_a_stable_id_and_vice_versa() -> None:
    derived = revision_id({"k": "v"})
    assert not is_valid_id(derived)
    assert not is_valid_revision_id(new_id("component"))
    assert not is_valid_revision_id("revision_" + "G" * 64)
