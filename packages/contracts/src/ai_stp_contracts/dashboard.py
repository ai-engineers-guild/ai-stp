"""Closed Corporate Hub health query and saved-view contracts."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_stp_contracts.context import RemoteProjectId
from ai_stp_contracts.corporate import AccountId, OrganizationId
from ai_stp_contracts.heartbeat import DeviceId
from ai_stp_contracts.http import IdempotencyKey, Timestamp, open_wire_object, strict_request_object
from ai_stp_foundation.ids import stable_id_pattern

DashboardDataset = Literal["ci", "heartbeat", "provider"]
DashboardDimension = Literal[
    "state",
    "project",
    "team",
    "account",
    "device",
    "harness",
    "setup",
    "provider",
    "day",
    "checked_at",
    "reason",
]
DashboardMeasure = Literal["count", "devices", "projects"]
DashboardChart = Literal["table", "bar", "line", "pie", "heatmap"]
DashboardScope = Literal["user", "team", "organization"]
CiStatus = Literal[
    "pass", "fail", "outdated", "revoked", "unsupported", "not_enrolled", "unverifiable"
]
CiReason = Literal[
    "none",
    "check_failed",
    "target_drift",
    "source_unavailable",
    "permission_denied",
    "unsupported",
    "unknown",
]
_FilterValue = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]


class CorporateCiCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    project_id: RemoteProjectId
    account_id: AccountId
    device_id: DeviceId
    harness: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")]
    setup_id: Annotated[str, Field(pattern=stable_id_pattern("setup"))] | None = None
    status: CiStatus
    reason: CiReason = "none"
    checked_at: Timestamp


class CorporateCiCheckView(CorporateCiCheckRequest):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    organization_id: OrganizationId
    received_at: Timestamp
    revision: Annotated[int, Field(ge=1)]


class DashboardFilter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    dimension: DashboardDimension
    values: Annotated[list[_FilterValue], Field(min_length=1, max_length=16)]


class DashboardQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    dataset: DashboardDataset
    dimensions: Annotated[list[DashboardDimension], Field(max_length=8)] = Field(
        default_factory=list[DashboardDimension]
    )
    measures: Annotated[list[DashboardMeasure], Field(min_length=1, max_length=3)] = Field(
        default_factory=lambda: ["count"]
    )
    filters: Annotated[list[DashboardFilter], Field(max_length=8)] = Field(
        default_factory=list[DashboardFilter]
    )
    group_by: Annotated[list[DashboardDimension], Field(max_length=2)] = Field(
        default_factory=list[DashboardDimension]
    )
    pivot_rows: Annotated[list[DashboardDimension], Field(max_length=2)] = Field(
        default_factory=list[DashboardDimension]
    )
    pivot_columns: Annotated[list[DashboardDimension], Field(max_length=2)] = Field(
        default_factory=list[DashboardDimension]
    )
    sort_by: DashboardDimension | DashboardMeasure = "count"
    sort_order: Literal["asc", "desc"] = "desc"
    view: DashboardChart = "table"
    limit: Annotated[int, Field(ge=1, le=200)] = 100


class DashboardQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    query: DashboardQuery


class DashboardCell(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    dimensions: dict[str, str]
    measures: dict[str, int]


class DashboardResult(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    query: DashboardQuery
    evaluated_at: Timestamp
    total_source_rows: Annotated[int, Field(ge=0)]
    total_groups: Annotated[int, Field(ge=0)]
    items: Annotated[list[DashboardCell], Field(max_length=200)]


class DashboardViewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    name: Annotated[str, Field(min_length=1, max_length=120)]
    scope: DashboardScope
    scope_id: Annotated[str, Field(min_length=1, max_length=64)]
    query: DashboardQuery
    authorization_revision: Annotated[int, Field(ge=1)]
    expected_revision: Annotated[int, Field(ge=0)] = 0
    idempotency_key: IdempotencyKey


class DashboardView(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    id: Annotated[str, Field(pattern=stable_id_pattern("dashboard_view"))]
    organization_id: OrganizationId
    name: str
    scope: DashboardScope
    scope_id: str
    owner_account_id: AccountId
    query: DashboardQuery
    revision: Annotated[int, Field(ge=1)]


class DashboardViewList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    items: Annotated[list[DashboardView], Field(max_length=200)]
