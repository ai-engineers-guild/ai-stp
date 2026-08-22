# pyright: reportPrivateUsage=false
"""Which provider copies a pair can restore from (`SPEC-012` `REQ-1207`).

The read half the requirement assumed and nothing answered. A `BackupRef` used
to appear exactly once — in the answer to `install apply` — so an agent that did
not keep that stdout could not name the copy again, and "I took a backup" led to
"restore it" only by remembering.

Every property the acceptance criterion names is observed here: creation order,
an unfinished operation offering nothing, another pair's copy staying out, and a
rollback plan that needs neither `--setup` nor `--proposal`.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing

import pytest

from ai_stp_cli.commands import install as install_cmd
from ai_stp_cli.local import installation, targets
from ai_stp_cli.local.database import configured_path, open_registry

pytestmark = pytest.mark.cli

PROJECT = "project_01J0000000000000000000000A"
HARNESS = "claude-code"
PAIR = f"{PROJECT}:{HARNESS}"
OTHER_PAIR = f"{PROJECT}:codex"


@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        yield connection


def _plan(
    connection: sqlite3.Connection,
    version: str,
    *,
    at: str,
    target_id: str = PAIR,
) -> installation.Plan:
    return installation.propose(
        connection,
        action="install",
        author="account_x",
        target_id=target_id,
        expected_target_digest="sha256:" + "0" * 64,
        provider_version="1.0.0",
        effects=("write something",),
        recovery_action="restore",
        idempotency_key=f"key-{target_id}-{version}",
        at=at,
        expires_at="2099-01-01T00:00:00.000Z",
        setup_stable_id="setup_01J0000000000000000000000B",
        setup_version=version,
    )


def _take_copy(
    connection: sqlite3.Connection,
    version: str,
    *,
    backup_ref: str,
    at: str,
    target_id: str = PAIR,
    settle: bool = True,
) -> str:
    """One operation that took a provider copy, as the log would record it."""
    plan = _plan(connection, version, at=at, target_id=target_id)
    installation.approve(connection, plan.operation_id, plan_digest=plan.digest, at=at)
    installation.begin(
        connection,
        plan.operation_id,
        observed_target_digest="sha256:" + "0" * 64,
        at=at,
    )
    installation.applied(connection, plan.operation_id, at=at, backup_ref=backup_ref)
    if settle:
        installation.verify(
            connection,
            plan.operation_id,
            postconditions_met=True,
            at=at,
            observed_target_digest="sha256:" + "1" * 64,
        )
    return plan.operation_id


def _listed() -> list[str]:
    answer = install_cmd.target_backups({"project": PROJECT, "harness": HARNESS})
    return [item.backup_ref for item in answer.payload.backups]


def test_a_copy_can_be_named_again_after_the_operation_that_took_it(
    registry: sqlite3.Connection,
) -> None:
    """The whole point: the reference survives the stdout that first carried it."""
    _take_copy(registry, "1.0", backup_ref="backup-a", at="2026-01-01T00:00:00.000Z")

    answer = install_cmd.target_backups({"project": PROJECT, "harness": HARNESS})

    assert [item.backup_ref for item in answer.payload.backups] == ["backup-a"]
    held = answer.payload.backups[0]
    assert held.setup_version == "1.0"
    assert held.operation_id
    assert held.created_at


def test_copies_are_listed_in_the_order_they_were_taken(
    registry: sqlite3.Connection,
) -> None:
    """Creation order, and not by timestamp.

    Millisecond stamps tie when a run is fast, and a list whose order depends on
    how quickly the machine worked is not an order at all. The durable local
    sequence answers it, the same way the previous verified version is found.
    """
    at = "2026-01-01T00:00:00.000Z"
    for index in range(3):
        _take_copy(registry, f"1.{index}", backup_ref=f"backup-{index}", at=at)

    assert _listed() == ["backup-0", "backup-1", "backup-2"]


def test_an_operation_that_never_settled_offers_no_copy(
    registry: sqlite3.Connection,
) -> None:
    """A reference on an operation that stopped belongs to `install recover`.

    Offering it here would read as "restorable" without anything having said so,
    and the operation may still be holding the target half-changed.
    """
    _take_copy(
        registry,
        "1.0",
        backup_ref="backup-unsettled",
        at="2026-01-01T00:00:00.000Z",
        settle=False,
    )

    assert _listed() == []


def test_a_copy_of_another_pair_is_not_offered(registry: sqlite3.Connection) -> None:
    """A copy restores one target. Listing another pair's would offer a restore
    that puts one harness's configuration onto another."""
    at = "2026-01-01T00:00:00.000Z"
    _take_copy(registry, "1.0", backup_ref="backup-mine", at=at)
    _take_copy(registry, "1.0", backup_ref="backup-theirs", at=at, target_id=OTHER_PAIR)

    assert _listed() == ["backup-mine"]


