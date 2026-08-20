"""The mechanics every evidence slice shares, tested where they are owned.

Three slices prove different things and all four of these behaviours are the
same in each: a bare origin, an envelope, a typed refusal code, and a report that
cannot carry a credential. The last one is why this file exists at its own level
rather than once per slice — a guard copied three times is a guard that stops
matching in one of them, and the artefact it protects is meant to be pasted into
an issue.
"""

import pytest
from release_scripts import _evidence


@pytest.mark.parametrize(
    "refused",
    [
        "http://nddev.asia",
        "https://nddev.asia/v1",
        "https://nddev.asia?query=1",
        "https://nddev.asia#fragment",
        "nddev.asia",
        "",
    ],
)
def test_only_a_bare_https_origin_is_accepted(refused: str) -> None:
    with pytest.raises(_evidence.EvidenceError):
        _evidence.origin(refused)


def test_a_trailing_slash_is_not_a_different_environment() -> None:
    assert _evidence.origin("https://nddev.asia/") == "https://nddev.asia"
    assert _evidence.origin("https://nddev.asia") == "https://nddev.asia"


def test_a_report_that_gained_a_credential_is_refused() -> None:
    clean: dict[str, object] = {"scenarios": {"fast_forward": {"state": "verified"}}}
    assert _evidence.without_credentials(clean) is clean

    for leak in ("Bearer abc", "refresh_token", "ACCESS_TOKEN", "Authorization"):
        with pytest.raises(_evidence.EvidenceError):
            _evidence.without_credentials({"note": leak})


def test_a_refusal_is_read_by_its_typed_code_rather_than_its_message() -> None:
    assert _evidence.error_code({"ok": False, "error": {"code": "AI_STP_CONFLICT"}}) == (
        "AI_STP_CONFLICT"
    )
    assert _evidence.error_code({"ok": True, "data": {}}) == ""
    assert _evidence.error_code({"ok": False, "error": {"message": "no code"}}) == ""


def test_an_envelope_without_data_is_not_evidence() -> None:
    assert _evidence.data({"data": {"state": "up_to_date"}}, "sync preview") == {
        "state": "up_to_date"
    }
    with pytest.raises(_evidence.EvidenceError):
        _evidence.data({"ok": True}, "sync preview")
