"""The recommendation session: a snapshot, ephemeral proposals, one confirmation.

`ADR-0027` draws the line this module implements. Showing a composition must
stay distinguishable from creating one, so proposing writes no version, no
target and no registry record — the proposal row exists only because proposing
and confirming are two processes, and it is not an `entity`, has no revision and
no head. Nothing here makes an object exist.

**Confirmation is the only way a `SetupVersion` appears, and it is atomic.** The
definition artifact, full passport/version, trace and pin are written inside one
transaction: a decision without its reasons is what `REQ-616` exists to prevent,
and a version nothing points at is a half-made state a later run would have to
guess about. `REQ-623` says the three public outcomes exist together or not at
all; `REQ-628` adds their artifact/passport foundation to the same
`BEGIN IMMEDIATE`.

**A proposal is bound to the input it was built from.** Candidate digests,
context passport revisions and the policy version go into one domain-separated
snapshot; confirmation recomputes it and refuses a mismatch as
`AI_STP_PLAN_STALE`. Comparing the parts one by one would answer the same
question with more code and more ways to forget a part.

**The row outlives its own confirmation.** Deleting it on success would be the
tidy thing to do and would break `REQ-624`: a repeated confirmation must return
the version already created, and a deleted proposal answers "unknown" instead.
So confirmation marks the row rather than removing it, and a repeat reads the
mark.

**Selected is not installed.** Confirmation leaves the pair at `pending_install`
and goes no further. `selection-proposal.md` is explicit that the window between
selected and installed is ordinary and not a drift, and installation belongs to
the provider plan of phase 7.
"""

import json
import sqlite3
from dataclasses import dataclass
from typing import Final, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, journal, lifecycle, revisions, setup_versions, versions
from ai_stp_cli.local.database import transaction
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id

#: The snapshot's own domain (`canonical-data.md`). Separate from the passports
#: it is built from: two different facts must not share an identifier just
#: because their bytes happen to agree.
SNAPSHOT_DOMAIN: Final[str] = "ai-stp:selection-snapshot:v1"

#: States of `SelectionRun` (`SPEC-006`). Closed, and `confirmed` is reachable
#: only through `confirm` below.
STATE_OPEN: Final[str] = "open"
STATE_CONFIRMED: Final[str] = "confirmed"
STATE_CANCELLED: Final[str] = "cancelled"
STATE_EXPIRED: Final[str] = "expired"
STATES: Final[frozenset[str]] = frozenset(
    {STATE_OPEN, STATE_CONFIRMED, STATE_CANCELLED, STATE_EXPIRED}
)

#: What a confirmed pair is until a provider reports `verified`. A normal state,
#: not a disagreement between what is selected and what is on disk.
PENDING_INSTALL: Final[str] = "pending_install"

#: The kind a composed object is recorded under. A setup belongs to exactly one
#: harness by `ADR-0014`, which is why the harness is part of the pair below and
#: not a property that could later differ.
SETUP_KIND: Final[str] = "setup"


@dataclass(frozen=True)
class Member:
    """One exact reference inside a proposal, and why it was allowed.

    The lane and the consent source travel with the member rather than being
    looked up later: `REQ-616` wants the trace to record them per candidate, and
    a lane recomputed at confirmation time could differ from the one the user
    was shown.
    """

    stable_id: str
    version: str
    passport_digest: str
    lane: str
    lane_reason: str

    #: How an unverified candidate was allowed in, when one was. Empty for
    #: everything that needed no consent.
    consent_source: str = ""

    #: A bounded overlay's revision, when this member is derived (`REQ-605`).
    overlay_revision_id: str = ""

    def as_json(self) -> dict[str, JsonValue]:
        return {
            "stable_id": self.stable_id,
            "version": self.version,
            "passport_digest": self.passport_digest,
            "lane": self.lane,
            "lane_reason": self.lane_reason,
            "consent_source": self.consent_source,
            "overlay_revision_id": self.overlay_revision_id,
        }


