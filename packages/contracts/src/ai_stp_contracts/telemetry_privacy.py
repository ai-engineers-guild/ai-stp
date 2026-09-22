"""Corporate telemetry privacy contracts: bounded events, policy, and data rights."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_stp_contracts.corporate import AccountId, OrganizationId
from ai_stp_contracts.http import (
    IdempotencyKey,
    Timestamp,
    open_wire_object,
    strict_request_object,
)
from ai_stp_foundation.versioning import VERSION_PATTERN

TelemetryEventKind = Literal["heartbeat", "invocation"]
TelemetryEventOutcome = Literal["succeeded", "failed", "denied", "unknown"]
TelemetryHealth = Literal["active", "stale", "failing", "disabled", "unknown"]
TelemetryLegalBasis = Literal["consent", "contract", "legitimate_interest"]
TelemetryRightState = Literal["active", "revoked", "deleted"]
TelemetrySubjectState = Literal["active", "anonymized"]
TelemetrySubjectKind = Literal["account", "device"]
TelemetryDeletionMode = Literal["anonymize", "delete"]

_IDENTIFIER = Annotated[str, Field(min_length=1, max_length=64)]
_SAFE_TEXT = Annotated[str, Field(min_length=1, max_length=200)]
_SAFE_VALUE = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[^\x00-\x1f]+$")]


class CorporateTelemetryHeartbeatEvent(BaseModel):
    """One corporate heartbeat; the field list is closed and enumerable."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    kind: Literal["heartbeat"] = "heartbeat"
    event_id: Annotated[str, Field(min_length=1, max_length=128)]
    account_id: AccountId | None = None
    device_id: _IDENTIFIER | None = None
    harness: _IDENTIFIER
    harness_version: _SAFE_VALUE | None = None
    provider_name: _IDENTIFIER | None = None
    provider_version: _SAFE_VALUE | None = None
    capabilities: Annotated[list[_SAFE_VALUE], Field(max_length=32)] = Field(
        default_factory=list[str]
    )
    last_sync_at: Timestamp | None = None
    health: TelemetryHealth = "unknown"
    occurred_at: Timestamp


