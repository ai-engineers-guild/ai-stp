"""The exact set of plans one setup's publication needs, held between two commands.

`setup publish plan` creates server plans; `setup publish confirm` confirms them.
Nothing can recompute the first from the second — a plan id exists only because
a plan was created — so the set is written down here in between, the same way
`report_plans` holds an exact report preview for the confirm that follows it.

What is stored is the decision, not a cache: `set_digest` covers every member in
confirmation order, and confirming a digest is confirming exactly that graph.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, cast

from ai_stp_contracts.machine_help import PublicationSetMemberView
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical

#: Separate from `ai-stp:plan:v1`: a set is a different kind of decision, and
#: two domains keep one digest from ever being mistaken for the other.
DIGEST_DOMAIN: Final[str] = "ai-stp:publication-set:v1"

#: Planned, and nothing confirmed yet.
STATE_PLANNED: Final[str] = "planned"
#: Confirmation stopped part-way. Resumable: what published stays published.
STATE_PARTIAL: Final[str] = "partial"
#: Every member is public.
STATE_PUBLISHED: Final[str] = "published"


@dataclass(frozen=True)
class StoredSet:
    """One reviewed publication set, exactly as it was planned."""

    set_digest: str
    setup_stable_id: str
    setup_version: str
    account_id: str
    device_id: str
    members: tuple[PublicationSetMemberView, ...]
    state: str
    created_at: str


def set_digest(members: Sequence[PublicationSetMemberView]) -> str:
    """The digest that identifies this exact graph, in this exact order.

    Only the fields a decision turns on: what is being published, at which
    version, under which plan. Deliberately not `state` — a member moving from
    `draft` to `ready` while the operator reads the plan is not a different
    decision, and a digest that changed underneath them would make confirming
    impossible rather than safe.
    """
    document: list[JsonValue] = [
        {
            "role": member.role,
            "object_kind": member.object_kind,
            "stable_id": member.stable_id,
            "version": member.version,
            "plan_hash": member.plan_hash,
            "already_published": member.already_published,
        }
        for member in members
    ]
    return digest_canonical(DIGEST_DOMAIN, cast(JsonValue, document))


def record(
    connection: sqlite3.Connection,
    *,
    setup_stable_id: str,
    setup_version: str,
    account_id: str,
    device_id: str,
    members: Sequence[PublicationSetMemberView],
    at: str,
) -> StoredSet:
    """Write this set, or return the identical one already held.

    Idempotent by digest: planning twice without anything changing is the same
    decision, and returning a second row for it would let an operator confirm a
    set the other half of their session had already superseded.
    """
    digest = set_digest(members)
    held = get(connection, digest)
    if held is not None:
        return held
    # An open set for the same exact version is the same decision, replanned.
    # It is replaced rather than kept beside the new one: two open sets for one
    # setup version differ only in which is stale, and nothing on the wire says
    # which.
    connection.execute(
        "DELETE FROM setup_publication_set "
        "WHERE account_id = ? AND setup_stable_id = ? AND setup_version = ? AND state != ?",
        (account_id, setup_stable_id, setup_version, STATE_PUBLISHED),
    )
    connection.execute(
        "INSERT INTO setup_publication_set "
        "(set_digest, setup_stable_id, setup_version, account_id, device_id, "
        "members_json, state, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            digest,
            setup_stable_id,
            setup_version,
            account_id,
            device_id,
            json.dumps([member.model_dump(mode="json") for member in members]),
            STATE_PLANNED,
            at,
        ),
    )
    connection.commit()
    return StoredSet(
        set_digest=digest,
        setup_stable_id=setup_stable_id,
        setup_version=setup_version,
        account_id=account_id,
        device_id=device_id,
        members=tuple(members),
        state=STATE_PLANNED,
        created_at=at,
    )


def get(connection: sqlite3.Connection, digest: str) -> StoredSet | None:
    row = connection.execute(
        "SELECT * FROM setup_publication_set WHERE set_digest = ?", (digest,)
    ).fetchone()
    return None if row is None else _stored(row)


def settle(
    connection: sqlite3.Connection,
    digest: str,
    *,
    members: Sequence[PublicationSetMemberView],
    state: str,
) -> StoredSet:
    """Record what confirmation actually achieved, member by member.

    Written even when confirmation stopped part-way, and especially then: the
    members already published are public whatever happens next, and a set that
    forgot them would offer to publish them again.
    """
    connection.execute(
        "UPDATE setup_publication_set SET members_json = ?, state = ? WHERE set_digest = ?",
        (json.dumps([member.model_dump(mode="json") for member in members]), state, digest),
    )
    connection.commit()
    held = get(connection, digest)
    if held is None:  # pragma: no cover - the row was read moments earlier
        raise LookupError(digest)
    return held


def _stored(row: sqlite3.Row) -> StoredSet:
    raw = cast(list[dict[str, object]], json.loads(str(row["members_json"])))
    return StoredSet(
        set_digest=str(row["set_digest"]),
        setup_stable_id=str(row["setup_stable_id"]),
        setup_version=str(row["setup_version"]),
        account_id=str(row["account_id"]),
        device_id=str(row["device_id"]),
        members=tuple(PublicationSetMemberView.model_validate(item) for item in raw),
        state=str(row["state"]),
        created_at=str(row["created_at"]),
    )
