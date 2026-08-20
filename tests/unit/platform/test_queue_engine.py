"""Unit tests for the pure queue-engine logic (SPEC-018)."""

from __future__ import annotations

import pytest

from ai_stp_platform.queue.engine import BACKOFF_CAP_SECONDS, backoff_seconds
from ai_stp_platform.queue.states import CLAIMABLE_STATES, TERMINAL_STATES, JobState

pytestmark = pytest.mark.platform


def test_backoff_is_monotonic_until_cap() -> None:
    values = [backoff_seconds(attempt) for attempt in range(1, 6)]
    assert values == sorted(values)


def test_backoff_is_capped() -> None:
    assert backoff_seconds(1000) == BACKOFF_CAP_SECONDS


def test_claimable_and_terminal_states_are_disjoint() -> None:
    assert set(CLAIMABLE_STATES).isdisjoint(TERMINAL_STATES)
    assert JobState.SUCCEEDED in TERMINAL_STATES
    assert JobState.QUEUED in CLAIMABLE_STATES
