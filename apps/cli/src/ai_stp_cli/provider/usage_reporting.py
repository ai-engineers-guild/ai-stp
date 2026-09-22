"""The provider runtime adapter's only usage-telemetry seam (SPEC-088).

Components are untrusted content: they cannot emit telemetry, choose event
fields, or name a destination. The provider adapter observes an invocation it
accepted, calls `record_invocation` with identities and exact coordinates
only, and the event lands in the bounded local outbox. Heartbeats, health
checks, and lifecycle operations never reach this module - they are not
component invocations.

The function returns a status string instead of raising into the invocation
path: a malformed record is dropped and counted locally, because an adapter
that crashes on telemetry would fail the operation it only observes.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal

from ai_stp_cli import runtime_usage
from ai_stp_cli.application import usage_outbox

RecordResult = Literal["queued", "duplicate", "full", "dropped"]


def record_invocation(
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
    outbox: sqlite3.Connection | None = None,
    outbox_path: Path | None = None,
    now: float | None = None,
) -> RecordResult:
    """Buffer exactly one event for one accepted component invocation.

    `dropped` means the record failed the closed-field contract and nothing
    was stored; `full` means the bounded outbox refused, which in a mandatory
    posture is the signal that blocks the next invocation.
    """
    if outcome not in runtime_usage.OUTCOMES or component_kind not in (
        runtime_usage.COMPONENT_KINDS
    ):
        return "dropped"
    try:
        event = runtime_usage.build_event(
            organization_id=organization_id,
            employee_id=employee_id,
            device_id=device_id,
            project_id=project_id,
            harness=harness,
            setup_stable_id=setup_stable_id,
            setup_version=setup_version,
            setup_passport_digest=setup_passport_digest,
            component_kind=component_kind,
            component_stable_id=component_stable_id,
            component_version=component_version,
            component_passport_digest=component_passport_digest,
            invoked_at=invoked_at,
            outcome=outcome,
            event_id=event_id,
        )
        payload = runtime_usage.event_payload(event)
    except ValueError:
        return "dropped"
    if outbox is not None:
        return usage_outbox.enqueue(outbox, event.event_id, payload, now=now)
    connection = usage_outbox.connect(outbox_path)
    try:
        return usage_outbox.enqueue(connection, event.event_id, payload, now=now)
    finally:
        connection.close()


__all__ = ["RecordResult", "record_invocation"]
