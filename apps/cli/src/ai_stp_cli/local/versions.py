"""Immutable `X.Y` versions and forks (`#160`, `SPEC-005` REQ-503 to REQ-524).

Four rules, and each one is arranged so that breaking it is difficult rather
than forbidden.

**A number is never reused.** REQ-504 says one `X.Y` cannot stand for two
different hashes, and the primary key `(stable_id, version)` says it too. Writing
the same number with a different digest fails in the schema, on every path,
including ones written later by someone who did not read this file.

**Minor numbering is deterministic.** REQ-506 makes any change of composition,
exact reference or materialised overlay the next minor version. "Next" is
computed from what is stored — the highest minor in the current major, plus one
— so two machines with the same history propose the same number, and a proposal
is never a guess about what a user meant.

**Major is a decision, not a computation.** REQ-507 requires an explicit user
decision and creates a separate access boundary. So `next_major` refuses without
one instead of defaulting to a value; there is no argument shape here that lets
a caller bump a major line by accident.

**A fork copies, and the original is untouched.** REQ-521 gives the copy a new
identity, the recipient as owner and private visibility, and records where it
came from — on the copy, because writing anything on the original would be
changing an object the recipient does not own. REQ-522 to REQ-524 then govern
publishing a derivative, and those refusals are the whole of `publishable`.
"""

import sqlite3
from dataclasses import dataclass
from typing import Final

from ai_stp_cli.errors import CliFailure
from ai_stp_foundation.digests import is_digest
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.versioning import VersionError, format_version, parse_version

#: The first version of anything. `1.0` rather than `0.1`: a published version is
#: immutable and usable, and a leading zero is a convention for "not yet", which
#: is what a draft is for.
FIRST_VERSION: Final[str] = "1.0"


@dataclass(frozen=True)
class Recorded:
    """One immutable version of one logical object."""

    stable_id: str
    version: str
    major: int
    minor: int
    passport_digest: str
    revision_id: str
    created_at: str


@dataclass(frozen=True)
class Fork:
    """Where a forked object came from. Held by the copy, never the original."""

    stable_id: str
    source_stable_id: str
    source_version: str
    source_digest: str
    created_at: str


@dataclass(frozen=True)
class Verdict:
    """Whether a derivative may be published, and if not, exactly why."""

    allowed: bool
    reason: str


