"""The installation machine: an approval that means something, and a failure matrix."""

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import installation, journal
from ai_stp_cli.local.database import configured_path, open_registry

AT = "2026-08-08T10:00:00.000Z"
SOON = "2026-08-08T11:00:00.000Z"
LATE = "2026-08-08T12:00:00.000Z"
HELD = "sha256:" + "a" * 64
MOVED = "sha256:" + "b" * 64


@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        yield connection


def _plan(connection: sqlite3.Connection, key: str, **overrides: object) -> installation.Plan:
    facts: dict[str, object] = {
        "action": "install",
        "author": "account_01J0000000000000000000000A",
        "target_id": "pair_project_claude-code",
        "expected_target_digest": HELD,
        "provider_version": "1.0.0",
        "effects": ("write .claude/skills/review.md",),
        "recovery_action": "restore the provider backup",
        "idempotency_key": key,
        "at": AT,
        "expires_at": SOON,
    }
    facts.update(overrides)
    return installation.propose(connection, **facts)  # pyright: ignore[reportArgumentType]


def _approved(connection: sqlite3.Connection, key: str) -> installation.Plan:
    plan = _plan(connection, key)
    installation.approve(connection, plan.operation_id, plan_digest=plan.digest, at=AT)
    return plan


def _applying(connection: sqlite3.Connection, key: str) -> installation.Plan:
    plan = _approved(connection, key)
    installation.begin(connection, plan.operation_id, observed_target_digest=HELD, at=AT)
    return plan


def _state(connection: sqlite3.Connection, operation_id: str) -> str:
    held = journal.get(connection, operation_id)
    assert held is not None
    return held.state


# The plan itself.
def test_a_plan_has_no_effect_of_its_own(registry: sqlite3.Connection) -> None:
    """`REQ-805`: planning is free, and its state says so."""
    plan = _plan(registry, "k1")
    assert _state(registry, plan.operation_id) == installation.STATE_PLANNED


def test_the_digest_covers_every_field_a_decision_turns_on(
    registry: sqlite3.Connection,
) -> None:
    first = _plan(registry, "k1")
    for changed in (
        {"action": "remove"},
        {"target_id": "somewhere-else"},
        {"expected_target_digest": MOVED},
        {"provider_version": "2.0.0"},
        {"provider_protocol_version": 2},
        {"provider_target": "/var/lib/ai-stp/provider-target"},
        {"provider_release_manifest": '{"provider_id":"codex"}'},
        {"provider_release_recovery": True},
        {"bundle_format": "ai-stp-bundle/1"},
        {"bundle_digest": HELD},
        {"bundle_artifact_digest": MOVED},
        {"bundle_size": 4096},
        {"provider_plan_digest": "sha256:" + "c" * 64},
        {"effects": ("write something else",)},
        {"recovery_action": "do nothing"},
        {"expires_at": LATE},
    ):
        other = _plan(registry, f"k-{sorted(changed)[0]}", **changed)
        assert other.digest != first.digest, changed


def test_a_migrated_v1_plan_keeps_its_original_digest(registry: sqlite3.Connection) -> None:
    """Adding the v2 binding must not invalidate an already-approved v1 plan."""
    current = _plan(registry, "old-plan")
    old = installation.Plan(
        operation_id=current.operation_id,
        action=current.action,
        author=current.author,
        target_id=current.target_id,
        expected_target_digest=current.expected_target_digest,
        provider_version=current.provider_version,
        effects=current.effects,
        confirmation=current.confirmation,
        recovery_action=current.recovery_action,
        expires_at=current.expires_at,
        created_at=current.created_at,
        setup_stable_id=current.setup_stable_id,
        setup_version=current.setup_version,
        schema_version=1,
    )
    registry.execute(
        """
        UPDATE operation_plan
        SET plan_digest = ?, provider_protocol_version = NULL,
            provider_target = NULL, plan_schema_version = NULL
        WHERE operation_id = ?
        """,
        (old.digest, old.operation_id),
    )

    decoded = installation._require(  # pyright: ignore[reportPrivateUsage]
        registry, old.operation_id
    )

    assert decoded.schema_version == 1
    assert decoded.provider_protocol_version == 1
    assert decoded.provider_target == ""
    assert decoded.digest == old.digest


def test_a_repeat_with_one_key_returns_the_plan_already_recorded(
    registry: sqlite3.Connection,
) -> None:
    first = _plan(registry, "k1")
    second = _plan(registry, "k1")
    assert second.operation_id == first.operation_id
    held = registry.execute("SELECT count(*) AS n FROM operation_plan").fetchone()
    assert held["n"] == 1


