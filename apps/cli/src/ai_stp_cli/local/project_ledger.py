"""Local cache of the organization project ledger, and the projection it accepts.

The API stores content-addressed project revisions. The CLI had link/plan/apply
and no way to put a revision in that ledger, so a `local_to_remote` plan was
unreachable: planning refuses a revision the organization has not already seen.
This module is the missing transport — push what the local passport may publish,
pull what another device already published, and remember both.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, cast

from ai_stp_cli.local import revisions
from ai_stp_contracts.context import (
    PROJECT_PROJECTION_FIELDS,
    ProjectRevisionPushRequest,
    ProjectRevisionPushResponse,
    ProjectRevisionView,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import is_valid_id

REVISION_DOMAIN: Final[str] = "ai-stp:revision:v1"
_DIGEST: Final[re.Pattern[str]] = re.compile(r"^sha256:[0-9a-f]{64}$")
PUSH_STATES: Final[frozenset[str]] = frozenset(
    {"pending", "accepted", "conflict", "rejected", "superseded", "failed", "unknown"}
)


@dataclass(frozen=True)
class CachedPush:
    """One durable attempt to publish a projection."""

    link_id: str
    organization_id: str
    event_id: str
    idempotency_key: str
    request: ProjectRevisionPushRequest
    state: str | None
    receipt: ProjectRevisionPushResponse | None


def is_revision_id(value: str) -> bool:
    """Whether a coordinate is a ledger revision rather than `initial`."""
    return _DIGEST.fullmatch(value) is not None


def projection_from_passport(
    stored: revisions.StoredRevision, *, remote_project_id: str
) -> dict[str, object]:
    """The allowlisted view of one local passport. Paths never leave."""
    document = stored.envelope.model_dump(mode="json")
    facts = cast(Mapping[str, object], document["facts"])
    projection: dict[str, object] = {
        "schema_version": 1,
        "kind": "project",
        "remote_project_id": remote_project_id,
        "index_digest": _digest_fact(facts, "index_digest"),
        "toolchain_digest": _digest_fact(facts, "toolchain_digest"),
        "configuration_digest": _digest_fact(facts, "configuration_digest"),
        "file_count": _int_fact(facts, "file_count"),
        "index_state": _text_fact(facts, "index_state"),
    }
    unknown = set(projection) - PROJECT_PROJECTION_FIELDS
    if unknown:
        raise ValueError("project projection contains fields outside the public allowlist")
    return projection


def signed_revision(
    *,
    remote_project_id: str,
    parent_revision_ids: list[str],
    operation: str,
    projection: dict[str, object],
) -> tuple[str, str]:
    """The revision id and content digest the server will recompute."""
    document: dict[str, object] = {
        "schema_version": 1,
        "remote_project_id": remote_project_id,
        "parent_revision_ids": list(parent_revision_ids),
        "operation": operation,
        "projection": dict(projection),
    }
    revision_id = digest_canonical(REVISION_DOMAIN, cast(JsonValue, document))
    content_digest = digest_canonical(REVISION_DOMAIN, cast(JsonValue, projection))
    return revision_id, content_digest


def cache_revision(
    connection: sqlite3.Connection,
    *,
    local_project_id: str,
    link_id: str,
    item: ProjectRevisionView,
    origin: str,
) -> None:
    """Remember one ledger node this device has seen."""
    if origin not in {"pushed", "pulled"}:
        raise ValueError("unknown project ledger origin")
    if not is_valid_id(local_project_id, "project"):
        raise ValueError("local project id is not valid")
    connection.execute(
        """
        INSERT INTO project_ledger_revision (
            revision_id, local_project_id, link_id, origin, view_json
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(local_project_id, revision_id) DO UPDATE SET
            link_id = excluded.link_id,
            origin = excluded.origin,
            view_json = excluded.view_json
        """,
        (item.revision_id, local_project_id, link_id, origin, item.model_dump_json()),
    )


def cached_revision(
    connection: sqlite3.Connection, *, local_project_id: str, revision_id: str
) -> ProjectRevisionView | None:
    """One cached ledger node, if this device has seen it."""
    row = connection.execute(
        "SELECT view_json FROM project_ledger_revision "
        "WHERE local_project_id = ? AND revision_id = ?",
        (local_project_id, revision_id),
    ).fetchone()
    if row is None:
        return None
    return ProjectRevisionView.model_validate_json(str(row[0]))


def begin_push(
    connection: sqlite3.Connection,
    *,
    local_project_id: str,
    link_id: str,
    organization_id: str,
    request: ProjectRevisionPushRequest,
) -> None:
    """Retain the exact request before it leaves this device.

    A key that already finished must not be rewritten into a second attempt.
    Retrying a pending or unknown send of the *same* bytes is the same
    operation; a different body under that key is the caller's to refuse.
    """
    if not is_valid_id(local_project_id, "project"):
        raise ValueError("local project id is not valid")
    if not is_valid_id(organization_id, "organization"):
        raise ValueError("organization id is not valid")
    connection.execute(
        """
        INSERT INTO project_ledger_push (
            local_project_id, link_id, organization_id, event_id, idempotency_key,
            request_json, state, receipt_json
        ) VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL)
        ON CONFLICT(local_project_id, idempotency_key) DO UPDATE SET
            state = 'pending'
        WHERE project_ledger_push.state IN ('pending', 'failed', 'unknown')
          AND project_ledger_push.request_json = excluded.request_json
          AND project_ledger_push.event_id = excluded.event_id
          AND project_ledger_push.link_id = excluded.link_id
          AND project_ledger_push.organization_id = excluded.organization_id
        """,
        (
            local_project_id,
            link_id,
            organization_id,
            request.event_id,
            request.idempotency_key,
            request.model_dump_json(),
        ),
    )


def mark_push(
    connection: sqlite3.Connection,
    *,
    local_project_id: str,
    idempotency_key: str,
    state: str,
) -> None:
    """Record how an attempt ended when no receipt arrived."""
    if state not in PUSH_STATES:
        raise ValueError("unknown project ledger push state")
    connection.execute(
        "UPDATE project_ledger_push SET state = ? "
        "WHERE local_project_id = ? AND idempotency_key = ?",
        (state, local_project_id, idempotency_key),
    )


def record_push(
    connection: sqlite3.Connection,
    *,
    local_project_id: str,
    idempotency_key: str,
    receipt: ProjectRevisionPushResponse,
) -> None:
    """Persist the server's receipt for a push that answered."""
    connection.execute(
        """
        UPDATE project_ledger_push SET state = ?, receipt_json = ?
        WHERE local_project_id = ? AND idempotency_key = ?
        """,
        (receipt.receipt.state, receipt.model_dump_json(), local_project_id, idempotency_key),
    )


