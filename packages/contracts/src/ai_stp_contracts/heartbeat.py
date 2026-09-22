"""Corporate installation heartbeat contracts (t-heartbeat, GitHub #215).

The heartbeat is an authenticated, tenant-scoped channel - separate from the
anonymous consented ping (ADR-0112). The closed field set is the whole
payload: account and device references bound to the session, `cli_version`,
`capabilities`, `last_sync_at`, the reported `health_state`, and `checked_at`.
Capability tokens accept only a small alphabet so paths, environment values,
and secrets cannot smuggle through the field.
"""

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_stp_contracts.corporate import AccountId, OrganizationId
from ai_stp_contracts.http import Timestamp, open_wire_object, strict_request_object
from ai_stp_foundation.ids import stable_id_pattern

DeviceId = Annotated[str, Field(pattern=stable_id_pattern("device"))]

# What an installation reports about itself. `stale` and `unknown` are never
# reported: they are read-time projections of freshness, not claims.
HeartbeatReportedState = Literal["active", "failing", "disabled"]
HeartbeatHealthState = Literal["active", "stale", "failing", "disabled", "unknown"]

# `name` or `name@version`; no whitespace or path separators.
CAPABILITY_TOKEN_PATTERN: Final = r"^[a-z0-9][a-z0-9._-]{0,63}(@[A-Za-z0-9][A-Za-z0-9.+_-]{0,63})?$"
CLI_VERSION_PATTERN: Final = r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$"

CapabilityToken = Annotated[str, Field(max_length=128, pattern=CAPABILITY_TOKEN_PATTERN)]


class InstallationHeartbeatRequest(BaseModel):
    """One CLI heartbeat write. Replayed or delayed writes coalesce."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    account_id: AccountId
    device_id: DeviceId
    cli_version: Annotated[str, Field(min_length=1, max_length=64, pattern=CLI_VERSION_PATTERN)]
    capabilities: Annotated[list[CapabilityToken], Field(max_length=64)] = Field(
        default_factory=list
    )
    last_sync_at: Timestamp | None = None
    health_state: HeartbeatReportedState
    checked_at: Timestamp


class InstallationHeartbeat(BaseModel):
    """Stored heartbeat plus the health state evaluated at read time."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    account_id: AccountId
    device_id: DeviceId
    cli_version: Annotated[str, Field(min_length=1, max_length=64)]
    capabilities: Annotated[list[CapabilityToken], Field(max_length=64)]
    last_sync_at: Timestamp | None = None
    reported_state: HeartbeatReportedState
    health_state: HeartbeatHealthState
    checked_at: Timestamp
    received_at: Timestamp
    revision: Annotated[int, Field(ge=1)]
    stale_after_seconds: Annotated[int, Field(ge=1)]


class InstallationHeartbeatStatus(BaseModel):
    """The caller's own installation health; `unknown` before the first beat."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    device_id: DeviceId
    health_state: HeartbeatHealthState
    evaluated_at: Timestamp
    stale_after_seconds: Annotated[int, Field(ge=1)]
    heartbeat: InstallationHeartbeat | None = None


class InstallationHeartbeatList(BaseModel):
    """Installation health rows visible to the caller's role."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    evaluated_at: Timestamp
    stale_after_seconds: Annotated[int, Field(ge=1)]
    total: Annotated[int, Field(ge=0)]
    items: Annotated[list[InstallationHeartbeat], Field(max_length=256)]
