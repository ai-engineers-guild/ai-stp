"""Runtime component-usage event, report, and export wire contracts (SPEC-088).

Corporate runtime telemetry is a closed field set on the authenticated `/v1`
channel under `slices/corporate/`. It shares nothing with the anonymous
collector of `ADR-0112`: no `telemetry.url`, no `anon` identifier, and no
payload content of any kind. An event carries identities and exact coordinates
only - outcomes, never arguments, prompts, model output, paths, or secrets.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_stp_contracts.corporate import (
    AccountId,
    DigestValue,
    OrganizationId,
    ProjectId,
    TeamId,
    TechnologyId,
)
from ai_stp_contracts.http import (
    IdempotencyKey,
    Timestamp,
    open_wire_object,
    strict_request_object,
)
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_foundation.versioning import VERSION_PATTERN

RuntimeUsageOutcome = Literal["succeeded", "failed", "cancelled"]
RuntimeUsageComponentKind = Literal[
    "instruction",
    "skill",
    "mcp",
    "hook",
    "command",
    "agent",
    "plugin",
    "setting",
    "cli",
]
RuntimeUsageGroupBy = Literal[
    "component",
    "setup",
    "employee",
    "device",
    "project",
    "harness",
    "outcome",
]
RuntimeUsageInstalledState = Literal["invoked", "not_invoked"]

#: A safe correlation identifier: printable ASCII, no whitespace, no free
#: text. The provider mints it once per accepted invocation; it is the
#: deduplication key across offline buffering and retries.
UsageEventId = Annotated[
    str,
    Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,79}$"),
]
#: Device references arrive as opaque corporate identifiers; the employee's
#: device passport lives in the identity slice, not in this contract.
UsageDeviceId = Annotated[str, Field(min_length=1, max_length=64)]
UsageObjectId = Annotated[str, Field(min_length=1, max_length=128)]

INGEST_BATCH_LIMIT = 256
EVENT_PAGE_LIMIT = 256
REPORT_ROW_LIMIT = 512
EXPORT_ROW_LIMIT = 5000


class RuntimeUsageSetupCoordinate(BaseModel):
    """The exact setup the invoked component belongs to."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    stable_id: UsageObjectId
    version: Annotated[str, Field(pattern=VERSION_PATTERN)]
    passport_digest: DigestValue


class RuntimeUsageComponentCoordinate(BaseModel):
    """The exact component that was invoked, kind-qualified."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    kind: RuntimeUsageComponentKind
    stable_id: UsageObjectId
    version: Annotated[str, Field(pattern=VERSION_PATTERN)]
    passport_digest: DigestValue


class RuntimeUsageEvent(BaseModel):
    """One component invocation. The closed field set is the contract."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    event_id: UsageEventId
    organization_id: OrganizationId
    employee_id: AccountId
    device_id: UsageDeviceId
    project_id: ProjectId
    harness: HarnessId
    setup: RuntimeUsageSetupCoordinate
    component: RuntimeUsageComponentCoordinate
    invoked_at: Timestamp
    outcome: RuntimeUsageOutcome


class RuntimeUsageEventBatch(BaseModel):
    """A bounded outbox drain: the only ingestion envelope."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    events: Annotated[list[RuntimeUsageEvent], Field(min_length=1, max_length=INGEST_BATCH_LIMIT)]


class RuntimeUsageIngestResult(BaseModel):
    """Per-batch bookkeeping; the server never returns event content."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    accepted: Annotated[int, Field(ge=0)]
    duplicates: Annotated[int, Field(ge=0)]
    rejected: Annotated[int, Field(ge=0)]