@dataclass(frozen=True)
class Context:
    """The input a session was built from (`REQ-621`).

    Assembled by the caller from the developer, device and project passports and
    the chosen harness. Held as revision identifiers rather than as passport
    contents: a revision id already is that content's digest, so carrying the
    content would restate it and give two things to keep in step.
    """

    project_id: str
    harness_id: str
    developer_revision: str
    device_revision: str
    project_revision: str

    #: The effective policy, spelled by the caller. Derived from configuration
    #: rather than pinned in code, so `REQ-620` holds — a changed limit changes
    #: the outcome without an edit here — and `REQ-624` holds with it, because a
    #: changed policy makes every open proposal stale on its own.
    policy_version: str

    def snapshot(self, members: tuple[Member, ...]) -> str:
        """One digest over everything staleness depends on.

        Members are sorted, so a proposal does not become stale because an agent
        listed the same composition in another order. Everything else is a
        revision identifier or a version string, and each of them is already a
        statement about content.
        """
        value: dict[str, JsonValue] = {
            "project_id": self.project_id,
            "harness_id": self.harness_id,
            "developer_revision": self.developer_revision,
            "device_revision": self.device_revision,
            "project_revision": self.project_revision,
            "policy_version": self.policy_version,
            "members": [
                {
                    "stable_id": item.stable_id,
                    "version": item.version,
                    "passport_digest": item.passport_digest,
                    "overlay_revision_id": item.overlay_revision_id,
                }
                for item in sorted(members, key=lambda item: (item.stable_id, item.version))
            ],
        }
        return digest_canonical(SNAPSHOT_DOMAIN, value)


@dataclass(frozen=True)
class Proposal:
    """One derived, short-lived composition inside a session."""

    proposal_id: str
    project_id: str
    harness_id: str
    snapshot: str
    members: tuple[Member, ...]
    created_at: str
    expires_at: str
    cancelled_at: str | None = None
    confirmed_stable_id: str | None = None
    confirmed_version: str | None = None

    def state(self, now: str) -> str:
        """What this proposal is, at a named moment.

        `now` is a parameter rather than a reading of the clock: a state that
        depends on when it is asked cannot be tested twice with the same answer,
        and every caller here already has the moment it is working at.
        """
        if self.confirmed_version is not None:
            return STATE_CONFIRMED
        if self.cancelled_at is not None:
            return STATE_CANCELLED
        # Timestamps are RFC 3339 in UTC with a fixed shape, so string order is
        # time order; parsing them to compare would add a failure mode to a
        # comparison that already works.
        if now >= self.expires_at:
            return STATE_EXPIRED
        return STATE_OPEN


@dataclass(frozen=True)
class Confirmation:
    """What a confirmation produced, and whether it produced it just now."""

    stable_id: str
    version: str
    revision_id: str
    state: str

    #: False when the proposal had already been confirmed and this call returned
    #: the same version. `REQ-624` makes that a success, not a conflict, and a
    #: caller still deserves to know which of the two happened.
    created: bool


