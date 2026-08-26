"""The local installation operation state machine (`#173`, `operation.md`).

An immutable plan, an approval bound to its exact digest, a lock taken before
the first effect and preconditions re-checked *after* the lock, three
distinguishable outcomes, resume and a durable append-only journal.

**The plan cannot change, so an approval means something.** `operation.md` binds
confirmation to an exact plan hash and says it does not carry to a new plan.
Here the digest is computed from the plan's own fields and stored beside it, and
approving with any other digest is refused. A plan that could be edited after
approval would make the approval a statement about something else.

**Preconditions are re-checked after the lock, not before it.** Checking first
and then locking leaves a window in which the target moves; the whole point of
`REQ-806` is that the check and the effect are on the same side of the lock.

**An external effect must pass through `applied_unverified`.** `journal` allows
the shortcut because a transactional local write has no window between effect
and verification. An installation does — a provider wrote files and nobody has
looked yet — so this layer refuses `applying → verified` and forces the state
that exists precisely to describe that window. `verified` is the only name for
success, and only a durable postcondition check produces it.

**A timeout is `partial`, never `failed`.** `operation.md` says an expired
external call does not prove the absence of an effect, so the machine has no
path from an interrupted apply to `failed` that does not go through somebody
deciding what actually happened.

**Recovery is a new operation.** A terminal state allows nothing, so recovering
from `partial` means planning again with the recovery report in hand. An
operation that could leave its outcome never really had one.
"""

import json
import sqlite3
from dataclasses import dataclass
from typing import Final, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import journal
from ai_stp_cli.local.database import transaction
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import is_valid_id, new_id

#: The plan's own hash domain (`canonical-data.md`).
PLAN_DOMAIN: Final[str] = "ai-stp:plan:v1"

#: What a plan may ask for. Closed: an action nobody named has no declared
#: effects, no recovery and no place in the failure matrix.
#: What the **journal** accepts, which is not the same as what `install` does.
#: The state machine — planned, approved, applying, applied_unverified,
#: verified — plus backup and `plan-digest` are identical whether configuration
#: or a program is being installed, so there is one journal rather than two
#: (`ADR-0122`, amended). The split between setups and the program lifecycle
#: lives on the command surface: `install` refuses a `software_*` action and
#: names `harness`, which is where it is carried out.
ACTIONS: Final[frozenset[str]] = frozenset(
    {
        "install",
        "update",
        "backup",
        "remove",
        "rollback",
        "software_install",
        "software_update",
        "software_remove",
    }
)

#: How the user's decision is expressed for a plan. A plan carrying an effect
#: always needs the digest form — an explicit flag says "yes" to whatever is in
#: front of it, and a plan is exactly the thing that can have changed.
CONFIRMATION_PLAN_DIGEST: Final[str] = "plan_digest"

#: States this machine may leave an operation in, mapped from a provider result
#: by `provider.protocol.operation_state`.
STATE_PLANNED: Final[str] = "planned"
STATE_APPROVED: Final[str] = "approved"
STATE_APPLYING: Final[str] = "applying"
STATE_APPLIED_UNVERIFIED: Final[str] = "applied_unverified"
STATE_VERIFIED: Final[str] = "verified"
STATE_PARTIAL: Final[str] = "partial"
STATE_FAILED: Final[str] = "failed"
STATE_STALE: Final[str] = "stale"
STATE_CANCELLED: Final[str] = "cancelled"
STATE_ROLLED_BACK: Final[str] = "rolled_back"

#: Outcomes after which the same logical request may be planned again.  The
#: old operation remains immutable and auditable; only its internal retry key
#: is retired so one new operation can own the live key.  ``partial`` is not in
#: ``journal.SETTLED`` because it stays visible to recovery reporting, but an
#: operation cannot leave it and recovery is explicitly a new operation.
REPLANNABLE_STATES: Final[frozenset[str]] = journal.SETTLED | frozenset({STATE_PARTIAL})


