"""Recoverable consumer-owned multi-root transaction state (SPEC-058)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import installation, journal, multi_root
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_cli.local.multi_root_orchestrator import Coordinator

AT = "2026-09-03T00:00:00.000Z"
LATER = "2026-09-03T00:01:00.000Z"
EXPIRES = "2099-01-01T00:00:00.000Z"


@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        yield connection


def _child(registry: sqlite3.Connection, suffix: str, scope: multi_root.Scope) -> multi_root.Child:
    operation_id = f"operation_01J0000000000000000000000{suffix}"
    plan = installation.propose(
        registry,
        action="install",
        author="account_test",
        target_id=f"target_{scope}",
        expected_target_digest="sha256:" + suffix.lower() * 64,
        provider_version="1.0.0",
        effects=(f"write {scope}",),
        recovery_action="restore exact backup",
        idempotency_key=f"child-{suffix}",
        at=AT,
        expires_at=EXPIRES,
        provider_protocol_version=3,
        bundle_format="ai-stp-bundle/2",
        bundle_digest="sha256:" + "a" * 64,
        bundle_artifact_digest="sha256:" + "b" * 64,
        bundle_size=1,
        provider_plan_digest="sha256:" + "c" * 64,
        setup_stable_id="setup_01J0000000000000000000000A",
        setup_version="1.0",
        operation_id=operation_id,
    )
    return multi_root.Child(scope, operation_id, f"target_{scope}", plan.digest)


def test_plan_orders_children_and_replays_exact_input(registry: sqlite3.Connection) -> None:
    project = _child(registry, "C", "project")
    global_child = _child(registry, "A", "global")
    user = _child(registry, "B", "user_root")
    planned = multi_root.propose(
        registry,
        setup_stable_id="setup_01J0000000000000000000000A",
        setup_version="1.0",
        harness_id="codex",
        children=(project, global_child, user),
        idempotency_key="same",
        at=AT,
    )
    replay = multi_root.propose(
        registry,
        setup_stable_id=planned.setup_stable_id,
        setup_version=planned.setup_version,
        harness_id=planned.harness_id,
        children=(user, project, global_child),
        idempotency_key="same",
        at=LATER,
    )
    assert replay.transaction_id == planned.transaction_id
    assert [child.scope for child in planned.children] == ["global", "user_root", "project"]
    assert replay.digest == planned.digest


def test_one_approval_atomically_approves_every_child(registry: sqlite3.Connection) -> None:
    children = (_child(registry, "A", "global"), _child(registry, "C", "project"))
    planned = multi_root.propose(
        registry,
        setup_stable_id="setup_01J0000000000000000000000A",
        setup_version="1.0",
        harness_id="claude-code",
        children=children,
        idempotency_key="approve",
        at=AT,
    )
    approved = multi_root.approve(
        registry, planned.transaction_id, expected_digest=planned.digest, at=LATER
    )
    assert approved.approved_digest == planned.digest
    assert {
        journal.get(registry, child.operation_id).state  # type: ignore[union-attr]
        for child in children
    } == {installation.STATE_APPROVED}


def test_invalid_child_rolls_back_every_approval(registry: sqlite3.Connection) -> None:
    children = (_child(registry, "A", "global"), _child(registry, "C", "project"))
    planned = multi_root.propose(
        registry,
        setup_stable_id="setup_01J0000000000000000000000A",
        setup_version="1.0",
        harness_id="claude-code",
        children=children,
        idempotency_key="atomic",
        at=AT,
    )
    installation.cancel(registry, children[-1].operation_id, at=LATER, reason="test")
    with pytest.raises(CliFailure, match="cannot move"):
        multi_root.approve(
            registry, planned.transaction_id, expected_digest=planned.digest, at=LATER
        )
    assert journal.get(registry, children[0].operation_id).state == installation.STATE_PLANNED  # type: ignore[union-attr]


def test_active_targets_are_locked_until_a_proven_terminal_state(
    registry: sqlite3.Connection,
) -> None:
    children = (_child(registry, "A", "global"), _child(registry, "C", "project"))
    planned = multi_root.propose(
        registry,
        setup_stable_id="setup_01J0000000000000000000000A",
        setup_version="1.0",
        harness_id="claude-code",
        children=children,
        idempotency_key="first",
        at=AT,
    )
    replacements = (
        _child(registry, "D", "global"),
        multi_root.Child(
            "project",
            _child(registry, "E", "user_root").operation_id,
            "target_project",
            installation.plan(registry, "operation_01J0000000000000000000000E").digest,
        ),
    )
    with pytest.raises(CliFailure, match="already belongs"):
        multi_root.propose(
            registry,
            setup_stable_id=planned.setup_stable_id,
            setup_version=planned.setup_version,
            harness_id=planned.harness_id,
            children=replacements,
            idempotency_key="second",
            at=LATER,
        )
    multi_root.move(
        registry,
        planned.transaction_id,
        expected=frozenset({"planned"}),
        state="rolled_back",
        result="nothing changed",
        at=LATER,
    )
    assert not multi_root.child_is_owned(registry, children[0].operation_id)


def test_coordinator_never_claims_success_before_every_child_is_verified(
    registry: sqlite3.Connection,
) -> None:
    children = (_child(registry, "A", "global"), _child(registry, "C", "project"))
    coordinator = Coordinator(registry)
    planned = coordinator.plan(
        setup_stable_id="setup_01J0000000000000000000000A",
        setup_version="1.0",
        harness_id="claude-code",
        children=children,
        idempotency_key="aggregate",
        at=AT,
    )
    coordinator.approve(planned.transaction_id, expected_digest=planned.digest, at=LATER)
    coordinator.begin(planned.transaction_id, at=LATER)
    with pytest.raises(CliFailure, match="every child"):
        coordinator.finish_verified(planned.transaction_id, at=LATER)

    for child in children:
        installation.begin(
            registry,
            child.operation_id,
            observed_target_digest=installation.plan(
                registry, child.operation_id
            ).expected_target_digest,
            at=LATER,
        )
        installation.applied(
            registry, child.operation_id, at=LATER, backup_ref=f"slot-{child.scope}"
        )
        installation.verify(
            registry,
            child.operation_id,
            postconditions_met=True,
            at=LATER,
        )
        coordinator.observe_child(planned.transaction_id, child.operation_id, at=LATER)
    finished = coordinator.finish_verified(planned.transaction_id, at=LATER)
    assert finished.state == "verified"
    assert not coordinator.owns(children[0].operation_id)


def test_coordinator_keeps_unsettled_compensation_recoverable(
    registry: sqlite3.Connection,
) -> None:
    children = (_child(registry, "A", "global"), _child(registry, "C", "project"))
    coordinator = Coordinator(registry)
    planned = coordinator.plan(
        setup_stable_id="setup_01J0000000000000000000000A",
        setup_version="1.0",
        harness_id="claude-code",
        children=children,
        idempotency_key="recovery",
        at=AT,
    )
    coordinator.approve(planned.transaction_id, expected_digest=planned.digest, at=LATER)
    coordinator.begin(planned.transaction_id, at=LATER)
    installation.begin(
        registry,
        children[0].operation_id,
        observed_target_digest=installation.plan(
            registry, children[0].operation_id
        ).expected_target_digest,
        at=LATER,
    )
    installation.interrupted(
        registry, children[0].operation_id, at=LATER, reason="lost provider answer"
    )
    coordinator.observe_child(planned.transaction_id, children[0].operation_id, at=LATER)
    coordinator.begin_compensation(planned.transaction_id, at=LATER)
    with pytest.raises(CliFailure, match="possible effect"):
        coordinator.finish_rolled_back(planned.transaction_id, at=LATER)
    recovering = coordinator.require_recovery(
        planned.transaction_id, at=LATER, reason="the first root remains partial"
    )
    assert recovering.state == "recovery_required"
    assert coordinator.owns(children[0].operation_id)
