"""The publication slice must separate reading from changing (`#182`).

The mechanics it shares with the other slices are tested in
`test_evidence_helpers.py`. What is specific here is the split that makes the
script safe to point at production: reading what an account owns changes
nothing, while publishing a version is immutable and changing somebody's access
is not the script's decision to take.
"""

import json
import sys
from pathlib import Path

import pytest
from release_scripts import verify_publication_slice


def test_a_write_scenario_never_decides_the_exit_code() -> None:
    """They are `not_verified` by design, so a red code every run teaches nothing."""
    read_only = {
        "scenarios": {
            "owner_objects": {"state": "verified"},
            "grant_list": {"state": "verified"},
            "report_list": {"state": "verified"},
            "owner_object_show": {"state": "verified"},
            "attestation": {"state": "verified"},
            "report_preview": {"state": "verified"},
            "publication": {"state": "not_verified", "reason": "immutable"},
            "grants": {"state": "not_verified", "reason": "another person's access"},
            "report_confirm": {"state": "not_verified", "reason": "moderation record"},
        }
    }
    assert verify_publication_slice.refused(read_only) is False

    unread = {
        "scenarios": {
            "owner_objects": {"state": "not_verified", "reason": "not signed in"},
            "publication": {"state": "not_verified", "reason": "immutable"},
        }
    }
    assert verify_publication_slice.refused(unread) is True

    broken = {"scenarios": {"grant_list": {"state": "failed", "error_code": "AI_STP_FORBIDDEN"}}}
    assert verify_publication_slice.refused(broken) is True


def test_nothing_is_written_without_an_explicit_decision(tmp_path: Path) -> None:
    """Default is read-only, and the write scenarios say what they would change."""
    report = verify_publication_slice.verify_publication_slice(
        "https://nddev.asia",
        tmp_path / "home",
        python=sys.executable,
    )

    assert report["writes_allowed"] is False
    assert report["auth_state"] == "local_only"
    for name, _reason in verify_publication_slice.WRITES:
        held = report["scenarios"][name]
        assert held["state"] == "not_verified", name
        assert "--allow-writes" in held["reason"], name
    for name, _arguments in verify_publication_slice.READS:
        assert report["scenarios"][name]["state"] == "not_verified", name
    assert verify_publication_slice.refused(report) is True


def test_a_read_reports_identities_and_counts_rather_than_content(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`#182` forbids carrying source code out of the allowed set.

    The guard for that is not a filter over the output — it is what the report is
    built from. A row is reduced to its identity and the rows to a count before
    anything is printed, so content the server returned cannot reach the
    artefact even when it is there.
    """

    def answered(*_arguments: object, **_options: object) -> dict[str, object]:
        return {
            "ok": True,
            "data": {
                "items": [
                    {"stable_id": "component_01", "body": "the exact source bytes"},
                    {"stable_id": "component_02", "body": "more source"},
                ]
            },
        }

    monkeypatch.setattr(verify_publication_slice, "cli", answered)

    result = verify_publication_slice._read(  # pyright: ignore[reportPrivateUsage]
        "owner_objects", ("owner", "objects"), tmp_path, python=sys.executable
    )

    assert result == {
        "state": "verified",
        "command": "owner objects",
        "rows": 2,
        "identities": ["component_01", "component_02"],
    }
    assert "source" not in json.dumps(result)


def test_a_local_write_that_failed_does_decide_the_exit_code() -> None:
    """`attestation sign` and `report preview` change nothing outside the machine.

    They are driven rather than gated, so unlike the three that mutate the
    deployed catalogue they are not `not_verified` by design — and a failure in
    one is a failure of the run. Treating them as write scenarios would hide a
    broken local signature behind a green exit code, which is the whole reason
    they moved out of the gated set.
    """
    signed_badly = {
        "scenarios": {
            "owner_objects": {"state": "verified"},
            "grant_list": {"state": "verified"},
            "report_list": {"state": "verified"},
            "owner_object_show": {"state": "verified"},
            "attestation": {"state": "failed", "error_code": "AI_STP_VALIDATION_ERROR"},
            "report_preview": {"state": "verified"},
            "publication": {"state": "not_verified", "reason": "immutable"},
            "grants": {"state": "not_verified", "reason": "another person's access"},
            "report_confirm": {"state": "not_verified", "reason": "moderation record"},
        }
    }
    assert verify_publication_slice.refused(signed_badly) is True
