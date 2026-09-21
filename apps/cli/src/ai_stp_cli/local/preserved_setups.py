"""Local setup identities bound to complete retained native recovery snapshots."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import installation, revisions, versions
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


def latest_for(connection: sqlite3.Connection, target_id: str) -> PreservedSetup | None:
    """The most recent user working config for one target. Never an upstream default."""
    held = all_saved(connection, target_id)
    return held[-1] if held else None


@dataclass(frozen=True)
class Origin:
    """The verified setup version this snapshot's target held when it was captured.

    `modified` is None when the preserving operation recorded no reference
    digest to compare the snapshot against.
    """

    stable_id: str
    version: str
    name: str
    modified: bool | None


def origin(connection: sqlite3.Connection, saved: PreservedSetup) -> Origin | None:
    """Derive which recorded setup the captured native state was, if any.

    The fact is read rather than stored: `operation_plan` already names the
    verified setup version that stood on the target when the preserving
    operation started, and the snapshot digest either equals that plan's
    reference digest — the bytes are that setup, untouched — or does not,
    which is the local modification marker.
    """
    prior = connection.execute(
        "SELECT p.setup_stable_id, p.setup_version, "
        "       COALESCE(p.verified_target_digest, p.expected_target_digest) "
        "FROM operation_plan AS p "
        "JOIN operation AS o ON o.operation_id = p.operation_id "
        "WHERE p.target_id = ? AND o.state = ? AND p.setup_stable_id <> '' "
        "  AND o.started_at < (SELECT started_at FROM operation WHERE operation_id = ?) "
        "ORDER BY o.started_at DESC, p.operation_id DESC LIMIT 1",
        (saved.target_id, installation.STATE_VERIFIED, saved.operation_id),
    ).fetchone()
    if prior is None:
        return None
    stable_id, version = str(prior[0]), str(prior[1])
    name = ""
    recorded = versions.held(connection, stable_id, version)
    if recorded is not None:
        revision = revisions.get(connection, recorded.revision_id)
        extra = None if revision is None else revision.envelope.model_extra
        if extra:
            name = str(extra.get("name") or "")
    reference = prior[2]
    modified = (
        None
        if not isinstance(reference, str) or not reference
        else saved.snapshot_digest != reference
    )
    return Origin(stable_id=stable_id, version=version, name=name, modified=modified)


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