def test_a_terminal_plan_hands_its_retry_key_to_one_new_operation(
    registry: sqlite3.Connection,
) -> None:
    first = _plan(registry, "replan-key")
    installation.cancel(registry, first.operation_id, at=AT, reason="changed decision")

    second = _plan(registry, "replan-key")
    repeated = _plan(registry, "replan-key")

    assert second.operation_id != first.operation_id
    assert repeated.operation_id == second.operation_id
    rows = registry.execute(
        "SELECT operation_id, idempotency_key FROM operation_plan ORDER BY created_at, operation_id"
    ).fetchall()
    assert {str(row["operation_id"]) for row in rows} == {
        first.operation_id,
        second.operation_id,
    }
    keys = {str(row["idempotency_key"]) for row in rows}
    assert "replan-key" in keys
    assert f"retired:{first.operation_id}:replan-key" in keys


def test_a_partial_operation_can_only_recover_as_a_new_operation(
    registry: sqlite3.Connection,
) -> None:
    first = _approved(registry, "recovery-key")
    installation.begin(registry, first.operation_id, observed_target_digest=HELD, at=AT)
    installation.interrupted(registry, first.operation_id, at=AT, reason="provider timed out")

    replacement = _plan(registry, "recovery-key")

    assert replacement.operation_id != first.operation_id
    assert _state(registry, first.operation_id) == installation.STATE_PARTIAL
    assert _state(registry, replacement.operation_id) == installation.STATE_PLANNED


