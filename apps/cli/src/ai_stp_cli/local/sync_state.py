"""Durable client state for replay-safe private revision synchronisation."""

import sqlite3
import uuid
from dataclasses import dataclass
from typing import cast

from ai_stp_cli.cloud import login
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import lifecycle, revisions, versions
from ai_stp_cli.local.database import transaction
from ai_stp_contracts.sync import SyncEvent, SyncEventReceipt, SyncPullResponse, SyncStreamEvent
from ai_stp_contracts.sync_payload import SyncPayloadRejection, check_sync_payload
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.revisions import revision_id
from ai_stp_passports.envelope import PassportEnvelope, verify_revision_id


@dataclass(frozen=True)
class Pending:
    """One exact request retained until its durable receipt is recorded."""

    request: SyncEvent
    state: str


@dataclass(frozen=True)
class MappingRecord:
    """Known remote identity and outcome for one local revision."""

    event_id: str
    remote_revision_id: str
    state: str


_KIND = {
    "developer": "developer_passport",
    "component": "component_private",
    "setup": "setup_private",
}


def _validate_payload(value: object) -> None:
    """Refuse secret-bearing fields and local paths before any network call.

    The rule itself belongs to `ai_stp_contracts.sync_payload`, which the server
    boundary enforces as well. Keeping a second copy here is what let the two
    sides disagree about `required_env`; this function only turns the shared
    refusal into the CLI's typed failure.
    """
    try:
        check_sync_payload(value)
    except SyncPayloadRejection as rejection:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            rejection.reason,
            details={"field": rejection.path},
        ) from rejection


def _remote_parents(
    connection: sqlite3.Connection, account_id: str, local_parents: tuple[str, ...]
) -> list[str]:
    result: list[str] = []
    for parent in local_parents:
        row = connection.execute(
            "SELECT remote_revision_id FROM sync_event "
            "WHERE account_id = ? AND local_revision_id = ? "
            "AND state IN ('accepted', 'conflict')",
            (account_id, parent),
        ).fetchone()
        if row is None:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "a parent revision must be accepted before its child can be pushed",
                details={"revision_id": parent},
            )
        result.append(str(row[0]))
    return result


def mapping_for_local(
    connection: sqlite3.Connection, *, account_id: str, local_revision_id: str
) -> MappingRecord | None:
    row = connection.execute(
        "SELECT event_id, remote_revision_id, state FROM sync_event "
        "WHERE account_id = ? AND local_revision_id = ? "
        "AND state IN ('accepted', 'conflict') ORDER BY direction LIMIT 1",
        (account_id, local_revision_id),
    ).fetchone()
    if row is None:
        return None
    return MappingRecord(str(row[0]), str(row[1]), str(row[2]))


def prepare(
    connection: sqlite3.Connection,
    *,
    account_id: str,
    device_id: str,
    stored: revisions.StoredRevision,
) -> Pending:
    """Return an existing exact event or durably create it once."""
    known = connection.execute(
        "SELECT request_json, state FROM sync_event "
        "WHERE account_id = ? AND sync_key = ? AND direction = 'push'",
        (account_id, stored.revision_id),
    ).fetchone()
    if known is not None:
        return Pending(SyncEvent.model_validate_json(str(known[0])), str(known[1]))
    entity_kind = _KIND.get(stored.envelope.kind)
    if entity_kind is None:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this local passport kind is not allowed in private sync",
            details={"kind": stored.envelope.kind},
        )
    payload = cast(dict[str, object], stored.envelope.model_dump(mode="json"))
    if stored.envelope.kind in {"component", "setup"}:
        payload["sync_released_versions"] = [
            {
                "version": item.version,
                "passport_digest": item.passport_digest,
                "revision_id": item.revision_id,
                "created_at": item.created_at,
            }
            for item in versions.line(connection, stored.stable_id)
        ]
    _validate_payload(payload)
    remote_parents = _remote_parents(connection, account_id, stored.parents)
    head = connection.execute(
        "SELECT remote_revision_id FROM sync_remote_head WHERE account_id = ? AND entity_id = ?",
        (account_id, stored.stable_id),
    ).fetchone()
    expected_head = None if head is None else str(head[0])
    created_at = stored.created_at
    sealed: dict[str, JsonValue] = {
        "schema_version": 1,
        "entity_id": stored.stable_id,
        "entity_kind": entity_kind,
        "parent_revision_ids": cast(list[JsonValue], remote_parents),
        "operation": "upsert",
        "payload": cast(JsonValue, payload),
        "device_id": device_id,
        "actor_id": account_id,
        "created_at": created_at,
    }
    request = SyncEvent(
        event_id=f"event_{uuid.uuid4().hex}",
        entity_id=stored.stable_id,
        entity_kind=entity_kind,  # pyright: ignore[reportArgumentType]
        revision_id=revision_id(sealed),
        parent_revision_ids=remote_parents,
        device_id=device_id,
        actor_id=account_id,
        operation="upsert",
        content_digest=digest_canonical("ai-stp:revision:v1", cast(JsonValue, payload)),
        created_at=created_at,
        idempotency_key=login.new_idempotency_key(),
        expected_head_revision_id=expected_head,
        payload=payload,
    )
    rendered = canonize(cast(JsonValue, request.model_dump(mode="json"))).decode("utf-8")
    with transaction(connection):
        connection.execute(
            "INSERT INTO sync_event "
            "(account_id, event_id, sync_key, local_revision_id, remote_revision_id, entity_id, "
            "direction, request_json, state, receipt_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'push', ?, 'pending', NULL, ?)",
            (
                account_id,
                request.event_id,
                stored.revision_id,
                stored.revision_id,
                request.revision_id,
                stored.stable_id,
                rendered,
                created_at,
            ),
        )
    return Pending(request, "pending")


