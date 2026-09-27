"""Content-free corporate discovery snapshots, separate from usage events."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_stp_contracts.corporate import AccountId, DigestValue, OrganizationId, ProjectId
from ai_stp_contracts.http import Timestamp, open_wire_object, strict_request_object
from ai_stp_contracts.runtime_usage import (
    RuntimeUsageComponentKind,
    UsageDeviceId,
    UsageEventId,
    UsageObjectId,
)
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_foundation.versioning import VERSION_PATTERN


class InventoryObservedComponent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    location_digest: DigestValue
    kind: RuntimeUsageComponentKind
    harness: HarnessId
    source: Literal["managed", "external", "unknown"]
    state: Literal["present", "modified", "missing", "unknown"]
    stable_id: UsageObjectId | None = None
    version: Annotated[str, Field(pattern=VERSION_PATTERN)] | None = None
    setup_stable_id: UsageObjectId | None = None
    setup_version: Annotated[str, Field(pattern=VERSION_PATTERN)] | None = None

    @model_validator(mode="after")
    def managed_coordinates(self) -> "InventoryObservedComponent":
        if self.source == "managed" and (not self.stable_id or not self.version):
            raise ValueError("managed observations require component coordinates")
        if self.source != "managed" and (self.stable_id or self.version):
            raise ValueError("unmanaged observations cannot claim managed coordinates")
        return self


class InstallationInventorySnapshot(BaseModel):
    """One global or registered-project scope, including failed/partial checks."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    scan_id: UsageEventId
    organization_id: OrganizationId
    employee_id: AccountId
    device_id: UsageDeviceId
    project_id: ProjectId | None = None
    scope: Literal["global", "project"]
    scanned_at: Timestamp
    complete: bool
    components: Annotated[list[InventoryObservedComponent], Field(max_length=1024)]

    @model_validator(mode="after")
    def project_scope_matches_id(self) -> "InstallationInventorySnapshot":
        if (self.scope == "project") != (self.project_id is not None):
            raise ValueError("project scope requires a project id")
        return self


class InstallationInventoryBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    snapshots: Annotated[list[InstallationInventorySnapshot], Field(min_length=1, max_length=64)]


class InstallationInventoryReceipt(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    accepted_ids: list[UsageEventId] = Field(default_factory=list)
    duplicate_ids: list[UsageEventId] = Field(default_factory=list)
    rejected_ids: list[UsageEventId] = Field(default_factory=list)
