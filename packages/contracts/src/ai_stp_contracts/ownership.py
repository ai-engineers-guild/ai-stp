"""Verified-maintainer ownership claim transfer (SPEC-057 REQ-5717)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_stp_contracts.http import (
    IdempotencyKey,
    Timestamp,
    open_wire_object,
    strict_request_object,
)

type ClaimState = Literal["requested", "approved", "denied"]
type Version = Annotated[str, Field(pattern=r"^\d+\.\d+$")]


class OwnershipClaimCreateRequest(BaseModel):
    """POST /v1/ownership-claims body."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=8, max_length=64)]
    reason: Annotated[str, Field(min_length=1, max_length=2000)]
    evidence: Annotated[str, Field(min_length=1, max_length=4000)]
    idempotency_key: IdempotencyKey


class OwnershipClaimPreview(BaseModel):
    """Exact object and major lines that a claim would transfer."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    object_kind: Literal["component"] = "component"
    stable_id: str
    name: str = ""
    current_owner_account_id: str
    versions: list[Version]
    major_lines: list[int]


class OwnershipClaimResponse(BaseModel):
    """One ownership claim, including the staff preview."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    claim_id: Annotated[str, Field(min_length=8, max_length=64)]
    stable_id: str
    requester_account_id: str
    from_account_id: str
    to_account_id: str
    reason: str
    evidence: str
    state: ClaimState
    preview: OwnershipClaimPreview
    created_at: Timestamp
    decided_at: Timestamp | None = None
    staff_account_id: str | None = None
    decision_reason: str | None = None


class OwnershipClaimDecisionRequest(BaseModel):
    """POST /v1/staff/ownership-claims/{claim_id}/approve or /deny body."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    reason: Annotated[str, Field(min_length=1, max_length=2000)]
    idempotency_key: IdempotencyKey


class OwnershipRevisionView(BaseModel):
    """One immutable ownership revision. Published version passports are unchanged."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    revision_id: Annotated[str, Field(min_length=8, max_length=64)]
    claim_id: str
    stable_id: str
    from_account_id: str
    to_account_id: str
    major_lines: list[int]
    reason: str
    staff_account_id: str
    created_at: Timestamp


class OwnershipRevisionListResponse(BaseModel):
    """History of ownership revisions for one catalog component."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: str
    items: list[OwnershipRevisionView]