def prepare_tombstone(
    connection: sqlite3.Connection,
    *,
    account_id: str,
    device_id: str,
    stable_id: str,
) -> Pending:
    """Create one durable tombstone event for the first local deletion mark."""
    mark = lifecycle.entombed(connection, stable_id)
    if mark is None:
        raise CliFailure("AI_STP_NOT_FOUND", "that identifier has no local tombstone")
    sync_key = f"tombstone:{stable_id}:{mark.created_at}"
    known = connection.execute(
        "SELECT request_json, state FROM sync_event "
        "WHERE account_id = ? AND sync_key = ? AND direction = 'push'",
        (account_id, sync_key),
    ).fetchone()
    if known is not None:
        return Pending(SyncEvent.model_validate_json(str(known[0])), str(known[1]))
    local_head = revisions.head(connection, stable_id)
    if local_head is None:
        raise CliFailure("AI_STP_NOT_FOUND", "the tombstoned entity has no local revision")
    entity_kind = _KIND.get(local_head.envelope.kind)
    if entity_kind is None:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this local passport kind is not allowed in private sync",
        )
    head = connection.execute(
        "SELECT remote_revision_id FROM sync_remote_head WHERE account_id = ? AND entity_id = ?",
        (account_id, stable_id),
    ).fetchone()
    if head is None:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the entity must be accepted remotely before its tombstone can be pushed",
        )
    remote_head = str(head[0])
    payload: dict[str, object] = {}
    sealed: dict[str, JsonValue] = {
        "schema_version": 1,
        "entity_id": stable_id,
        "entity_kind": entity_kind,
        "parent_revision_ids": cast(list[JsonValue], [remote_head]),
        "operation": "tombstone",
        "payload": {},
        "device_id": device_id,
        "actor_id": account_id,
        "created_at": mark.created_at,
    }
    request = SyncEvent(
        event_id=f"event_{uuid.uuid4().hex}",
        entity_id=stable_id,
        entity_kind=entity_kind,  # pyright: ignore[reportArgumentType]
        revision_id=revision_id(sealed),
        parent_revision_ids=[remote_head],
        device_id=device_id,
        actor_id=account_id,
        operation="tombstone",
        content_digest=digest_canonical("ai-stp:revision:v1", cast(JsonValue, payload)),
        created_at=mark.created_at,
        idempotency_key=login.new_idempotency_key(),
        expected_head_revision_id=remote_head,
        payload=payload,
    )
    rendered = canonize(cast(JsonValue, request.model_dump(mode="json"))).decode("utf-8")
    with transaction(connection):
        connection.execute(
            "INSERT INTO sync_event "
            "(account_id, event_id, sync_key, local_revision_id, remote_revision_id, entity_id, "
            "direction, request_json, state, receipt_json, created_at) "
            "VALUES (?, ?, ?, NULL, ?, ?, 'push', ?, 'pending', NULL, ?)",
            (
                account_id,
                request.event_id,
                sync_key,
                request.revision_id,
                stable_id,
                rendered,
                mark.created_at,
            ),
        )
    return Pending(request, "pending")


