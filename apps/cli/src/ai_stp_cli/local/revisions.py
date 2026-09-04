"""Entities, content-addressed revisions and heads.

`SPEC-009` REQ-903: a revision is addressed by the canonical hash of its content
and carries parents, schema version, author, device and operation. The first
three live in the passport envelope, so they are part of what is hashed; the
device and the operation are registry metadata about *how* the revision came to
exist, so they are columns beside it.

Content addressing does the deduplication by itself: identical content seals to
an identical `revision_id`, and the primary key refuses the second insert. There
is no separate "have I seen this before" check to get wrong.
"""

import json
import sqlite3
from collections import deque
from dataclasses import dataclass
from typing import cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local.database import transaction
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_passports.envelope import PassportEnvelope, seal_envelope


@dataclass(frozen=True)
class StoredRevision:
    """One revision as the registry holds it."""

    revision_id: str
    stable_id: str
    envelope: PassportEnvelope
    device_id: str
    operation_id: str | None
    created_at: str
    parents: tuple[str, ...]


def _decode(row: sqlite3.Row, parents: tuple[str, ...]) -> StoredRevision:
    document = cast(dict[str, JsonValue], json.loads(row["content"]))
    return StoredRevision(
        revision_id=str(row["revision_id"]),
        stable_id=str(row["stable_id"]),
        envelope=PassportEnvelope.model_validate(document),
        device_id=str(row["device_id"]),
        operation_id=None if row["operation_id"] is None else str(row["operation_id"]),
        created_at=str(row["created_at"]),
        parents=parents,
    )


def _parents_of(connection: sqlite3.Connection, revision_id: str) -> tuple[str, ...]:
    rows = connection.execute(
        "SELECT parent_revision_id FROM revision_parent WHERE revision_id = ? "
        "ORDER BY parent_revision_id",
        (revision_id,),
    ).fetchall()
    return tuple(str(row[0]) for row in rows)


def get(connection: sqlite3.Connection, revision_id: str) -> StoredRevision | None:
    """One revision by its identifier, or `None`. Reads nothing into existence."""
    row = connection.execute(
        "SELECT * FROM revision WHERE revision_id = ?", (revision_id,)
    ).fetchone()
    if row is None:
        return None
    return _decode(row, _parents_of(connection, revision_id))


def heads(connection: sqlite3.Connection, stable_id: str) -> tuple[StoredRevision, ...]:
    """Every current head of one entity, oldest first.

    Plural because divergence is representable: two devices can extend the same
    entity independently, and `SPEC-009` REQ-905 resolves that by merging rather
    than by picking. Locally there is normally one.
    """
    rows = connection.execute(
        "SELECT r.* FROM head h JOIN revision r ON r.revision_id = h.revision_id "
        # Insertion order, not `created_at`: a child may legitimately share its
        # parent's timestamp, and then a content hash would decide the order of
        # a causal chain.
        "WHERE h.stable_id = ? ORDER BY r.rowid",
        (stable_id,),
    ).fetchall()
    return tuple(_decode(row, _parents_of(connection, str(row["revision_id"]))) for row in rows)


def head(connection: sqlite3.Connection, stable_id: str) -> StoredRevision | None:
    """The single head, refusing to choose when there is more than one."""
    found = heads(connection, stable_id)
    if len(found) > 1:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "this object has more than one head and needs a merge",
            details={"stable_id": stable_id, "heads": str(len(found))},
        )
    return next(iter(found), None)


def _ancestor_distances(connection: sqlite3.Connection, revision_id: str) -> dict[str, int]:
    """Return every known ancestor and its shortest distance from a revision."""
    if get(connection, revision_id) is None:
        return {}
    distances = {revision_id: 0}
    frontier = deque([revision_id])
    while frontier:
        child = frontier.popleft()
        distance = distances[child] + 1
        for parent in _parents_of(connection, child):
            previous = distances.get(parent)
            if previous is not None and previous <= distance:
                continue
            distances[parent] = distance
            frontier.append(parent)
    return distances


def is_ancestor(connection: sqlite3.Connection, ancestor: str, descendant: str) -> bool:
    """Whether both revisions exist and ``ancestor`` is in ``descendant``'s graph."""
    return ancestor in _ancestor_distances(connection, descendant)


def common_ancestor(connection: sqlite3.Connection, left: str, right: str) -> StoredRevision | None:
    """Find the deterministic nearest common ancestor of two known revisions.

    A merge graph can have more than one common ancestor. The candidate with
    the smallest maximum distance is closest to both heads; total distance and
    revision ID make the choice stable when the graph is symmetric. Unknown or
    disconnected revisions have no common ancestor.
    """
    left_distances = _ancestor_distances(connection, left)
    right_distances = _ancestor_distances(connection, right)
    shared = set(left_distances).intersection(right_distances)
    if not shared:
        return None
    chosen = min(
        shared,
        key=lambda revision_id: (
            max(left_distances[revision_id], right_distances[revision_id]),
            left_distances[revision_id] + right_distances[revision_id],
            revision_id,
        ),
    )
    return get(connection, chosen)