def propose(
    connection: sqlite3.Connection,
    *,
    context: Context,
    members: tuple[Member, ...],
    at: str,
    expires_at: str,
    empty: bool = False,
) -> Proposal:
    """Record one proposal. Writes nothing else — no version, no target.

    The only row is in `proposal`, which is not a registry record: there is no
    `entity`, no revision and no head, so nothing here brings an object into
    existence. That is `REQ-622` and it is the whole reason this table is
    separate from the ones that do.

    `empty` is how a caller says it means zero members (`REQ-630`). Without it
    zero members stays the refusal it has always been, because that is what a
    search matching nothing produces, and an immutable version is too expensive
    a thing to get by omission. With it, and with members, the flag asserts
    something false about the call and is refused rather than ignored.
    """
    if empty and members:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "an empty proposal cannot name members",
            details={"members": str(len(members))},
            next_actions=["select propose --harness <id> --empty --json"],
        )
    if not members and not empty:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a proposal with no members composes nothing",
            details={"empty_is_deliberate": "select propose --harness <id> --empty"},
            next_actions=["select eligibility --harness <id> --json"],
        )
    _distinct(members)

    proposal_id = new_id("proposal")
    connection.execute(
        """
        INSERT INTO proposal
            (proposal_id, project_id, harness_id, snapshot, graph, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            proposal_id,
            context.project_id,
            context.harness_id,
            context.snapshot(members),
            json.dumps([item.as_json() for item in members], sort_keys=True),
            at,
            expires_at,
        ),
    )
    held_now = held(connection, proposal_id)
    if held_now is None:  # pragma: no cover - the insert above guarantees a row
        raise CliFailure("AI_STP_INTERNAL", "the proposal vanished after being written")
    return held_now


def held(connection: sqlite3.Connection, proposal_id: str) -> Proposal | None:
    """One proposal, if this session still has it."""
    row = connection.execute(
        "SELECT * FROM proposal WHERE proposal_id = ?", (proposal_id,)
    ).fetchone()
    return None if row is None else _decode(row)


def open_proposals(
    connection: sqlite3.Connection, *, project_id: str, harness_id: str, now: str
) -> tuple[Proposal, ...]:
    """Every proposal still open for one pair, oldest first."""
    rows = connection.execute(
        """
        SELECT * FROM proposal
        WHERE project_id = ? AND harness_id = ?
        ORDER BY created_at, proposal_id
        """,
        (project_id, harness_id),
    ).fetchall()
    found = (_decode(row) for row in rows)
    return tuple(item for item in found if item.state(now) == STATE_OPEN)


def cancel(connection: sqlite3.Connection, proposal_id: str, *, at: str) -> Proposal:
    """End a proposal without creating a version or changing a target.

    A confirmed proposal is not cancellable: the version it created exists, and
    a flag saying otherwise would describe a state the registry does not have.
    The terminal session row stays so repeating the same cancellation returns
    the same outcome instead of turning a completed request into not-found.
    """
    proposal = _require(connection, proposal_id)
    if proposal.confirmed_version is not None:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this proposal was already confirmed and its version exists",
            details={"proposal_id": proposal_id, "version": proposal.confirmed_version},
        )
    if proposal.cancelled_at is not None:
        return proposal
    connection.execute(
        "UPDATE proposal SET cancelled_at = ? WHERE proposal_id = ?", (at, proposal_id)
    )
    return _require(connection, proposal_id)


def confirm(
    connection: sqlite3.Connection,
    proposal_id: str,
    *,
    context: Context,
    owner_id: str,
    device_id: str,
    at: str,
) -> Confirmation:
    """Freeze one proposal as a private `SetupVersion`, atomically (`REQ-623`).

    The version, trace and pin exist together or not at all; the definition
    artifact and passport revision that make the version meaningful share the
    same transaction. A caller that found only a subset could not tell which
    run left it.

    Context staleness is decided before the transaction opens, against the live
    context the caller assembled. Registry member validity is checked there for
    a fast refusal and again under the write lock, so a concurrent deletion
    cannot be frozen between validation and persistence.
    """
    proposal = _require(connection, proposal_id)

    # Idempotent replay comes first: a repeat of a confirmation is a success
    # that returns the same version, and checking staleness before it would let
    # a later context change turn an already-created version into an error.
    if proposal.confirmed_version is not None and proposal.confirmed_stable_id is not None:
        recorded = versions.held(
            connection, proposal.confirmed_stable_id, proposal.confirmed_version
        )
        if recorded is None:  # pragma: no cover - the transaction below is atomic
            raise CliFailure(
                "AI_STP_INTERNAL",
                "a confirmed proposal names a version the registry does not hold",
                details={"proposal_id": proposal_id},
            )
        return Confirmation(
            stable_id=recorded.stable_id,
            version=recorded.version,
            revision_id=recorded.revision_id,
            state=PENDING_INSTALL,
            created=False,
        )

    state = proposal.state(at)
    if state == STATE_CANCELLED:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this proposal was cancelled",
            details={"proposal_id": proposal_id},
            next_actions=["select propose --harness <id> --json"],
        )
    if state == STATE_EXPIRED:
        raise CliFailure(
            "AI_STP_PLAN_STALE",
            "this proposal has expired and a new session is required",
            details={"proposal_id": proposal_id, "expired_at": proposal.expires_at},
            next_actions=["select propose --harness <id> --json"],
        )

    _members_still_valid(connection, proposal)

    current = context.snapshot(proposal.members)
    if current != proposal.snapshot:
        raise CliFailure(
            "AI_STP_PLAN_STALE",
            "the context this proposal was built from has changed",
            details={"proposal_id": proposal_id, "expected": proposal.snapshot, "found": current},
            next_actions=["select propose --harness <id> --json"],
        )

    operation_id = journal.begin(connection, "selection.confirm", at)
    try:
        with transaction(connection):
            # The preflight check above did not hold a lock. This one does, and
            # closes the only interval in which another process could change a
            # context passport or member before its exact refs become immutable.
            _context_still_current(connection, context)
            _members_still_valid(connection, proposal)
            confirmation = _freeze(
                connection,
                proposal,
                context=context,
                owner_id=owner_id,
                device_id=device_id,
                operation_id=operation_id,
                at=at,
            )
    except BaseException as error:
        journal.settle(connection, operation_id, "failed", at, type(error).__name__)
        raise
    journal.settle(connection, operation_id, "verified", at)
    return confirmation


def selected(
    connection: sqlite3.Connection, *, project_id: str, harness_id: str
) -> tuple[str, str, str] | None:
    """The version selected for one pair, and its state, if one is selected."""
    row = connection.execute(
        "SELECT stable_id, version, state FROM selected_version "
        "WHERE project_id = ? AND harness_id = ?",
        (project_id, harness_id),
    ).fetchone()
    if row is None:
        return None
    return str(row["stable_id"]), str(row["version"]), str(row["state"])


def trace_of(connection: sqlite3.Connection, stable_id: str, version: str) -> dict[str, JsonValue]:
    """The recorded reasons behind one version. Empty when none was recorded."""
    row = connection.execute(
        "SELECT body FROM recommendation_trace WHERE stable_id = ? AND version = ?",
        (stable_id, version),
    ).fetchone()
    if row is None:
        return {}
    decoded: object = json.loads(str(row["body"]))
    return cast(dict[str, JsonValue], decoded) if isinstance(decoded, dict) else {}


def _freeze(
    connection: sqlite3.Connection,
    proposal: Proposal,
    *,
    context: Context,
    owner_id: str,
    device_id: str,
    operation_id: str,
    at: str,
) -> Confirmation:
    """The atomic SetupVersion outcome of `REQ-623` and `REQ-628`."""
    stable_id = new_id(SETUP_KIND)
    connection.execute(
        "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, ?, ?)",
        (stable_id, SETUP_KIND, at),
    )

    passport = setup_versions.passport_content(
        connection,
        stable_id=stable_id,
        version=versions.FIRST_VERSION,
        owner_id=owner_id,
        project_id=proposal.project_id,
        harness_id=proposal.harness_id,
        snapshot=proposal.snapshot,
        members=tuple(
            setup_versions.MemberRef(item.stable_id, item.version, item.passport_digest)
            for item in proposal.members
        ),
        at=at,
    )
    stored = revisions.commit(connection, passport, device_id=device_id, operation_id=operation_id)
    recorded = versions.record(
        connection,
        stable_id=stable_id,
        version=versions.FIRST_VERSION,
        # The catalogue's own digest, from the one function that knows how.
        # A revision id would have been available and wrong: it is a different
        # hash in a different domain, and every verification of this version
        # against a conforming server would fail and look like corruption.
        passport_digest=cache.digest_of(cast(JsonValue, stored.envelope.model_dump(mode="json"))),
        revision_id=stored.revision_id,
        at=at,
    )

    body: dict[str, JsonValue] = {
        "policy_version": context.policy_version,
        "developer_revision": context.developer_revision,
        "device_revision": context.device_revision,
        "project_revision": context.project_revision,
        "candidates": [item.as_json() for item in proposal.members],
    }
    connection.execute(
        """
        INSERT INTO recommendation_trace
            (stable_id, version, proposal_id, snapshot, body, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            stable_id,
            recorded.version,
            proposal.proposal_id,
            proposal.snapshot,
            json.dumps(body, sort_keys=True),
            at,
        ),
    )

    connection.execute(
        """
        INSERT INTO selected_version
            (project_id, harness_id, stable_id, version, state, selected_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (project_id, harness_id) DO UPDATE SET
            stable_id = excluded.stable_id,
            version = excluded.version,
            state = excluded.state,
            selected_at = excluded.selected_at
        """,
        (
            proposal.project_id,
            proposal.harness_id,
            stable_id,
            recorded.version,
            PENDING_INSTALL,
            at,
        ),
    )

    connection.execute(
        "UPDATE proposal SET confirmed_stable_id = ?, confirmed_version = ? WHERE proposal_id = ?",
        (stable_id, recorded.version, proposal.proposal_id),
    )

    return Confirmation(
        stable_id=stable_id,
        version=recorded.version,
        revision_id=stored.revision_id,
        state=PENDING_INSTALL,
        created=True,
    )