def record_receipt(
    connection: sqlite3.Connection, *, account_id: str, receipt: SyncEventReceipt
) -> None:
    """Atomically persist a receipt and any accepted remote head/cursor."""
    rendered = canonize(cast(JsonValue, receipt.model_dump(mode="json"))).decode("utf-8")
    with transaction(connection):
        changed = connection.execute(
            "UPDATE sync_event SET state = ?, receipt_json = ? "
            "WHERE account_id = ? AND event_id = ?",
            (receipt.state, rendered, account_id, receipt.event_id),
        ).rowcount
        if changed != 1:
            raise CliFailure("AI_STP_CONFLICT", "the sync receipt names no pending local event")
        if receipt.state == "accepted" and receipt.server_head_revision_id is not None:
            row = connection.execute(
                "SELECT entity_id FROM sync_event WHERE account_id = ? AND event_id = ?",
                (account_id, receipt.event_id),
            ).fetchone()
            assert row is not None
            connection.execute(
                "INSERT INTO sync_remote_head (account_id, entity_id, remote_revision_id) "
                "VALUES (?, ?, ?) ON CONFLICT (account_id, entity_id) DO UPDATE SET "
                "remote_revision_id = excluded.remote_revision_id",
                (account_id, str(row[0]), receipt.server_head_revision_id),
            )


