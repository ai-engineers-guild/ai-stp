"""The publication plan state partition covers `PlanState` and nothing else."""

from typing import get_args

from ai_stp_contracts.publication import (
    PLAN_STATE_PUBLISHED,
    PLAN_STATES_IN_PROGRESS,
    PLAN_STATES_REFUSED,
    PlanState,
)

DECLARED: frozenset[str] = frozenset(get_args(PlanState.__value__))


def test_the_partition_covers_every_declared_plan_state() -> None:
    """A new `PlanState` must be classified, not silently ignored.

    Three call sites used to answer this question separately, and one of them
    checked for `rejected` and `expired` while missing `cancelled` and `stale`.
    Adding a state without placing it here now fails, rather than leaving a
    caller polling a plan that will never move.
    """
    partitioned = PLAN_STATES_IN_PROGRESS | PLAN_STATES_REFUSED | {PLAN_STATE_PUBLISHED}
    assert partitioned == DECLARED, sorted(partitioned ^ DECLARED)


def test_no_plan_state_is_both_pending_and_refused() -> None:
    """The parts decide different actions, so a state may only be in one."""
    assert not PLAN_STATES_IN_PROGRESS & PLAN_STATES_REFUSED
    assert PLAN_STATE_PUBLISHED not in PLAN_STATES_IN_PROGRESS
    assert PLAN_STATE_PUBLISHED not in PLAN_STATES_REFUSED


def test_the_partition_names_only_real_plan_states() -> None:
    """Guards against the dead branch this partition was written to remove."""
    assert not (PLAN_STATES_IN_PROGRESS | PLAN_STATES_REFUSED) - DECLARED
    assert "rejected" not in DECLARED
    assert "expired" not in DECLARED
