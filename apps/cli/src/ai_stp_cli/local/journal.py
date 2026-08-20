"""The operation journal: enough to diagnose a local mutation that stopped.

`#74` asks for a journal "sufficient to diagnose interrupted local mutations".
That is a specific bar: after a crash a reader must be able to tell whether the
effect happened. The states are the ones `docs/contracts/operation.md` owns, and
the load-bearing one is `applied_unverified` — written *after* the effect and
*before* the check, so an entry left in it is exactly the case that needs
looking at. `verified` is the only name for success.

Rows are only ever added or moved forward. A read never writes one.
"""

import sqlite3
from dataclasses import dataclass
from typing import Final, Literal

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local.database import transaction
from ai_stp_foundation.ids import new_id

type OperationState = Literal[
    "planned",
    "approved",
    "applying",
    "applied_unverified",
    "verified",
    "partial",
    "failed",
    "stale",
    "cancelled",
    "rolled_back",
]

#: States after which nothing more happens. An entry outside this set found on
#: startup describes work that stopped without saying how it ended.
#:
#: `partial` is deliberately absent: it is an outcome, but it is one that still
#: needs a person, so an operation sitting in it must keep showing up in the
#: list of things that stopped.
SETTLED: Final[frozenset[str]] = frozenset(
    {"verified", "failed", "cancelled", "rolled_back", "stale"}
)

#: Which move each state allows (`operation.md`: "переходы выполняются только по
#: явно разрешённым событиям"). Declared here because this module already owns
#: the state names, and a second table beside them would drift.
#:
#: Terminal states allow nothing, `partial` included. Recovering from a partial
#: operation creates a *new* operation with its own plan rather than reopening
#: the old one — an operation that can leave its outcome is an operation whose
#: recorded outcome was never final.
TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "planned": frozenset({"approved", "stale", "cancelled"}),
    "approved": frozenset({"applying", "stale", "cancelled"}),
    # Once an effect may have happened, `cancelled` is gone: cancelling claims
    # nothing was done, and after this point nobody can claim that.
    #
    # `verified` is reachable directly, and that is not a loophole. A local
    # write inside one transaction either happened or did not, so there is no
    # window between the effect and its verification for `applied_unverified` to
    # describe — recording it would be recording a state that never existed.
    # The rule that an *external* effect must pass through it belongs to the
    # installation machine, which is the layer that knows its effect is
    # external; this table is the general one.
    "applying": frozenset(
        {"applied_unverified", "verified", "partial", "failed", "stale", "rolled_back"}
    ),
    "applied_unverified": frozenset({"verified", "partial", "failed", "rolled_back"}),
    "verified": frozenset(),
    "failed": frozenset(),
    "partial": frozenset(),
    "stale": frozenset(),
    "cancelled": frozenset(),
    "rolled_back": frozenset(),
}


def allowed(before: str, after: str) -> bool:
    """Whether one state may move to another. Unknown names allow nothing."""
    return after in TRANSITIONS.get(before, frozenset())


@dataclass(frozen=True)
class Operation:
    """One local mutation, as the journal recorded it."""

    operation_id: str
    kind: str
    state: OperationState
    started_at: str
    finished_at: str | None
    detail: str | None


def _row(row: sqlite3.Row) -> Operation:
    return Operation(
        operation_id=str(row["operation_id"]),
        kind=str(row["kind"]),
        state=str(row["state"]),  # pyright: ignore[reportArgumentType]
        started_at=str(row["started_at"]),
        finished_at=None if row["finished_at"] is None else str(row["finished_at"]),
        detail=None if row["detail"] is None else str(row["detail"]),
    )


def begin(connection: sqlite3.Connection, kind: str, moment: str) -> str:
    """Record that a mutation started, and return its identifier."""
    operation_id = new_id("operation")
    with transaction(connection):
        connection.execute(
            "INSERT INTO operation (operation_id, kind, state, started_at) VALUES (?, ?, ?, ?)",
            (operation_id, kind, "applying", moment),
        )
    return operation_id


def settle(
    connection: sqlite3.Connection,
    operation_id: str,
    state: OperationState,
    moment: str,
    detail: str | None = None,
) -> None:
    """Move an operation to its outcome, refusing a move nothing allows.

    The transition is checked here rather than trusted, because the failure it
    prevents is silent: an operation moved from `verified` back to `applying`
    would look like ordinary progress in the table and would have erased the one
    durable record saying the work had finished.
    """
    with transaction(connection):
        current = get(connection, operation_id)
        if current is None:
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "no operation with that identifier is recorded",
                details={"operation_id": operation_id},
            )
        if current.state != state and not allowed(current.state, state):
            raise CliFailure(
                "AI_STP_CONFLICT",
                "that operation cannot move to that state",
                details={"operation_id": operation_id, "from": current.state, "to": state},
            )
        connection.execute(
            "UPDATE operation SET state = ?, finished_at = ?, detail = ? WHERE operation_id = ?",
            (state, moment if state in SETTLED else None, detail, operation_id),
        )


def get(connection: sqlite3.Connection, operation_id: str) -> Operation | None:
    row = connection.execute(
        "SELECT * FROM operation WHERE operation_id = ?", (operation_id,)
    ).fetchone()
    return None if row is None else _row(row)


def unsettled(connection: sqlite3.Connection) -> tuple[Operation, ...]:
    """Operations that started and never said how they ended, oldest first.

    This is the diagnostic the journal exists for: after an interrupted run,
    these are the entries worth looking at.

    A registry whose schema predates the journal has no such table. That is not
    a fault to report — it is an older database, and the honest answer is that
    there is nothing to show.
    """
    placeholders = ", ".join("?" for _ in SETTLED)
    try:
        # The SQL text contains only one generated placeholder per trusted enum value;
        # every state remains bound separately below.
        rows = connection.execute(  # nosemgrep: repo-safety.opengrep.sql-fstring
            f"SELECT * FROM operation WHERE state NOT IN ({placeholders}) "
            "ORDER BY started_at, operation_id",
            tuple(sorted(SETTLED)),
        ).fetchall()
    except sqlite3.OperationalError:
        return ()
    return tuple(_row(row) for row in rows)