class RuntimeUsageReportQuery(BaseModel):
    """Aggregate report filters. Every field narrows; none widens."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    employee_id: AccountId | None = None
    team_id: TeamId | None = None
    device_id: UsageDeviceId | None = None
    project_id: ProjectId | None = None
    technology_id: TechnologyId | None = None
    harness: HarnessId | None = None
    setup_stable_id: UsageObjectId | None = None
    component_stable_id: UsageObjectId | None = None
    component_kind: RuntimeUsageComponentKind | None = None
    outcome: RuntimeUsageOutcome | None = None
    invoked_from: Timestamp | None = None
    invoked_to: Timestamp | None = None
    group_by: RuntimeUsageGroupBy = "component"
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=REPORT_ROW_LIMIT)] = 128


class RuntimeUsageReportRow(BaseModel):
    """One deterministic aggregate bucket over a defined window."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    group_value: str
    component_kind: RuntimeUsageComponentKind | None = None
    component_stable_id: str | None = None
    component_version: str | None = None
    setup_stable_id: str | None = None
    setup_version: str | None = None
    invocations: Annotated[int, Field(ge=0)]
    succeeded: Annotated[int, Field(ge=0)]
    failed: Annotated[int, Field(ge=0)]
    cancelled: Annotated[int, Field(ge=0)]
    employees: Annotated[int, Field(ge=0)]
    devices: Annotated[int, Field(ge=0)]
    first_invoked_at: Timestamp
    last_invoked_at: Timestamp


class RuntimeUsageInstalledRow(BaseModel):
    """One currently assigned object and whether it was ever invoked."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    object_kind: Literal["setup", "component"]
    stable_id: str
    version: str | None = None
    state: RuntimeUsageInstalledState
    invocations: Annotated[int, Field(ge=0)]
    last_invoked_at: Timestamp | None = None


class RuntimeUsageReport(BaseModel):
    """The aggregate answer plus the installed-vs-invoked comparison."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    generated_at: Timestamp
    invoked_from: Timestamp | None = None
    invoked_to: Timestamp | None = None
    group_by: RuntimeUsageGroupBy
    total_events: Annotated[int, Field(ge=0)]
    rows: list[RuntimeUsageReportRow]
    installed: list[RuntimeUsageInstalledRow]


class RuntimeUsageEventQuery(BaseModel):
    """Drill-down filters over redacted event rows; separately permissioned."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    employee_id: AccountId | None = None
    team_id: TeamId | None = None
    device_id: UsageDeviceId | None = None
    project_id: ProjectId | None = None
    technology_id: TechnologyId | None = None
    harness: HarnessId | None = None
    setup_stable_id: UsageObjectId | None = None
    component_stable_id: UsageObjectId | None = None
    component_kind: RuntimeUsageComponentKind | None = None
    outcome: RuntimeUsageOutcome | None = None
    invoked_from: Timestamp | None = None
    invoked_to: Timestamp | None = None
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=EVENT_PAGE_LIMIT)] = 128


class RuntimeUsageEventView(BaseModel):
    """The redacted drill-down row: identities and coordinates, nothing else."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    event_id: str
    employee_id: str
    device_id: str
    project_id: str
    harness: str
    setup_stable_id: str
    setup_version: str
    component_kind: str
    component_stable_id: str
    component_version: str
    invoked_at: Timestamp
    outcome: RuntimeUsageOutcome


class RuntimeUsageEventList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    offset: Annotated[int, Field(ge=0)]
    limit: Annotated[int, Field(ge=1)]
    events: list[RuntimeUsageEventView]


class RuntimeUsageExportRequest(BaseModel):
    """A bounded, auditable export of the aggregate report surface."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    query: RuntimeUsageReportQuery = RuntimeUsageReportQuery()
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey


class RuntimeUsageExportView(BaseModel):
    """The export receipt: what was produced, bounded and digested."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    export_id: str
    organization_id: OrganizationId
    created_at: Timestamp
    row_count: Annotated[int, Field(ge=0)]
    content_digest: str
    state: Literal["completed"]


class RuntimeUsageRecordResult(BaseModel):
    """The outcome of recording one accepted invocation into the outbox.

    `queued` and `duplicate` are the durable states; `full` and `dropped`
    mean the local queue could not accept the event - the caller treats them
    as non-fatal telemetry loss, never as a reason to fail the invocation.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    event_id: str
    state: Literal["queued", "duplicate", "full", "dropped"]


class RuntimeUsageOutboxStatus(BaseModel):
    """Local CLI outbox inspection; never leaves the machine."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    pending: Annotated[int, Field(ge=0)]
    dead: Annotated[int, Field(ge=0)]
    capacity: Annotated[int, Field(ge=0)]
    oldest_pending_at: Timestamp | None = None


class RuntimeUsageFlushResult(BaseModel):
    """One drain attempt over the local outbox."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    sent: Annotated[int, Field(ge=0)]
    remaining: Annotated[int, Field(ge=0)]
    dead: Annotated[int, Field(ge=0)]
