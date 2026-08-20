"""Report case and staff moderation wire payloads (SPEC-026, SPEC-016)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_stp_contracts.http import (
    IdempotencyKey,
    Timestamp,
    open_wire_object,
    strict_request_object,
)
from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.versioning import VERSION_PATTERN

type ReportState = Literal[
    "submitted",
    "triaged",
    "awaiting_author",
    "security_escalated",
    "resolved",
    "dismissed",
]
type ObjectKind = Literal["component", "setup"]
type LifecycleAction = Literal["block", "hide", "restore"]
type ContentDigest = Annotated[str, Field(pattern=DIGEST_PATTERN)]
type Version = Annotated[str, Field(pattern=VERSION_PATTERN)]


class ReportCaseCreateRequest(BaseModel):
    """POST /v1/reports body."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    object_kind: ObjectKind
    stable_id: Annotated[str, Field(min_length=8, max_length=64)]
    version: Version
    content_digest: ContentDigest
    harness_id: Annotated[str, Field(default="", max_length=64)] = ""
    harness_version: Annotated[str, Field(default="", max_length=32)] = ""
    provider_version: Annotated[str, Field(default="", max_length=32)] = ""
    operation_id: Annotated[str, Field(default="", max_length=64)] = ""
    error_code: Annotated[str, Field(default="", max_length=64)] = ""
    validation_snapshot_ids: Annotated[list[str], Field(default_factory=list, max_length=16)]
    diagnostics: Annotated[str, Field(default="", max_length=4000)] = ""
    diagnostics_previewed: bool = False
    vulnerability: bool = False
    idempotency_key: IdempotencyKey


class ReportCaseResponse(BaseModel):
    """One closed report case (reporter view — no secrets)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    case_id: Annotated[str, Field(min_length=8, max_length=64)]
    object_kind: ObjectKind
    stable_id: str
    version: Version
    state: ReportState
    vulnerability: bool = False
    created_at: Timestamp


class ReportCaseListResponse(BaseModel):
    """Reporter's own cases."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    items: Annotated[list[ReportCaseResponse], Field(default_factory=list)]


class StaffTriageRequest(BaseModel):
    """POST /v1/staff/reports/{case_id}/triage body."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    state: Literal["triaged", "awaiting_author", "security_escalated", "resolved", "dismissed"]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    idempotency_key: IdempotencyKey


class StaffLifecycleRequest(BaseModel):
    """POST /v1/staff/versions/lifecycle body."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    object_kind: ObjectKind
    stable_id: Annotated[str, Field(min_length=8, max_length=64)]
    version: Version
    action: LifecycleAction
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    idempotency_key: IdempotencyKey


class StaffAuthorVerifiedRequest(BaseModel):
    """POST /v1/staff/author-verified body."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    subject_account_id: Annotated[str, Field(min_length=8, max_length=64)]
    verified: bool
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    idempotency_key: IdempotencyKey


class StaffActionResponse(BaseModel):
    """Generic staff mutation outcome."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    applied: bool = True
    action: Annotated[str, Field(min_length=1, max_length=64)]


class CliReportPreview(BaseModel):
    """Durable exact report payload shown before its external submission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    plan_id: Annotated[str, Field(min_length=8, max_length=64)]
    plan_digest: ContentDigest
    report: ReportCaseCreateRequest
    submitted: bool = False


class CliReportCaseView(ReportCaseResponse):
    """CLI reporter view, intentionally separate from the HTTP schema."""


class CliReportListView(ReportCaseListResponse):
    """CLI list view, intentionally separate from the HTTP schema."""
