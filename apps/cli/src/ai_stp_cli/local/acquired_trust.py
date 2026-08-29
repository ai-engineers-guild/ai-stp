"""What the catalogue said about a version this machine acquired (`#447`).

Everything in the local registry used to be `owned_or_pinned=True`, on the
reasoning that it was adopted or authored here and no platform ever confirmed
it. `registry acquire` makes that false: it materialises a published setup and
its exact graph into the same tables, and those objects have an author who is
not this user and a verdict the catalogue already reached.

Left alone, `lane_of` checks ownership first, so an acquired object took the
`local_owner_or_pinned` lane and never reached `experimental` — skipping the
unverified-consent question, the licence and the grant in one step. That is an
excess permission rather than a missing refusal, which is why the repair is to
record what the catalogue said rather than to add a check.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Verdict:
    """The catalogue's trust axes for one exact acquired version."""

    trust_lane: str
    author_verified: bool
    component_verified: bool


def record(
    connection: sqlite3.Connection,
    *,
    stable_id: str,
    version: str,
    passport_digest: str,
    verdict: Verdict,
    at: str,
) -> None:
    """Store the verdict that came with an acquired version.

    Idempotent by primary key: acquiring the same exact version twice records
    the same answer, and an immutable `X.Y` cannot carry two.
    """
    connection.execute(
        """
        INSERT INTO acquired_trust (
            stable_id, version, passport_digest,
            trust_lane, author_verified, component_verified, acquired_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (stable_id, version) DO NOTHING
        """,
        (
            stable_id,
            version,
            passport_digest,
            verdict.trust_lane,
            int(verdict.author_verified),
            int(verdict.component_verified),
            at,
        ),
    )


def verdicts(connection: sqlite3.Connection) -> dict[tuple[str, str], Verdict]:
    """Every recorded verdict, keyed by the exact version it describes.

    Read in one statement rather than per candidate: the caller is building a
    whole candidate set, and a query per row is how a list becomes a loop over
    the database.
    """
    rows = connection.execute(
        """
        SELECT stable_id, version, trust_lane, author_verified, component_verified
        FROM acquired_trust
        """
    ).fetchall()
    return {
        (str(row["stable_id"]), str(row["version"])): Verdict(
            trust_lane=str(row["trust_lane"]),
            author_verified=bool(row["author_verified"]),
            component_verified=bool(row["component_verified"]),
        )
        for row in rows
    }
