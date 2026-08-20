"""Head transition rules without I/O (REQ-2505, REQ-2507): no LWW, FF only."""

from __future__ import annotations

import pytest

from ai_stp_api.slices.sync.validation import (
    SyncValidationError,
    can_accept_head_transition,
    validate_parents,
)

pytestmark = pytest.mark.platform


def test_initial_only_when_no_head_no_parents() -> None:
    assert can_accept_head_transition(current_head=None, expected_head=None, parent_revision_ids=[])
    assert not can_accept_head_transition(
        current_head=None, expected_head="revision_a", parent_revision_ids=[]
    )
    assert not can_accept_head_transition(
        current_head=None, expected_head=None, parent_revision_ids=["revision_a"]
    )


def test_fast_forward_requires_expected_head_as_parent() -> None:
    head = "revision_" + ("a" * 64)
    child_parent = "revision_" + ("b" * 64)
    assert can_accept_head_transition(
        current_head=head, expected_head=head, parent_revision_ids=[head]
    )
    assert can_accept_head_transition(
        current_head=head, expected_head=head, parent_revision_ids=[head, child_parent]
    )
    assert not can_accept_head_transition(
        current_head=head, expected_head=child_parent, parent_revision_ids=[child_parent]
    )
    assert not can_accept_head_transition(
        current_head=head, expected_head=head, parent_revision_ids=[child_parent]
    )


def test_divergent_history_is_never_auto_accepted() -> None:
    head = "revision_" + ("a" * 64)
    other = "revision_" + ("b" * 64)
    # LWW would accept the newer of head/other; the gate must refuse both.
    assert not can_accept_head_transition(
        current_head=head, expected_head=other, parent_revision_ids=[other]
    )
    assert not can_accept_head_transition(
        current_head=head, expected_head=None, parent_revision_ids=[other]
    )


def test_parent_list_rejects_duplicates_and_too_many() -> None:
    rid = "revision_" + ("c" * 64)
    with pytest.raises(SyncValidationError):
        validate_parents([rid, rid], operation="upsert")
    with pytest.raises(SyncValidationError):
        validate_parents([rid, rid.replace("c", "d"), rid.replace("c", "e")], operation="upsert")
