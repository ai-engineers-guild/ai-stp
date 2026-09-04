"""Drafts, overlay provenance and tombstones (`#159`).

Three states an entity can be in that its revisions alone do not say.

A **draft** is an entity whose head declares itself incomplete. `SPEC-005`
REQ-509 lets an incomplete draft sync privately while keeping it out of
registration, ranking and search, so the local store has to be able to answer
"is this ready" without reading a caller's mind — the answer lives in the
passport content, where a revision already carries it, rather than in a column
that could disagree with the content it describes.

An **overlay** records where a materialised change came from. REQ-506 makes
applying one a composition change that creates the next minor version, so the
provenance has to outlive the act: recomputing later which base an overlay was
applied to is guessing, and the version it produced is immutable.

A **tombstone** marks an entity deleted (`SPEC-013` REQ-1308) without removing
anything. The sync contract replays a `tombstone` operation and replay must be
idempotent, so this is a row keyed by the entity — replaying it a second time
finds the mark already there and changes nothing, which is a much easier
property to hold than making a destructive delete repeatable.
"""

import sqlite3
from dataclasses import dataclass
from typing import Final

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import revisions

#: Lifecycle states a passport declares about itself (`SPEC-003`). `tombstoned`
#: is not among them: being deleted is a fact about the entity, recorded here,
#: not a claim the content makes about itself.
STATE_DRAFT: Final[str] = "draft"
STATE_COMPLETE: Final[str] = "complete"
STATE_CONFLICT: Final[str] = "conflict"
DECLARED_STATES: Final[frozenset[str]] = frozenset({STATE_DRAFT, STATE_COMPLETE, STATE_CONFLICT})

#: Where an overlay's bytes came from. Closed: an unnamed origin is the one
#: thing a provenance record must not be able to hold.
ORIGIN_KINDS: Final[frozenset[str]] = frozenset({"local_file", "component_version", "generated"})


@dataclass(frozen=True)
class Overlay:
    """Where one materialised overlay came from, and what it was applied to."""

    revision_id: str
    source_kind: str
    source_ref: str
    base_digest: str
    applied_at: str


@dataclass(frozen=True)
class Tombstone:
    """The mark that an entity was deleted, and why."""

    stable_id: str
    reason: str
    created_at: str


def declared_state(stored: revisions.StoredRevision) -> str:
    """What this revision says about its own completeness.

    Carried through the envelope's preserved-fields channel rather than as a
    declared field, and that is not laziness. Sealing hashes the complete
    serialized form *including defaults*, so a new field with a default would
    change the bytes of every passport ever written and therefore every
    `revision_id` already stored. As an extra it appears only on a passport that
    actually sets it, and nothing already sealed moves.

    Distinct from the version lifecycle of `SPEC-005`, which stays outside the
    hashed bytes because a published version is immutable. This one belongs
    inside them: finishing a draft *is* a change to the passport, and it should
    produce a revision saying so.

    A passport with no declared state is `complete`. Every passport written
    before drafts existed is finished, and reading silence as `draft` would
    retroactively hide all of them from search.
    """
    content = stored.envelope.model_dump(mode="json")
    held = content.get("lifecycle_state")
    if held is None:
        return STATE_COMPLETE
    if str(held) not in DECLARED_STATES:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a passport declares an unknown lifecycle state",
            details={"revision_id": stored.revision_id, "state": str(held)},
        )
    return str(held)


def is_draft(stored: revisions.StoredRevision) -> bool:
    """Whether this revision is an incomplete draft (`REQ-509`)."""
    return declared_state(stored) == STATE_DRAFT


def registrable(connection: sqlite3.Connection, stored: revisions.StoredRevision) -> bool:
    """Whether this revision may be registered, ranked or returned by search.

    Both exclusions in one place on purpose. A draft and a tombstoned object are
    invisible for different reasons — one is not finished, the other is deleted
    — but every caller that filters needs both, and two predicates would be two
    chances to apply only one of them.

    A *revision* rather than an entity, because the two kinds disagree about
    what an entity's current state even is. `developer`, `device` and `project`
    are mutable and have one head; `component` and `setup` are snapshots that
    the envelope forbids from having parents, so one logical object holds many
    unrelated heads and asking "is the entity a draft" has no single answer.
    Draft-ness belongs to the revision. Deletion belongs to the entity, and is
    looked up from the revision's own `stable_id`.
    """
    if entombed(connection, stored.stable_id) is not None:
        return False
    return not is_draft(stored)


def record_overlay(
    connection: sqlite3.Connection,
    *,
    revision_id: str,
    source_kind: str,
    source_ref: str,
    base_digest: str,
    at: str,
) -> Overlay:
    """Record where an overlay came from, beside the revision it produced."""
    if source_kind not in ORIGIN_KINDS:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "an overlay origin is not one this contract defines",
            details={"source_kind": source_kind, "allowed": ", ".join(sorted(ORIGIN_KINDS))},
        )
    if not source_ref or not base_digest:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "an overlay must name both its source and the base it was applied to",
            details={"source_kind": source_kind},
        )
    connection.execute(
        """
        INSERT INTO overlay_origin
            (revision_id, source_kind, source_ref, base_digest, applied_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (revision_id) DO NOTHING
        """,
        (revision_id, source_kind, source_ref, base_digest, at),
    )
    found = overlay_of(connection, revision_id)
    if found is None:  # pragma: no cover - the insert above guarantees a row
        raise CliFailure("AI_STP_INTERNAL", "the overlay record vanished after being written")
    return found


def overlay_of(connection: sqlite3.Connection, revision_id: str) -> Overlay | None:
    """The provenance of one revision, if it came from an overlay."""
    row = connection.execute(
        "SELECT * FROM overlay_origin WHERE revision_id = ?", (revision_id,)
    ).fetchone()
    if row is None:
        return None
    return Overlay(
        revision_id=str(row["revision_id"]),
        source_kind=str(row["source_kind"]),
        source_ref=str(row["source_ref"]),
        base_digest=str(row["base_digest"]),
        applied_at=str(row["applied_at"]),
    )


def entomb(connection: sqlite3.Connection, stable_id: str, *, reason: str, at: str) -> Tombstone:
    """Mark an entity deleted. Replaying this finds the mark and changes nothing.

    The first mark wins, including its reason and its moment. A replayed
    `tombstone` event carrying a later timestamp must not move the record — the
    deletion happened once, and `SPEC-013` REQ-1309 wants the repeat to be safe,
    not to be a second deletion.
    """
    row = connection.execute("SELECT 1 FROM entity WHERE stable_id = ?", (stable_id,)).fetchone()
    if row is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "nothing is registered under that identifier",
            details={"stable_id": stable_id},
        )
    connection.execute(
        """
        INSERT INTO tombstone (stable_id, reason, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT (stable_id) DO NOTHING
        """,
        (stable_id, reason, at),
    )
    found = entombed(connection, stable_id)
    if found is None:  # pragma: no cover - the insert above guarantees a row
        raise CliFailure("AI_STP_INTERNAL", "the tombstone vanished after being written")
    return found


def entombed(connection: sqlite3.Connection, stable_id: str) -> Tombstone | None:
    """The deletion mark for an entity, if it has one."""
    row = connection.execute("SELECT * FROM tombstone WHERE stable_id = ?", (stable_id,)).fetchone()
    if row is None:
        return None
    return Tombstone(
        stable_id=str(row["stable_id"]),
        reason=str(row["reason"]),
        created_at=str(row["created_at"]),
    )
