"""Canonical JSON properties: determinism, parse-idempotence, NFC, rejections."""

import json
import math
from typing import cast

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ai_stp_foundation import CanonicalizationError, canonize
from ai_stp_foundation.canonical import JsonValue

_ascii_keys = st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126), max_size=12)
# Numbers stay inside the I-JSON safe domain (|n| < 2**53): a float with an
# integral value above it serializes as an integral token, reparses as an int
# outside the RFC 8785 integer domain and is rightly rejected there.
_scalars = (
    st.none()
    | st.booleans()
    | st.integers(min_value=-(2**53) + 1, max_value=2**53 - 1)
    | st.floats(
        allow_nan=False,
        allow_infinity=False,
        width=64,
        min_value=float(-(2**53) + 1),
        max_value=float(2**53 - 1),
    )
    | st.text(
        alphabet=st.characters(blacklist_characters="\ufeff", blacklist_categories=("Cs",)),
        max_size=24,
    )
)
_values = st.recursive(
    _scalars,
    lambda children: (
        st.lists(children, max_size=4) | st.dictionaries(_ascii_keys, children, max_size=4)
    ),
    max_leaves=20,
)


@given(_values)
def test_canonization_is_deterministic(value: JsonValue) -> None:
    assert canonize(value) == canonize(value)


@given(_values)
def test_canonization_is_idempotent_through_parsing(value: JsonValue) -> None:
    first = canonize(value)
    reparsed = cast(JsonValue, json.loads(first.decode("utf-8")))
    assert canonize(reparsed) == first


def test_nfc_makes_composed_and_decomposed_equal() -> None:
    assert canonize({"k": "é"}) == canonize({"k": "é"})
    assert canonize({"é": 1}) == canonize({"é": 1})


def test_object_keys_are_sorted() -> None:
    assert canonize({"b": 1, "a": 2, "A": 3}) == b'{"A":3,"a":2,"b":1}'


def test_bom_inside_strings_is_rejected() -> None:
    with pytest.raises(CanonicalizationError):
        canonize({"k": "\ufeffvalue"})


def test_non_finite_numbers_are_rejected() -> None:
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(CanonicalizationError):
            canonize({"k": bad})


def test_key_collision_after_nfc_is_rejected() -> None:
    with pytest.raises(CanonicalizationError):
        canonize({"é": 1, "é": 2})


def test_non_string_keys_are_rejected() -> None:
    with pytest.raises(CanonicalizationError):
        canonize(cast(JsonValue, {1: "x"}))


@pytest.mark.parametrize(
    "bad",
    [(1, 2), b"bytes", {1, 2}, object(), {"nested": (1, 2)}, [["deep", {"k": b"x"}]]],
    ids=["tuple", "bytes", "set", "object", "nested-tuple", "deep-bytes"],
)
def test_unsupported_runtime_types_raise_typed_errors(bad: object) -> None:
    with pytest.raises(CanonicalizationError):
        canonize(cast(JsonValue, bad))
