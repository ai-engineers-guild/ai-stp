"""Two-integer versions: canonical form, numeric comparison, rejections."""

import pytest

from ai_stp_foundation import VersionError, compare_versions, format_version, parse_version


def test_parse_and_format_round_trip() -> None:
    assert parse_version("0.0") == (0, 0)
    assert parse_version("2.10") == (2, 10)
    assert format_version(2, 10) == "2.10"


def test_comparison_is_numeric_not_lexicographic() -> None:
    assert compare_versions("2.10", "2.9") == 1
    assert compare_versions("2.9", "10.0") == -1
    assert compare_versions("1.0", "1.0") == 0


@pytest.mark.parametrize("bad", ["1", "1.2.3", "01.2", "1.02", "-1.0", "1.-2", "a.b", "1. 2", ""])
def test_non_canonical_forms_are_rejected(bad: str) -> None:
    with pytest.raises(VersionError):
        parse_version(bad)


def test_negative_parts_cannot_be_formatted() -> None:
    with pytest.raises(VersionError):
        format_version(-1, 0)
