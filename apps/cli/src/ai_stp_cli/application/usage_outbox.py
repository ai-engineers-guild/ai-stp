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

import json
import sqlite3
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Final, Literal

from ai_stp_cli.paths import data_dir

#: Bounds, stated once: a disconnected device cannot grow an unbounded queue,
#: and an event too old to matter becomes `dead` instead of a surprise upload.
MAX_ROWS: Final[int] = 4096
MAX_AGE_SECONDS: Final[float] = 30 * 24 * 3600
MAX_ATTEMPTS: Final[int] = 8
FLUSH_BATCH: Final[int] = 64

EnqueueResult = Literal["queued", "duplicate", "full"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_outbox (
    event_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    enqueued_at REAL NOT NULL,
    next_attempt_at REAL NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT ''
)
"""


def default_path() -> Path:
    return data_dir() / "runtime-usage-outbox.sqlite3"


def connect(path: Path | None = None) -> sqlite3.Connection:
    location = path if path is not None else default_path()
    location.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(location))
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(_SCHEMA)
    return connection


def enqueue(
    connection: sqlite3.Connection,
    event_id: str,
    payload: Mapping[str, object],
    *,
    now: float | None = None,
) -> EnqueueResult:
    """Buffer one event. Duplicates are no-ops; a full outbox refuses."""
    moment = time.time() if now is None else now
    row = connection.execute(
        "SELECT state FROM usage_outbox WHERE event_id = ?", (event_id,)
    ).fetchone()
    if row is not None:
        return "duplicate"
    held = connection.execute("SELECT count(*) FROM usage_outbox").fetchone()[0]
    if held >= MAX_ROWS:
        return "full"
    connection.execute(
        "INSERT INTO usage_outbox (event_id, payload, enqueued_at) VALUES (?, ?, ?)",
        (event_id, json.dumps(dict(payload), sort_keys=True), moment),
    )
    connection.commit()
    return "queued"


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


def mark_sent(connection: sqlite3.Connection, event_id: str) -> None:
    """Accepted or duplicate server-side: either way the fact is durable."""
    connection.execute("DELETE FROM usage_outbox WHERE event_id = ?", (event_id,))
    connection.commit()


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
    send: Callable[[list[dict[str, object]]], None],
    *,
    now: float | None = None,
) -> tuple[int, int]:
    """Drain due events through `send`; returns (sent, remaining).

    `send` takes a whole batch and raises on failure. A raised batch marks
    every member failed once and stops the drain - a server that refused one
    request gets no more this round.
    """
    moment = time.time() if now is None else now
    sent = 0
    while True:
        batch = due(connection, now=moment)
        if not batch:
            break
        try:
            send([payload for _, payload in batch])
        except Exception as error:
            for event_id, _ in batch:
                mark_failed(connection, event_id, error=type(error).__name__, now=moment)
            break
        for event_id, _ in batch:
            mark_sent(connection, event_id)
        sent += len(batch)
    remaining = connection.execute(
        "SELECT count(*) FROM usage_outbox WHERE state = 'pending'"
    ).fetchone()[0]
    return sent, remaining
