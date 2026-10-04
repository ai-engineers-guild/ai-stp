"""The bounded local outbox for corporate runtime usage events.

A separate SQLite file under the data dir, owned whole by this module: the
shared local database is outside this stream's boundary, and an outbox that
shares someone else's schema versioning is an outbox someone else's migration
can break.

Semantics, per the pinned seam contract:

- deduplication on the event/correlation key across buffering and retries
  (`event_id` is the primary key; a repeat enqueue is a no-op);
- retry with backoff and a bounded attempt count, then `dead`;
- a bounded store: `MAX_ROWS` rows and `MAX_AGE_SECONDS`, both fail-closed -
  in a mandatory-telemetry posture a full outbox blocks the next invocation
  rather than dropping silently;
- payloads are the closed-field JSON documents only. The outbox never sees a
  prompt, an argument, or a path.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Final, Literal

from ai_stp_cli.local import database
from ai_stp_cli.paths import data_dir
from ai_stp_contracts.runtime_usage import RuntimeUsageIngestResult

#: Bounds, stated once: a disconnected device cannot grow an unbounded queue,
#: and an event too old to matter becomes `dead` instead of a surprise upload.
MAX_ROWS: Final[int] = 4096
MAX_AGE_SECONDS: Final[float] = 30 * 24 * 3600
MAX_ATTEMPTS: Final[int] = 8
FLUSH_BATCH: Final[int] = 64

EnqueueResult = Literal["queued", "duplicate", "full", "dropped"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_outbox (
    event_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    enqueued_at REAL NOT NULL,
    next_attempt_at REAL NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS usage_collection_policy (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled INTEGER NOT NULL,
    registration_required INTEGER NOT NULL
)
"""


def default_path() -> Path:
    return data_dir() / "runtime-usage-outbox.sqlite3"


def scoped_path(account_id: str, organization_id: str) -> Path:
    """Keep each authenticated account and organization in its own queue."""
    digest = hashlib.sha256(f"{account_id}\0{organization_id}".encode()).hexdigest()
    return data_dir() / f"runtime-usage-outbox-{digest}.sqlite3"


def connect(path: Path | None = None) -> sqlite3.Connection:
    location = path if path is not None else default_path()
    location.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(location), factory=database.Connection)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(_SCHEMA)
    return connection


def save_policy(connection: sqlite3.Connection, *, enabled: bool, required: bool) -> None:
    """Cache the authenticated organization policy for offline invocation checks."""
    connection.execute(
        "INSERT INTO usage_collection_policy (id, enabled, registration_required) "
        "VALUES (1, ?, ?) ON CONFLICT (id) DO UPDATE SET "
        "enabled = excluded.enabled, registration_required = excluded.registration_required",
        (enabled, required),
    )
    connection.commit()


def cached_policy(connection: sqlite3.Connection) -> tuple[bool, bool] | None:
    row = connection.execute(
        "SELECT enabled, registration_required FROM usage_collection_policy WHERE id = 1"
    ).fetchone()
    return None if row is None else (bool(row[0]), bool(row[1]))


def enqueue(
    connection: sqlite3.Connection,
    event_id: str,
    payload: Mapping[str, object],
    *,
    now: float | None = None,
) -> EnqueueResult:
    """Buffer one invocation, promoting a matching fallback to native evidence."""
    moment = time.time() if now is None else now
    encoded = json.dumps(dict(payload), sort_keys=True)
    with database.transaction(connection):
        inserted = connection.execute(
            "INSERT INTO usage_outbox (event_id, payload, enqueued_at) "
            "SELECT ?, ?, ? WHERE (SELECT count(*) FROM usage_outbox) < ? "
            "ON CONFLICT (event_id) DO NOTHING",
            (event_id, encoded, moment, MAX_ROWS),
        )
        if inserted.rowcount:
            return "queued"
        row = connection.execute(
            "SELECT payload FROM usage_outbox WHERE event_id = ?", (event_id,)
        ).fetchone()
        if row is None:
            return "full"
        previous = json.loads(row[0])
        evidence_fields = {"source", "outcome", "invoked_at"}
        if {key: value for key, value in previous.items() if key not in evidence_fields} != {
            key: value for key, value in payload.items() if key not in evidence_fields
        }:
            return "dropped"
        if previous.get("source") == "agent_reported" and payload.get("source") == "native_hook":
            connection.execute(
                "UPDATE usage_outbox SET payload = ?, state = 'pending', attempts = 0, "
                "next_attempt_at = 0, last_error = '' WHERE event_id = ?",
                (encoded, event_id),
            )
        return "duplicate"


def due(
    connection: sqlite3.Connection,
    *,
    now: float | None = None,
    limit: int = FLUSH_BATCH,
) -> list[tuple[str, dict[str, object]]]:
    """The pending events whose backoff has elapsed, oldest first."""
    moment = time.time() if now is None else now
    expire(connection, now=moment)
    rows = connection.execute(
        "SELECT event_id, payload FROM usage_outbox "
        "WHERE state = 'pending' AND next_attempt_at <= ? "
        "ORDER BY enqueued_at LIMIT ?",
        (moment, limit),
    ).fetchall()
    return [(row[0], json.loads(row[1])) for row in rows]


