"""Durable consent to unverified objects (`docs/contracts/unverified-consent.md`).

Publisher and object-major records compare a stored capability fingerprint to
what the candidate needs now. Task authority is a different question: under an
authorized full-auto profile (`ADR-0150`) the agent does not collect a fresh
grant per object or capability expansion. The object stays `experimental`.

Three scopes and no fourth. There is still no "everything unverified, forever":
the removed `search.include_unverified` config key was exactly that, and a
wildcard target under `task` would restore it under another name. `task` names
one authorized profile (`full-auto`), is revocable, and loses to a narrower
exclusion. `SCOPES` is closed and an unknown scope is refused.

Consent never promotes anything. A covered candidate appears in the
`experimental` lane and nowhere else — it does not become `authoritative`, it
does not gain a platform confirmation, and it does not skip an install check.
Nothing in this module can express otherwise, which is the point of it not
returning a trust lane.
"""

import json
import sqlite3
from dataclasses import dataclass
from typing import Final, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_foundation.canonical import JsonValue, canonize

#: The three forms of durable record the contract defines. Closed on purpose.
SCOPE_PUBLISHER: Final[str] = "publisher"
SCOPE_OBJECT_MAJOR: Final[str] = "object_major"
SCOPE_TASK: Final[str] = "task"
SCOPES: Final[frozenset[str]] = frozenset({SCOPE_PUBLISHER, SCOPE_OBJECT_MAJOR, SCOPE_TASK})

#: The only `task` target. Any other string would be a wildcard by another name.
TASK_PROFILE_FULL_AUTO: Final[str] = "full-auto"

#: What a fingerprint records, in the contract's own terms: the permissions and
#: capabilities a candidate needed when the user agreed. Declared as a closed
#: set so a fingerprint cannot quietly start carrying something else — such as a
#: value the record is forbidden to hold.
FINGERPRINT_FIELDS: Final[tuple[str, ...]] = (
    "file_permissions",
    "network_permissions",
    "process_permissions",
    "credential_requirements",
    "external_endpoints",
    "managed_paths",
    "native_surfaces",
)


@dataclass(frozen=True)
class Record:
    """One durable consent, and the shape the candidate had when it was given."""

    consent_id: str
    scope: str
    target: str
    fingerprint: dict[str, JsonValue]

    #: The objects whose capabilities the fingerprint was taken from, at the
    #: moment of consent. Empty is a distinct fact from "they needed nothing":
    #: a record made before any covered object existed has observed no shape,
    #: and `covers` refuses it rather than treating an empty ceiling as a
    #: ceiling. The contract asks for the fingerprint *of the candidate*, so a
    #: record with no candidate behind it is incomplete, not permissive.
    observed: tuple[str, ...]

    decided_by: str
    origin: str
    created_at: str
    revoked_at: str | None

    @property
    def active(self) -> bool:
        return self.revoked_at is None


@dataclass(frozen=True)
class Verdict:
    """Whether a record still covers a candidate, and if not, exactly why."""

    covered: bool
    reason: str

    #: Which fields now ask for more than the fingerprint recorded. Named rather
    #: than counted: the contract requires the user be shown the exact cause,
    #: and "something changed" is not a cause.
    changed: tuple[str, ...] = ()


