"""Durable recoverable coordination above scope-specific provider operations."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import installation, journal
from ai_stp_cli.local.database import transaction
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id

type Scope = Literal["global", "user_root", "project"]
type TransactionState = Literal[
    "planned",
    "applying",
    "compensating",
    "recovery_required",
    "verified",
    "rolled_back",
    "cancelled",
]

TRANSACTION_DOMAIN: Final[str] = "ai-stp:multi-root-transaction:v1"
SCOPE_ORDER: Final[dict[Scope, int]] = {"global": 0, "user_root": 1, "project": 2}
TERMINAL: Final[frozenset[str]] = frozenset({"verified", "rolled_back", "cancelled"})


@dataclass(frozen=True)
class Child:
    scope: Scope
    operation_id: str
    target_id: str
    plan_digest: str
    state: str = installation.STATE_PLANNED
    backup_ref: str | None = None
    undo_operation_id: str | None = None
    resource_prefixes: tuple[str, ...] = ()


@dataclass(frozen=True)
class MultiRootTransaction:
    transaction_id: str
    setup_stable_id: str
    setup_version: str
    harness_id: str
    state: TransactionState
    children: tuple[Child, ...]
    created_at: str
    updated_at: str
    approved_digest: str | None = None

    @property
    def digest(self) -> str:
        value: dict[str, JsonValue] = {
            "schema_version": 1,
            "transaction_id": self.transaction_id,
            "setup_stable_id": self.setup_stable_id,
            "setup_version": self.setup_version,
            "harness_id": self.harness_id,
            "children": [
                {
                    "scope": child.scope,
                    "operation_id": child.operation_id,
                    "target_id": child.target_id,
                    "plan_digest": child.plan_digest,
                }
                for child in self.children
            ],
        }
        return digest_canonical(TRANSACTION_DOMAIN, value)


def propose(
    connection: sqlite3.Connection,
    *,
    setup_stable_id: str,
    setup_version: str,
    harness_id: str,
    children: tuple[Child, ...],
    idempotency_key: str,
    at: str,
) -> MultiRootTransaction:
    """Record one exact multi-root decision after every child was purely planned."""
    ordered = tuple(sorted(children, key=lambda child: SCOPE_ORDER[child.scope]))
    if len(ordered) < 2:
        raise _invalid("a multi-root transaction requires at least two scopes")
    if len({child.scope for child in ordered}) != len(ordered):
        raise _invalid("a multi-root transaction contains a duplicate scope")
    if len({child.target_id for child in ordered}) != len(ordered):
        raise _invalid("a multi-root transaction contains a duplicate target")
    for child in ordered:
        plan = installation.plan(connection, child.operation_id)
        current = journal.get(connection, child.operation_id)
        if (
            plan.digest != child.plan_digest
            or plan.setup_stable_id != setup_stable_id
            or plan.setup_version != setup_version
            or current is None
            or current.state != installation.STATE_PLANNED
        ):
            raise _invalid("a child is not the exact unmodified planned operation")

    held = _by_key(connection, idempotency_key)
    if held is not None:
        candidate = _candidate(
            held.transaction_id,
            setup_stable_id,
            setup_version,
            harness_id,
            ordered,
            held.created_at,
            held.updated_at,
        )
        if candidate.digest != held.digest:
            raise CliFailure(
                "AI_STP_CONFLICT",
                "the multi-root idempotency key names different exact input",
            )
        return held

    with transaction(connection):
        for child in ordered:
            collision = connection.execute(
                "SELECT transaction_id FROM installation_transaction_target WHERE target_id = ?",
                (child.target_id,),
            ).fetchone()
            if collision is not None:
                raise CliFailure(
                    "AI_STP_CONFLICT",
                    "a target already belongs to an active multi-root transaction",
                    details={"target_id": child.target_id},
                )
            held_transaction = overlapping_reservation(connection, child.resource_prefixes)
            if held_transaction is not None:
                raise CliFailure(
                    "AI_STP_CONFLICT",
                    "a target already belongs to an active multi-root transaction",
                    details={
                        "target_id": child.target_id,
                        "transaction_id": held_transaction,
                    },
                )
        for index, child in enumerate(ordered):
            for other in ordered[index + 1 :]:
                if prefixes_overlap(child.resource_prefixes, other.resource_prefixes):
                    raise CliFailure(
                        "AI_STP_CONFLICT",
                        "a multi-root transaction contains overlapping physical roots",
                        details={"target_id": child.target_id, "other": other.target_id},
                    )
        transaction_id = new_id("operation")
        planned = _candidate(
            transaction_id,
            setup_stable_id,
            setup_version,
            harness_id,
            ordered,
            at,
            at,
        )
        connection.execute(
            """
            INSERT INTO installation_transaction (
                transaction_id, idempotency_key, transaction_digest,
                setup_stable_id, setup_version, harness_id, state,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'planned', ?, ?)
            """,
            (
                transaction_id,
                idempotency_key,
                planned.digest,
                setup_stable_id,
                setup_version,
                harness_id,
                at,
                at,
            ),
        )
        for position, child in enumerate(ordered):
            connection.execute(
                """
                INSERT INTO installation_transaction_child (
                    transaction_id, position, scope, operation_id,
                    target_id, plan_digest, state
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transaction_id,
                    position,
                    child.scope,
                    child.operation_id,
                    child.target_id,
                    child.plan_digest,
                    child.state,
                ),
            )
            connection.execute(
                "INSERT INTO installation_transaction_target (target_id, transaction_id) "
                "VALUES (?, ?)",
                (child.target_id, transaction_id),
            )
            _record_resource_prefixes(connection, transaction_id, child)
        _event(connection, transaction_id, "planned", "planned", "all child plans bound", at)
        return planned


