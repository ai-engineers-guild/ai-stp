"""Immutable bytes, addressed by their own digest (`#159`, `SPEC-005` REQ-503).

The name is the proof. A row lives at its digest, so a lookup cannot be answered
with different bytes and storing the same bytes twice is refused by a primary
key rather than by a check somebody has to remember to write. Nothing here
updates a row: there is no statement in this module that could, which is a
stronger guarantee about immutability than a rule stating it.

Bytes rather than text. What an author wrote is whatever they wrote — a binary
plugin, a file in an encoding nobody declared — and `TEXT` would assert UTF-8
that SQLite cannot enforce on the way in.
"""

import hashlib as _hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ai_stp_cli.errors import CliFailure
from ai_stp_foundation.digests import digest_bytes

#: The domain these bytes are hashed in. `artifact` because that is what they
#: are: the exact content of one published or draft object.
CONTENT_DOMAIN: Final[str] = "ai-stp:artifact:v1"

#: The largest object the local store accepts. A setup component is a file a
#: person wrote; something larger is a mistake worth refusing before it fills a
#: user's disk in a table they did not know existed.
MAX_CONTENT_BYTES: Final[int] = 64 * 1024 * 1024


@dataclass(frozen=True)
class Stored:
    """One immutable object in the local store."""

    digest: str
    byte_length: int
    stored_at: str


def put(connection: sqlite3.Connection, payload: bytes, *, at: str) -> Stored:
    """Store bytes and return their address. Storing the same bytes twice is free.

    Deduplication needs no check and no comparison: identical bytes hash to an
    identical digest, and the primary key refuses the second insert. `ON
    CONFLICT DO NOTHING` expresses exactly that — the row that is already there
    is by construction the row that would have been written.
    """
    if len(payload) > MAX_CONTENT_BYTES:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the object is larger than the local store accepts",
            details={"bytes": str(len(payload)), "limit": str(MAX_CONTENT_BYTES)},
        )
    digest = address_of(payload)
    connection.execute(
        """
        INSERT INTO content (digest, bytes, byte_length, stored_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (digest) DO NOTHING
        """,
        (digest, payload, len(payload), at),
    )
    row = connection.execute(
        "SELECT digest, byte_length, stored_at FROM content WHERE digest = ?", (digest,)
    ).fetchone()
    return Stored(str(row["digest"]), int(row["byte_length"]), str(row["stored_at"]))


def get(connection: sqlite3.Connection, digest: str) -> bytes:
    """Read bytes back, and prove on the way out that they are still those bytes.

    Re-hashed even though the address was computed on the way in. Between then
    and now the row has been at rest in a file the CLI does not own — one a
    backup could restore over, a sync could touch, or a disk could corrupt — and
    the check costs one hash of something already in memory.
    """
    row = connection.execute("SELECT bytes FROM content WHERE digest = ?", (digest,)).fetchone()
    if row is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no object is stored at that address",
            details={"digest": digest},
        )
    payload = bytes(row["bytes"])
    found = address_of(payload)
    if found != digest:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the stored object no longer matches the address it is filed under",
            details={"expected": digest, "found": found},
        )
    return payload


def address_of(payload: bytes) -> str:
    """The address these bytes would have, without storing them.

    Separate from `put` because a plan has to name what it would write before it
    writes it, and computing the address is the only part of that which is safe
    to do twice.
    """
    return digest_bytes(CONTENT_DOMAIN, payload)


def address_of_file(place: Path, *, chunk: int = 1024 * 1024) -> tuple[str, int]:
    """The address of a file's bytes and its length, without holding them.

    For a subject too large to allocate. `REQ-841` says an oversized file is
    read and hashed, and it is — the change is that "read" no longer means
    "read into one object". A harness root can hold a multi-gigabyte cache blob
    that the import plan hashes only to record that it was seen and excluded,
    and doing that through `read_bytes` allocated the whole thing first.
    """
    digest = _hashlib.sha256(CONTENT_DOMAIN.encode("ascii") + b"\x00")
    length = 0
    with place.open("rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            length += len(block)
            digest.update(block)
    return f"sha256:{digest.hexdigest()}", length
