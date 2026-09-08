"""Snapshot closure and durable legacy references for private version sync."""

from __future__ import annotations

import sqlite3
from typing import cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, revisions, versions
from ai_stp_contracts.machine_help import SyncPendingVersion
from ai_stp_contracts.sync_versions import (
    MAX_VERSIONS,
    VersionBinding,
    VersionBindingError,
    parse_binding,
    verify_snapshot,
)
from ai_stp_foundation.canonical import JsonValue


def _invalid(reason: str) -> CliFailure:
    return CliFailure("AI_STP_VALIDATION_ERROR", reason)


def outgoing(connection: sqlite3.Connection, stored: revisions.StoredRevision) -> list[JsonValue]:
    line = versions.line(connection, stored.stable_id)
    if len(line) > MAX_VERSIONS:
        raise _invalid("released versions exceed the bounded sync payload")
    result: list[JsonValue] = []
    for item in line:
        snapshot = revisions.get(connection, item.revision_id)
        if snapshot is None:
            raise _invalid("a released version has no retained local snapshot")
        body = cast(dict[str, JsonValue], snapshot.envelope.model_dump(mode="json"))
        row: dict[str, JsonValue] = {
            "version": item.version,
            "passport_digest": item.passport_digest,
            "revision_id": item.revision_id,
            "created_at": item.created_at,
        }
        # Historical versions could refer to an ordinary ancestor. Its event
        # precedes the current head, so it need not become a parentless snapshot.
        if not snapshot.parents:
            try:
                verify_snapshot(body, parse_binding(row, stored.stable_id), stored.envelope.kind)
            except VersionBindingError as error:
                raise _invalid(str(error)) from error
            row["snapshot"] = body
        result.append(row)
    return result


def _no_collision(connection: sqlite3.Connection, account: str, item: VersionBinding) -> None:
    held = next(
        (v for v in versions.line(connection, item.stable_id) if v.version == item.version), None
    )
    pending = connection.execute(
        "SELECT passport_digest, revision_id FROM sync_pending_version "
        "WHERE account_id = ? AND stable_id = ? AND version = ?",
        (account, item.stable_id, item.version),
    ).fetchone()
    if (
        held is not None
        and (held.passport_digest, held.revision_id) != (item.passport_digest, item.revision_id)
    ) or (pending is not None and tuple(pending) != (item.passport_digest, item.revision_id)):
        raise CliFailure(
            "AI_STP_CONFLICT",
            "a released version number already names different immutable content",
            details={"stable_id": item.stable_id, "version": item.version},
        )


def receive(
    connection: sqlite3.Connection,
    raw: object,
    *,
    account: str,
    event_id: str,
    stable_id: str,
    kind: str,
    device_id: str,
) -> None:
    if not isinstance(raw, dict):
        raise _invalid("a pulled released version is not an object")
    row = cast(dict[str, object], raw)
    try:
        item = parse_binding(row, stable_id)
    except VersionBindingError as error:
        raise _invalid(str(error)) from error
    _no_collision(connection, account, item)
    if "snapshot" in row:
        try:
            snapshot = verify_snapshot(row["snapshot"], item, kind)
        except VersionBindingError as error:
            raise _invalid(str(error)) from error
        revisions.store_snapshot(
            connection,
            cast(dict[str, JsonValue], snapshot.model_dump(mode="json")),
            device_id=device_id,
            operation_id=event_id,
        )
    stored = revisions.get(connection, item.revision_id)
    if stored is None:
        connection.execute(
            "INSERT OR IGNORE INTO sync_pending_version "
            "(account_id, stable_id, version, passport_digest, revision_id, created_at, event_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                account,
                stable_id,
                item.version,
                item.passport_digest,
                item.revision_id,
                item.created_at,
                event_id,
            ),
        )
        return
    if (
        stored.stable_id != stable_id
        or stored.envelope.kind != kind
        or cache.digest_of(cast(JsonValue, stored.envelope.model_dump(mode="json")))
        != item.passport_digest
    ):
        raise _invalid("a pulled released version does not match its retained snapshot")
    versions.record(
        connection,
        stable_id=stable_id,
        version=item.version,
        passport_digest=item.passport_digest,
        revision_id=item.revision_id,
        at=item.created_at,
    )
    connection.execute(
        "DELETE FROM sync_pending_version WHERE account_id = ? AND stable_id = ? AND version = ?",
        (account, stable_id, item.version),
    )


def reconcile(connection: sqlite3.Connection, *, account: str) -> None:
    rows = connection.execute(
        "SELECT p.*, e.kind FROM sync_pending_version p "
        "JOIN revision r ON r.revision_id = p.revision_id "
        "JOIN entity e ON e.stable_id = p.stable_id WHERE p.account_id = ?",
        (account,),
    ).fetchall()
    for row in rows:
        receive(
            connection,
            dict(row),
            account=account,
            event_id=str(row["event_id"]),
            stable_id=str(row["stable_id"]),
            kind=str(row["kind"]),
            device_id="",
        )


def pending(
    connection: sqlite3.Connection, *, account: str
) -> tuple[int, list[SyncPendingVersion]]:
    count = int(
        connection.execute(
            "SELECT COUNT(*) FROM sync_pending_version WHERE account_id = ?", (account,)
        ).fetchone()[0]
    )
    rows = connection.execute(
        "SELECT stable_id, version, passport_digest, revision_id, event_id "
        "FROM sync_pending_version WHERE account_id = ? ORDER BY stable_id, version LIMIT ?",
        (account, MAX_VERSIONS),
    ).fetchall()
    return count, [SyncPendingVersion.model_validate(dict(row)) for row in rows]
