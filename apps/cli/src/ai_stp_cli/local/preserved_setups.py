"""Local setup identities bound to complete retained native recovery snapshots."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import installation
from ai_stp_cli.local.database import transaction
from ai_stp_cli.provider.status import BackupObservation
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.ids import new_id


@dataclass(frozen=True)
class PreservedSetup:
    """An immutable local setup with a separate provider recovery identity."""

    stable_id: str
    operation_id: str
    target_id: str
    provider_target: str
    target_scope: str
    provider_id: str
    backup_ref: str
    snapshot_digest: str
    roots: tuple[str, ...]
    excluded: tuple[str, ...]
    created_at: str
    base_root: str = "target"


def _read(row: sqlite3.Row) -> PreservedSetup:
    values = dict(row)
    values["roots"] = tuple(json.loads(values["roots"]))
    values["excluded"] = tuple(json.loads(values["excluded"]))
    return PreservedSetup(**values)


def held(connection: sqlite3.Connection, stable_id: str) -> PreservedSetup | None:
    """Read one saved setup without requiring its target to be online."""
    row = connection.execute(
        "SELECT * FROM preserved_setup WHERE stable_id = ?", (stable_id,)
    ).fetchone()
    return None if row is None else _read(row)


def for_operation(connection: sqlite3.Connection, operation_id: str) -> PreservedSetup | None:
    """Return the same setup identity when a completed operation is retried."""
    row = connection.execute(
        "SELECT * FROM preserved_setup WHERE operation_id = ?", (operation_id,)
    ).fetchone()
    return None if row is None else _read(row)


def all_saved(connection: sqlite3.Connection, target_id: str = "") -> tuple[PreservedSetup, ...]:
    """List preserved setups in stable capture order after a process restart."""
    rows = connection.execute(
        "SELECT * FROM preserved_setup WHERE (? = '' OR target_id = ?) "
        "ORDER BY created_at, stable_id",
        (target_id, target_id),
    ).fetchall()
    return tuple(_read(row) for row in rows)


def register(
    connection: sqlite3.Connection,
    *,
    plan: installation.Plan,
    provider_id: str,
    artifact: dict[str, JsonValue],
    observed: BackupObservation,
    at: str,
) -> PreservedSetup:
    """Require fresh provider evidence before giving captured state a setup identity."""
    binding = artifact.get("native_capture")
    snapshot = observed.native_snapshot
    if (
        not isinstance(binding, dict)
        or snapshot is None
        or snapshot.verification != "verified"
        or observed.held is not True
        or snapshot.operation_id != plan.operation_id
        or snapshot.digest != binding.get("current_digest")
        or snapshot.base_root != binding.get("base_root", "target")
        or list(snapshot.roots) != binding.get("roots")
        or list(snapshot.excluded) != binding.get("excluded")
    ):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "complete retained native recovery evidence is unavailable",
        )
    with transaction(connection):
        existing = for_operation(connection, plan.operation_id)
        if existing is not None:
            if (
                existing.backup_ref != observed.backup_ref
                or existing.snapshot_digest != snapshot.digest
            ):
                raise CliFailure(
                    "AI_STP_CONFLICT", "the operation already preserved a different native setup"
                )
            return existing
        stable_id = new_id("setup")
        connection.execute(
            "INSERT INTO preserved_setup VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                stable_id,
                plan.operation_id,
                plan.target_id,
                plan.provider_target,
                str(artifact.get("target_scope") or "global"),
                provider_id,
                observed.backup_ref,
                snapshot.digest,
                json.dumps(snapshot.roots),
                json.dumps(snapshot.excluded),
                at,
                snapshot.base_root,
            ),
        )
        return cast(PreservedSetup, held(connection, stable_id))
