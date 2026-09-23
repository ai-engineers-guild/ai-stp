"""`usage` commands — scoped reports, drill-down, export, and the local outbox.

The read surface mirrors the API: aggregates by default (`usage report`),
event-level drill-down behind its own permission (`usage events`), and a
bounded audited export (`usage export`). `usage outbox` inspects the local
buffer; `usage flush` drains it over the authenticated corporate channel.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import closing
from datetime import UTC, datetime

from ai_stp_cli import runtime_usage
from ai_stp_cli.answer import Answer
from ai_stp_cli.application import usage_outbox
from ai_stp_cli.cloud import session
from ai_stp_cli.commands import cloud_auth
from ai_stp_cli.commands.auth import endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider import usage_reporting
from ai_stp_contracts.runtime_usage import (
    RuntimeUsageEvent,
    RuntimeUsageEventList,
    RuntimeUsageEventQuery,
    RuntimeUsageExportRequest,
    RuntimeUsageExportView,
    RuntimeUsageFlushResult,
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
    event_id = _optional(parameters, "event-id") or runtime_usage.new_event_id()
    state = usage_reporting.record_invocation(
        organization_id=_required(parameters, "organization"),
        employee_id=held.account_id,
        device_id=held.device_id,
        project_id=_required(parameters, "project"),
        harness=_required(parameters, "harness"),
        setup_stable_id=_required(parameters, "setup"),
        setup_version=_required(parameters, "setup-version"),
        setup_passport_digest=_required(parameters, "setup-digest"),
        component_kind=_required(parameters, "kind"),
        component_stable_id=_required(parameters, "component"),
        component_version=_required(parameters, "component-version"),
        component_passport_digest=_required(parameters, "component-digest"),
        invoked_at=_required(parameters, "invoked-at"),
        outcome=_required(parameters, "outcome"),
        event_id=event_id,
    )
    return Answer(RuntimeUsageRecordResult(event_id=event_id, state=state))


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
    del parameters
    with closing(usage_outbox.connect()) as connection:
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

    def send(batch: list[dict[str, object]]) -> None:
        events_batch = [RuntimeUsageEvent.model_validate(item) for item in batch]
        runtime_usage.submit_events(target, held.access_token, organization_id, events_batch)

    with closing(usage_outbox.connect()) as connection:
        sent, remaining = usage_outbox.flush(connection, send)
        held_stats = usage_outbox.stats(connection)
    return Answer(
        RuntimeUsageFlushResult(
            sent=sent,
            remaining=remaining,
            dead=int(held_stats["dead"] or 0),
        )
    )