@dataclass(frozen=True)
class Plan:
    """An immutable plan. Its digest is its identity as a decision."""

    operation_id: str
    action: str
    author: str
    target_id: str

    #: What the target was when the plan was made. Re-read under the lock, and a
    #: difference makes the plan stale rather than something to apply anyway.
    expected_target_digest: str

    provider_version: str
    effects: tuple[str, ...]
    confirmation: str
    recovery_action: str
    expires_at: str
    created_at: str
    provider_protocol_version: int = 1
    provider_target: str = ""
    provider_release_manifest: str = ""
    provider_release_recovery: bool = False
    provider_release_trust: str = "unverified"
    provider_release_evidence: str = ""
    bundle_format: str = ""
    bundle_digest: str = ""
    bundle_artifact_digest: str = ""
    bundle_size: int = 0
    provider_plan_digest: str = ""

    #: Which exact setup version this plan installs. Rollback has to name "the
    #: exact previous verified version" (`#177`), and the effect strings are
    #: sentences written for a person — reading a version out of one would be
    #: parsing prose.
    setup_stable_id: str = ""
    setup_version: str = ""

    schema_version: int = 6

    @property
    def digest(self) -> str:
        """One digest over every field a decision could turn on.

        Built by naming the fields rather than by dumping the object: a field
        added later must be a deliberate change to what an approval covers, not
        something that silently starts being covered.
        """
        value: dict[str, JsonValue] = {
            "schema_version": self.schema_version,
            "operation_id": self.operation_id,
            "action": self.action,
            "author": self.author,
            "target_id": self.target_id,
            "expected_target_digest": self.expected_target_digest,
            "provider_version": self.provider_version,
            "effects": list(self.effects),
            "confirmation": self.confirmation,
            "recovery_action": self.recovery_action,
            "expires_at": self.expires_at,
            "setup_stable_id": self.setup_stable_id,
            "setup_version": self.setup_version,
        }
        if self.schema_version >= 2:
            value["provider_protocol_version"] = self.provider_protocol_version
            value["provider_target"] = self.provider_target
        if self.schema_version >= 3:
            value["provider_release_manifest"] = self.provider_release_manifest
        if self.schema_version >= 4:
            value["provider_release_recovery"] = self.provider_release_recovery
        if self.schema_version >= 5:
            value["bundle_format"] = self.bundle_format
            value["bundle_digest"] = self.bundle_digest
            value["bundle_artifact_digest"] = self.bundle_artifact_digest
            value["bundle_size"] = self.bundle_size
            value["provider_plan_digest"] = self.provider_plan_digest
        if self.schema_version >= 6:
            value["provider_release_trust"] = self.provider_release_trust
            value["provider_release_evidence"] = self.provider_release_evidence
        return digest_canonical(PLAN_DOMAIN, value)


@dataclass(frozen=True)
class Event:
    """One recorded step. Append-only, and safe to show anyone."""

    sequence: int
    at: str
    state_before: str
    state_after: str
    result: str
    evidence: str | None


@dataclass(frozen=True)
class Recovery:
    """What a stopped operation left behind, and what may be done next.

    `operation.md` asks a recovery report for the last confirmed state, the
    effects already carried out, the backup reference and the allowed next
    actions. All four, because three of them without the fourth leaves a person
    to guess at the one thing they must not guess at.
    """

    operation_id: str
    state: str
    effects_recorded: tuple[str, ...]
    backup_ref: str | None
    next_actions: tuple[str, ...]


