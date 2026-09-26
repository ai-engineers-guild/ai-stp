"""Recover a rollback's exact prior bundle from the local journal.

The backup a rollback restores is ``artifact['backup_ref']`` on its digest-checked
cached provider plan. ``operation_plan.backup_ref`` is the backup taken before
that operation runs, so the column on the rollback itself is a different slot.
Provider backup files are not opened, and a setup is not inferred from the
backup label. Ambiguity, a digest mismatch, a partial or cross-account mutation,
a missing artifact, or a cycle leaves the rollback without a bundle.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, installation, journal, managed_diff
from ai_stp_cli.provider import operation_v3
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import is_digest

_MAX_HOPS = 8
_BINDING = ("organization_id", "project_id", "account_id", "device_id", "scope")


@dataclass(frozen=True)
class RecoveredBundle:
    """The install or update whose verified bytes a rollback put back."""

    source_operation_id: str
    bundle_artifact_digest: str
    setup_stable_id: str
    setup_version: str


def recovered_bundle(connection: sqlite3.Connection, operation_id: str) -> RecoveredBundle | None:
    """The bundle a verified rollback restored, or None when that is not exact."""
    try:
        return _recover(connection, operation_id, frozenset())
    except (CliFailure, OSError, ValueError, TypeError):
        return None


def _recover(
    connection: sqlite3.Connection, operation_id: str, seen: frozenset[str]
) -> RecoveredBundle | None:
    if operation_id in seen or len(seen) >= _MAX_HOPS:
        return None
    seen = seen | {operation_id}
    row = _plan_row(connection, operation_id)
    if row is None or _state(connection, operation_id) != installation.STATE_VERIFIED:
        return None
    action = str(row["action"])
    if action in {"install", "update"}:
        return _from_mutation(row)
    if action != "rollback":
        return None
    binding = _binding(connection, operation_id)
    artifact = _artifact(str(row["provider_plan_digest"] or ""))
    if binding is None or artifact is None:
        return None
    selected = artifact.get("backup_ref")
    restore_native = _native(artifact, "restore_digest")
    restore_target = artifact.get("restore_target_digest")
    if (
        not isinstance(selected, str)
        or not selected
        or restore_native is None
        or not isinstance(restore_target, str)
        or not is_digest(restore_target)
    ):
        return None
    capturer = _capturer(connection, operation_id, selected)
    if (
        capturer is None
        or not _same_surface(row, capturer)
        or _binding(connection, str(capturer["operation_id"])) != binding
    ):
        return None
    captured = _artifact(str(capturer["provider_plan_digest"] or ""))
    if (
        captured is None
        or _native(captured, "current_digest") != restore_native
        or str(capturer["expected_target_digest"] or "") != restore_target
    ):
        return None
    applying = _sequence(connection, operation_id, "applying", earliest=True)
    captured_at = _sequence(connection, str(capturer["operation_id"]), "verified", earliest=False)
    capture_applying = _sequence(
        connection, str(capturer["operation_id"]), "applying", earliest=True
    )
    if (
        applying is None
        or captured_at is None
        or capture_applying is None
        or captured_at >= applying
    ):
        return None
    prior = _prior(connection, capturer, binding, capture_applying)
    if prior is None or str(prior["verified_target_digest"] or "") != restore_target:
        return None
    prior_verified = _sequence(connection, str(prior["operation_id"]), "verified", earliest=False)
    if (
        prior_verified is None
        or prior_verified >= capture_applying
        or _interrupted(
            connection,
            target_id=str(row["target_id"]),
            provider_target=str(row["provider_target"]),
            after=prior_verified,
            before=capture_applying,
        )
    ):
        return None
    prior_action = str(prior["action"])
    if prior_action == "rollback":
        return _recover(connection, str(prior["operation_id"]), seen)
    if prior_action in {"install", "update"}:
        return _from_mutation(prior)
    return None


def _from_mutation(row: sqlite3.Row) -> RecoveredBundle | None:
    digest = str(row["bundle_artifact_digest"] or "")
    if not is_digest(digest):
        return None
    archive = cache.stored_raw_artifact(digest)
    if archive is None:
        return None
    overview = managed_diff.bundle_overview(archive)
    return RecoveredBundle(
        source_operation_id=str(row["operation_id"]),
        bundle_artifact_digest=digest,
        setup_stable_id=str(row["setup_stable_id"] or "") or overview.setup_stable_id,
        setup_version=str(row["setup_version"] or "") or overview.setup_version,
    )


def _plan_row(connection: sqlite3.Connection, operation_id: str) -> sqlite3.Row | None:
    return cast(
        "sqlite3.Row | None",
        connection.execute(
            "SELECT operation_id, action, target_id, provider_target, expected_target_digest, "
            "verified_target_digest, bundle_artifact_digest, provider_plan_digest, "
            "setup_stable_id, setup_version FROM operation_plan WHERE operation_id = ?",
            (operation_id,),
        ).fetchone(),
    )


def _state(connection: sqlite3.Connection, operation_id: str) -> str:
    held = journal.get(connection, operation_id)
    return "" if held is None else held.state


def _binding(
    connection: sqlite3.Connection, operation_id: str
) -> tuple[str, str, str, str, str] | None:
    row = connection.execute(
        "SELECT organization_id, project_id, account_id, device_id, scope "
        "FROM operation_corporate_binding WHERE operation_id = ?",
        (operation_id,),
    ).fetchone()
    if row is None:
        return None
    return cast(
        "tuple[str, str, str, str, str]",
        tuple(str(row[name]) for name in _BINDING),
    )


def _artifact(digest: str) -> dict[str, JsonValue] | None:
    if not is_digest(digest):
        return None
    path = cache.stored_provider_plan(digest)
    if path is None:
        return None
    return operation_v3.load_plan(path, digest).artifact


def _native(artifact: dict[str, JsonValue], key: str) -> str | None:
    native = artifact.get("native_capture")
    if not isinstance(native, dict):
        return None
    value = cast("dict[str, JsonValue]", native).get(key)
    if not isinstance(value, str) or not is_digest(value):
        return None
    return value


def _capturer(
    connection: sqlite3.Connection, rollback_id: str, backup_ref: str
) -> sqlite3.Row | None:
    rows = connection.execute(
        "SELECT p.operation_id, o.state FROM operation_plan p "
        "JOIN operation o ON o.operation_id = p.operation_id "
        "WHERE p.backup_ref = ? AND p.operation_id != ?",
        (backup_ref, rollback_id),
    ).fetchall()
    if len(rows) != 1 or str(rows[0]["state"]) != installation.STATE_VERIFIED:
        return None
    return _plan_row(connection, str(rows[0]["operation_id"]))


def _same_surface(left: sqlite3.Row, right: sqlite3.Row) -> bool:
    target = str(left["provider_target"] or "")
    return (
        bool(target)
        and target == str(right["provider_target"] or "")
        and str(left["target_id"]) == str(right["target_id"])
    )


def _prior(
    connection: sqlite3.Connection,
    capturer: sqlite3.Row,
    binding: tuple[str, str, str, str, str],
    before: int,
) -> sqlite3.Row | None:
    row = connection.execute(
        "SELECT p.operation_id FROM operation_plan p "
        "JOIN operation o ON o.operation_id = p.operation_id "
        "JOIN operation_corporate_binding b ON b.operation_id = p.operation_id "
        "JOIN operation_event e ON e.operation_id = p.operation_id AND e.state_after = 'verified' "
        "WHERE p.target_id = ? AND p.provider_target = ? AND o.state = 'verified' "
        "AND b.organization_id = ? AND b.project_id = ? AND b.account_id = ? "
        "AND b.device_id = ? AND b.scope = ? "
        "AND p.action IN ('install', 'update', 'remove', 'rollback') "
        "AND p.operation_id != ? AND e.global_sequence < ? "
        "ORDER BY e.global_sequence DESC LIMIT 1",
        (
            str(capturer["target_id"]),
            str(capturer["provider_target"]),
            *binding,
            str(capturer["operation_id"]),
            before,
        ),
    ).fetchone()
    if row is None:
        return None
    return _plan_row(connection, str(row["operation_id"]))


def _sequence(
    connection: sqlite3.Connection, operation_id: str, state: str, *, earliest: bool
) -> int | None:
    if earliest:
        query = (
            "SELECT MIN(global_sequence) FROM operation_event "
            "WHERE operation_id = ? AND state_after = ?"
        )
    else:
        query = (
            "SELECT MAX(global_sequence) FROM operation_event "
            "WHERE operation_id = ? AND state_after = ?"
        )
    row = connection.execute(query, (operation_id, state)).fetchone()
    if row is None or row[0] is None:
        return None
    return int(row[0])


def _interrupted(
    connection: sqlite3.Connection,
    *,
    target_id: str,
    provider_target: str,
    after: int,
    before: int,
) -> bool:
    row = connection.execute(
        "SELECT 1 FROM operation_plan p "
        "JOIN operation_event e ON e.operation_id = p.operation_id "
        "WHERE (p.target_id = ? OR p.provider_target = ?) "
        "AND e.global_sequence > ? AND e.global_sequence < ? AND ("
        "e.state_after IN ('partial', 'rolled_back', 'applied_unverified') "
        "OR (e.state_after IN ('applying', 'verified') "
        "AND p.action IN ('install', 'update', 'remove', 'rollback'))) LIMIT 1",
        (target_id, provider_target, after, before),
    ).fetchone()
    return row is not None
