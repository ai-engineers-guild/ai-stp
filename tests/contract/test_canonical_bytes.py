"""Byte-level REQ-1504 rejections: every file in the invalid corpus must fail
the full ``canonize(from_json_bytes(data))`` pipeline with a typed error."""

from pathlib import Path

import pytest

from ai_stp_foundation import CanonicalizationError, canonize, from_json_bytes

INVALID_DIR = Path(__file__).parents[1] / "golden" / "canonical-invalid"
INVALID_PATHS = sorted(INVALID_DIR.glob("*"))

# Every fixture name maps to a fragment expected in the typed error message,
# so a rejection for the wrong reason fails the test instead of hiding.
EXPECTED_REASONS: dict[str, str] = {
    "bom-prefix.json": "byte-order mark prefix",
    "duplicate-keys.json": "duplicate object key",
    "infinity-literal.json": "non-finite JSON literal",
    "integer-overflow.json": "exceeds safe integer domain",
    "interior-bom.json": "byte-order mark inside a string",
    "invalid-utf8.bin": "not valid UTF-8",
    "nan-literal.json": "non-finite JSON literal",
    "nfc-key-collision.json": "collide after NFC",
    "truncated.json": "not valid JSON",
}


def test_invalid_corpus_is_present_and_fully_mapped() -> None:
    names = {path.name for path in INVALID_PATHS}
    assert names == set(EXPECTED_REASONS)
    assert len(names) >= 9


@pytest.mark.parametrize("path", INVALID_PATHS, ids=lambda path: path.stem)
def test_invalid_bytes_fail_closed_with_the_right_reason(path: Path) -> None:
    with pytest.raises(CanonicalizationError) as failure:
        canonize(from_json_bytes(path.read_bytes()))
    assert EXPECTED_REASONS[path.name] in str(failure.value)


def test_valid_bytes_round_trip_through_the_pipeline() -> None:
    payload = '{"b": 1, "a": "é"}'.encode()
    assert canonize(from_json_bytes(payload)) == canonize({"a": "é", "b": 1})
