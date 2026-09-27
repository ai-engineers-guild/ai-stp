"""Bounded, content-free discovery snapshots for linked corporate projects."""

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from ai_stp_cli.cloud.client import Endpoint, call, open_client
from ai_stp_cli.cloud.session import Session
from ai_stp_cli.local import cache, components, installation, managed_diff, restored_provenance
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_contracts.installation_inventory import (
    InstallationInventoryBatch,
    InstallationInventoryReceipt,
    InstallationInventorySnapshot,
    InventoryObservedComponent,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.timestamps import format_timestamp


@dataclass(frozen=True)
class ObservedComponent:
    location_digest: str
    kind: str
    harness: str
    source: str = "external"
    state: str = "present"
    stable_id: str | None = None
    version: str | None = None
    setup_stable_id: str | None = None
    setup_version: str | None = None


@dataclass(frozen=True)
class InventoryScope:
    project_id: str | None
    scope: str
    complete: bool
    components: tuple[ObservedComponent, ...]


def scan(
    connection: sqlite3.Connection,
    organization_id: str,
    *,
    account_id: str | None = None,
    device_id: str | None = None,
) -> tuple[InventoryScope, ...]:
    """Scan global config and linked projects; missing roots remain unknown."""
    roots: list[tuple[str | None, Path | None]] = [(None, None)]
    roots.extend(
        (str(row[0]), Path(str(row[1])))
        for row in connection.execute(
            "SELECT l.remote_project_id, r.root FROM project_link l "
            "JOIN project_root r ON r.stable_id = l.local_project_id "
            "WHERE l.organization_id = ? AND l.state = 'linked'",
            (organization_id,),
        )
    )
    snapshots: list[InventoryScope] = []
    for project_id, root in roots:
        if root is not None and not root.is_dir():
            snapshots.append(InventoryScope(project_id, "project", False, ()))
            continue
        try:
            report = components.discover_report(project=root, include_global=root is None)
        except Exception:
            snapshots.append(
                InventoryScope(project_id, "global" if root is None else "project", False, ())
            )
            continue
        managed, covered, managed_complete = (
            _managed_components(
                connection,
                organization_id=organization_id,
                account_id=account_id,
                device_id=device_id,
                project_id=project_id,
            )
            if account_id is not None and device_id is not None
            else ((), frozenset[str](), True)
        )
        external = tuple(
            ObservedComponent(
                location_digest=digest_canonical(
                    "ai-stp:corporate-inventory-location:v1",
                    {
                        "project_id": project_id,
                        "harness": item.harness_id,
                        "kind": item.component_type,
                        "native_path": item.native_path,
                    },
                ),
                kind=item.component_type,
                harness=item.harness_id,
                source="external" if managed_complete else "unknown",
            )
            for item in report.components
            if not item.holds_secret and not _covered(item.absolute, covered)
        )
        snapshots.append(
            InventoryScope(
                project_id,
                "global" if root is None else "project",
                report.complete and managed_complete,
                (*managed, *external),
            )
        )
    return tuple(snapshots)


def _covered(candidate: Path, paths: frozenset[str]) -> bool:
    location = os.path.normcase(str(candidate.resolve()))
    return any(path == location or path.startswith(f"{location}{os.sep}") for path in paths)


def _managed_components(
    connection: sqlite3.Connection,
    *,
    organization_id: str,
    account_id: str,
    device_id: str,
    project_id: str | None,
) -> tuple[tuple[ObservedComponent, ...], frozenset[str], bool]:
    """Read the newest settled provider result per target and compare its exact bundle."""
    scope = "global" if project_id is None else "project"
    rows = connection.execute(
        "SELECT p.operation_id, p.action, p.target_id, p.provider_target, "
        "p.bundle_artifact_digest, o.state FROM operation_corporate_binding b "
        "JOIN operation_plan p ON p.operation_id = b.operation_id "
        "JOIN operation o ON o.operation_id = b.operation_id "
        "JOIN operation_event e ON e.operation_id = o.operation_id "
        "AND e.state_after = o.state "
        "WHERE b.organization_id = ? AND b.account_id = ? AND b.device_id = ? "
        "AND b.scope = ? AND (? IS NULL OR b.project_id = ?) "
        "AND o.state IN ('verified','partial','rolled_back','failed','stale') "
        "ORDER BY e.global_sequence DESC",
        (organization_id, account_id, device_id, scope, project_id, project_id),
    ).fetchall()
    seen_targets: set[tuple[str, str]] = set()
    observed: list[ObservedComponent] = []
    covered: set[str] = set()
    complete = True
    for row in rows:
        target_id = str(row["target_id"])
        _, harness = installation.target_pair(target_id)
        target = str(row["provider_target"] or "")
        key = (harness, target or target_id)
        if key in seen_targets:
            continue
        seen_targets.add(key)
        if str(row["state"]) != "verified":
            complete = False
            continue
        if str(row["action"]) == "remove":
            continue
        artifact = str(row["bundle_artifact_digest"] or "")
        if str(row["action"]) == "rollback":
            recovered = restored_provenance.recovered_bundle(connection, str(row["operation_id"]))
            artifact = "" if recovered is None else recovered.bundle_artifact_digest
        try:
            archive = cache.stored_raw_artifact(artifact) if artifact else None
        except Exception:
            complete = False
            continue
        if not target or archive is None:
            complete = False
            continue
        try:
            overview = managed_diff.bundle_overview(archive)
            changes = managed_diff.compare(Path(target), overview.manifest)
        except Exception:
            complete = False
            continue
        changed = {change.path: change.code for change in changes}
        for binding in overview.components:
            passport = managed_diff.component_passport(connection, binding)
            if passport is None:
                complete = False
                continue
            unchanged = managed_diff.unchanged_contributions(
                connection, Path(target), passport, harness=harness, scope=scope
            )
            if not binding.member_paths:
                complete = False
                state = "unknown"
            elif any(
                changed.get(path) == "modified" and path not in unchanged
                for path in binding.member_paths
            ):
                state = "modified"
            elif any(changed.get(path) == "deleted" for path in binding.member_paths):
                state = "missing"
            else:
                state = "present"
            covered.update(
                os.path.normcase(str((Path(target) / path).resolve()))
                for path in binding.member_paths
            )
            member_paths = cast("list[JsonValue]", sorted(binding.member_paths))
            location_facts: dict[str, JsonValue] = {
                "project_id": project_id,
                "target_id": target_id,
                "harness": harness,
                "kind": passport.component_type,
                "member_paths": member_paths,
            }
            observed.append(
                ObservedComponent(
                    location_digest=digest_canonical(
                        "ai-stp:corporate-inventory-location:v1",
                        location_facts,
                    ),
                    kind=passport.component_type,
                    harness=harness,
                    source="managed",
                    state=state,
                    stable_id=binding.stable_id,
                    version=binding.version,
                    setup_stable_id=overview.setup_stable_id or None,
                    setup_version=overview.setup_version or None,
                )
            )
    return tuple(observed), frozenset(covered), complete


def enqueue(
    connection: sqlite3.Connection,
    *,
    organization_id: str,
    account_id: str,
    device_id: str,
) -> int:
    """Persist one bounded scan before any network delivery is attempted."""
    scopes = scan(
        connection,
        organization_id,
        account_id=account_id,
        device_id=device_id,
    )
    scanned_at = format_timestamp(datetime.now(UTC))
    for scope in scopes:
        observed: list[InventoryObservedComponent] = []
        complete = scope.complete and len(scope.components) <= 1024
        for item in scope.components[:1024]:
            try:
                observed.append(
                    InventoryObservedComponent(
                        location_digest=item.location_digest,
                        kind=item.kind,  # pyright: ignore[reportArgumentType]
                        harness=item.harness,  # pyright: ignore[reportArgumentType]
                        source=item.source,  # pyright: ignore[reportArgumentType]
                        state=item.state,  # pyright: ignore[reportArgumentType]
                        stable_id=item.stable_id,
                        version=item.version,
                        setup_stable_id=item.setup_stable_id,
                        setup_version=item.setup_version,
                    )
                )
            except ValueError:
                complete = False
        snapshot = InstallationInventorySnapshot(
            scan_id=f"inv:{uuid.uuid4()}",
            organization_id=organization_id,
            employee_id=account_id,
            device_id=device_id,
            project_id=scope.project_id,
            scope=scope.scope,  # pyright: ignore[reportArgumentType]
            scanned_at=scanned_at,
            complete=complete,
            components=observed,
        )
        connection.execute(
            "INSERT INTO corporate_inventory_outbox "
            "(scan_id, organization_id, account_id, device_id, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                snapshot.scan_id,
                organization_id,
                account_id,
                device_id,
                snapshot.model_dump_json(),
                scanned_at,
            ),
        )
    connection.commit()
    return len(scopes)


