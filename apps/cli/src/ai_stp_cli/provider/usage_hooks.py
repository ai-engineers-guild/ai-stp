"""Bind terminal native MCP hooks to verified installs; never persist hook payloads."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, installation, managed_diff, restored_provenance
from ai_stp_cli.provider import usage_reporting
from ai_stp_cli.provider.usage_reporting import RecordResult
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_passports.versions import adaptation_for


def derive_event_id(operation_id: str, session_id: str, tool_use_id: str) -> str:
    """Unambiguous, bounded identity shared by repeated posts of the same call."""
    raw = json.dumps([operation_id, session_id, tool_use_id], separators=(",", ":")).encode()
    return "usage_event_" + hashlib.sha256(raw).hexdigest()[:48]


def resolve_operation(
    connection: sqlite3.Connection,
    account_id: str,
    device_id: str,
    harness: str,
    scope: str,
    cwd: Path,
) -> str | None:
    """Use the deepest registered project, its current link, and newest bound operation."""
    roots = [
        (Path(str(row["root"])).resolve(), str(row["stable_id"]))
        for row in connection.execute("SELECT stable_id, root FROM project_root")
        if cwd.resolve().is_relative_to(Path(str(row["root"])).resolve())
    ]
    if not roots:
        return None
    deepest = max(len(root.parts) for root, _ in roots)
    projects = {project for root, project in roots if len(root.parts) == deepest}
    if len(projects) != 1:
        return None
    project = projects.pop()
    row = connection.execute(
        "SELECT b.operation_id FROM operation_corporate_binding b "
        "JOIN operation_plan p ON p.operation_id = b.operation_id "
        "JOIN operation_event e ON e.operation_id = b.operation_id "
        "JOIN project_link l ON l.local_project_id = ? "
        "AND l.organization_id = b.organization_id AND l.remote_project_id = b.project_id "
        "WHERE b.account_id = ? AND b.device_id = ? AND b.scope = ? "
        "AND p.target_id = ? AND l.state = 'linked' "
        "ORDER BY e.global_sequence DESC LIMIT 1",
        (project, account_id, device_id, scope, f"{project}:{harness}"),
    ).fetchone()
    return str(row[0]) if row is not None else None


def record_hook_usage(
    connection: sqlite3.Connection,
    operation_id: str,
    account_id: str,
    device_id: str,
    payload: Mapping[str, object],
    *,
    outbox: sqlite3.Connection | None = None,
    outbox_path: Path | None = None,
    now: float | None = None,
) -> RecordResult:
    """Accept only a terminal MCP result with exact, current corporate provenance."""
    row = connection.execute(
        "SELECT b.*, o.state, p.action, p.target_id, p.provider_target, "
        "p.bundle_artifact_digest FROM operation_corporate_binding b "
        "JOIN operation o ON o.operation_id = b.operation_id "
        "JOIN operation_plan p ON p.operation_id = b.operation_id "
        "WHERE b.operation_id = ?",
        (operation_id,),
    ).fetchone()
    if row is None or row["account_id"] != account_id or row["device_id"] != device_id:
        return "dropped"
    if row["state"] != installation.STATE_VERIFIED or row["action"] == "remove":
        return "dropped"
    _, harness = installation.target_pair(str(row["target_id"]))
    if harness not in {"codex", "grok-build"}:
        return "dropped"
    session_key, call_key, tool_key = (
        ("session_id", "tool_use_id", "tool_name")
        if harness == "codex"
        else ("sessionId", "toolUseId", "toolName")
    )
    session_id, call_id, tool_name = (payload.get(key) for key in (session_key, call_key, tool_key))
    if not all(
        isinstance(value, str) and 0 < len(value) <= 1024
        for value in (session_id, call_id, tool_name)
    ):
        return "dropped"
    tool_name = cast(str, tool_name)
    outcome = _terminal_outcome(harness, payload, tool_name)
    if outcome is None:
        return "dropped"
    parts = tool_name.split("__")
    if harness == "codex":
        if len(parts) < 3 or parts[0] != "mcp":
            return "dropped"
        server = parts[1]
    else:
        if len(parts) < 2 or parts[0] == "mcp":
            return "dropped"
        server = parts[0]
    if not server or not parts[-1] or _superseded(connection, operation_id, row):
        return "dropped"
    digest = str(row["bundle_artifact_digest"] or "")
    if str(row["action"]) == "rollback":
        recovered = restored_provenance.recovered_bundle(connection, operation_id)
        if recovered is None:
            return "dropped"
        digest = recovered.bundle_artifact_digest
    try:
        archive = cache.stored_raw_artifact(digest)
        if archive is None or not row["provider_target"]:
            return "dropped"
        overview = managed_diff.bundle_overview(archive)
        if overview.manifest.target_scope != row["scope"]:
            return "dropped"
        changes = managed_diff.compare(Path(str(row["provider_target"])), overview.manifest)
        changed = {change.path for change in changes}
        matches: list[tuple[managed_diff.ComponentBinding, frozenset[str]]] = []
        for component in overview.components:
            passport = managed_diff.component_passport(connection, component)
            if passport is None or passport.component_type != "mcp":
                continue
            adaptation = adaptation_for(passport, cast(HarnessId, harness))
            scope = next(
                (item for item in adaptation.scope_adaptations if item.scope == row["scope"]), None
            )
            if scope is None:
                continue
            native_ids = {native_id for member in scope.members for native_id in member.native_ids}
            if tool_name in native_ids or server in native_ids or f"mcp__{server}" in native_ids:
                unchanged = managed_diff.unchanged_contributions(
                    connection,
                    Path(str(row["provider_target"])),
                    passport,
                    harness=harness,
                    scope=str(row["scope"]),
                )
                matches.append((component, unchanged))
        if len(matches) != 1:
            return "dropped"
        component, unchanged = matches[0]
        if not component.member_paths or (changed - unchanged).intersection(component.member_paths):
            return "dropped"
    except (CliFailure, OSError, ValueError, KeyError):
        return "dropped"
    return usage_reporting.record_invocation(
        organization_id=str(row["organization_id"]),
        employee_id=account_id,
        device_id=device_id,
        project_id=str(row["project_id"]),
        harness=harness,
        setup_stable_id=overview.setup_stable_id or None,
        setup_version=overview.setup_version or None,
        setup_passport_digest=overview.setup_passport_digest or None,
        component_kind="mcp",
        component_stable_id=component.stable_id,
        component_version=component.version,
        component_passport_digest=component.passport_digest,
        invoked_at=format_timestamp(
            datetime.fromtimestamp(now, UTC) if now is not None else datetime.now(UTC)
        ),
        outcome=outcome,
        source="native_hook",
        activity_kind="invocation",
        event_id=derive_event_id(operation_id, cast(str, session_id), cast(str, call_id)),
        outbox=outbox,
        outbox_path=outbox_path,
        now=now,
    )


def _terminal_outcome(harness: str, payload: Mapping[str, object], tool_name: str) -> str | None:
    """Read native result envelopes, never output text or tool arguments."""
    if harness == "codex":
        response = payload.get("tool_response")
        if payload.get("hook_event_name") != "PostToolUse" or not isinstance(response, dict):
            return None
        response = cast(dict[str, object], response)
        if not isinstance(response.get("content"), list) or not isinstance(
            response.get("isError", False), bool
        ):
            return None
        return "failed" if response.get("isError") is True else "succeeded"
    event = payload.get("hookEventName")
    if event not in {"post_tool_use", "post_tool_use_failure"}:
        return None
    response = payload.get("toolResult")
    if payload.get("toolResultTruncated") is True or not isinstance(response, dict):
        return None
    response = cast(dict[str, object], response)
    output = response.get("output")
    if not isinstance(output, dict):
        return None
    output = cast(dict[str, object], output)
    # Grok's Error variant includes dispatch failures. Only OkayOutput proves an MCP response.
    if (
        response.get("type") != "MCP"
        or set(output) != {"OkayOutput"}
        or not isinstance(output["OkayOutput"], str)
        or not isinstance(response.get("is_error", False), bool)
        or tool_name != f"{response.get('server_name')}__{response.get('tool_name')}"
    ):
        return None
    failed = response.get("is_error") is True
    if event == "post_tool_use_failure" and not failed:
        return None
    return "failed" if failed else "succeeded"


def _superseded(connection: sqlite3.Connection, operation_id: str, row: sqlite3.Row) -> bool:
    """A later mutation of this target invalidates provenance, even under another account."""
    return (
        connection.execute(
            "SELECT 1 FROM operation_plan p "
            "JOIN operation_event e ON e.operation_id = p.operation_id "
            "WHERE p.operation_id != ? AND (p.target_id = ? OR p.provider_target = ?) "
            "AND e.state_after IN "
            "('applying','applied','verified','partial','rolled_back','failed','stale') "
            "AND e.global_sequence > (SELECT MAX(global_sequence) FROM operation_event "
            "WHERE operation_id = ?) LIMIT 1",
            (operation_id, row["target_id"], row["provider_target"], operation_id),
        ).fetchone()
        is not None
    )
