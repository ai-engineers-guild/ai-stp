"""Recoverable consumer-owned multi-root transaction state (SPEC-058)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import cast

import pytest

from ai_stp_cli.answer import Answer
from ai_stp_cli.commands import install as install_command
from ai_stp_cli.commands import install_transaction
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import installation, journal, multi_root
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_cli.local.multi_root_orchestrator import Coordinator
from ai_stp_contracts.machine_help import InstallationView

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
        target_id="project_test:claude-code",
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


def test_cancel_releases_targets_and_can_be_replanned(
    registry: sqlite3.Connection,
) -> None:
    children = (_child(registry, "A", "global"), _child(registry, "C", "project"))
    planned = multi_root.propose(
        registry,
        setup_stable_id="setup_01J0000000000000000000000A",
        setup_version="1.0",
        harness_id="claude-code",
        children=children,
        idempotency_key="cancel-first",
        at=AT,
    )
    cancelled = multi_root.cancel(
        registry,
        planned.transaction_id,
        at=LATER,
        reason="strategy changed",
    )
    assert cancelled.state == "cancelled"
    again = multi_root.cancel(
        registry,
        planned.transaction_id,
        at=LATER,
        reason="already gone",
    )
    assert again.transaction_id == cancelled.transaction_id
    replacements = (_child(registry, "D", "global"), _child(registry, "E", "project"))
    second = multi_root.propose(
        registry,
        setup_stable_id=planned.setup_stable_id,
        setup_version=planned.setup_version,
        harness_id=planned.harness_id,
        children=replacements,
        idempotency_key="cancel-second",
        at=LATER,
    )
    assert second.state == "planned"
    applying = multi_root.move(
        registry,
        second.transaction_id,
        expected=frozenset({"planned"}),
        state="applying",
        result="started",
        at=LATER,
    )
    with pytest.raises(CliFailure, match="unapplied"):
        multi_root.cancel(registry, applying.transaction_id, at=LATER, reason="too late")


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


def test_public_transaction_plans_approves_and_owns_children(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roots = {
        "global": tmp_path / "global",
        "project": tmp_path / "project",
    }
    for root in roots.values():
        root.mkdir()
    suffixes = {"global": "A", "project": "C"}

    def child_plan(parameters: dict[str, object]) -> Answer[InstallationView]:
        scope = str(parameters["scope"])
        child = _child(registry, suffixes[scope], cast(multi_root.Scope, scope))
        held = installation.plan(registry, child.operation_id)
        return Answer(
            InstallationView(
                operation_id=held.operation_id,
                action="install",
                state="planned",
                plan_digest=held.digest,
                target_id=held.target_id,
                expected_target_digest=held.expected_target_digest,
                expires_at=held.expires_at,
            )
        )

    monkeypatch.setattr("ai_stp_cli.commands.install_transaction.install.plan", child_plan)
    planned = install_transaction.plan(
        {
            "setup": "setup_01J0000000000000000000000A@1.0",
            "project": "project_01J0000000000000000000000A",
            "provider": "/provider",
            "scope-target": [f"{scope}={root}" for scope, root in roots.items()],
            "unverified-provider": True,
        }
    ).payload
    assert [child.scope for child in planned.children] == ["global", "project"]
    approved = install_transaction.approve(
        {
            "transaction": planned.transaction_id,
            "transaction-digest": planned.transaction_digest,
        }
    ).payload
    assert approved.approved
    with pytest.raises(CliFailure, match="multi-root transaction owns"):
        install_command.cancel(
            {"operation": approved.children[0].operation_id, "reason": "outside coordinator"}
        )

    def child_apply(parameters: dict[str, object]) -> Answer[InstallationView]:
        operation_id = str(parameters["operation"])
        held = installation.plan(registry, operation_id)
        installation.begin(
            registry,
            operation_id,
            observed_target_digest=held.expected_target_digest,
            at=LATER,
        )
        installation.applied(registry, operation_id, at=LATER, backup_ref=f"backup-{operation_id}")
        installation.verify(
            registry,
            operation_id,
            postconditions_met=True,
            at=LATER,
        )
        return Answer(
            InstallationView(
                operation_id=operation_id,
                action="install",
                state="verified",
                plan_digest=held.digest,
                target_id=held.target_id,
                expected_target_digest=held.expected_target_digest,
                expires_at=held.expires_at,
            )
        )

    monkeypatch.setattr("ai_stp_cli.commands.install_transaction.install.apply", child_apply)
    completed = install_transaction.apply(
        {"transaction": planned.transaction_id, "provider": "/provider"}
    ).payload
    assert completed.state == "verified"
    assert all(child.state == "verified" for child in completed.children)


def test_compensation_restores_verified_children_in_reverse_safe_state(
    registry: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    children = (_child(registry, "A", "global"), _child(registry, "C", "project"))
    coordinator = Coordinator(registry)
    planned = coordinator.plan(
        setup_stable_id="setup_01J0000000000000000000000A",
        setup_version="1.0",
        harness_id="claude-code",
        children=children,
        idempotency_key="compensate-command",
        at=AT,
    )
    coordinator.approve(planned.transaction_id, expected_digest=planned.digest, at=LATER)
    coordinator.begin(planned.transaction_id, at=LATER)

    first = installation.plan(registry, children[0].operation_id)
    installation.begin(
        registry,
        first.operation_id,
        observed_target_digest=first.expected_target_digest,
        at=LATER,
    )
    installation.applied(registry, first.operation_id, at=LATER, backup_ref="slot-global")
    installation.verify(registry, first.operation_id, postconditions_met=True, at=LATER)
    coordinator.observe_child(planned.transaction_id, first.operation_id, at=LATER)
    second = installation.plan(registry, children[1].operation_id)
    installation.begin(
        registry,
        second.operation_id,
        observed_target_digest=second.expected_target_digest,
        at=LATER,
    )
    installation.fail(
        registry,
        children[1].operation_id,
        at=LATER,
        reason="project refused before effect",
    )
    coordinator.observe_child(planned.transaction_id, children[1].operation_id, at=LATER)

    def rollback_plan(parameters: dict[str, object]) -> Answer[InstallationView]:
        operation_id = str(parameters.get("operation-id") or "operation_01J0000000000000000000000D")
        held = installation.propose(
            registry,
            action="rollback",
            author="account_test",
            target_id="project_test:claude-code",
            expected_target_digest="sha256:" + "d" * 64,
            provider_version="1.0.0",
            effects=("restore global",),
            recovery_action="restore exact backup",
            idempotency_key="rollback-global",
            at=AT,
            expires_at=EXPIRES,
            provider_protocol_version=3,
            operation_id=operation_id,
        )
        return Answer(
            InstallationView(
                operation_id=held.operation_id,
                action="rollback",
                state="planned",
                plan_digest=held.digest,
                target_id=held.target_id,
                expected_target_digest=held.expected_target_digest,
                expires_at=held.expires_at,
            )
        )

    def rollback_approve(parameters: dict[str, object]) -> Answer[InstallationView]:
        operation_id = str(parameters["operation"])
        held = installation.approve(
            registry,
            operation_id,
            plan_digest=str(parameters["plan-digest"]),
            at=LATER,
        )
        return Answer(
            InstallationView(
                operation_id=held.operation_id,
                action="rollback",
                state="approved",
                plan_digest=held.digest,
                target_id=held.target_id,
                expected_target_digest=held.expected_target_digest,
                expires_at=held.expires_at,
            )
        )

    def rollback_apply(parameters: dict[str, object]) -> Answer[InstallationView]:
        operation_id = str(parameters["operation"])
        held = installation.plan(registry, operation_id)
        installation.begin(
            registry,
            operation_id,
            observed_target_digest=held.expected_target_digest,
            at=LATER,
        )
        installation.applied(registry, operation_id, at=LATER)
        installation.verify(registry, operation_id, postconditions_met=True, at=LATER)
        return Answer(
            InstallationView(
                operation_id=operation_id,
                action="rollback",
                state="verified",
                plan_digest=held.digest,
                target_id=held.target_id,
                expected_target_digest=held.expected_target_digest,
                expires_at=held.expires_at,
            )
        )

    monkeypatch.setattr("ai_stp_cli.commands.install_transaction.install.plan", rollback_plan)
    monkeypatch.setattr("ai_stp_cli.commands.install_transaction.install.approve", rollback_approve)
    monkeypatch.setattr("ai_stp_cli.commands.install_transaction.install.apply", rollback_apply)
    result = install_transaction._compensate(  # pyright: ignore[reportPrivateUsage]
        coordinator,
        planned.transaction_id,
        provider="/provider",
        parameters={"unverified-provider": True},
    )
    assert result.state == "rolled_back"
    assert [child.state for child in result.children] == ["rolled_back", "failed"]


def test_compensation_reuses_the_bound_undo_after_an_interrupted_acknowledgment(
    registry: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    children = (_child(registry, "A", "global"), _child(registry, "C", "project"))
    coordinator = Coordinator(registry)
    planned = coordinator.plan(
        setup_stable_id="setup_01J0000000000000000000000A",
        setup_version="1.0",
        harness_id="claude-code",
        children=children,
        idempotency_key="compensate-reuse",
        at=AT,
    )
    coordinator.approve(planned.transaction_id, expected_digest=planned.digest, at=LATER)
    coordinator.begin(planned.transaction_id, at=LATER)
    first = installation.plan(registry, children[0].operation_id)
    installation.begin(
        registry,
        first.operation_id,
        observed_target_digest=first.expected_target_digest,
        at=LATER,
    )
    installation.applied(registry, first.operation_id, at=LATER, backup_ref="slot-global")
    installation.verify(registry, first.operation_id, postconditions_met=True, at=LATER)
    coordinator.observe_child(planned.transaction_id, first.operation_id, at=LATER)
    second_child = installation.plan(registry, children[1].operation_id)
    installation.begin(
        registry,
        second_child.operation_id,
        observed_target_digest=second_child.expected_target_digest,
        at=LATER,
    )
    installation.fail(
        registry,
        children[1].operation_id,
        at=LATER,
        reason="project refused before effect",
    )
    coordinator.observe_child(planned.transaction_id, children[1].operation_id, at=LATER)

    plan_ids: list[str] = []

    def rollback_plan(parameters: dict[str, object]) -> Answer[InstallationView]:
        operation_id = str(parameters["operation-id"])
        plan_ids.append(operation_id)
        held = installation.propose(
            registry,
            action="rollback",
            author="account_test",
            target_id="project_test:claude-code",
            expected_target_digest="sha256:" + "d" * 64,
            provider_version="1.0.0",
            effects=("restore global",),
            recovery_action="restore exact backup",
            idempotency_key=f"rollback-{operation_id}",
            at=AT,
            expires_at=EXPIRES,
            provider_protocol_version=3,
            operation_id=operation_id,
        )
        return Answer(
            InstallationView(
                operation_id=held.operation_id,
                action="rollback",
                state="planned",
                plan_digest=held.digest,
                target_id=held.target_id,
                expected_target_digest=held.expected_target_digest,
                expires_at=held.expires_at,
            )
        )

    def rollback_approve(parameters: dict[str, object]) -> Answer[InstallationView]:
        operation_id = str(parameters["operation"])
        held = installation.approve(
            registry,
            operation_id,
            plan_digest=str(parameters["plan-digest"]),
            at=LATER,
        )
        return Answer(
            InstallationView(
                operation_id=held.operation_id,
                action="rollback",
                state="approved",
                plan_digest=held.digest,
                target_id=held.target_id,
                expected_target_digest=held.expected_target_digest,
                expires_at=held.expires_at,
            )
        )

    apply_calls = 0

    def rollback_apply(parameters: dict[str, object]) -> Answer[InstallationView]:
        nonlocal apply_calls
        apply_calls += 1
        operation_id = str(parameters["operation"])
        if apply_calls == 1:
            raise CliFailure("AI_STP_UNAVAILABLE", "provider lost during rollback apply")
        held = installation.plan(registry, operation_id)
        installation.begin(
            registry,
            operation_id,
            observed_target_digest=held.expected_target_digest,
            at=LATER,
        )
        installation.applied(registry, operation_id, at=LATER)
        installation.verify(registry, operation_id, postconditions_met=True, at=LATER)
        return Answer(
            InstallationView(
                operation_id=operation_id,
                action="rollback",
                state="verified",
                plan_digest=held.digest,
                target_id=held.target_id,
                expected_target_digest=held.expected_target_digest,
                expires_at=held.expires_at,
            )
        )

    monkeypatch.setattr("ai_stp_cli.commands.install_transaction.install.plan", rollback_plan)
    monkeypatch.setattr("ai_stp_cli.commands.install_transaction.install.approve", rollback_approve)
    monkeypatch.setattr("ai_stp_cli.commands.install_transaction.install.apply", rollback_apply)
    first_pass = install_transaction._compensate(  # pyright: ignore[reportPrivateUsage]
        coordinator,
        planned.transaction_id,
        provider="/provider",
        parameters={"unverified-provider": True},
    )
    assert first_pass.state == "recovery_required"
    bound = multi_root.get(registry, planned.transaction_id)
    assert bound.children[0].undo_operation_id == plan_ids[0]
    second = install_transaction._compensate(  # pyright: ignore[reportPrivateUsage]
        coordinator,
        planned.transaction_id,
        provider="/provider",
        parameters={"unverified-provider": True},
    )
    assert second.state == "rolled_back"
    assert plan_ids == [plan_ids[0]]
    assert (
        multi_root.get(registry, planned.transaction_id).children[0].undo_operation_id
        == plan_ids[0]
    )