def fingerprint_of(capabilities: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Reduce a candidate's capabilities to the fields a fingerprint records.

    Built by naming the fields rather than by copying and deleting. The record
    is forbidden to hold secrets or environment values, and a whitelist cannot
    carry something nobody listed — a blacklist has to be right about every
    field that has not been invented yet.
    """
    return {name: capabilities.get(name, []) for name in FINGERPRINT_FIELDS}


def grant(
    connection: sqlite3.Connection,
    *,
    consent_id: str,
    scope: str,
    target: str,
    fingerprint: dict[str, JsonValue],
    observed: tuple[str, ...],
    decided_by: str,
    origin: str,
    at: str,
) -> Record:
    """Record a durable consent, or replace the one already covering this target.

    Re-granting the same target overwrites rather than adding a second row: two
    records for one target would make "which fingerprint applies" a question
    with two answers, and the safe one would not always be the one read.
    """
    if scope not in SCOPES:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "that consent scope is not one this contract defines",
            details={"scope": scope, "allowed": ", ".join(sorted(SCOPES))},
        )
    if not target:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a consent record must name what it covers",
            details={"scope": scope},
        )
    if scope == SCOPE_TASK and target != TASK_PROFILE_FULL_AUTO:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "that task profile is not one this contract defines",
            details={"target": target, "allowed": TASK_PROFILE_FULL_AUTO},
        )
    connection.execute(
        """
        INSERT INTO consent
            (consent_id, scope, target, fingerprint, observed,
             decided_by, origin, created_at, revoked_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
        ON CONFLICT (scope, target) DO UPDATE SET
            consent_id = excluded.consent_id,
            fingerprint = excluded.fingerprint,
            observed = excluded.observed,
            decided_by = excluded.decided_by,
            origin = excluded.origin,
            created_at = excluded.created_at,
            revoked_at = NULL
        """,
        (
            consent_id,
            scope,
            target,
            canonize(fingerprint).decode("utf-8"),
            canonize(cast(JsonValue, sorted(observed))).decode("utf-8"),
            decided_by,
            origin,
            at,
        ),
    )
    found = held(connection, scope=scope, target=target)
    if found is None:  # pragma: no cover - the insert above guarantees a row
        raise CliFailure("AI_STP_INTERNAL", "the consent record vanished after being written")
    return found


def revoke(connection: sqlite3.Connection, *, scope: str, target: str, at: str) -> bool:
    """Withdraw a consent. Takes effect immediately for every later request.

    The row survives, marked. A deleted record would leave nothing to show a
    user who asks why a candidate they once allowed has stopped appearing.
    """
    cursor = connection.execute(
        "UPDATE consent SET revoked_at = ? WHERE scope = ? AND target = ? AND revoked_at IS NULL",
        (at, scope, target),
    )
    return cursor.rowcount > 0


def held(connection: sqlite3.Connection, *, scope: str, target: str) -> Record | None:
    """The record covering this target, revoked or not."""
    row = connection.execute(
        "SELECT * FROM consent WHERE scope = ? AND target = ?", (scope, target)
    ).fetchone()
    return None if row is None else _decode(row)


def active(connection: sqlite3.Connection) -> tuple[Record, ...]:
    """Every consent still in force, oldest first."""
    rows = connection.execute(
        "SELECT * FROM consent WHERE revoked_at IS NULL ORDER BY created_at, consent_id"
    ).fetchall()
    return tuple(_decode(row) for row in rows)


def covers(record: Record, candidate: dict[str, JsonValue], *, major: int | None = None) -> Verdict:
    """Whether this record still covers a candidate (`unverified-consent.md`).

    A candidate asking for *more* than the fingerprint recorded is not covered,
    and the fields that grew are named. Asking for *less* stays covered: consent
    was given to a shape, and a smaller shape is inside it — refusing that would
    make removing a permission a reason to interrogate the user again.

    A new major line is never covered by an `object_major` record for the
    previous one. That is not a capability comparison at all, so it is decided
    before one is attempted.
    """
    if not record.active:
        return Verdict(False, "the consent was withdrawn")

    if record.scope == SCOPE_TASK:
        return Verdict(True, "covered by the authorized full-task profile")

    if not record.observed:
        return Verdict(
            False,
            "the consent was recorded before any object of this target was known, "
            "so the shape it would cover was never observed",
        )

    if record.scope == SCOPE_OBJECT_MAJOR and major is not None:
        _, _, recorded = record.target.rpartition("@")
        if recorded and recorded != str(major):
            return Verdict(
                False,
                f"consent covers major line {recorded}, and this candidate is major line {major}",
            )

    wanted = fingerprint_of(candidate)
    grew: list[str] = []
    for name in FINGERPRINT_FIELDS:
        before = _as_set(record.fingerprint.get(name))
        now = _as_set(wanted.get(name))
        if now - before:
            grew.append(name)
    if grew:
        return Verdict(
            False,
            "the candidate now requires more than when consent was given",
            tuple(grew),
        )
    return Verdict(True, f"covered by the {record.scope} consent recorded at {record.created_at}")


def ceiling_of(capabilities: tuple[dict[str, JsonValue], ...]) -> dict[str, JsonValue]:
    """The union of several candidates' fingerprints, as one recorded shape.

    The contract asks for "the fingerprint of the candidate at the moment of
    consent", and a `publisher` record covers more than one candidate. The
    honest generalisation is the union of what those objects need *now*: the
    user is agreeing to everything the target currently asks for, and anything
    beyond it is the revoking event the contract describes.

    Taking the union rather than the intersection is deliberate. An
    intersection would refuse objects the user could plainly see when they
    agreed, and re-asking about something already shown is not caution.
    """
    merged: dict[str, JsonValue] = {}
    for name in FINGERPRINT_FIELDS:
        wanted: set[str] = set()
        for capability in capabilities:
            wanted |= set(_as_set(capability.get(name)))
        merged[name] = cast(JsonValue, sorted(wanted))
    return merged


def major_of(version: str) -> int | None:
    """The major line of an `X.Y` version, or `None` when there is not one."""
    major, _, _ = version.partition(".")
    return int(major) if major.isdigit() else None


@dataclass(frozen=True)
class Consultation:
    """What the durable records say about one candidate, and which one said it."""

    covered: bool
    reason: str

    #: The record that decided, as `scope:target`. Empty when none applied —
    #: the outcome the trail and the install plan record as "no durable
    #: consent", distinct from "a record refused".
    source: str = ""

    changed: tuple[str, ...] = ()


def consulted(
    connection: sqlite3.Connection,
    *,
    stable_id: str,
    owner_id: str,
    version: str,
    capabilities: dict[str, JsonValue],
) -> Consultation:
    """Whether any durable record covers this candidate, and on what basis.

    Order is the product, not an implementation detail:

    1. A revoked narrower record is an exclusion. It answers before a broader
       grant, including task authority. Claiming the narrower exclusion wins
       while returning the first covering grant is the A06 bug.
    2. An active `object_major` or `publisher` record that still matches the
       fingerprint answers next, most specific first, so the source names the
       record the user actually wrote.
    3. An active `task` grant covers without a fingerprint or major ceiling.
       Capability growth and a new major line do not re-prompt (`ADR-0150`).
    4. Otherwise a fingerprint miss reports that miss; otherwise there is no
       durable consent.

    Until 2026-08-29 nothing called this, under either publisher scope. The
    records were writable, listable and inert.
    """
    major = major_of(version)
    held_records: list[tuple[str, Record]] = []
    if major is not None:
        narrow = held(connection, scope=SCOPE_OBJECT_MAJOR, target=f"{stable_id}@{major}")
        if narrow is not None:
            held_records.append((SCOPE_OBJECT_MAJOR, narrow))
    if owner_id:
        publisher = held(connection, scope=SCOPE_PUBLISHER, target=owner_id)
        if publisher is not None:
            held_records.append((SCOPE_PUBLISHER, publisher))
    task = held(connection, scope=SCOPE_TASK, target=TASK_PROFILE_FULL_AUTO)
    if task is not None:
        held_records.append((SCOPE_TASK, task))

    if not held_records:
        return Consultation(False, "no durable consent record covers this candidate")

    for scope, record in held_records:
        if not record.active:
            return Consultation(False, "the consent was withdrawn", f"{scope}:{record.target}")

    fingerprint_miss: Consultation | None = None
    for scope, record in held_records:
        if scope == SCOPE_TASK:
            continue
        verdict = covers(record, capabilities, major=major)
        if verdict.covered:
            return Consultation(True, verdict.reason, f"{scope}:{record.target}")
        if fingerprint_miss is None:
            fingerprint_miss = Consultation(
                False, verdict.reason, f"{scope}:{record.target}", verdict.changed
            )

    for scope, record in held_records:
        if scope == SCOPE_TASK:
            return Consultation(
                True, covers(record, capabilities).reason, f"{scope}:{record.target}"
            )

    if fingerprint_miss is not None:
        return fingerprint_miss
    return Consultation(False, "no durable consent record covers this candidate")


def _as_set(value: JsonValue) -> frozenset[str]:
    """A fingerprint field as a comparable set, whatever shape it arrived in."""
    if isinstance(value, list):
        return frozenset(str(item) for item in value)
    if value is None:
        return frozenset()
    return frozenset({str(value)})


def _decode(row: sqlite3.Row) -> Record:
    decoded: JsonValue = json.loads(str(row["fingerprint"]))
    held_fingerprint: dict[str, JsonValue] = decoded if isinstance(decoded, dict) else {}
    seen: JsonValue = json.loads(str(row["observed"]))
    return Record(
        consent_id=str(row["consent_id"]),
        scope=str(row["scope"]),
        target=str(row["target"]),
        fingerprint=held_fingerprint,
        observed=tuple(str(item) for item in seen) if isinstance(seen, list) else (),
        decided_by=str(row["decided_by"]),
        origin=str(row["origin"]),
        created_at=str(row["created_at"]),
        revoked_at=None if row["revoked_at"] is None else str(row["revoked_at"]),
    )