def mark_sent(connection: sqlite3.Connection, event_id: str, payload: Mapping[str, object]) -> int:
    """A receipt acknowledges only the bytes sent, not a concurrent promotion."""
    deleted = connection.execute(
        "DELETE FROM usage_outbox WHERE event_id = ? AND payload = ?",
        (event_id, json.dumps(dict(payload), sort_keys=True)),
    )
    connection.commit()
    return deleted.rowcount


def mark_failed(
    connection: sqlite3.Connection,
    event_id: str,
    *,
    error: str = "",
    now: float | None = None,
) -> None:
    """Back off exponentially; after `MAX_ATTEMPTS` the event is `dead`."""
    moment = time.time() if now is None else now
    row = connection.execute(
        "SELECT attempts FROM usage_outbox WHERE event_id = ?", (event_id,)
    ).fetchone()
    if row is None:
        return
    attempts = row[0] + 1
    if attempts >= MAX_ATTEMPTS:
        connection.execute(
            "UPDATE usage_outbox SET state = 'dead', attempts = ?, last_error = ? "
            "WHERE event_id = ?",
            (attempts, error[:200], event_id),
        )
    else:
        delay = min(60.0 * (2 ** (attempts - 1)), 24 * 3600)
        connection.execute(
            "UPDATE usage_outbox SET attempts = ?, next_attempt_at = ?, last_error = ? "
            "WHERE event_id = ?",
            (attempts, moment + delay, error[:200], event_id),
        )
    connection.commit()


def expire(connection: sqlite3.Connection, *, now: float | None = None) -> int:
    """Events past `MAX_AGE_SECONDS` become dead rather than sent late."""
    moment = time.time() if now is None else now
    cursor = connection.execute(
        "UPDATE usage_outbox SET state = 'dead', last_error = 'expired' "
        "WHERE state = 'pending' AND enqueued_at < ?",
        (moment - MAX_AGE_SECONDS,),
    )
    connection.commit()
    return cursor.rowcount


def stats(connection: sqlite3.Connection) -> dict[str, int | float | None]:
    pending = connection.execute(
        "SELECT count(*) FROM usage_outbox WHERE state = 'pending'"
    ).fetchone()[0]
    dead = connection.execute("SELECT count(*) FROM usage_outbox WHERE state = 'dead'").fetchone()[
        0
    ]
    oldest = connection.execute(
        "SELECT min(enqueued_at) FROM usage_outbox WHERE state = 'pending'"
    ).fetchone()[0]
    return {
        "pending": pending,
        "dead": dead,
        "capacity": MAX_ROWS,
        "oldest_pending_at": oldest,
    }


def flush(
    connection: sqlite3.Connection,
    send: Callable[[list[dict[str, object]]], RuntimeUsageIngestResult],
    *,
    now: float | None = None,
) -> tuple[int, int]:
    """Drain due events through `send`; returns (sent, remaining).

    `send` takes a whole batch and raises on failure. A raised batch marks
    every member failed once and stops the drain - a server that refused one
    request gets no more this round.
    """
    policy = cached_policy(connection)
    if policy is not None and not policy[0]:
        remaining = connection.execute(
            "SELECT count(*) FROM usage_outbox WHERE state = 'pending'"
        ).fetchone()[0]
        return 0, remaining
    moment = time.time() if now is None else now
    sent = 0
    while True:
        batch = due(connection, now=moment)
        if not batch:
            break
        try:
            result = send([payload for _, payload in batch])
        except Exception as error:
            for event_id, _ in batch:
                mark_failed(connection, event_id, error=type(error).__name__, now=moment)
            break
        ids = {event_id for event_id, _ in batch}
        confirmed = set(result.accepted_ids) | set(result.duplicate_ids)
        rejected = set(result.rejected_ids)
        if (
            confirmed & rejected
            or confirmed | rejected != ids
            or result.accepted + result.duplicates + result.rejected != len(ids)
            or len(result.accepted_ids) != result.accepted
            or len(result.duplicate_ids) != result.duplicates
            or len(result.rejected_ids) != result.rejected
        ):
            for event_id in ids:
                mark_failed(connection, event_id, error="invalid_receipt", now=moment)
            break
        sent_payloads = dict(batch)
        for event_id in confirmed:
            sent += mark_sent(connection, event_id, sent_payloads[event_id])
        for event_id in rejected:
            mark_failed(connection, event_id, error="rejected", now=moment)
        if rejected:
            break
    remaining = connection.execute(
        "SELECT count(*) FROM usage_outbox WHERE state = 'pending'"
    ).fetchone()[0]
    return sent, remaining