def approve(
    connection: sqlite3.Connection, transaction_id: str, *, expected_digest: str, at: str
) -> MultiRootTransaction:
    """Atomically approve the transaction and every exact child plan."""
    with transaction(connection):
        held = get(connection, transaction_id)
        if held.state != "planned" or held.digest != expected_digest:
            raise _invalid("only the exact planned multi-root transaction can be approved")
        for child in held.children:
            installation.approve(
                connection, child.operation_id, plan_digest=child.plan_digest, at=at
            )
        connection.execute(
            "UPDATE installation_transaction SET approved_digest = ?, updated_at = ? "
            "WHERE transaction_id = ?",
            (expected_digest, at, transaction_id),
        )
        return get(connection, transaction_id)


def move(
    connection: sqlite3.Connection,
    transaction_id: str,
    *,
    expected: frozenset[str],
    state: TransactionState,
    result: str,
    at: str,
) -> MultiRootTransaction:
    """Persist one coordinator transition without claiming a child effect."""
    with transaction(connection):
        held = get(connection, transaction_id)
        if held.state not in expected:
            raise _invalid("the multi-root transaction is not in the required state")
        connection.execute(
            "UPDATE installation_transaction SET state = ?, updated_at = ? "
            "WHERE transaction_id = ?",
            (state, at, transaction_id),
        )
        _event(connection, transaction_id, held.state, state, result, at)
        if state in TERMINAL:
            _release_reservations(connection, transaction_id)
        return get(connection, transaction_id)


def record_undo(
    connection: sqlite3.Connection,
    transaction_id: str,
    operation_id: str,
    *,
    undo_operation_id: str,
    at: str,
) -> MultiRootTransaction:
    """Bind the exact undo operation before any compensation effect."""
    with transaction(connection):
        held = get(connection, transaction_id)
        if operation_id not in {child.operation_id for child in held.children}:
            raise _invalid("the operation is not a child of this transaction")
        connection.execute(
            """
            UPDATE installation_transaction_child
            SET undo_operation_id = ?
            WHERE transaction_id = ? AND operation_id = ?
            """,
            (undo_operation_id, transaction_id, operation_id),
        )
        connection.execute(
            "UPDATE installation_transaction SET updated_at = ? WHERE transaction_id = ?",
            (at, transaction_id),
        )
        return get(connection, transaction_id)


def record_child(
    connection: sqlite3.Connection,
    transaction_id: str,
    operation_id: str,
    *,
    state: str,
    backup_ref: str | None,
    at: str,
) -> MultiRootTransaction:
    """Record the last accurate child state after reading its durable journal."""
    with transaction(connection):
        held = get(connection, transaction_id)
        if operation_id not in {child.operation_id for child in held.children}:
            raise _invalid("the operation is not a child of this transaction")
        connection.execute(
            """
            UPDATE installation_transaction_child
            SET state = ?, backup_ref = ?
            WHERE transaction_id = ? AND operation_id = ?
            """,
            (state, backup_ref, transaction_id, operation_id),
        )
        connection.execute(
            "UPDATE installation_transaction SET updated_at = ? WHERE transaction_id = ?",
            (at, transaction_id),
        )
        return get(connection, transaction_id)


