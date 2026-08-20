"""Durable verified provider releases and the anti-rollback floor.

This module records evidence; it does not decide trust. Its writer is meant to
run only after signature, exact artifact bytes and the installation result have
all been verified. A lower sequence can be recovered only when its exact digest
is already in the history — a newly encountered old artifact is not recovery.
"""

import sqlite3

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local.database import transaction
from ai_stp_foundation.digests import is_digest


def minimum_sequence(connection: sqlite3.Connection, provider_id: str) -> int:
    """Highest accepted sequence for one provider, or zero before any install."""
    row = connection.execute(
        "SELECT minimum_sequence FROM provider_release_floor WHERE provider_id = ?",
        (provider_id,),
    ).fetchone()
    return 0 if row is None else int(row["minimum_sequence"])


def observed_minimum_sequence(connection: sqlite3.Connection, provider_id: str) -> int:
    """Read the floor without requiring a read-only legacy registry migration.

    Registries older than the provider-release migration cannot contain verified
    release history. Read commands must not mutate them merely to report trust,
    so an absent floor table is the same observable state as no prior install.
    """
    table = connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = ?",
        ("provider_release_floor",),
    ).fetchone()
    if table is None:
        return 0
    return minimum_sequence(connection, provider_id)


def was_verified(
    connection: sqlite3.Connection,
    *,
    provider_id: str,
    sequence: int,
    artifact_digest: str,
) -> bool:
    """Whether this exact recovery candidate was verified on this machine."""
    row = connection.execute(
        """
        SELECT 1 FROM verified_provider_release
        WHERE provider_id = ? AND sequence = ? AND artifact_digest = ?
        """,
        (provider_id, sequence, artifact_digest),
    ).fetchone()
    return row is not None


def record_verified(
    connection: sqlite3.Connection,
    *,
    provider_id: str,
    sequence: int,
    artifact_digest: str,
    at: str,
) -> int:
    """Record exact verified evidence and advance, but never lower, the floor."""
    if not provider_id or sequence < 0 or not is_digest(artifact_digest) or not at:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "verified provider release evidence is incomplete",
            details={"provider_id": provider_id, "sequence": str(sequence)},
        )

    with transaction(connection):
        known = minimum_sequence(connection, provider_id)
        same_sequence = connection.execute(
            """
            SELECT artifact_digest FROM verified_provider_release
            WHERE provider_id = ? AND sequence = ?
            """,
            (provider_id, sequence),
        ).fetchone()
        if same_sequence is not None and str(same_sequence["artifact_digest"]) != artifact_digest:
            raise CliFailure(
                "AI_STP_CONFLICT",
                "one provider release sequence cannot identify different artifact bytes",
                details={
                    "provider_id": provider_id,
                    "sequence": str(sequence),
                    "recorded_digest": str(same_sequence["artifact_digest"]),
                    "candidate_digest": artifact_digest,
                },
            )
        if sequence < known and not was_verified(
            connection,
            provider_id=provider_id,
            sequence=sequence,
            artifact_digest=artifact_digest,
        ):
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                (
                    "a lower provider release is recoverable only when this exact digest "
                    "was verified before"
                ),
                details={
                    "provider_id": provider_id,
                    "sequence": str(sequence),
                    "known_sequence": str(known),
                    "artifact_digest": artifact_digest,
                },
            )

        connection.execute(
            """
            INSERT OR IGNORE INTO verified_provider_release (
                provider_id, sequence, artifact_digest, verified_at
            ) VALUES (?, ?, ?, ?)
            """,
            (provider_id, sequence, artifact_digest, at),
        )
        if sequence > known:
            connection.execute(
                """
                INSERT INTO provider_release_floor (
                    provider_id, minimum_sequence, artifact_digest, advanced_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(provider_id) DO UPDATE SET
                    minimum_sequence = excluded.minimum_sequence,
                    artifact_digest = excluded.artifact_digest,
                    advanced_at = excluded.advanced_at
                WHERE excluded.minimum_sequence > provider_release_floor.minimum_sequence
                """,
                (provider_id, sequence, artifact_digest, at),
            )
        elif known == 0:
            # Sequence zero is valid and still needs a durable floor row.
            connection.execute(
                """
                INSERT OR IGNORE INTO provider_release_floor (
                    provider_id, minimum_sequence, artifact_digest, advanced_at
                ) VALUES (?, ?, ?, ?)
                """,
                (provider_id, sequence, artifact_digest, at),
            )
        return max(known, sequence)
