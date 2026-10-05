"""Runtime component-usage event, report, and export wire contracts (SPEC-088).

Corporate runtime telemetry is a closed field set on the authenticated `/v1`
channel under `slices/corporate/`. It shares nothing with the anonymous
collector of `ADR-0112`: no `telemetry.url`, no `anon` identifier, and no
payload content of any kind. An event carries identities and exact coordinates
only - outcomes, never arguments, prompts, model output, paths, or secrets.
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import ConfigDict, Field

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
from ai_stp_contracts.model import ContractModel
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_foundation.versioning import VERSION_PATTERN

RuntimeUsageOutcome = Literal["succeeded", "failed", "cancelled"]
RuntimeUsageSource = Literal["native_hook", "agent_reported"]
RuntimeUsageActivityKind = Literal["invocation", "load"]
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
RuntimeUsageAssignmentState = Literal["recorded_use", "no_recorded_use"]

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


class RuntimeUsageSetupCoordinate(ContractModel):
    """The exact setup the invoked component belongs to."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    stable_id: UsageObjectId
    version: Annotated[str, Field(pattern=VERSION_PATTERN)]
    passport_digest: DigestValue


class RuntimeUsageComponentCoordinate(ContractModel):
    """The exact component that was invoked, kind-qualified."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    kind: RuntimeUsageComponentKind
    stable_id: UsageObjectId
    version: Annotated[str, Field(pattern=VERSION_PATTERN)]
    passport_digest: DigestValue


class RuntimeUsageEvent(ContractModel):
    """One component invocation. The closed field set is the contract."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    event_id: UsageEventId
    organization_id: OrganizationId
    employee_id: AccountId
    device_id: UsageDeviceId
    project_id: ProjectId
    harness: HarnessId
    setup: RuntimeUsageSetupCoordinate | None = None
    component: RuntimeUsageComponentCoordinate
    invoked_at: Timestamp
    outcome: RuntimeUsageOutcome
    source: RuntimeUsageSource = "agent_reported"
    activity_kind: RuntimeUsageActivityKind = "invocation"


class RuntimeUsageEventBatch(ContractModel):
    """A bounded outbox drain: the only ingestion envelope."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    events: Annotated[list[RuntimeUsageEvent], Field(min_length=1, max_length=INGEST_BATCH_LIMIT)]


class RuntimeUsageIngestResult(ContractModel):
    """Per-batch bookkeeping; the server never returns event content."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    accepted: Annotated[int, Field(ge=0)]
    duplicates: Annotated[int, Field(ge=0)]
    rejected: Annotated[int, Field(ge=0)]
    accepted_ids: list[UsageEventId] = Field(default_factory=list)
    duplicate_ids: list[UsageEventId] = Field(default_factory=list)
    rejected_ids: list[UsageEventId] = Field(default_factory=list)


class RuntimeUsageReportQuery(ContractModel):
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
    usage_state: Literal["all", "recorded", "no_recorded"] = "all"
    collection_state: Literal["all", "complete", "partial", "stale", "unknown", "disabled"] = "all"
    invoked_from: Timestamp | None = None
    invoked_to: Timestamp | None = None
    group_by: RuntimeUsageGroupBy = "component"
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=REPORT_ROW_LIMIT)] = 128


class RuntimeUsageReportRow(ContractModel):
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
    active_days: Annotated[int, Field(ge=0)]
    first_invoked_at: Timestamp
    last_invoked_at: Timestamp


class RuntimeUsageAssignedRow(ContractModel):
    """One currently assigned object and its observed use in the selected period."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    object_kind: Literal["setup", "component"]
    stable_id: str
    version: str | None = None
    state: RuntimeUsageAssignmentState
    invocations: Annotated[int, Field(ge=0)]
    last_invoked_at: Timestamp | None = None


class RuntimeUsageDayBucket(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    day: str
    uses: Annotated[int, Field(ge=0)]


class RuntimeUsageHourBucket(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    weekday: Annotated[int, Field(ge=0, le=6)]
    hour: Annotated[int, Field(ge=0, le=23)]
    uses: Annotated[int, Field(ge=0)]


class RuntimeUsageInventoryEmployeeRow(ContractModel):
    """Current managed observations; no inferred removal from partial scans."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    employee_id: AccountId
    observed_present: Annotated[int, Field(ge=0)]
    observed_modified: Annotated[int, Field(ge=0)]
    coverage: Literal["complete", "partial", "stale"]
    last_scan_at: Timestamp
    last_complete_at: Timestamp | None = None