def cancel(
    connection: sqlite3.Connection,
    transaction_id: str,
    *,
    at: str,
    reason: str,
) -> MultiRootTransaction:
    """Abandon an unapplied plan and release every reserved target.

    Cancellation means no native effect was made. Once application may have
    started, recovery is the public path; this refuses rather than deleting
    evidence.
    """
    held = get(connection, transaction_id)
    if held.state == "cancelled":
        return held
    if held.state != "planned":
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "only an unapplied multi-root transaction can be cancelled",
            details={"transaction_id": transaction_id, "state": held.state},
        )
    with transaction(connection):
        held = get(connection, transaction_id)
        if held.state == "cancelled":
            return held
        if held.state != "planned":
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "only an unapplied multi-root transaction can be cancelled",
                details={"transaction_id": transaction_id, "state": held.state},
            )
        for child in held.children:
            current = journal.get(connection, child.operation_id)
            if current is not None and current.state in {
                installation.STATE_PLANNED,
                installation.STATE_APPROVED,
            }:
                installation.cancel(
                    connection,
                    child.operation_id,
                    at=at,
                    reason=reason,
                )
            recorded = journal.get(connection, child.operation_id)
            connection.execute(
                """
                UPDATE installation_transaction_child
                SET state = ?
                WHERE transaction_id = ? AND operation_id = ?
                """,
                (
                    installation.STATE_CANCELLED if recorded is None else recorded.state,
                    transaction_id,
                    child.operation_id,
                ),
            )
        connection.execute(
            "UPDATE installation_transaction SET state = ?, updated_at = ? "
            "WHERE transaction_id = ?",
            ("cancelled", at, transaction_id),
        )
        _release_reservations(connection, transaction_id)
        _event(connection, transaction_id, held.state, "cancelled", reason, at)
        return get(connection, transaction_id)


def get(connection: sqlite3.Connection, transaction_id: str) -> MultiRootTransaction:
    row = connection.execute(
        "SELECT * FROM installation_transaction WHERE transaction_id = ?",
        (transaction_id,),
    ).fetchone()
    if row is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no multi-root transaction with that identifier is recorded",
        )
    children = _children(connection, transaction_id)
    return MultiRootTransaction(
        transaction_id=str(row["transaction_id"]),
        setup_stable_id=str(row["setup_stable_id"]),
        setup_version=str(row["setup_version"]),
        harness_id=str(row["harness_id"]),
        state=str(row["state"]),  # type: ignore[arg-type]
        children=children,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        approved_digest=None if row["approved_digest"] is None else str(row["approved_digest"]),
    )


def child_is_owned(connection: sqlite3.Connection, operation_id: str) -> bool:
    """Report whether an active multi-root transaction owns this child."""
    row = connection.execute(
        """
        SELECT 1
        FROM installation_transaction_child AS child
        JOIN installation_transaction AS parent USING (transaction_id)
        WHERE child.operation_id = ? AND parent.state NOT IN (
            'verified', 'rolled_back', 'cancelled'
        )
        """,
        (operation_id,),
    ).fetchone()
    return row is not None


def _children(connection: sqlite3.Connection, transaction_id: str) -> tuple[Child, ...]:
    rows = connection.execute(
        "SELECT * FROM installation_transaction_child WHERE transaction_id = ? ORDER BY position",
        (transaction_id,),
    ).fetchall()
    return tuple(
        Child(
            scope=str(row["scope"]),  # type: ignore[arg-type]
            operation_id=str(row["operation_id"]),
            target_id=str(row["target_id"]),
            plan_digest=str(row["plan_digest"]),
            state=str(row["state"]),
            backup_ref=None if row["backup_ref"] is None else str(row["backup_ref"]),
            undo_operation_id=(
                None if row["undo_operation_id"] is None else str(row["undo_operation_id"])
            ),
        )
        for row in rows
    )


def _by_key(connection: sqlite3.Connection, key: str) -> MultiRootTransaction | None:
    row = connection.execute(
        "SELECT transaction_id FROM installation_transaction WHERE idempotency_key = ?",
        (key,),
    ).fetchone()
    return None if row is None else get(connection, str(row["transaction_id"]))