def commit(
    connection: sqlite3.Connection,
    content: dict[str, JsonValue],
    *,
    device_id: str,
    operation_id: str | None = None,
) -> StoredRevision:
    """Seal `content`, store it, and move the entity's head onto it.

    Content arrives without a `revision_id`; sealing derives it from the content
    itself, so a caller cannot store bytes under an identifier that does not
    describe them.

    Storing the same content twice is not an error and does not create a second
    revision — that is what content addressing is for — but it does not move the
    head backwards either. A revision this registry already holds is returned
    untouched: identical identifier means identical content, so there is nothing
    to write, and nothing to decide about heads.

    That last part was the defect. Head movement used to run whichever branch
    was taken, so replaying an **ancestor** — which is what a sync, an import or
    a recovery does — added it back as a second head beside the current one. The
    entity then had two heads and `head()` refused it as a conflict, with no
    concurrent edit anywhere in sight.

    `device_id` and `operation_id` describe how a revision came to exist rather
    than what it says, so they are columns beside the content and not part of the
    hash. Re-committing known content from another device therefore keeps the
    original pair: the first writer is the one that recorded it.
    """
    sealed = seal_envelope(content)
    stored_bytes = canonize(cast(dict[str, JsonValue], sealed.model_dump(mode="json")))
    document = stored_bytes.decode("utf-8")

    with transaction(connection):
        known = connection.execute(
            "SELECT 1 FROM revision WHERE revision_id = ?", (sealed.revision_id,)
        ).fetchone()
        if known is not None:
            stored = get(connection, sealed.revision_id)
            assert stored is not None
            return stored

        _validate_parents(connection, sealed)
        connection.execute(
            "INSERT OR IGNORE INTO entity (stable_id, kind, created_at) VALUES (?, ?, ?)",
            (sealed.stable_id, sealed.kind, sealed.created_at),
        )
        # `OR IGNORE` swallows the singleton constraint as readily as it swallows
        # a re-insert of the same row, and the next statement would then fail on
        # a foreign key with nothing to explain it. Ask directly instead.
        if (
            connection.execute(
                "SELECT 1 FROM entity WHERE stable_id = ?", (sealed.stable_id,)
            ).fetchone()
            is None
        ):
            raise CliFailure(
                "AI_STP_CONFLICT",
                "this installation already has a different passport of that kind",
                details={"stable_id": sealed.stable_id, "kind": sealed.kind},
                next_actions=["doctor --json"],
            )
        connection.execute(
            "INSERT INTO revision "
            "(revision_id, stable_id, content, device_id, operation_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                sealed.revision_id,
                sealed.stable_id,
                document,
                device_id,
                operation_id,
                sealed.created_at,
            ),
        )
        for parent in sealed.parent_revision_ids:
            connection.execute(
                "INSERT INTO revision_parent (revision_id, parent_revision_id) VALUES (?, ?)",
                (sealed.revision_id, parent),
            )
        # The parents this revision replaces stop being heads; a parent that was
        # not a head was already superseded and simply is not there to delete.
        for parent in sealed.parent_revision_ids:
            connection.execute(
                "DELETE FROM head WHERE stable_id = ? AND revision_id = ?",
                (sealed.stable_id, parent),
            )
        connection.execute(
            "INSERT OR IGNORE INTO head (stable_id, revision_id) VALUES (?, ?)",
            (sealed.stable_id, sealed.revision_id),
        )

    stored = get(connection, sealed.revision_id)
    assert stored is not None
    return stored


def store_snapshot(
    connection: sqlite3.Connection,
    content: dict[str, JsonValue],
    *,
    device_id: str,
    operation_id: str | None = None,
) -> StoredRevision:
    """Store an immutable version snapshot without changing the draft head."""
    sealed = seal_envelope(content)
    if sealed.parent_revision_ids:
        raise CliFailure("AI_STP_CONFLICT", "an immutable snapshot cannot name draft parents")
    document = canonize(cast(dict[str, JsonValue], sealed.model_dump(mode="json"))).decode("utf-8")
    with transaction(connection):
        known = get(connection, sealed.revision_id)
        if known is not None:
            return known
        entity = connection.execute(
            "SELECT kind FROM entity WHERE stable_id = ?", (sealed.stable_id,)
        ).fetchone()
        if entity is None or str(entity["kind"]) != sealed.kind:
            raise CliFailure("AI_STP_CONFLICT", "an immutable snapshot has no matching entity")
        connection.execute(
            "INSERT INTO revision "
            "(revision_id, stable_id, content, device_id, operation_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                sealed.revision_id,
                sealed.stable_id,
                document,
                device_id,
                operation_id,
                sealed.created_at,
            ),
        )
    stored = get(connection, sealed.revision_id)
    assert stored is not None
    return stored


def _validate_parents(connection: sqlite3.Connection, sealed: PassportEnvelope) -> None:
    """Every parent must exist and belong to the same entity.

    A dangling parent would make the graph unwalkable, and a parent from another
    entity would join two histories that describe different objects. Neither is
    something a later merge could untangle.
    """
    for parent in sealed.parent_revision_ids:
        row = connection.execute(
            "SELECT stable_id FROM revision WHERE revision_id = ?", (parent,)
        ).fetchone()
        if row is None:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "a parent revision is not in the local registry",
                details={"revision_id": parent},
            )
        if str(row["stable_id"]) != sealed.stable_id:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "a parent revision belongs to a different object",
                details={"revision_id": parent, "expected": sealed.stable_id},
            )