def record(
    connection: sqlite3.Connection,
    *,
    stable_id: str,
    version: str,
    passport_digest: str,
    revision_id: str,
    at: str,
) -> Recorded:
    """Store one immutable version, or refuse to overwrite a number (`REQ-504`).

    Recording the same number with the same digest is a no-op that returns what
    is already there: that is a replay, not a conflict. With a *different*
    digest it is refused, because the number would then stand for two things and
    every exact reference to it would be ambiguous.
    """
    try:
        major, minor = parse_version(version)
    except VersionError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            f"a published version must be X.Y: {version}",
            details={"version": version},
        ) from error

    # A digest in the wrong form is not a near miss. An exact reference names a
    # version *and* its content, and a version recorded under something that is
    # not a digest can never be referenced exactly — the closure resolver would
    # report it as floating, far from here and long after the mistake. A
    # revision id is the value most likely to arrive by accident: it is a hash
    # of the same bytes in a different domain, and it is always to hand.
    if not is_digest(passport_digest):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a version is recorded under its passport digest, not under another identifier",
            details={"stable_id": stable_id, "version": version, "given": passport_digest},
            next_actions=["component version release --id <stable_id> --json"],
        )

    existing = held(connection, stable_id, version)
    if existing is not None:
        if existing.passport_digest == passport_digest:
            return existing
        raise CliFailure(
            "AI_STP_CONFLICT",
            f"version {version} already stands for different content",
            details={
                "stable_id": stable_id,
                "version": version,
                "recorded": existing.passport_digest,
                "offered": passport_digest,
            },
            next_actions=["registry version next --id <stable_id>"],
        )

    connection.execute(
        """
        INSERT INTO object_version
            (stable_id, version, major, minor, passport_digest, revision_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (stable_id, version, major, minor, passport_digest, revision_id, at),
    )
    found = held(connection, stable_id, version)
    if found is None:  # pragma: no cover - the insert above guarantees a row
        raise CliFailure("AI_STP_INTERNAL", "the version vanished after being written")
    return found


def held(connection: sqlite3.Connection, stable_id: str, version: str) -> Recorded | None:
    """One recorded version, if it exists."""
    row = connection.execute(
        "SELECT * FROM object_version WHERE stable_id = ? AND version = ?", (stable_id, version)
    ).fetchone()
    return None if row is None else _decode(row)


def line(
    connection: sqlite3.Connection, stable_id: str, major: int | None = None
) -> tuple[Recorded, ...]:
    """Every recorded version, newest last. One major line when one is named."""
    if major is None:
        rows = connection.execute(
            "SELECT * FROM object_version WHERE stable_id = ? ORDER BY major, minor",
            (stable_id,),
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT * FROM object_version WHERE stable_id = ? AND major = ? ORDER BY minor",
            (stable_id, major),
        ).fetchall()
    return tuple(_decode(row) for row in rows)


def next_minor(connection: sqlite3.Connection, stable_id: str, *, major: int | None = None) -> str:
    """The next minor version in a major line (`REQ-506`).

    Computed from what is stored rather than from what was last proposed, so two
    machines with the same history answer the same thing and a proposal made
    twice does not drift. An object with nothing recorded starts at `1.0`.
    """
    recorded = line(connection, stable_id)
    if not recorded:
        return FIRST_VERSION
    wanted = max(item.major for item in recorded) if major is None else major
    within = [item for item in recorded if item.major == wanted]
    if not within:
        # A major line the user opened but has not filled yet starts at `.0`.
        return format_version(wanted, 0)
    return format_version(wanted, max(item.minor for item in within) + 1)


def next_major(connection: sqlite3.Connection, stable_id: str, *, decided: bool) -> str:
    """The first version of the next major line, only on an explicit decision.

    `REQ-507` makes this a user decision that creates a separate access
    boundary, so the flag is required and false is a refusal rather than a
    default. Computing it silently is how a minor change becomes a new access
    boundary nobody chose.
    """
    if not decided:
        raise CliFailure(
            "AI_STP_USER_DECISION_REQUIRED",
            "a new major line needs the user's explicit decision",
            details={"stable_id": stable_id},
            next_actions=["registry version next --id <stable_id> --major --confirm"],
        )
    recorded = line(connection, stable_id)
    highest = max((item.major for item in recorded), default=0)
    return format_version(highest + 1, 0)


def fork(
    connection: sqlite3.Connection,
    *,
    source_stable_id: str,
    source_version: str,
    source_digest: str,
    kind: str,
    at: str,
) -> Fork:
    """Copy an object under a new identity, leaving the original alone (`REQ-521`).

    The new entity is created here and its provenance recorded on it. Nothing
    touches the source: a fork is a statement the recipient makes about their
    own object, and a recipient cannot write to something they do not own.
    """
    if kind not in {"component", "setup"}:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "only a component or a setup can be forked",
            details={"kind": kind},
        )
    stable_id = new_id(kind)
    connection.execute(
        "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, ?, ?)",
        (stable_id, kind, at),
    )
    connection.execute(
        """
        INSERT INTO fork_origin
            (stable_id, source_stable_id, source_version, source_digest, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (stable_id, source_stable_id, source_version, source_digest, at),
    )
    found = forked_from(connection, stable_id)
    if found is None:  # pragma: no cover - the insert above guarantees a row
        raise CliFailure("AI_STP_INTERNAL", "the fork record vanished after being written")
    return found


def forked_from(connection: sqlite3.Connection, stable_id: str) -> Fork | None:
    """Where this object was forked from, if it was."""
    row = connection.execute(
        "SELECT * FROM fork_origin WHERE stable_id = ?", (stable_id,)
    ).fetchone()
    if row is None:
        return None
    return Fork(
        stable_id=str(row["stable_id"]),
        source_stable_id=str(row["source_stable_id"]),
        source_version=str(row["source_version"]),
        source_digest=str(row["source_digest"]),
        created_at=str(row["created_at"]),
    )


def publishable(
    connection: sqlite3.Connection,
    stable_id: str,
    *,
    passport_digest: str,
    public: bool,
    included_public: bool = True,
    licences_permit: bool | None = True,
) -> Verdict:
    """Whether a derivative may be published (`REQ-522` to `REQ-524`).

    Three refusals, in the order that makes each one meaningful.

    An unmodified clone is refused first (REQ-522): republishing someone else's
    object under a new namespace is the case the whole rule exists for, and it
    is decided by comparing the digest to the source's, which is exact.

    A public derivative then needs every included byte and reference to be
    public or the recipient's own (REQ-524). And a distribution right nobody
    knows is a refusal, not a maybe: `licences_permit=None` means unknown, and
    the closed answer is the safe one when the alternative is distributing
    something we were not allowed to.
    """
    origin = forked_from(connection, stable_id)
    if origin is not None and origin.source_digest == passport_digest:
        return Verdict(
            False,
            "an unmodified clone is not published under a new namespace; "
            "change the composition, the passport or the included bytes first",
        )
    if not public:
        return Verdict(True, "a private derivative needs no distribution right")
    if not included_public:
        return Verdict(
            False,
            "a public derivative needs every included byte and reference to be public or your own",
        )
    if licences_permit is None:
        return Verdict(
            False, "the distribution right is unknown, which is refused rather than assumed"
        )
    if not licences_permit:
        return Verdict(False, "an applicable licence does not permit distribution")
    return Verdict(True, "modified, and every included byte and licence permits distribution")


def _decode(row: sqlite3.Row) -> Recorded:
    return Recorded(
        stable_id=str(row["stable_id"]),
        version=str(row["version"]),
        major=int(row["major"]),
        minor=int(row["minor"]),
        passport_digest=str(row["passport_digest"]),
        revision_id=str(row["revision_id"]),
        created_at=str(row["created_at"]),
    )