def _candidate(
    transaction_id: str,
    setup_stable_id: str,
    setup_version: str,
    harness_id: str,
    children: tuple[Child, ...],
    created_at: str,
    updated_at: str,
) -> MultiRootTransaction:
    return MultiRootTransaction(
        transaction_id=transaction_id,
        setup_stable_id=setup_stable_id,
        setup_version=setup_version,
        harness_id=harness_id,
        state="planned",
        children=children,
        created_at=created_at,
        updated_at=updated_at,
    )


def _event(
    connection: sqlite3.Connection,
    transaction_id: str,
    before: str,
    after: str,
    result: str,
    at: str,
) -> None:
    row = connection.execute(
        "SELECT max(sequence) AS held FROM installation_transaction_event WHERE transaction_id = ?",
        (transaction_id,),
    ).fetchone()
    sequence = 1 if row is None or row["held"] is None else int(row["held"]) + 1
    connection.execute(
        "INSERT INTO installation_transaction_event "
        "(transaction_id, sequence, at, state_before, state_after, result) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (transaction_id, sequence, at, before, after, result),
    )


def _invalid(message: str) -> CliFailure:
    return CliFailure("AI_STP_PRECONDITION_FAILED", message)


def canonical_resource(path: Path) -> Path:
    """The filesystem object `path` names, independent of how it was spelled."""
    text = str(path.expanduser().resolve())
    if os.name == "nt":
        text = os.path.normcase(text)
    return Path(text)


def resource_identity(path: Path) -> str:
    """Reservation token for one physical root. Scope is not part of identity."""
    return digest_canonical(TRANSACTION_DOMAIN, {"resource": str(canonical_resource(path))})


def resource_prefix_digests(path: Path) -> tuple[str, ...]:
    """Digests of every ancestor of `path`, ending at the path itself.

    Stored instead of the path string so overlap can be detected without
    putting absolute locations in the registry (REQ-5808).
    """
    canonical = canonical_resource(path)
    prefixes: list[str] = []
    accumulated = Path(canonical.anchor) if canonical.anchor else Path(canonical.parts[0])
    prefixes.append(digest_canonical(TRANSACTION_DOMAIN, {"resource": str(accumulated)}))
    for part in canonical.parts[1:]:
        accumulated = accumulated / part
        prefixes.append(digest_canonical(TRANSACTION_DOMAIN, {"resource": str(accumulated)}))
    return tuple(prefixes)


def prefixes_overlap(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    """True when two prefix chains name the same root or an ancestor/descendant."""
    if not left or not right:
        return False
    return left[-1] in right or right[-1] in left


def overlapping_reservation(
    connection: sqlite3.Connection, prefixes: tuple[str, ...]
) -> str | None:
    """Return the active transaction that already holds an overlapping root."""
    if not prefixes:
        return None
    exact = connection.execute(
        "SELECT transaction_id FROM installation_transaction_resource "
        "WHERE resource_digest = ? LIMIT 1",
        (prefixes[-1],),
    ).fetchone()
    if exact is not None:
        return str(exact["transaction_id"])
    ancestors = prefixes[:-1]
    if not ancestors:
        return None
    placeholders = ",".join("?" * len(ancestors))
    held = connection.execute(
        "SELECT transaction_id FROM installation_transaction_resource "
        f"WHERE is_exact = 1 AND resource_digest IN ({placeholders}) LIMIT 1",
        ancestors,
    ).fetchone()
    return None if held is None else str(held["transaction_id"])


def _record_resource_prefixes(
    connection: sqlite3.Connection, transaction_id: str, child: Child
) -> None:
    if not child.resource_prefixes:
        return
    last = len(child.resource_prefixes) - 1
    for index, digest in enumerate(child.resource_prefixes):
        connection.execute(
            """
            INSERT INTO installation_transaction_resource (
                resource_digest, target_id, transaction_id, is_exact
            ) VALUES (?, ?, ?, ?)
            """,
            (digest, child.target_id, transaction_id, 1 if index == last else 0),
        )


def _release_reservations(connection: sqlite3.Connection, transaction_id: str) -> None:
    connection.execute(
        "DELETE FROM installation_transaction_resource WHERE transaction_id = ?",
        (transaction_id,),
    )
    connection.execute(
        "DELETE FROM installation_transaction_target WHERE transaction_id = ?",
        (transaction_id,),
    )