def test_an_operation_without_a_copy_is_not_listed_as_one(
    registry: sqlite3.Connection,
) -> None:
    """Most operations take no copy, and a row of nothing is not a copy."""
    at = "2026-01-01T00:00:00.000Z"
    plan = _plan(registry, "1.0", at=at)
    installation.approve(registry, plan.operation_id, plan_digest=plan.digest, at=at)
    installation.begin(
        registry, plan.operation_id, observed_target_digest="sha256:" + "0" * 64, at=at
    )
    installation.applied(registry, plan.operation_id, at=at)
    installation.verify(
        registry,
        plan.operation_id,
        postconditions_met=True,
        at=at,
        observed_target_digest="sha256:" + "1" * 64,
    )

    assert _listed() == []


def test_a_pair_with_no_registry_at_all_answers_rather_than_failing() -> None:
    """A machine that has installed nothing has no copies, which is an answer."""
    answer = install_cmd.target_backups({"project": PROJECT, "harness": HARNESS})

    assert answer.payload.backups == []
    assert answer.payload.project_id == PROJECT


def test_listing_copies_is_not_where_the_previous_version_is_named() -> None:
    """`REQ-814` keeps the copy and the setup apart, so the two reads do too.

    `target rollback` names the previous verified *version*; a reference to a
    copy is not the identity of a setup. Answering both from one place would
    blur exactly the distinction those requirements exist to keep.
    """
    from ai_stp_contracts.machine_help import TargetBackups

    assert "setup_stable_id" not in TargetBackups.model_fields
    assert set(TargetBackups.model_fields) >= {"project_id", "harness_id", "backups"}


def test_the_rollback_plan_needs_neither_a_setup_nor_a_proposal() -> None:
    """The plan binds to the pair and the copy, and nothing else.

    Requiring a setup would make restoring depend on knowing what was installed
    — which is the thing a person restoring has usually just lost.
    """
    from ai_stp_cli.registry import DECLARATIONS

    declaration = next(item for item in DECLARATIONS if item.path == ["target", "rollback"])
    required = {option.name for option in declaration.parameters if option.required}

    assert "setup" not in required
    assert "proposal" not in required
    assert {"project", "harness"} <= required


def test_the_backups_read_changes_nothing(registry: sqlite3.Connection) -> None:
    """Declared read-only, and read-only in what it opens.

    A command that names recovery options is the last one that should be able
    to alter them.
    """
    from ai_stp_cli.registry import DECLARATIONS

    declaration = next(item for item in DECLARATIONS if item.path == ["target", "backups"])
    assert declaration.mutability == "read"

    _take_copy(registry, "1.0", backup_ref="backup-a", at="2026-01-01T00:00:00.000Z")
    before = targets.backups(registry, project_id=PROJECT, harness_id=HARNESS)
    _listed()
    after = targets.backups(registry, project_id=PROJECT, harness_id=HARNESS)

    assert before == after


def test_a_sourceless_action_can_name_the_pair_it_acts_on() -> None:
    """`backup` and `rollback` read a harness the command could not accept.

    Neither names a setup, so nothing else supplies the pair: `install plan`
    reads `parameters["harness"]` for them and the declaration had no such
    option. Both actions were unreachable from the CLI — `install plan --action
    rollback --backup-ref …` answered "the harness must be named" and offered no
    way to name it.

    It survived because the agent surface is generated from this declaration and
    the handler reads parameters by name; the two agreed about everything except
    whether the option existed.
    """
    from ai_stp_cli.commands.install import _SOURCELESS_ACTIONS
    from ai_stp_cli.registry import DECLARATIONS

    plan = next(d for d in DECLARATIONS if list(d.path) == ["install", "plan"])
    options = {option.name for option in plan.parameters}

    assert _SOURCELESS_ACTIONS, "the sourceless set is what makes this option necessary"
    for name in ("project", "harness"):
        assert name in options, (
            f"install plan reads {name!r} for {sorted(_SOURCELESS_ACTIONS)} and cannot accept it"
        )