def sync(
    endpoint: Endpoint,
    session: Session,
    organization_id: str,
    *,
    timeout: float | None = None,
    attempts: int | None = None,
) -> InstallationInventoryReceipt:
    """Delete only snapshots acknowledged as accepted or duplicate."""
    connection = open_registry(configured_path(), create=True)
    try:
        rows = connection.execute(
            "SELECT scan_id, payload_json FROM corporate_inventory_outbox "
            "WHERE organization_id = ? AND account_id = ? AND device_id = ? "
            "ORDER BY created_at, scan_id LIMIT 64",
            (organization_id, session.account_id, session.device_id),
        ).fetchall()
        if not rows:
            return InstallationInventoryReceipt()
        snapshots = [
            InstallationInventorySnapshot.model_validate(json.loads(str(row["payload_json"])))
            for row in rows
        ]
        with open_client(endpoint, access_token=session.access_token, timeout=timeout) as client:
            receipt = call(
                client,
                "POST",
                f"/corporate/organizations/{organization_id}/telemetry/installation-inventory",
                InstallationInventoryReceipt,
                body=InstallationInventoryBatch(snapshots=snapshots),
                attempts=endpoint.max_attempts if attempts is None else attempts,
            )
        sent = {snapshot.scan_id for snapshot in snapshots}
        confirmed = set(receipt.accepted_ids) | set(receipt.duplicate_ids)
        rejected = set(receipt.rejected_ids)
        if confirmed & rejected or confirmed | rejected != sent:
            raise ValueError("inventory receipt does not match batch")
        for scan_id in confirmed:
            connection.execute(
                "DELETE FROM corporate_inventory_outbox WHERE scan_id = ?", (scan_id,)
            )
        connection.commit()
        return receipt
    finally:
        connection.close()
