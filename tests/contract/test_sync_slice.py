"""The sync slice must refuse rather than quietly report nothing (`#180`).

The origin, envelope and credential mechanics belong to `release_scripts._evidence`
and are tested there. What is specific to this slice is which scenarios it names
and what it does when it could not run them.
"""

import sys
from collections import deque
from pathlib import Path

import pytest
from release_scripts import verify_sync_slice
from release_scripts._evidence import cli, data


@pytest.mark.parametrize("fault", ["none", "fast_forward", "replay", "merge"])
def test_sync_verdict_checks_remote_effects_and_receipt_states(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    """An accepted envelope alone cannot prove delivery, replay or a merged push."""
    left, right = tmp_path / "a", tmp_path / "b"
    pulls = deque(
        [
            {"ok": True},
            {"ok": True, "applied": 1, "next_cursor": "settled"},
            {
                "ok": True,
                "applied": 0,
                "replayed": 1 if fault == "replay" else 0,
                "next_cursor": "settled",
            },
            {"ok": True, "applied": 1},
        ]
    )
    pushes = deque(
        [
            "accepted",
            "accepted",
            "accepted",
            "conflict",
            "conflict" if fault == "merge" else "accepted",
        ]
    )

    def command(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {"ok": True, "data": {"state": "up_to_date"}}

    def developer(*_args: object, **_kwargs: object) -> str:
        return "developer-probe"

    def pull(*_args: object, **_kwargs: object) -> dict[str, object]:
        return pulls.popleft()

    def push(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {"ok": True, "state": pushes.popleft()}

    def preview(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {"state": "merge_ready"}

    def head(home: Path, **_kwargs: object) -> str:
        return "other" if fault == "fast_forward" and home == right else "same"

    monkeypatch.setattr(verify_sync_slice, "cli", command)
    monkeypatch.setattr(verify_sync_slice, "_developer_id", developer)
    monkeypatch.setattr(verify_sync_slice, "_pull", pull)
    monkeypatch.setattr(verify_sync_slice, "_push", push)
    monkeypatch.setattr(verify_sync_slice, "_preview", preview)
    monkeypatch.setattr(verify_sync_slice, "_head", head)
    scenarios = verify_sync_slice._run_scenarios(left, right, python=sys.executable)  # pyright: ignore[reportPrivateUsage]
    assert {name for name, result in scenarios.items() if result["state"] == "failed"} == (
        set() if fault == "none" else {fault}
    )
    assert not pulls and not pushes


def test_collision_probe_can_release_two_distinct_local_versions(tmp_path: Path) -> None:
    """The authenticated scenario must reach immutable collision validation."""
    identifier = verify_sync_slice._seed_component(tmp_path, python=sys.executable)  # pyright: ignore[reportPrivateUsage]
    verify_sync_slice._declare(tmp_path, identifier, "a", python=sys.executable)  # pyright: ignore[reportPrivateUsage]
    first = verify_sync_slice._release(tmp_path, identifier, python=sys.executable)  # pyright: ignore[reportPrivateUsage]
    first_digest = verify_sync_slice._released_digest(  # pyright: ignore[reportPrivateUsage]
        tmp_path, identifier, first, python=sys.executable
    )
    verify_sync_slice._declare(tmp_path, identifier, "b", python=sys.executable)  # pyright: ignore[reportPrivateUsage]
    second = verify_sync_slice._release(tmp_path, identifier, python=sys.executable)  # pyright: ignore[reportPrivateUsage]
    assert first == "1.0"
    assert second == "1.1"
    assert first_digest != verify_sync_slice._released_digest(  # pyright: ignore[reportPrivateUsage]
        tmp_path, identifier, second, python=sys.executable
    )
    # A later invocation must retain the old probe and create an independent
    # object, even when adoption would otherwise match the same native path.
    repeated = verify_sync_slice._seed_component(tmp_path, python=sys.executable)  # pyright: ignore[reportPrivateUsage]
    assert repeated != identifier
    assert (
        verify_sync_slice._released_digest(  # pyright: ignore[reportPrivateUsage]
            tmp_path, identifier, first, python=sys.executable
        )
        == first_digest
    )
    assert verify_sync_slice._release(tmp_path, repeated, python=sys.executable) == "1.0"  # pyright: ignore[reportPrivateUsage]


def test_collision_probe_prepares_source_bytes_on_the_other_device(tmp_path: Path) -> None:
    source, peer = tmp_path / "a", tmp_path / "b"
    identifier = verify_sync_slice._seed_component(  # pyright: ignore[reportPrivateUsage]
        source, python=sys.executable, peer_home=peer
    )
    target = next((peer / "work" / ".claude" / "skills").iterdir())
    adopted = data(
        cli(
            ["component", "adopt", "--path", str(target), "--root", str(peer / "work")],
            home=peer,
            python=sys.executable,
        ),
        "component adopt",
    )
    assert adopted["stable_id"] != identifier
    assert (
        verify_sync_slice._release(  # pyright: ignore[reportPrivateUsage]
            peer, str(adopted["stable_id"]), python=sys.executable
        )
        == "1.0"
    )


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