def unreachable_server_head(connection: sqlite3.Connection, stable_id: str) -> str | None:
    """A server head this device recorded but never received, if there is one.

    A receipt is durable local knowledge: when the server refused a push it
    named the head it holds. If that revision is absent from this registry, the
    device is behind in a way no local read can resolve — and answering
    `up_to_date` from local heads alone would contradict the refusal this
    device already stored.
    """
    row = connection.execute(
        "SELECT receipt_json FROM sync_event "
        "WHERE entity_id = ? AND receipt_json IS NOT NULL "
        "ORDER BY created_at DESC, rowid DESC LIMIT 1",
        (stable_id,),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    held = SyncEventReceipt.model_validate_json(row[0]).server_head_revision_id
    if held is None:
        return None
    # Remote and local revision ids are not the same value: an applied event is
    # resealed against local parents, and `sync_event` is what maps one to the
    # other. Asking the revision table directly would call every received head
    # unreachable.
    known = connection.execute(
        "SELECT 1 FROM sync_event WHERE remote_revision_id = ?", (held,)
    ).fetchone()
    return None if known is not None else held


def saved_receipt(
    connection: sqlite3.Connection, *, account_id: str, event_id: str
) -> SyncEventReceipt | None:
    row = connection.execute(
        "SELECT receipt_json FROM sync_event WHERE account_id = ? AND event_id = ?",
        (account_id, event_id),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return SyncEventReceipt.model_validate_json(str(row[0]))


def cursor(connection: sqlite3.Connection, account_id: str) -> str | None:
    row = connection.execute(
        "SELECT cursor FROM sync_cursor WHERE account_id = ?", (account_id,)
    ).fetchone()
    return None if row is None or row[0] is None else str(row[0])


def _apply_event(connection: sqlite3.Connection, *, account_id: str, event: SyncStreamEvent) -> str:
    sealed: dict[str, JsonValue] = {
        "schema_version": 1,
        "entity_id": event.entity_id,
        "entity_kind": event.entity_kind,
        "parent_revision_ids": cast(list[JsonValue], event.parent_revision_ids),
        "operation": event.operation,
        "payload": cast(JsonValue, event.payload),
        "device_id": event.device_id,
        "actor_id": event.actor_id,
        "created_at": event.created_at,
    }
    if (
        revision_id(sealed) != event.revision_id
        or digest_canonical("ai-stp:revision:v1", cast(JsonValue, event.payload))
        != event.content_digest
        or event.actor_id != account_id
    ):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a pulled event fails its content-addressed account binding",
        )
    known = connection.execute(
        "SELECT state FROM sync_event WHERE account_id = ? AND remote_revision_id = ?",
        (account_id, event.revision_id),
    ).fetchone()
    if known is not None:
        return "replayed"
    local_revision_id: str | None = None
    if event.operation == "upsert":
        payload = dict(event.payload)
        raw_versions_value = payload.pop("sync_released_versions", [])
        if not isinstance(raw_versions_value, list):
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR", "pulled released versions must be a bounded list"
            )
        raw_versions = cast(list[object], raw_versions_value)
        if len(raw_versions) > 128:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR", "pulled released versions must be a bounded list"
            )
        try:
            envelope = PassportEnvelope.model_validate(payload)
        except ValueError as error:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR", "a pulled sync payload is not a passport envelope"
            ) from error
        # Which of the three, and for which event. The refusal used to carry
        # neither, and a page is applied atomically: one unacceptable event
        # stops every future pull for that account, with nothing in the answer
        # to say which one or why. Two such events reached production before
        # `seal_envelope` was corrected, and finding them meant reimplementing
        # this check outside the CLI to ask it one condition at a time.
        mismatch = {
            "revision_id is not derived from the payload": not verify_revision_id(envelope),
            "stable_id does not match entity_id": envelope.stable_id != event.entity_id,
            "kind does not match entity_kind": _KIND.get(envelope.kind) != event.entity_kind,
        }
        failed = [reason for reason, broken in mismatch.items() if broken]
        if failed:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "a pulled sync payload does not match its exact event coordinates",
                details={
                    "event_id": event.event_id,
                    "entity_id": event.entity_id,
                    "entity_kind": event.entity_kind,
                    "revision_id": envelope.revision_id,
                    "reason": "; ".join(failed),
                },
            )
        document = cast(dict[str, JsonValue], envelope.model_dump(mode="json"))
        document.pop("revision_id", None)
        stored = revisions.commit(
            connection,
            document,
            device_id=event.device_id,
            operation_id=event.event_id,
        )
        local_revision_id = stored.revision_id
        for raw in raw_versions:
            if not isinstance(raw, dict):
                raise CliFailure(
                    "AI_STP_VALIDATION_ERROR", "a pulled released version is not an object"
                )
            item = cast(dict[str, object], raw)
            try:
                version = str(item["version"])
                passport_digest = str(item["passport_digest"])
                version_revision = str(item["revision_id"])
                created_at = str(item["created_at"])
            except KeyError as error:
                raise CliFailure(
                    "AI_STP_VALIDATION_ERROR", "a pulled released version is incomplete"
                ) from error
            # A released number points at a revision, and this device may not
            # hold it: the revision's own event was walked past with
            # `--skip-event`, so its number arrives with nothing to stand on.
            # Measured on a real account after such a skip, the recorder's
            # foreign key refused and the refusal reached the caller as
            # `AI_STP_INTERNAL: IntegrityError` — a defect report about a
            # decision the operator had just made. Named here instead, with
            # the way past it, which is the same one that led here.
            if revisions.get(connection, version_revision) is None:
                raise CliFailure(
                    "AI_STP_CONFLICT",
                    "a pulled released version points at a revision this device does not hold",
                    details={
                        "stable_id": event.entity_id,
                        "version": version,
                        "version_revision_id": version_revision,
                    },
                    next_actions=["sync pull --skip-event <event_id> --confirm --json"],
                )
            versions.record(
                connection,
                stable_id=event.entity_id,
                version=version,
                passport_digest=passport_digest,
                revision_id=version_revision,
                at=created_at,
            )
    else:
        lifecycle.entomb(
            connection,
            event.entity_id,
            reason="received account tombstone from sync",
            at=event.created_at,
        )
    connection.execute(
        "INSERT INTO sync_event "
        "(account_id, event_id, sync_key, local_revision_id, remote_revision_id, entity_id, "
        "direction, request_json, state, receipt_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'pull', ?, 'accepted', NULL, ?)",
        (
            account_id,
            event.event_id,
            event.revision_id,
            local_revision_id,
            event.revision_id,
            event.entity_id,
            canonize(cast(JsonValue, event.model_dump(mode="json"))).decode("utf-8"),
            event.created_at,
        ),
    )
    connection.execute(
        "INSERT INTO sync_remote_head (account_id, entity_id, remote_revision_id) "
        "VALUES (?, ?, ?) ON CONFLICT (account_id, entity_id) DO UPDATE SET "
        "remote_revision_id = excluded.remote_revision_id",
        (account_id, event.entity_id, event.revision_id),
    )
    return "applied"


def abandoned_events(connection: sqlite3.Connection, account_id: str) -> frozenset[str]:
    """Every event this device was told to walk past for this account."""
    rows = connection.execute(
        "SELECT event_id FROM sync_abandoned_event WHERE account_id = ?", (account_id,)
    ).fetchall()
    return frozenset(str(row[0]) for row in rows)