def test_concurrent_replans_share_one_replacement_operation(tmp_path: Path) -> None:
    place = tmp_path / "replan-race.sqlite3"
    with closing(open_registry(place, create=True)) as connection:
        first = _plan(connection, "raced-replan")
        installation.cancel(connection, first.operation_id, at=AT, reason="retry")

    replacements: list[str] = []
    failures: list[BaseException] = []

    def replan() -> None:
        try:
            with closing(open_registry(place, create=False)) as connection:
                replacements.append(_plan(connection, "raced-replan").operation_id)
        except BaseException as error:  # pragma: no cover - asserted below
            failures.append(error)

    workers = [threading.Thread(target=replan) for _ in range(8)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert failures == []
    assert len(set(replacements)) == 1
    assert replacements[0] != first.operation_id
    with closing(open_registry(place, create=False)) as connection:
        count = connection.execute("SELECT COUNT(*) AS n FROM operation_plan").fetchone()
        assert count["n"] == 2


@pytest.mark.parametrize("action", ["install", "update", "backup", "remove", "rollback"])
def test_every_declared_action_can_be_planned(registry: sqlite3.Connection, action: str) -> None:
    assert _plan(registry, f"k-{action}", action=action).action == action


def test_an_action_nobody_named_is_refused(registry: sqlite3.Connection) -> None:
    with pytest.raises(CliFailure) as raised:
        _plan(registry, "k1", action="reformat-the-disk")
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_a_plan_with_no_effects_is_refused(registry: sqlite3.Connection) -> None:
    """A plan enumerates its effects; one with none changes nothing."""
    with pytest.raises(CliFailure) as raised:
        _plan(registry, "k1", effects=())
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


# The approval is bound to the exact plan.
def test_approving_with_another_plans_digest_is_refused(
    registry: sqlite3.Connection,
) -> None:
    """`operation.md`: an approval is to an exact hash and does not carry over."""
    first = _plan(registry, "k1")
    other = _plan(registry, "k2", effects=("write something else",))
    with pytest.raises(CliFailure) as raised:
        installation.approve(registry, first.operation_id, plan_digest=other.digest, at=AT)
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    assert _state(registry, first.operation_id) == installation.STATE_PLANNED, (
        "a wrong approval leaves the plan approvable; it is the approval that was wrong"
    )


def test_approving_an_expired_plan_marks_it_stale_durably(
    registry: sqlite3.Connection,
) -> None:
    """The terminal state is recorded before the caller is answered.

    Marking inside the transaction and raising from inside it would roll the
    mark back and answer "stale" about an operation the registry still calls
    planned.
    """
    plan = _plan(registry, "k1")
    with pytest.raises(CliFailure) as raised:
        installation.approve(registry, plan.operation_id, plan_digest=plan.digest, at=LATE)
    assert raised.value.code == "AI_STP_PLAN_STALE"
    assert _state(registry, plan.operation_id) == installation.STATE_STALE


# Preconditions are re-checked on the inside of the lock.
def test_a_target_that_moved_makes_the_plan_stale_durably(
    registry: sqlite3.Connection,
) -> None:
    plan = _approved(registry, "k1")
    with pytest.raises(CliFailure) as raised:
        installation.begin(registry, plan.operation_id, observed_target_digest=MOVED, at=AT)
    assert raised.value.code == "AI_STP_PLAN_STALE"
    assert _state(registry, plan.operation_id) == installation.STATE_STALE


def test_a_plan_that_expired_before_applying_is_stale(registry: sqlite3.Connection) -> None:
    plan = _approved(registry, "k1")
    with pytest.raises(CliFailure) as raised:
        installation.begin(registry, plan.operation_id, observed_target_digest=HELD, at=LATE)
    assert raised.value.code == "AI_STP_PLAN_STALE"
    assert _state(registry, plan.operation_id) == installation.STATE_STALE


def test_an_unapproved_plan_cannot_be_applied(registry: sqlite3.Connection) -> None:
    plan = _plan(registry, "k1")
    with pytest.raises(CliFailure) as raised:
        installation.begin(registry, plan.operation_id, observed_target_digest=HELD, at=AT)
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    assert _state(registry, plan.operation_id) == installation.STATE_PLANNED


# An external effect must pass through the state that describes its window.
def test_an_installation_cannot_reach_verified_without_applied_unverified(
    registry: sqlite3.Connection,
) -> None:
    """The journal allows the shortcut; an installation must not take it."""
    plan = _applying(registry, "k1")
    with pytest.raises(CliFailure) as raised:
        installation._move(  # pyright: ignore[reportPrivateUsage]
            registry, plan.operation_id, installation.STATE_VERIFIED, "shortcut", AT
        )
    assert raised.value.code == "AI_STP_CONFLICT"
    assert _state(registry, plan.operation_id) == installation.STATE_APPLYING


def test_the_whole_successful_path_is_recorded_step_by_step(
    registry: sqlite3.Connection,
) -> None:
    plan = _applying(registry, "k1")
    installation.applied(registry, plan.operation_id, at=AT, backup_ref="backup_1")
    assert (
        installation.verify(registry, plan.operation_id, postconditions_met=True, at=AT)
        == installation.STATE_VERIFIED
    )

    moves = [
        (item.state_before, item.state_after)
        for item in installation.events(registry, plan.operation_id)
    ]
    assert moves == [
        ("planned", "planned"),
        ("planned", "approved"),
        ("approved", "applying"),
        ("applying", "applied_unverified"),
        ("applied_unverified", "verified"),
    ]


def test_the_event_stream_is_numbered_and_ordered(registry: sqlite3.Connection) -> None:
    plan = _applying(registry, "k1")
    installation.applied(registry, plan.operation_id, at=AT)
    numbers = [item.sequence for item in installation.events(registry, plan.operation_id)]
    assert numbers == sorted(numbers)
    assert numbers == list(range(1, len(numbers) + 1))


def test_verified_is_the_only_name_for_success(registry: sqlite3.Connection) -> None:
    """A failed postcondition gives `partial`, not `failed`: the effect happened."""
    plan = _applying(registry, "k1")
    installation.applied(registry, plan.operation_id, at=AT)
    assert (
        installation.verify(registry, plan.operation_id, postconditions_met=False, at=AT)
        == installation.STATE_PARTIAL
    )


def test_verifying_something_that_was_never_applied_is_refused(
    registry: sqlite3.Connection,
) -> None:
    plan = _approved(registry, "k1")
    with pytest.raises(CliFailure) as raised:
        installation.verify(registry, plan.operation_id, postconditions_met=True, at=AT)
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


# The failure matrix.
def test_an_interrupted_apply_is_partial_and_never_failed(
    registry: sqlite3.Connection,
) -> None:
    """An expired external call does not prove the absence of an effect."""
    plan = _applying(registry, "k1")
    installation.applied(registry, plan.operation_id, at=AT)
    installation.interrupted(registry, plan.operation_id, at=AT, reason="the provider timed out")
    assert _state(registry, plan.operation_id) == installation.STATE_PARTIAL


def test_an_operation_whose_effect_happened_cannot_be_called_a_plain_failure(
    registry: sqlite3.Connection,
) -> None:
    plan = _applying(registry, "k1")
    installation.applied(registry, plan.operation_id, at=AT)
    with pytest.raises(CliFailure) as raised:
        installation.fail(registry, plan.operation_id, at=AT, reason="give up")
    assert raised.value.code == "AI_STP_CONFLICT"


def test_a_failure_before_any_effect_is_a_plain_failure(registry: sqlite3.Connection) -> None:
    plan = _applying(registry, "k1")
    installation.fail(registry, plan.operation_id, at=AT, reason="the provider refused the bundle")
    assert _state(registry, plan.operation_id) == installation.STATE_FAILED


def test_cancelling_after_applying_begins_is_refused(registry: sqlite3.Connection) -> None:
    """Cancelling claims nothing was done; past `applying` nobody can claim it."""
    plan = _applying(registry, "k1")
    with pytest.raises(CliFailure) as raised:
        installation.cancel(registry, plan.operation_id, at=AT, reason="changed my mind")
    assert raised.value.code == "AI_STP_CONFLICT"


def test_cancelling_before_any_effect_is_allowed(registry: sqlite3.Connection) -> None:
    plan = _approved(registry, "k1")
    installation.cancel(registry, plan.operation_id, at=AT, reason="changed my mind")
    assert _state(registry, plan.operation_id) == installation.STATE_CANCELLED


def test_an_undone_effect_is_rolled_back(registry: sqlite3.Connection) -> None:
    plan = _applying(registry, "k1")
    installation.applied(registry, plan.operation_id, at=AT, backup_ref="backup_1")
    installation.roll_back(registry, plan.operation_id, at=AT, reason="restored from the backup")
    assert _state(registry, plan.operation_id) == installation.STATE_ROLLED_BACK


# Resume and recovery.
def test_a_recovery_report_carries_all_four_things_it_owes(
    registry: sqlite3.Connection,
) -> None:
    plan = _applying(registry, "k1")
    installation.applied(registry, plan.operation_id, at=AT, backup_ref="backup_1")
    installation.interrupted(registry, plan.operation_id, at=AT, reason="the provider timed out")

    report = installation.recovery(registry, plan.operation_id)
    assert report.state == installation.STATE_PARTIAL
    assert report.backup_ref == "backup_1"
    assert report.effects_recorded, "the effects already carried out"
    assert report.next_actions, "and what may be done next"


def test_a_partial_operation_is_not_retried_and_needs_a_new_plan(
    registry: sqlite3.Connection,
) -> None:
    plan = _applying(registry, "k1")
    installation.applied(registry, plan.operation_id, at=AT)
    installation.interrupted(registry, plan.operation_id, at=AT, reason="unknown")
    report = installation.recovery(registry, plan.operation_id)
    assert "plan a recovery operation" in report.next_actions
    assert journal.TRANSITIONS[installation.STATE_PARTIAL] == frozenset()


def test_a_stopped_operation_is_resumable_and_a_finished_one_is_not(
    registry: sqlite3.Connection,
) -> None:
    stopped = _applying(registry, "k1")
    installation.applied(registry, stopped.operation_id, at=AT)

    finished = _applying(registry, "k2")
    installation.applied(registry, finished.operation_id, at=AT)
    installation.verify(registry, finished.operation_id, postconditions_met=True, at=AT)

    resumable = {item.operation_id for item in installation.resumable(registry)}
    assert stopped.operation_id in resumable
    assert finished.operation_id not in resumable


def test_a_partial_operation_keeps_showing_up(registry: sqlite3.Connection) -> None:
    """Terminal, but it is the outcome that still needs a person."""
    plan = _applying(registry, "k1")
    installation.applied(registry, plan.operation_id, at=AT)
    installation.interrupted(registry, plan.operation_id, at=AT, reason="unknown")
    assert plan.operation_id in {item.operation_id for item in installation.resumable(registry)}


def test_a_recovery_report_for_an_unknown_operation_is_not_found(
    registry: sqlite3.Connection,
) -> None:
    with pytest.raises(CliFailure) as raised:
        installation.recovery(registry, "operation_01J0000000000000000000000Z")
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_approving_an_operation_with_no_plan_is_not_found(
    registry: sqlite3.Connection,
) -> None:
    with pytest.raises(CliFailure) as raised:
        installation.approve(
            registry,
            "operation_01J0000000000000000000000Z",
            plan_digest="sha256:" + "0" * 64,
            at=AT,
        )
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_the_plan_is_stored_exactly_as_it_was_made(registry: sqlite3.Connection) -> None:
    """Immutable means the digest still matches after a round trip."""
    plan = _plan(registry, "k1")
    reloaded = installation._require(registry, plan.operation_id)  # pyright: ignore[reportPrivateUsage]
    assert reloaded == plan
    assert reloaded.digest == plan.digest


def test_a_plan_always_asks_for_the_digest_form_of_confirmation() -> None:
    """An explicit flag says yes to whatever is in front of it.

    A plan is exactly the thing that can have changed since the user looked, so
    a decision about one is a decision about its digest.
    """
    assert installation.CONFIRMATION_PLAN_DIGEST == "plan_digest"