def propose(
    connection: sqlite3.Connection,
    *,
    action: str,
    author: str,
    target_id: str,
    expected_target_digest: str,
    provider_version: str,
    effects: tuple[str, ...],
    recovery_action: str,
    idempotency_key: str,
    at: str,
    expires_at: str,
    provider_protocol_version: int = 1,
    provider_target: str = "",
    provider_release_manifest: str = "",
    provider_release_recovery: bool = False,
    provider_release_trust: str = "unverified",
    provider_release_evidence: str = "",
    bundle_format: str = "",
    bundle_digest: str = "",
    bundle_artifact_digest: str = "",
    bundle_size: int = 0,
    provider_plan_digest: str = "",
    setup_stable_id: str = "",
    setup_version: str = "",
    operation_id: str | None = None,
) -> Plan:
    """Record an immutable plan. Has no effect of its own (`REQ-805`).

    A repeat with the same idempotency key returns the active plan already
    recorded rather than making a second one.  Once that operation has a
    terminal outcome, the key may name one new operation: recovery and replans
    must not reopen or return an operation that cannot leave its outcome.

    The uniqueness lives in the schema and the terminal-key handoff happens
    under ``BEGIN IMMEDIATE``.  Two processes racing to replan therefore cannot
    each retire the old key and create a replacement.
    """
    if action not in ACTIONS:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "that is not an action a plan may ask for",
            details={"action": action, "allowed": ", ".join(sorted(ACTIONS))},
        )
    if not effects:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a plan enumerates its effects, and a plan with none changes nothing",
            details={"action": action},
        )
    if operation_id is not None and not is_valid_id(operation_id, "operation"):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the caller-supplied operation id is not canonical",
            details={"operation_id": operation_id},
        )

    held = _by_key(connection, idempotency_key)
    if held is not None and not _is_replannable(connection, held.operation_id):
        return held

    with transaction(connection):
        # Re-read inside the lock: between the read above and here, another
        # process may have recorded the same key.
        held = _by_key(connection, idempotency_key)
        if held is not None:
            if not _is_replannable(connection, held.operation_id):
                return held
            _retire_idempotency_key(connection, held.operation_id, idempotency_key)

        operation_id = operation_id or new_id("operation")
        plan = Plan(
            operation_id=operation_id,
            action=action,
            author=author,
            target_id=target_id,
            expected_target_digest=expected_target_digest,
            provider_version=provider_version,
            provider_protocol_version=provider_protocol_version,
            provider_target=provider_target,
            provider_release_manifest=provider_release_manifest,
            provider_release_recovery=provider_release_recovery,
            provider_release_trust=provider_release_trust,
            provider_release_evidence=provider_release_evidence,
            bundle_format=bundle_format,
            bundle_digest=bundle_digest,
            bundle_artifact_digest=bundle_artifact_digest,
            bundle_size=bundle_size,
            provider_plan_digest=provider_plan_digest,
            effects=effects,
            confirmation=CONFIRMATION_PLAN_DIGEST,
            recovery_action=recovery_action,
            expires_at=expires_at,
            created_at=at,
            setup_stable_id=setup_stable_id,
            setup_version=setup_version,
        )
        connection.execute(
            "INSERT INTO operation (operation_id, kind, state, started_at) VALUES (?, ?, ?, ?)",
            (operation_id, f"install.{action}", STATE_PLANNED, at),
        )
        connection.execute(
            """
            INSERT INTO operation_plan (
                operation_id, idempotency_key, action, author, target_id,
                expected_target_digest, provider_version, effects, confirmation,
                recovery_action, plan_digest, expires_at, created_at,
                setup_stable_id, setup_version, provider_protocol_version,
                provider_target, plan_schema_version, provider_release_manifest,
                provider_release_recovery, provider_release_trust,
                provider_release_evidence, bundle_format, bundle_digest,
                bundle_artifact_digest, bundle_size, provider_plan_digest
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                operation_id,
                idempotency_key,
                action,
                author,
                target_id,
                expected_target_digest,
                provider_version,
                json.dumps(list(effects)),
                CONFIRMATION_PLAN_DIGEST,
                recovery_action,
                plan.digest,
                expires_at,
                at,
                setup_stable_id,
                setup_version,
                provider_protocol_version,
                provider_target,
                plan.schema_version,
                provider_release_manifest,
                int(provider_release_recovery),
                provider_release_trust,
                provider_release_evidence,
                bundle_format,
                bundle_digest,
                bundle_artifact_digest,
                bundle_size,
                provider_plan_digest,
            ),
        )
        _record(connection, operation_id, STATE_PLANNED, STATE_PLANNED, "planned", at)
        return plan


def active_for_idempotency(connection: sqlite3.Connection, key: str) -> Plan | None:
    """Return a non-terminal plan for one logical request before provider planning."""
    held = _by_key(connection, key)
    if held is None or _is_replannable(connection, held.operation_id):
        return None
    return held


def plan(connection: sqlite3.Connection, operation_id: str) -> Plan:
    """Read one exact durable operation plan without changing it."""
    return _require(connection, operation_id)


def approve(
    connection: sqlite3.Connection, operation_id: str, *, plan_digest: str, at: str
) -> Plan:
    """Record the user's decision against one exact plan.

    The digest must be the plan's. `operation.md` says an approval is to an
    exact hash and does not carry to a new plan, so approving with a digest from
    somewhere else is refused rather than treated as a near miss — that is the
    whole mechanism by which an approval means anything.

    A refusal that marks the plan `stale` commits that mark *before* raising.
    Raising from inside the transaction would roll the mark back and answer
    "stale" about an operation the registry still calls approved — and
    `operation.md` asks for the terminal state to be durable before the caller
    is answered, in exactly those words.
    """
    problem: CliFailure | None = None
    with transaction(connection):
        plan = _require(connection, operation_id)
        if at >= plan.expires_at:
            _move(connection, operation_id, STATE_STALE, "the plan expired before approval", at)
            problem = CliFailure(
                "AI_STP_PLAN_STALE",
                "this plan expired before it was approved",
                details={"operation_id": operation_id, "expired_at": plan.expires_at},
            )
        elif plan_digest != plan.digest:
            # Not stale — the plan is fine and the approval is for something
            # else. Nothing is recorded, so the plan stays approvable.
            problem = CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "that approval is for a different plan",
                details={"operation_id": operation_id, "expected": plan.digest},
                next_actions=["select bundle --json"],
            )
        else:
            _move(connection, operation_id, STATE_APPROVED, "approved by the user", at)
            connection.execute(
                "UPDATE operation_plan SET approved_digest = ? WHERE operation_id = ?",
                (plan_digest, operation_id),
            )
    if problem is not None:
        raise problem
    return plan


def begin(
    connection: sqlite3.Connection,
    operation_id: str,
    *,
    observed_target_digest: str,
    at: str,
) -> Plan:
    """Take the lock, re-check every precondition, and start applying.

    The order is the requirement. `REQ-806` wants the exact plan hash, the lock
    and a fresh look at the target, and the look has to be on the *inside* of
    the lock — checking first and locking after leaves a window in which the
    target moves and the plan is applied to something it was not made for.

    A precondition that fails marks the plan `stale` and commits that mark
    before raising, for the same reason as `approve`.
    """
    problem: CliFailure | None = None
    with transaction(connection):
        plan = _require(connection, operation_id)
        current = journal.get(connection, operation_id)
        if current is None or current.state != STATE_APPROVED:
            problem = CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "only an approved plan may be applied",
                details={
                    "operation_id": operation_id,
                    "state": "" if current is None else current.state,
                },
            )
        elif at >= plan.expires_at:
            _move(connection, operation_id, STATE_STALE, "the plan expired before applying", at)
            problem = CliFailure(
                "AI_STP_PLAN_STALE",
                "this plan expired before it was applied",
                details={"operation_id": operation_id, "expired_at": plan.expires_at},
            )
        elif observed_target_digest != plan.expected_target_digest:
            _move(connection, operation_id, STATE_STALE, "the target moved under the plan", at)
            problem = CliFailure(
                "AI_STP_PLAN_STALE",
                "the target changed since this plan was made",
                details={
                    "operation_id": operation_id,
                    "expected": plan.expected_target_digest,
                    "found": observed_target_digest,
                },
            )
        else:
            _move(
                connection,
                operation_id,
                STATE_APPLYING,
                "preconditions re-checked under the lock",
                at,
            )
    if problem is not None:
        raise problem
    return plan


def applied(
    connection: sqlite3.Connection,
    operation_id: str,
    *,
    at: str,
    backup_ref: str | None = None,
) -> None:
    """Record that the effect happened and nothing has checked it yet.

    This state is the point of the whole machine. It is written *after* the
    provider changed the target and *before* anyone looked, so an operation
    found sitting here after a crash is exactly the one that needs a person.
    """
    with transaction(connection):
        _move(connection, operation_id, STATE_APPLIED_UNVERIFIED, "the effect was applied", at)
        if backup_ref is not None:
            connection.execute(
                "UPDATE operation_plan SET backup_ref = ? WHERE operation_id = ?",
                (backup_ref, operation_id),
            )


def verify(
    connection: sqlite3.Connection,
    operation_id: str,
    *,
    postconditions_met: bool,
    at: str,
    evidence: str | None = None,
    observed_target_digest: str = "",
) -> str:
    """Turn a checked effect into success, or into the honest other answer.

    `verified` is the only name for success and only a durable postcondition
    check produces it. A failed check gives `partial`, not `failed`: the effect
    already happened, and calling that a failure would say nothing was done.
    """
    with transaction(connection):
        current = journal.get(connection, operation_id)
        if current is None or current.state != STATE_APPLIED_UNVERIFIED:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "only an applied and unverified operation can be verified",
                details={
                    "operation_id": operation_id,
                    "state": "" if current is None else current.state,
                },
            )
        state = STATE_VERIFIED if postconditions_met else STATE_PARTIAL
        if state == STATE_VERIFIED and observed_target_digest:
            # What the target became. Local drift is the difference between this
            # and what the target reads later, and without it there is nothing
            # to compare against — only the digest from *before* the change.
            connection.execute(
                "UPDATE operation_plan SET verified_target_digest = ? WHERE operation_id = ?",
                (observed_target_digest, operation_id),
            )
        _move(
            connection,
            operation_id,
            state,
            "postconditions hold" if postconditions_met else "postconditions do not hold",
            at,
            evidence,
        )
        return state


def interrupted(connection: sqlite3.Connection, operation_id: str, *, at: str, reason: str) -> None:
    """Record that an apply stopped without saying whether it took effect.

    Always `partial`, never `failed`. `operation.md` says an expired external
    call does not prove the absence of an effect, so there is no argument shape
    here that lets a caller record one as if it did.
    """
    with transaction(connection):
        _move(connection, operation_id, STATE_PARTIAL, reason, at)


def fail(connection: sqlite3.Connection, operation_id: str, *, at: str, reason: str) -> None:
    """Record a failure with no effect. Only before the effect."""
    with transaction(connection):
        current = journal.get(connection, operation_id)
        if current is not None and current.state == STATE_APPLIED_UNVERIFIED:
            raise CliFailure(
                "AI_STP_CONFLICT",
                "an operation whose effect already happened cannot be recorded as a plain failure",
                details={"operation_id": operation_id},
                next_actions=["install recover --operation <id> --json"],
            )
        _move(connection, operation_id, STATE_FAILED, reason, at)


def stale(connection: sqlite3.Connection, operation_id: str, *, at: str, reason: str) -> None:
    """Record the provider's locked compare-and-apply refusal before any effect.

    The provider protocol reserves ``stale`` for the case where the provider
    acquired its own target lock, found a digest other than the approved one
    and refused the effect.  Keeping that result distinct from ``partial`` is
    load-bearing: the former proves that no effect happened, while the latter
    says that an effect may have happened and requires recovery.
    """
    with transaction(connection):
        _move(connection, operation_id, STATE_STALE, reason, at)


def roll_back(connection: sqlite3.Connection, operation_id: str, *, at: str, reason: str) -> None:
    """Record that the effect was undone and the target is back where it was."""
    with transaction(connection):
        _move(connection, operation_id, STATE_ROLLED_BACK, reason, at)


def cancel(connection: sqlite3.Connection, operation_id: str, *, at: str, reason: str) -> None:
    """Cancel before any effect. Refused once applying has begun.

    Cancelling claims nothing was done. After `applying` nobody can claim that,
    which is why the transition table has no such move and this reports the
    conflict rather than quietly recording a lie.
    """
    with transaction(connection):
        _move(connection, operation_id, STATE_CANCELLED, reason, at)


def events(connection: sqlite3.Connection, operation_id: str) -> tuple[Event, ...]:
    """The whole append-only stream for one operation, in order."""
    rows = connection.execute(
        "SELECT * FROM operation_event WHERE operation_id = ? ORDER BY sequence",
        (operation_id,),
    ).fetchall()
    return tuple(
        Event(
            sequence=int(row["sequence"]),
            at=str(row["at"]),
            state_before=str(row["state_before"]),
            state_after=str(row["state_after"]),
            result=str(row["result"]),
            evidence=None if row["evidence"] is None else str(row["evidence"]),
        )
        for row in rows
    )


def recovery(connection: sqlite3.Connection, operation_id: str) -> Recovery:
    """What a stopped operation left, and what may be done about it."""
    current = journal.get(connection, operation_id)
    if current is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no operation with that identifier is recorded",
            details={"operation_id": operation_id},
        )
    row = connection.execute(
        "SELECT backup_ref FROM operation_plan WHERE operation_id = ?", (operation_id,)
    ).fetchone()
    done = tuple(
        item.result
        for item in events(connection, operation_id)
        if item.state_after in {STATE_APPLIED_UNVERIFIED, STATE_APPLYING}
    )
    return Recovery(
        operation_id=operation_id,
        state=current.state,
        effects_recorded=done,
        backup_ref=None if row is None or row["backup_ref"] is None else str(row["backup_ref"]),
        next_actions=_next_actions(current.state),
    )


def backup_reference(connection: sqlite3.Connection, operation_id: str) -> str | None:
    """Return the exact provider-owned backup reference recorded for an operation."""
    row = connection.execute(
        "SELECT backup_ref FROM operation_plan WHERE operation_id = ?", (operation_id,)
    ).fetchone()
    return None if row is None or row["backup_ref"] is None else str(row["backup_ref"])


def resumable(connection: sqlite3.Connection) -> tuple[Recovery, ...]:
    """Every operation that stopped without a settled outcome.

    `partial` is included even though it is terminal: it is an outcome that
    still needs a person, and an operation nobody is told about is one nobody
    recovers.
    """
    stopped = [
        item
        for item in journal.unsettled(connection)
        if item.state not in journal.SETTLED or item.state == STATE_PARTIAL
    ]
    partial = connection.execute(
        "SELECT operation_id FROM operation WHERE state = ? ORDER BY started_at, operation_id",
        (STATE_PARTIAL,),
    ).fetchall()
    identifiers = [item.operation_id for item in stopped]
    identifiers.extend(
        str(row["operation_id"]) for row in partial if str(row["operation_id"]) not in identifiers
    )
    return tuple(recovery(connection, item) for item in identifiers)


def _next_actions(state: str) -> tuple[str, ...]:
    """What may follow, derived from the transition table rather than restated."""
    if state == STATE_PARTIAL:
        # Terminal, and the one that needs a person. The next step is a new plan
        # built from the recovery report, not a retry of this operation.
        return ("inspect the target", "plan a recovery operation")
    allowed = journal.TRANSITIONS.get(state, frozenset())
    return tuple(sorted(allowed))


def _record(
    connection: sqlite3.Connection,
    operation_id: str,
    before: str,
    after: str,
    result: str,
    at: str,
    evidence: str | None = None,
) -> None:
    """Append one event with per-operation and global serialized sequences."""
    row = connection.execute(
        "SELECT max(sequence) AS held FROM operation_event WHERE operation_id = ?",
        (operation_id,),
    ).fetchone()
    held = 0 if row is None or row["held"] is None else int(row["held"])
    global_row = connection.execute(
        "SELECT max(global_sequence) AS held FROM operation_event"
    ).fetchone()
    global_held = 0 if global_row is None or global_row["held"] is None else int(global_row["held"])
    connection.execute(
        """
        INSERT INTO operation_event
            (operation_id, sequence, global_sequence, at,
             state_before, state_after, result, evidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (operation_id, held + 1, global_held + 1, at, before, after, result, evidence),
    )


def _move(
    connection: sqlite3.Connection,
    operation_id: str,
    state: str,
    result: str,
    at: str,
    evidence: str | None = None,
) -> None:
    """Move the operation and record the move in one place.

    A transition without an event would leave the state changed and the reason
    lost, which is the failure the journal exists to prevent.
    """
    current = journal.get(connection, operation_id)
    before = "" if current is None else current.state
    if before == STATE_APPLYING and state == STATE_VERIFIED:
        # `journal` allows this because a transactional local write has no
        # window between effect and verification. An installation does: a
        # provider wrote files and nobody has looked yet.
        raise CliFailure(
            "AI_STP_CONFLICT",
            "an installation reaches verified only through applied_unverified",
            details={"operation_id": operation_id},
        )
    journal.settle(connection, operation_id, state, at, result)  # pyright: ignore[reportArgumentType]
    _record(connection, operation_id, before, state, result, at, evidence)


def _by_key(connection: sqlite3.Connection, idempotency_key: str) -> Plan | None:
    row = connection.execute(
        "SELECT * FROM operation_plan WHERE idempotency_key = ?", (idempotency_key,)
    ).fetchone()
    return None if row is None else _decode(row)


def _is_replannable(connection: sqlite3.Connection, operation_id: str) -> bool:
    current = journal.get(connection, operation_id)
    if current is None:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "an installation plan has no operation state",
            details={"operation_id": operation_id},
        )
    return current.state in REPLANNABLE_STATES