class CorporateTelemetryInvocationEvent(BaseModel):
    """One corporate component invocation; prompts and content have no fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    kind: Literal["invocation"] = "invocation"
    event_id: Annotated[str, Field(min_length=1, max_length=128)]
    account_id: AccountId | None = None
    device_id: _IDENTIFIER | None = None
    project_id: _IDENTIFIER | None = None
    harness: _IDENTIFIER
    harness_version: _SAFE_VALUE | None = None
    setup_id: _IDENTIFIER | None = None
    component_kind: _IDENTIFIER | None = None
    component_stable_id: _IDENTIFIER | None = None
    component_version: Annotated[str, Field(pattern=VERSION_PATTERN)] | None = None
    outcome: TelemetryEventOutcome = "unknown"
    occurred_at: Timestamp


CorporateTelemetryEventPayload = Annotated[
    CorporateTelemetryHeartbeatEvent | CorporateTelemetryInvocationEvent,
    Field(discriminator="kind"),
]


class CorporateTelemetryEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    event: CorporateTelemetryEventPayload
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey


class CorporateTelemetryEventView(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    kind: TelemetryEventKind
    event_id: str
    account_id: str | None = None
    device_id: str | None = None
    project_id: str | None = None
    harness: str
    harness_version: str | None = None
    provider_name: str | None = None
    provider_version: str | None = None
    capabilities: list[str] = Field(default_factory=list[str])
    last_sync_at: Timestamp | None = None
    health: TelemetryHealth | None = None
    setup_id: str | None = None
    component_kind: str | None = None
    component_stable_id: str | None = None
    component_version: str | None = None
    outcome: TelemetryEventOutcome | None = None
    subject_state: TelemetrySubjectState
    occurred_at: Timestamp
    received_at: Timestamp


class CorporateTelemetryEventQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    event_kind: TelemetryEventKind | None = None
    account_id: AccountId | None = None
    before_occurred_at: Timestamp | None = None
    before_id: str | None = None
    limit: Annotated[int, Field(ge=1, le=100)] = 50


class CorporateTelemetryEventList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    items: list[CorporateTelemetryEventView] = Field(
        default_factory=list[CorporateTelemetryEventView]
    )
    next_before_occurred_at: Timestamp | None = None
    next_before_id: str | None = None


class CorporateTelemetryAggregate(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    day: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
    event_kind: TelemetryEventKind
    outcome: str | None = None
    event_count: Annotated[int, Field(ge=0)]


class CorporateTelemetryAggregateQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    occurred_from: Timestamp | None = None
    occurred_to: Timestamp | None = None


class CorporateTelemetryAggregateList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    items: list[CorporateTelemetryAggregate] = Field(
        default_factory=list[CorporateTelemetryAggregate]
    )


class CorporateTelemetryExportQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    occurred_from: Timestamp | None = None
    occurred_to: Timestamp | None = None
    limit: Annotated[int, Field(ge=1, le=1000)] = 1000


class CorporateTelemetryExport(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    exported_at: Timestamp
    items: list[CorporateTelemetryEventView] = Field(
        default_factory=list[CorporateTelemetryEventView]
    )


class CorporateTelemetryPolicyView(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    raw_retention_days: Annotated[int, Field(ge=1, le=3650)]
    aggregate_retention_days: Annotated[int, Field(ge=1, le=3650)]
    legal_basis: TelemetryLegalBasis
    notice_text: str | None = None
    notice_revision: Annotated[int, Field(ge=0)]
    policy_version: Annotated[int, Field(ge=1)]
    updated_at: Timestamp


class CorporateTelemetryPolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    raw_retention_days: Annotated[int, Field(ge=1, le=3650)]
    aggregate_retention_days: Annotated[int, Field(ge=1, le=3650)] = 365
    legal_basis: TelemetryLegalBasis
    notice_text: Annotated[str, Field(max_length=4000)] | None = None
    notice_revision: Annotated[int, Field(ge=0)]
    expected_policy_revision: Annotated[int, Field(ge=0)]
    authorization_revision: Annotated[int, Field(ge=1)]
    reason: _SAFE_TEXT = "telemetry policy"
    idempotency_key: IdempotencyKey


class CorporateTelemetryRightView(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    subject_kind: TelemetrySubjectKind
    subject_id: _IDENTIFIER
    state: TelemetryRightState
    legal_basis: TelemetryLegalBasis | None = None
    notice_revision: Annotated[int, Field(ge=0)] = 0
    notice_acknowledged_at: Timestamp | None = None
    revoked_at: Timestamp | None = None
    deletion_requested_at: Timestamp | None = None
    anonymized_at: Timestamp | None = None
    deleted_at: Timestamp | None = None
    updated_at: Timestamp


class CorporateTelemetryRightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    subject_kind: TelemetrySubjectKind = "account"
    subject_id: _IDENTIFIER
    legal_basis: TelemetryLegalBasis
    notice_revision: Annotated[int, Field(ge=0)]
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey


class CorporateTelemetryRevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    anonymize: bool = True
    reason: _SAFE_TEXT
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey


class CorporateTelemetryDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    subject_kind: TelemetrySubjectKind = "account"
    subject_id: _IDENTIFIER
    mode: TelemetryDeletionMode = "delete"
    reason: _SAFE_TEXT
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey


class CorporateTelemetryDeleteResult(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    subject_kind: TelemetrySubjectKind
    subject_id: str
    mode: TelemetryDeletionMode
    affected_events: Annotated[int, Field(ge=0)]
    state: TelemetryRightState
    processed_at: Timestamp


class CorporateTelemetryEventBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    events: Annotated[list[CorporateTelemetryEventPayload], Field(max_length=100)]
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey

    @model_validator(mode="after")
    def distinct_event_ids(self) -> Self:
        ids = [event.event_id for event in self.events]
        if len(ids) != len(set(ids)):
            raise ValueError("telemetry batch contains a repeated event_id")
        return self


class CorporateTelemetryEventBatchResult(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    accepted: Annotated[int, Field(ge=0)]
    deduplicated: Annotated[int, Field(ge=0)]
    items: list[CorporateTelemetryEventView] = Field(
        default_factory=list[CorporateTelemetryEventView]
    )


class CorporateTelemetryAuditView(BaseModel):
    """One governance audit row; `detail` carries counts and ids, no payloads."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    audit_id: int
    organization_id: OrganizationId
    actor_account_id: str | None = None
    action: str
    target_table: str
    target_id: str
    detail: dict[str, object] = Field(default_factory=dict)
    request_id: str | None = None
    created_at: Timestamp


class CorporateTelemetryAuditQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    before_id: Annotated[int, Field(ge=1)] | None = None
    limit: Annotated[int, Field(ge=1, le=100)] = 50


class CorporateTelemetryAuditList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    items: list[CorporateTelemetryAuditView] = Field(
        default_factory=list[CorporateTelemetryAuditView]
    )
    next_before_id: int | None = None
