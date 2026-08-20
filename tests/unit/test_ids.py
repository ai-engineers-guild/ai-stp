"""Typed stable IDs: closed prefix registry, ULID suffix, fail-closed parsing."""

import pytest

from ai_stp_foundation import ID_PREFIXES, StableIdError, is_valid_id, new_id, parse_id


def test_new_id_round_trips_for_every_registered_prefix() -> None:
    for prefix in ID_PREFIXES:
        value = new_id(prefix)
        parsed_prefix, suffix = parse_id(value)
        assert parsed_prefix == prefix
        assert len(suffix) == 26
        assert is_valid_id(value, prefix)


def test_unknown_prefix_is_rejected_on_mint_and_parse() -> None:
    with pytest.raises(StableIdError):
        new_id("marketplace")
    with pytest.raises(StableIdError):
        parse_id("marketplace_01ARZ3NDEKTSV4RRFFQ69G5FAV")


def test_malformed_suffixes_are_rejected() -> None:
    for bad in (
        "component",
        "component_",
        "component_short",
        "component_01arz3ndektsv4rrffq69g5fav",
        "component_01ARZ3NDEKTSV4RRFFQ69G5FAU",
        "component_01ARZ3NDEKTSV4RRFFQ69G5FAVX",
    ):
        assert not is_valid_id(bad)


def test_ulid_range_boundary_is_enforced() -> None:
    assert is_valid_id("component_7" + "Z" * 25)
    assert not is_valid_id("component_8" + "0" * 25)
    assert not is_valid_id("component_Z" + "0" * 25)


def test_prefix_registry_is_immutable() -> None:
    with pytest.raises(TypeError):
        ID_PREFIXES["hacked"] = "mutated"  # type: ignore[index]


def test_pattern_builder_matches_parser() -> None:
    import re

    from ai_stp_foundation.ids import stable_id_pattern

    pattern = re.compile(stable_id_pattern("component"))
    assert pattern.fullmatch(new_id("component"))
    assert pattern.fullmatch("component_8" + "0" * 25) is None
    with pytest.raises(StableIdError):
        stable_id_pattern("marketplace")


def test_prefix_filter_distinguishes_kinds() -> None:
    value = new_id("setup")
    assert is_valid_id(value, "setup")
    assert not is_valid_id(value, "component")