def _members_still_valid(connection: sqlite3.Connection, proposal: Proposal) -> None:
    """Refuse a proposal whose members stopped being usable since it was made.

    `selection-proposal.md` names an inadmissible candidate inside a proposal as
    its own confirmation error, separate from staleness — and it is a different
    situation: the snapshot compares what the proposal was built from, and an
    object deleted afterwards leaves those inputs untouched while making the
    composition impossible.

    Only registry facts are re-read here. A full re-assessment would rescan the
    project on every confirmation, and the inputs that assessment depends on are
    already covered by the snapshot.
    """
    for member in proposal.members:
        recorded = versions.held(connection, member.stable_id, member.version)
        if recorded is None:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "a member of this proposal no longer has that exact version",
                details={"stable_id": member.stable_id, "version": member.version},
                next_actions=["select propose --harness <id> --json"],
            )
        if recorded.passport_digest != member.passport_digest:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "a member of this proposal now stands for different content",
                details={"stable_id": member.stable_id, "version": member.version},
                next_actions=["select propose --harness <id> --json"],
            )
        stored = revisions.head(connection, member.stable_id)
        if stored is None or not lifecycle.registrable(connection, stored):
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "a member of this proposal is a draft or has been deleted",
                details={"stable_id": member.stable_id},
                next_actions=["select propose --harness <id> --json"],
            )


