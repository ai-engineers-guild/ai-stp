"""The sync slice must refuse rather than quietly report nothing (`#180`).

The origin, envelope and credential mechanics belong to `release_scripts._evidence`
and are tested there. What is specific to this slice is which scenarios it names
and what it does when it could not run them.
"""

import sys
from pathlib import Path

from release_scripts import verify_sync_slice


def test_a_run_that_proved_nothing_does_not_exit_zero() -> None:
    """An unmet precondition is a refusal; the named collision gap is not."""
    unauthenticated = {
        "scenarios": {
            "fast_forward": {"state": "not_verified", "reason": "home a reports 'local_only'"},
            "version_collision": {"state": "not_verified", "reason": "named gap"},
        }
    }
    assert verify_sync_slice._refused(unauthenticated) is True  # pyright: ignore[reportPrivateUsage]

    proved = {
        "scenarios": {
            "fast_forward": {"state": "verified"},
            "replay": {"state": "verified"},
            "conflict": {"state": "verified"},
            "merge": {"state": "verified"},
            "version_collision": {"state": "not_verified", "reason": "named gap"},
        }
    }
    assert verify_sync_slice._refused(proved) is False  # pyright: ignore[reportPrivateUsage]

    broken = {"scenarios": {"merge": {"state": "failed"}}}
    assert verify_sync_slice._refused(broken) is True  # pyright: ignore[reportPrivateUsage]


def test_the_slice_names_all_five_scenarios_even_with_nothing_signed_in(
    tmp_path: Path,
) -> None:
    """The artefact must show the gap, not omit it.

    Two homes that have never signed in prove nothing, and that is the point: the
    report still names every scenario `#180` requires, each with the reason and
    the exact commands that would close it. This runs the published CLI, so it
    also covers the two preconditions the CLI states itself — cloud sync enabled
    and a catalogue URL — which a hand-written report would forget.
    """
    report = verify_sync_slice.verify_sync_slice(
        "https://nddev.asia",
        tmp_path / "a",
        tmp_path / "b",
        python=sys.executable,
    )

    assert set(report["scenarios"]) == {
        "fast_forward",
        "replay",
        "conflict",
        "merge",
        "version_collision",
    }
    assert report["auth_states"] == {"a": "local_only", "b": "local_only"}
    for name, held in report["scenarios"].items():
        assert held["state"] == "not_verified", name
        assert held["reason"], name
    assert verify_sync_slice._refused(report) is True  # pyright: ignore[reportPrivateUsage]