def apply_page(
    connection: sqlite3.Connection,
    *,
    account_id: str,
    response: SyncPullResponse,
    at: str,
    skip_event_ids: frozenset[str] = frozenset(),
) -> tuple[int, int, list[str]]:
    """Apply one ordered page and advance its opaque cursor in one transaction.

    A null `next_cursor` is pagination state, not a position. `PageInfo` defines
    it as "no page after this one", and the server emits it for the last page of
    a walk — so storing it would erase the only position this device has.

    That is not a slow resync, it is a loop that never closes: `pull` takes one
    page per invocation, so reaching the end would clear the cursor, the next
    invocation would restart from the beginning, walk to the end and clear it
    again. An account whose whole outbox fits one page would replay that page
    forever, and `pull` could never answer "nothing new".

    So the stored position only ever moves forward. Ending on the last page
    leaves it on the page before, and the next `pull` re-reads at most one page,
    which `_apply_event` settles as replayed rather than applied. Reducing that
    to zero requires a cursor on every non-empty page; the cursor is signed and
    account-bound, so this side cannot mint one and must not try.
    """
    applied = replayed = 0
    skipped: list[str] = []
    with transaction(connection):
        # An abandonment is remembered. The ids named on this call join the
        # ones this device recorded before, so a lineage walked past once is
        # not named again on every later pull — measured on a real account,
        # five events had to travel as flags through every invocation, and a
        # device that forgot one stopped exactly where it had already decided
        # to move on.
        remembered = abandoned_events(connection, account_id)
        for event_id in sorted(skip_event_ids - remembered):
            connection.execute(
                "INSERT OR IGNORE INTO sync_abandoned_event (account_id, event_id, abandoned_at) "
                "VALUES (?, ?, ?)",
                (account_id, event_id, at),
            )
        walk_past = skip_event_ids | remembered
        for event in response.items:
            # Named, one exact id at a time, and never inferred. An event that
            # fails validation stops this account's pulls on every device and
            # no page size gets past it — observed on production, where two
            # events sealed before `seal_envelope` was corrected blocked the
            # walk permanently and nothing could move the cursor beyond them.
            #
            # Walking past one is abandoning a revision, so the caller has to
            # know which. `--skip-event` takes the exact id the refusal named
            # and nothing else: there is deliberately no "skip whatever is
            # broken", because that would silently drop a real revision the
            # moment a different defect made one unreadable.
            if event.event_id in walk_past:
                skipped.append(event.event_id)
                continue
            try:
                outcome = _apply_event(connection, account_id=account_id, event=event)
            except CliFailure as failure:
                # A refusal raised deeper than this loop knows nothing about
                # sync and cannot name the event, so the id `--skip-event`
                # needs is added here, where it is in hand. The code, message
                # and existing details are the deeper check's answer and stay
                # exactly as it gave them.
                raise CliFailure(
                    failure.code,
                    failure.message,
                    details={
                        **failure.details,
                        "event_id": event.event_id,
                        "entity_id": event.entity_id,
                        "entity_kind": event.entity_kind,
                        "revision_id": event.revision_id,
                    },
                    # The one action that moves past this event, with the id
                    # filled in: a template the caller has to complete from
                    # `details` is a second question about an answer already
                    # in hand.
                    next_actions=[
                        f"sync pull --skip-event {event.event_id} --confirm --json",
                        *[
                            action
                            for action in failure.next_actions
                            if "--skip-event" not in action
                        ],
                    ],
                ) from failure
            applied += outcome == "applied"
            replayed += outcome == "replayed"
        if response.page.next_cursor is None:
            # The row still records that a walk reached its end here, so a
            # cursor absent because nothing was ever pulled stays
            # distinguishable from one absent because the walk finished.
            connection.execute(
                "INSERT INTO sync_cursor (account_id, cursor, updated_at) VALUES (?, NULL, ?) "
                "ON CONFLICT (account_id) DO UPDATE SET updated_at = excluded.updated_at",
                (account_id, at),
            )
        else:
            connection.execute(
                "INSERT INTO sync_cursor (account_id, cursor, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT (account_id) DO UPDATE SET cursor = excluded.cursor, "
                "updated_at = excluded.updated_at",
                (account_id, response.page.next_cursor, at),
            )
    return applied, replayed, skipped