def _context_still_current(connection: sqlite3.Connection, context: Context) -> None:
    """Prove every context revision is still the sole head under the write lock."""
    expected = (
        ("developer", context.developer_revision, None),
        ("device", context.device_revision, None),
        ("project", context.project_revision, context.project_id),
    )
    for kind, revision_id, required_stable_id in expected:
        stored = revisions.get(connection, revision_id)
        if (
            stored is None
            or stored.envelope.kind != kind
            or (required_stable_id is not None and stored.stable_id != required_stable_id)
        ):
            raise _stale_context(kind)
        try:
            current = revisions.head(connection, stored.stable_id)
        except CliFailure as error:
            if error.code != "AI_STP_CONFLICT":
                raise
            raise _stale_context(kind) from error
        if current is None or current.revision_id != revision_id:
            raise _stale_context(kind)


def _stale_context(kind: str) -> CliFailure:
    return CliFailure(
        "AI_STP_PLAN_STALE",
        "a context passport changed after this proposal was checked",
        details={"kind": kind},
        next_actions=["select propose --harness <id> --json"],
    )


def _require(connection: sqlite3.Connection, proposal_id: str) -> Proposal:
    proposal = held(connection, proposal_id)
    if proposal is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no proposal with that identifier is held by this session",
            details={"proposal_id": proposal_id},
            next_actions=["select propose --harness <id> --json"],
        )
    return proposal


def _distinct(members: tuple[Member, ...]) -> None:
    """Refuse one object twice in a composition.

    Two versions of one component is one of the conflicts `REQ-606` names, and
    catching it here means the builder never receives a graph that cannot be
    resolved rather than discovering it later.
    """
    seen: set[str] = set()
    for item in members:
        if item.stable_id in seen:
            raise CliFailure(
                "AI_STP_CONFLICT",
                "one object appears twice in this composition",
                details={"stable_id": item.stable_id},
            )
        seen.add(item.stable_id)


def _decode(row: sqlite3.Row) -> Proposal:
    decoded: object = json.loads(str(row["graph"]))
    stored = cast(list[dict[str, object]], decoded) if isinstance(decoded, list) else []
    members = tuple(
        Member(
            stable_id=str(item.get("stable_id", "")),
            version=str(item.get("version", "")),
            passport_digest=str(item.get("passport_digest", "")),
            lane=str(item.get("lane", "")),
            lane_reason=str(item.get("lane_reason", "")),
            consent_source=str(item.get("consent_source", "")),
            overlay_revision_id=str(item.get("overlay_revision_id", "")),
        )
        for item in stored
    )
    return Proposal(
        proposal_id=str(row["proposal_id"]),
        project_id=str(row["project_id"]),
        harness_id=str(row["harness_id"]),
        snapshot=str(row["snapshot"]),
        members=members,
        created_at=str(row["created_at"]),
        expires_at=str(row["expires_at"]),
        cancelled_at=None if row["cancelled_at"] is None else str(row["cancelled_at"]),
        confirmed_stable_id=(
            None if row["confirmed_stable_id"] is None else str(row["confirmed_stable_id"])
        ),
        confirmed_version=(
            None if row["confirmed_version"] is None else str(row["confirmed_version"])
        ),
    )