def _retire_idempotency_key(
    connection: sqlite3.Connection, operation_id: str, idempotency_key: str
) -> None:
    """Preserve the old operation while handing its logical retry key forward."""
    retired = f"retired:{operation_id}:{idempotency_key}"
    changed = connection.execute(
        "UPDATE operation_plan SET idempotency_key = ? "
        "WHERE operation_id = ? AND idempotency_key = ?",
        (retired, operation_id, idempotency_key),
    ).rowcount
    if changed != 1:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the installation idempotency key changed while replanning",
            details={"operation_id": operation_id},
        )


def _require(connection: sqlite3.Connection, operation_id: str) -> Plan:
    row = connection.execute(
        "SELECT * FROM operation_plan WHERE operation_id = ?", (operation_id,)
    ).fetchone()
    if row is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no plan with that operation identifier is recorded",
            details={"operation_id": operation_id},
        )
    return _decode(row)


def _decode(row: sqlite3.Row) -> Plan:
    decoded: object = json.loads(str(row["effects"]))
    effects = (
        tuple(str(item) for item in cast(list[object], decoded))
        if isinstance(decoded, list)
        else ()
    )
    return Plan(
        operation_id=str(row["operation_id"]),
        action=str(row["action"]),
        author=str(row["author"]),
        target_id=str(row["target_id"]),
        expected_target_digest=str(row["expected_target_digest"]),
        provider_version=str(row["provider_version"]),
        provider_protocol_version=(
            1 if row["provider_protocol_version"] is None else int(row["provider_protocol_version"])
        ),
        provider_target="" if row["provider_target"] is None else str(row["provider_target"]),
        provider_release_manifest=(
            ""
            if row["provider_release_manifest"] is None
            else str(row["provider_release_manifest"])
        ),
        provider_release_recovery=bool(row["provider_release_recovery"]),
        provider_release_trust=(
            "unverified"
            if row["provider_release_trust"] is None
            else str(row["provider_release_trust"])
        ),
        provider_release_evidence=(
            ""
            if row["provider_release_evidence"] is None
            else str(row["provider_release_evidence"])
        ),
        bundle_format="" if row["bundle_format"] is None else str(row["bundle_format"]),
        bundle_digest="" if row["bundle_digest"] is None else str(row["bundle_digest"]),
        bundle_artifact_digest=(
            "" if row["bundle_artifact_digest"] is None else str(row["bundle_artifact_digest"])
        ),
        bundle_size=0 if row["bundle_size"] is None else int(row["bundle_size"]),
        provider_plan_digest=(
            "" if row["provider_plan_digest"] is None else str(row["provider_plan_digest"])
        ),
        effects=effects,
        confirmation=str(row["confirmation"]),
        recovery_action=str(row["recovery_action"]),
        expires_at=str(row["expires_at"]),
        created_at=str(row["created_at"]),
        setup_stable_id="" if row["setup_stable_id"] is None else str(row["setup_stable_id"]),
        setup_version="" if row["setup_version"] is None else str(row["setup_version"]),
        schema_version=(
            1 if row["plan_schema_version"] is None else int(row["plan_schema_version"])
        ),
    )
