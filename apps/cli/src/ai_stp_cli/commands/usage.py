"""`usage` commands — scoped reports, drill-down, export, and the local outbox.

The read surface mirrors the API: aggregates by default (`usage report`),
event-level drill-down behind its own permission (`usage events`), and a
bounded audited export (`usage export`). `usage outbox` inspects the local
buffer; `usage flush` drains it over the authenticated corporate channel.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from ai_stp_cli import runtime_usage
from ai_stp_cli.answer import Answer
from ai_stp_cli.application import usage_outbox
from ai_stp_cli.cloud import session
from ai_stp_cli.commands import cloud_auth
from ai_stp_cli.commands.auth import endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_cli.provider import usage_hooks, usage_reporting
from ai_stp_cli.secrets import open_store
from ai_stp_contracts.runtime_usage import (
    RuntimeUsageEvent,
    RuntimeUsageEventList,
    RuntimeUsageEventQuery,
    RuntimeUsageExportRequest,
    RuntimeUsageExportView,
    RuntimeUsageFlushResult,
    RuntimeUsageIngestResult,
    RuntimeUsageOutboxStatus,
    RuntimeUsageRecordResult,
    RuntimeUsageReport,
    RuntimeUsageReportQuery,
)
from ai_stp_foundation.timestamps import format_timestamp


def _required(parameters: Mapping[str, object], name: str) -> str:
    value = str(parameters.get(name) or "")
    if not value:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a required option was not supplied",
            details={"option": f"--{name}"},
        )
    return value


def _optional(parameters: Mapping[str, object], name: str) -> str | None:
    return str(parameters.get(name) or "") or None


def _integer(parameters: Mapping[str, object], name: str, default: int) -> int:
    value = parameters.get(name)
    try:
        return default if value is None else int(str(value))
    except ValueError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a required option must be an integer",
            details={"option": f"--{name}"},
        ) from error


def _session(purpose: str) -> session.Session:
    return cloud_auth.required(purpose)


def _report_query(parameters: Mapping[str, object]) -> RuntimeUsageReportQuery:
    return RuntimeUsageReportQuery(
        employee_id=_optional(parameters, "employee"),
        team_id=_optional(parameters, "team"),
        device_id=_optional(parameters, "device"),
        project_id=_optional(parameters, "project"),
        technology_id=_optional(parameters, "technology"),
        harness=_optional(parameters, "harness"),  # pyright: ignore[reportArgumentType]
        setup_stable_id=_optional(parameters, "setup"),
        component_stable_id=_optional(parameters, "component"),
        component_kind=_optional(parameters, "kind"),  # pyright: ignore[reportArgumentType]
        outcome=_optional(parameters, "outcome"),  # pyright: ignore[reportArgumentType]
        invoked_from=_optional(parameters, "from"),
        invoked_to=_optional(parameters, "to"),
        group_by=_optional(parameters, "group-by") or "component",  # pyright: ignore[reportArgumentType]
        offset=_integer(parameters, "offset", 0),
        limit=_integer(parameters, "limit", 128),
    )


def record(parameters: Mapping[str, object]) -> Answer[RuntimeUsageRecordResult]:
    """Buffer one accepted component invocation for later delivery.

    The provider adapter calls this after an invocation it accepted.
    Heartbeats, health checks, and install/plan/apply lifecycle operations
    never reach it: they are not component invocations. Employee and device
    come from the held session, never from options - the server binds the
    event to the authenticated identity again, so a flag could only lie.
    """
    held = _session("corporate usage record")
    organization_id = _required(parameters, "organization")
    event_id = _optional(parameters, "event-id") or runtime_usage.new_event_id()
    state = usage_reporting.record_invocation(
        organization_id=organization_id,
        employee_id=held.account_id,
        device_id=held.device_id,
        project_id=_required(parameters, "project"),
        harness=_required(parameters, "harness"),
        setup_stable_id=_optional(parameters, "setup"),
        setup_version=_optional(parameters, "setup-version"),
        setup_passport_digest=_optional(parameters, "setup-digest"),
        component_kind=_required(parameters, "kind"),
        component_stable_id=_required(parameters, "component"),
        component_version=_required(parameters, "component-version"),
        component_passport_digest=_required(parameters, "component-digest"),
        invoked_at=_required(parameters, "invoked-at"),
        outcome=_required(parameters, "outcome"),
        source="agent_reported",
        activity_kind=_optional(parameters, "activity-kind") or "invocation",
        event_id=event_id,
    )
    return Answer(RuntimeUsageRecordResult(event_id=event_id, state=state))


def hook(parameters: Mapping[str, object]) -> Answer[RuntimeUsageRecordResult]:
    """Read one bounded native hook from stdin; persist only bound usage facts offline."""
    event_id = runtime_usage.new_event_id()
    dropped = Answer(RuntimeUsageRecordResult(event_id=event_id, state="dropped"))
    raw = sys.stdin.buffer.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        return dropped
    try:
        payload: object = json.loads(raw)
    except (ValueError, UnicodeError):
        return dropped
    if not isinstance(payload, dict):
        return dropped
    document = cast(dict[str, object], payload)
    store, _warning = open_store()
    held = session.load(store)
    # Recording is offline: expiry does not change who owns the queued facts.
    if held is None or held.revoked:
        return dropped
    harness = _required(parameters, "harness")
    scope = _optional(parameters, "scope") or "project"
    with closing(open_registry(configured_path())) as connection:
        operation = usage_hooks.resolve_operation(
            connection, held.account_id, held.device_id, harness, scope, Path.cwd()
        )
        if operation is None:
            return dropped
        event_id = usage_hooks.derive_event_id(
            operation,
            str(document.get("session_id" if harness == "codex" else "sessionId") or ""),
            str(document.get("tool_use_id" if harness == "codex" else "toolUseId") or ""),
        )
        result = usage_hooks.record_hook_usage(
            connection, operation, held.account_id, held.device_id, document
        )
    return Answer(RuntimeUsageRecordResult(event_id=event_id, state=result))


def report(parameters: Mapping[str, object]) -> Answer[RuntimeUsageReport]:
    """The scoped aggregate report: frequency, first/last, installed state."""
    held = _session("corporate usage report")
    return Answer(
        runtime_usage.read_report(
            endpoint(),
            held.access_token,
            _required(parameters, "organization"),
            _report_query(parameters),
        )
    )


def events(parameters: Mapping[str, object]) -> Answer[RuntimeUsageEventList]:
    """The separately permissioned, redacted event-level drill-down."""
    held = _session("corporate usage events")
    query = RuntimeUsageEventQuery(
        employee_id=_optional(parameters, "employee"),
        team_id=_optional(parameters, "team"),
        device_id=_optional(parameters, "device"),
        project_id=_optional(parameters, "project"),
        technology_id=_optional(parameters, "technology"),
        harness=_optional(parameters, "harness"),  # pyright: ignore[reportArgumentType]
        setup_stable_id=_optional(parameters, "setup"),
        component_stable_id=_optional(parameters, "component"),
        component_kind=_optional(parameters, "kind"),  # pyright: ignore[reportArgumentType]
        outcome=_optional(parameters, "outcome"),  # pyright: ignore[reportArgumentType]
        source=_optional(parameters, "source"),  # pyright: ignore[reportArgumentType]
        activity_kind=_optional(parameters, "activity-kind"),  # pyright: ignore[reportArgumentType]
        invoked_from=_optional(parameters, "from"),
        invoked_to=_optional(parameters, "to"),
        offset=_integer(parameters, "offset", 0),
        limit=_integer(parameters, "limit", 128),
    )
    return Answer(
        runtime_usage.list_events(
            endpoint(),
            held.access_token,
            _required(parameters, "organization"),
            query,
        )
    )


def export(parameters: Mapping[str, object]) -> Answer[RuntimeUsageExportView]:
    """Create the bounded export receipt. Writes a receipt; needs --confirm."""
    if parameters.get("confirm") is not True:
        raise CliFailure(
            "AI_STP_USER_DECISION_REQUIRED",
            "creating a usage export records an auditable receipt and needs confirmation",
            details={"action": "usage export"},
            next_actions=["usage report --organization <organization> --json"],
        )
    held = _session("corporate usage export")
    try:
        authorization_revision = int(_required(parameters, "authorization-revision"))
    except ValueError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a required option must be an integer",
            details={"option": "--authorization-revision"},
        ) from error
    request = RuntimeUsageExportRequest(
        query=_report_query(parameters),
        authorization_revision=authorization_revision,
        idempotency_key=_required(parameters, "idempotency-key"),
    )
    return Answer(
        runtime_usage.create_export(
            endpoint(),
            held.access_token,
            _required(parameters, "organization"),
            request,
        )
    )


def outbox(parameters: Mapping[str, object]) -> Answer[RuntimeUsageOutboxStatus]:
    """Inspect the local buffer. Reads only; sends nothing."""
    held = _session("corporate usage outbox")
    organization_id = _required(parameters, "organization")
    with closing(
        usage_outbox.connect(usage_outbox.scoped_path(held.account_id, organization_id))
    ) as connection:
        held = usage_outbox.stats(connection)
    oldest = held["oldest_pending_at"]
    return Answer(
        RuntimeUsageOutboxStatus(
            pending=int(held["pending"] or 0),
            dead=int(held["dead"] or 0),
            capacity=int(held["capacity"] or 0),
            oldest_pending_at=(
                None
                if oldest is None
                else format_timestamp(datetime.fromtimestamp(float(oldest), UTC))
            ),
        )
    )


def flush(parameters: Mapping[str, object]) -> Answer[RuntimeUsageFlushResult]:
    """Drain due events to Corporate Hub over the authenticated channel."""
    held = _session("corporate usage flush")
    organization_id = _required(parameters, "organization")
    target = endpoint()

    def send(batch: list[dict[str, object]]) -> RuntimeUsageIngestResult:
        events_batch = [RuntimeUsageEvent.model_validate(item) for item in batch]
        return runtime_usage.submit_events(target, held.access_token, organization_id, events_batch)

    with closing(
        usage_outbox.connect(usage_outbox.scoped_path(held.account_id, organization_id))
    ) as connection:
        sent, remaining = usage_outbox.flush(connection, send)
        held_stats = usage_outbox.stats(connection)
    return Answer(
        RuntimeUsageFlushResult(
            sent=sent,
            remaining=remaining,
            dead=int(held_stats["dead"] or 0),
        )
    )
