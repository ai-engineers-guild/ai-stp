"""The publication slice must separate reading from changing (`#182`).

The mechanics it shares with the other slices are tested in
`test_evidence_helpers.py`. What is specific here is the split that makes the
script safe to point at production: reading what an account owns changes
nothing, while publishing a version is immutable and changing somebody's access
is not the script's decision to take.
"""

import json
import sys
from collections import deque
from hashlib import sha256
from pathlib import Path

import pytest
from release_scripts import verify_publication_slice

from ai_stp_foundation.ids import new_id


def _no_wait(_seconds: float) -> None:
    pass


@pytest.mark.parametrize("uncertain_confirm", [False, True])
def test_publication_probe_retains_its_exact_plan_before_confirmation_and_reuses_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, uncertain_confirm: bool
) -> None:
    subject = {"stable_id": new_id("component"), "version": "1.0"}
    marker = tmp_path / "publishable-subject.json"
    marker.write_text(json.dumps(subject))
    plan_id = new_id("plan")
    plan_hash = "sha256:" + sha256(b"planned publication").hexdigest()
    states = deque(["ready", "validating", "publish_planned", "published"])
    calls: list[tuple[str, str]] = []

    def answered(arguments: list[str], **_kwargs: object) -> dict[str, object]:
        action = (arguments[0], arguments[1])
        calls.append(action)
        if action == ("publication", "plan"):
            return {
                "ok": True,
                "data": {"plan_id": plan_id, "plan_hash": plan_hash, "state": "ready"},
            }
        if action == ("publication", "confirm"):
            held = json.loads(marker.read_text())
            assert held["plan_id"] == plan_id and held["plan_hash"] == plan_hash
            if uncertain_confirm:
                return {"ok": False, "error": {"code": "AI_STP_TIMEOUT_UNCONFIRMED"}}
            return {"ok": True, "data": {"state": "validating"}}
        assert action == ("publication", "status"), action
        return {
            "ok": True,
            "data": {"state": states.popleft() if states else "published", "plan_hash": plan_hash},
        }

    monkeypatch.setattr(verify_publication_slice, "cli", answered)
    monkeypatch.setattr(verify_publication_slice.time, "sleep", _no_wait)
    first = verify_publication_slice._driven_writes(tmp_path, "", python=sys.executable)  # pyright: ignore[reportPrivateUsage]
    assert first["publication"]["state"] == ("not_verified" if uncertain_confirm else "verified")
    states.clear()
    repeated = verify_publication_slice._driven_writes(tmp_path, "", python=sys.executable)  # pyright: ignore[reportPrivateUsage]
    assert repeated["publication"]["state"] == "verified"
    assert calls.count(("publication", "plan")) == 1
    assert calls.count(("publication", "confirm")) == 1
    assert repeated["grants"]["state"] == "not_verified"


def test_publication_probe_waits_for_the_existing_publish_job_without_replanning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "publishable-subject.json"
    marker.write_text(
        json.dumps(
            {
                "stable_id": new_id("component"),
                "version": "1.0",
                "plan_id": new_id("plan"),
                "plan_hash": "sha256:" + sha256(b"existing plan").hexdigest(),
            }
        )
    )
    states = deque(["publish_planned", "published"])

    def answered(arguments: list[str], **_kwargs: object) -> dict[str, object]:
        assert arguments[:2] == ["publication", "status"], arguments
        return {"ok": True, "data": {"state": states.popleft()}}

    monkeypatch.setattr(verify_publication_slice, "cli", answered)
    monkeypatch.setattr(verify_publication_slice.time, "sleep", _no_wait)
    result = verify_publication_slice._driven_writes(tmp_path, "", python=sys.executable)  # pyright: ignore[reportPrivateUsage]
    assert result["publication"]["state"] == "verified"
    assert not states


