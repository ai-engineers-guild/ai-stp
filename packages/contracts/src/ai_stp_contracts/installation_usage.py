"""Closed corporate facts for settled AI-STP installation operations."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_stp_contracts.corporate import AccountId, OrganizationId, ProjectId
from ai_stp_contracts.http import Timestamp, open_wire_object, strict_request_object
from ai_stp_contracts.runtime_usage import RuntimeUsageComponentKind, UsageDeviceId, UsageObjectId
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_foundation.ids import stable_id_pattern
from ai_stp_foundation.versioning import VERSION_PATTERN

OperationId = Annotated[str, Field(pattern=stable_id_pattern("operation"))]
InstallationAction = Literal["install", "update", "remove", "rollback"]
InstallationResult = Literal["verified", "partial", "rolled_back", "failed", "stale"]


class InstalledComponent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    kind: RuntimeUsageComponentKind
    stable_id: UsageObjectId
    version: Annotated[str, Field(pattern=VERSION_PATTERN)]


class InstallationOperationFact(BaseModel):
    """One settled local journal operation; no paths or provider payloads."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    operation_id: OperationId
    organization_id: OrganizationId
    employee_id: AccountId
    device_id: UsageDeviceId
    project_id: ProjectId
    harness: HarnessId
    scope: Literal["global", "project", "unknown"]
    action: InstallationAction
    result: InstallationResult
    occurred_at: Timestamp
    setup_stable_id: UsageObjectId | None = None
    setup_version: Annotated[str, Field(pattern=VERSION_PATTERN)] | None = None
    components: Annotated[list[InstalledComponent], Field(max_length=256)] = Field(
        default_factory=list[InstalledComponent]
    )
    components_complete: bool = False


class InstallationOperationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    operations: Annotated[list[InstallationOperationFact], Field(min_length=1, max_length=128)]


class InstallationOperationReceipt(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    accepted_ids: list[OperationId] = Field(default_factory=list)
    duplicate_ids: list[OperationId] = Field(default_factory=list)
    rejected_ids: list[OperationId] = Field(default_factory=list)
