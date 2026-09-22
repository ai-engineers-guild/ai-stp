"""Corporate runtime usage events: the closed field set and its transport.

This is a different channel from `telemetry.py`. That one is the anonymous,
consented `GET` of `ADR-0112`; this one is authenticated, tenant-scoped, and
carries component-invocation facts to Corporate Hub under
`/corporate/organizations/{id}/telemetry/...` (`SPEC-088`). The two never
share an identifier, an endpoint, or a field.

The field set is closed the same way the ping's is: the contract model is
`extra="forbid"`, the builder accepts only the named arguments, and
`event_payload` refuses to serialize a dict whose keys are not exactly
`EVENT_FIELDS`. Prompts, arguments, model output, MCP payloads, paths,
environment values, and secrets have no field to occupy.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Final, cast

from ai_stp_cli.cloud.client import Endpoint, as_query, call, open_client
from ai_stp_contracts.runtime_usage import (
    INGEST_BATCH_LIMIT,
    RuntimeUsageComponentCoordinate,
    RuntimeUsageEvent,
    RuntimeUsageEventBatch,
    RuntimeUsageEventList,
    RuntimeUsageEventQuery,
    RuntimeUsageExportRequest,
    RuntimeUsageExportView,
    RuntimeUsageIngestResult,
    RuntimeUsageReport,
    RuntimeUsageReportQuery,
    RuntimeUsageSetupCoordinate,
)

#: The closed wire set, in contract order. `event_payload` enforces equality,
#: so widening an event means widening this tuple and the contract together.
EVENT_FIELDS: Final[tuple[str, ...]] = (
    "schema_version",
    "event_id",
    "organization_id",
    "employee_id",
    "device_id",
    "project_id",
    "harness",
    "setup",
    "component",
    "invoked_at",
    "outcome",
)

#: Names that must never appear in an event, an outbox row, or a report.
#: The contract cannot carry them; this list exists so a test can prove it.
FORBIDDEN_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "prompt",
        "prompts",
        "input",
        "output",
        "arguments",
        "result",
        "payload",
        "mcp_payload",
        "content",
        "source",
        "path",
        "cwd",
        "env",
        "environment",
        "token",
        "credential",
        "secret",
        "cookie",
    }
)

OUTCOMES: Final[frozenset[str]] = frozenset({"succeeded", "failed", "cancelled"})
COMPONENT_KINDS: Final[frozenset[str]] = frozenset(
    {"instruction", "skill", "mcp", "hook", "command", "agent", "plugin", "setting", "cli"}
)


def new_event_id() -> str:
    """A safe correlation id: no timestamp, no machine data, no free text."""
    return f"usage_event_{uuid.uuid4().hex}"


def build_event(
    *,
    organization_id: str,
    employee_id: str,
    device_id: str,
    project_id: str,
    harness: str,
    setup_stable_id: str,
    setup_version: str,
    setup_passport_digest: str,
    component_kind: str,
    component_stable_id: str,
    component_version: str,
    component_passport_digest: str,
    invoked_at: str,
    outcome: str,
    event_id: str | None = None,
) -> RuntimeUsageEvent:
    """Build one validated event. Raises ``ValueError`` on a bad coordinate.

    The signature *is* the closed set: there is no `**extra` for a component
    or a caller to smuggle content through, which is what "components never
    choose event fields" means mechanically.
    """
    return RuntimeUsageEvent(
        event_id=event_id or new_event_id(),
        organization_id=organization_id,
        employee_id=employee_id,
        device_id=device_id,
        project_id=project_id,
        harness=harness,  # pyright: ignore[reportArgumentType]
        setup=RuntimeUsageSetupCoordinate(
            stable_id=setup_stable_id,
            version=setup_version,
            passport_digest=setup_passport_digest,
        ),
        component=RuntimeUsageComponentCoordinate(
            kind=component_kind,  # pyright: ignore[reportArgumentType]
            stable_id=component_stable_id,
            version=component_version,
            passport_digest=component_passport_digest,
        ),
        invoked_at=invoked_at,
        outcome=outcome,  # pyright: ignore[reportArgumentType]
    )


def event_payload(event: RuntimeUsageEvent) -> dict[str, object]:
    """Serialize exactly the closed set, or nothing.

    The guard mirrors `telemetry.ping`: a future field added to the model but
    not to `EVENT_FIELDS` produces a key mismatch, and the event is refused
    rather than shipped with a shape nobody reviewed.
    """
    payload = event.model_dump(mode="json")
    if tuple(payload) != EVENT_FIELDS:
        raise ValueError("runtime usage event carries a field outside the closed set")
    if FORBIDDEN_FIELDS & {key.lower() for key in _walk_keys(payload)}:
        raise ValueError("runtime usage event carries a forbidden field name")
    return payload


def _walk_keys(document: Mapping[str, object]) -> frozenset[str]:
    keys: set[str] = set(document)
    for value in document.values():
        if isinstance(value, Mapping):
            keys |= set(_walk_keys(cast("Mapping[str, object]", value)))
    return frozenset(keys)


def submit_events(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
    events: Sequence[RuntimeUsageEvent],
) -> RuntimeUsageIngestResult:
    """Drain one batch to the authenticated corporate channel.

    Batches larger than `INGEST_BATCH_LIMIT` are refused locally; the outbox
    caller chunks before this is reached.
    """
    batch = RuntimeUsageEventBatch(
        events=[RuntimeUsageEvent.model_validate(event) for event in events]
    )
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "POST",
            f"/corporate/organizations/{organization_id}/telemetry/usage-events",
            RuntimeUsageIngestResult,
            body=batch,
            attempts=endpoint.max_attempts,
        )


def read_report(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
    query: RuntimeUsageReportQuery,
) -> RuntimeUsageReport:
    """Read the scoped aggregate report for one tenant."""
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "GET",
            f"/corporate/organizations/{organization_id}/telemetry/usage-reports",
            RuntimeUsageReport,
            query=as_query(query),
            attempts=endpoint.max_attempts,
        )


def list_events(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
    query: RuntimeUsageEventQuery,
) -> RuntimeUsageEventList:
    """Read the separately permissioned, redacted drill-down page."""
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "GET",
            f"/corporate/organizations/{organization_id}/telemetry/usage-events",
            RuntimeUsageEventList,
            query=as_query(query),
            attempts=endpoint.max_attempts,
        )


def create_export(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
    request: RuntimeUsageExportRequest,
) -> RuntimeUsageExportView:
    """Create the bounded, audited export receipt."""
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "POST",
            f"/corporate/organizations/{organization_id}/telemetry/usage-exports",
            RuntimeUsageExportView,
            body=request,
            attempts=endpoint.max_attempts,
        )


__all__ = [
    "COMPONENT_KINDS",
    "EVENT_FIELDS",
    "FORBIDDEN_FIELDS",
    "INGEST_BATCH_LIMIT",
    "OUTCOMES",
    "build_event",
    "create_export",
    "event_payload",
    "list_events",
    "new_event_id",
    "read_report",
    "submit_events",
]