@pytest.mark.parametrize("terminal", ["failed", "cancelled", "stale"])
def test_publication_probe_can_start_a_new_attempt_after_a_terminal_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, terminal: str
) -> None:
    old_id, new_plan = new_id("plan"), new_id("plan")
    digest = "sha256:" + sha256(b"new attempt").hexdigest()
    marker = tmp_path / "publishable-subject.json"
    marker.write_text(
        json.dumps({"stable_id": new_id("component"), "version": "1.0", "plan_id": old_id})
    )
    new_states = deque(["ready", "published"])
    plans: list[str] = []

    def answered(arguments: list[str], **_kwargs: object) -> dict[str, object]:
        if arguments[:2] == ["publication", "plan"]:
            plans.append(new_plan)
            return {"ok": True, "data": {"plan_id": new_plan, "plan_hash": digest}}
        if arguments[:2] == ["publication", "confirm"]:
            assert arguments[3] == new_plan
            assert json.loads(marker.read_text())["plan_hash"] == digest
            return {"ok": True, "data": {"state": "validating"}}
        assert arguments[:2] == ["publication", "status"]
        state = terminal if arguments[3] == old_id else new_states.popleft()
        return {"ok": True, "data": {"state": state, "plan_hash": digest}}

    monkeypatch.setattr(verify_publication_slice, "cli", answered)
    result = verify_publication_slice._driven_writes(tmp_path, "", python=sys.executable)  # pyright: ignore[reportPrivateUsage]
    assert result["publication"]["state"] == "verified"
    assert plans == [new_plan]


@pytest.mark.parametrize("failure", ["changed_hash", "rate_limit"])
def test_publication_probe_preserves_binding_when_status_cannot_authorize_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    marker = tmp_path / "publishable-subject.json"
    marker.write_text(
        json.dumps(
            {
                "stable_id": new_id("component"),
                "version": "1.0",
                "plan_id": new_id("plan"),
                "plan_hash": "sha256:" + sha256(b"original plan").hexdigest(),
            }
        )
    )
    before = marker.read_bytes()
    calls: list[list[str]] = []

    def answered(arguments: list[str], **_kwargs: object) -> dict[str, object]:
        calls.append(arguments)
        assert arguments[:2] == ["publication", "status"]
        if failure == "rate_limit":
            return {"ok": False, "error": {"code": "AI_STP_RATE_LIMITED"}}
        return {
            "ok": True,
            "data": {
                "state": "ready",
                "plan_hash": "sha256:" + sha256(b"changed plan").hexdigest(),
            },
        }

    monkeypatch.setattr(verify_publication_slice, "cli", answered)
    result = verify_publication_slice._driven_writes(tmp_path, "", python=sys.executable)  # pyright: ignore[reportPrivateUsage]
    assert result["publication"]["state"] == (
        "failed" if failure == "changed_hash" else "not_verified"
    )
    assert len(calls) == 1 and marker.read_bytes() == before


def test_undriven_writes_do_not_fail_read_only_evidence() -> None:
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


@pytest.mark.parametrize("writes_allowed", [False, True])
def test_requested_publication_needs_a_conclusive_result(writes_allowed: bool) -> None:
    report = {
        "writes_allowed": writes_allowed,
        "scenarios": {
            "owner_objects": {"state": "verified"},
            "publication": {"state": "not_verified", "reason": "confirmation unconfirmed"},
            "grants": {"state": "not_verified", "reason": "no recipient requested"},
        },
    }
    assert verify_publication_slice.refused(report) is writes_allowed


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

    # The kind rides with the id because that is what it takes to address the
    # object: `owner object show` demands `--kind`, and `owner objects` returns
    # both kinds, so a bare id is not an address. It is still identity and not
    # content, which is what this test is about. A row that does not state its
    # kind is defaulted rather than dropped — dropping it would empty this list,
    # and an empty list reads downstream as "the account owns nothing".
    assert result == {
        "state": "verified",
        "command": "owner objects",
        "rows": 2,
        "identities": ["component:component_01", "component:component_02"],
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