class RuntimeUsageEmployeeRow(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    employee_id: AccountId
    name: str | None = None
    team_ids: list[TeamId]
    assigned_components: Annotated[int, Field(ge=0)]
    installed_components: Annotated[int, Field(ge=0)]
    used_components: Annotated[int, Field(ge=0)]
    uses: Annotated[int, Field(ge=0)]
    active_days: Annotated[int, Field(ge=0)]
    last_used_at: Timestamp | None = None


class RuntimeUsageObjectRow(ContractModel):
    """A setup or component, with a component's actual setup relation."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    object_kind: Literal["setup", "component"]
    stable_id: str
    name: str | None = None
    version: str
    parent_setup_stable_id: str | None = None
    parent_setup_version: str | None = None
    assigned_to: Annotated[int, Field(ge=0)]
    installed_for: Annotated[int, Field(ge=0)]
    installation_state: Literal["present", "modified", "missing", "unknown"] | None = None
    last_checked_at: Timestamp | None = None
    used_by: Annotated[int, Field(ge=0)]
    uses: Annotated[int, Field(ge=0)]
    active_days: Annotated[int, Field(ge=0)]
    last_used_at: Timestamp | None = None


class RuntimeUsageReport(ContractModel):
    """The aggregate answer plus current assignments and observed use."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    generated_at: Timestamp
    invoked_from: Timestamp | None = None
    invoked_to: Timestamp | None = None
    group_by: RuntimeUsageGroupBy
    total_events: Annotated[int, Field(ge=0)]
    report_timezone: str = "UTC"
    inventory_scan_enabled: bool = False
    usage_collection_enabled: bool = False
    inventory_employees: list[RuntimeUsageInventoryEmployeeRow]
    employees: list[RuntimeUsageEmployeeRow]
    objects: list[RuntimeUsageObjectRow]
    by_day: list[RuntimeUsageDayBucket]
    by_hour: list[RuntimeUsageHourBucket]
    rows: list[RuntimeUsageReportRow]
    assigned: list[RuntimeUsageAssignedRow]


class RuntimeUsageEventQuery(ContractModel):
    """Drill-down filters over redacted event rows; separately permissioned."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    employee_id: AccountId | None = None
    team_id: TeamId | None = None
    device_id: UsageDeviceId | None = None
    project_id: ProjectId | None = None
    technology_id: TechnologyId | None = None
    harness: HarnessId | None = None
    setup_stable_id: UsageObjectId | None = None
    setup_version: Annotated[str, Field(pattern=VERSION_PATTERN)] | None = None
    direct_only: bool = False
    component_stable_id: UsageObjectId | None = None
    component_version: Annotated[str, Field(pattern=VERSION_PATTERN)] | None = None
    component_kind: RuntimeUsageComponentKind | None = None
    outcome: RuntimeUsageOutcome | None = None
    source: RuntimeUsageSource | None = None
    activity_kind: RuntimeUsageActivityKind | None = None
    invoked_from: Timestamp | None = None
    invoked_to: Timestamp | None = None
    local_day: Annotated[date, Field(le=date(9999, 12, 30))] | None = None
    local_weekday: Annotated[int, Field(ge=0, le=6)] | None = None
    local_hour: Annotated[int, Field(ge=0, le=23)] | None = None
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=EVENT_PAGE_LIMIT)] = 128


class RuntimeUsageEventView(ContractModel):
    """The redacted drill-down row: identities and coordinates, nothing else."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    event_id: str
    employee_id: str
    device_id: str
    project_id: str
    harness: str
    setup_stable_id: str | None
    setup_version: str | None
    component_kind: str
    component_stable_id: str
    component_version: str
    invoked_at: Timestamp
    outcome: RuntimeUsageOutcome
    source: RuntimeUsageSource
    activity_kind: RuntimeUsageActivityKind


class RuntimeUsageEventList(ContractModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    offset: Annotated[int, Field(ge=0)]
    limit: Annotated[int, Field(ge=1)]
    events: list[RuntimeUsageEventView]


class RuntimeUsageExportRequest(ContractModel):
    """A bounded, auditable export of the aggregate report surface."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    query: RuntimeUsageReportQuery = RuntimeUsageReportQuery()
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey


class RuntimeUsageExportView(ContractModel):
    """The export receipt: what was produced, bounded and digested."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    export_id: str
    organization_id: OrganizationId
    created_at: Timestamp
    row_count: Annotated[int, Field(ge=0)]
    content_digest: str
    state: Literal["completed"]


class RuntimeUsageRecordResult(ContractModel):
    """The outcome of recording one accepted invocation into the outbox.

    `queued` and `duplicate` are durable states; `full` and `dropped` mean
    the queue refused the event. `disabled` means collection is off locally.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    event_id: str
    state: Literal["queued", "duplicate", "full", "dropped", "disabled"]


class RuntimeUsageOutboxStatus(ContractModel):
    """Local CLI outbox inspection; never leaves the machine."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    pending: Annotated[int, Field(ge=0)]
    dead: Annotated[int, Field(ge=0)]
    capacity: Annotated[int, Field(ge=0)]
    oldest_pending_at: Timestamp | None = None


class RuntimeUsageFlushResult(ContractModel):
    """One drain attempt over the local outbox."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    sent: Annotated[int, Field(ge=0)]
    remaining: Annotated[int, Field(ge=0)]
    dead: Annotated[int, Field(ge=0)]