def latest_accepted_revision(
    connection: sqlite3.Connection, *, local_project_id: str, link_id: str
) -> str | None:
    """The last ledger revision this device successfully published on the link."""
    row = connection.execute(
        """
        SELECT receipt_json FROM project_ledger_push
        WHERE local_project_id = ? AND link_id = ? AND state = 'accepted'
          AND receipt_json IS NOT NULL
        ORDER BY rowid DESC LIMIT 1
        """,
        (local_project_id, link_id),
    ).fetchone()
    if row is None:
        return None
    receipt = ProjectRevisionPushResponse.model_validate_json(str(row[0]))
    return receipt.receipt.revision_id


def cached_push(
    connection: sqlite3.Connection, *, local_project_id: str, idempotency_key: str
) -> CachedPush | None:
    """The last attempt this device recorded under one key."""
    row = connection.execute(
        """
        SELECT link_id, organization_id, event_id, idempotency_key,
               request_json, state, receipt_json
        FROM project_ledger_push
        WHERE local_project_id = ? AND idempotency_key = ?
        """,
        (local_project_id, idempotency_key),
    ).fetchone()
    if row is None:
        return None
    receipt = (
        None if row[6] is None else ProjectRevisionPushResponse.model_validate_json(str(row[6]))
    )
    return CachedPush(
        link_id=str(row[0]),
        organization_id=str(row[1]),
        event_id=str(row[2]),
        idempotency_key=str(row[3]),
        request=ProjectRevisionPushRequest.model_validate_json(str(row[4])),
        state=None if row[5] is None else str(row[5]),
        receipt=receipt,
    )


def _digest_fact(facts: Mapping[str, object], name: str) -> str:
    value = _fact(facts, name)
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"passport fact {name} is not a digest")
    return value


def _int_fact(facts: Mapping[str, object], name: str) -> int:
    value = _fact(facts, name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"passport fact {name} is not a count")
    return value


def _text_fact(facts: Mapping[str, object], name: str) -> str:
    value = _fact(facts, name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"passport fact {name} is not text")
    return value


def _fact(facts: Mapping[str, object], name: str) -> object:
    held: object | None = facts.get(name)
    if not isinstance(held, dict):
        return held
    nested = cast(dict[str, object], held)
    if "value" in nested:
        return nested["value"]
    return nested
