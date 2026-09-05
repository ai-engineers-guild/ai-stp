"""Report case and staff moderation wire payloads (SPEC-026, SPEC-016)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_stp_contracts.http import (
    IdempotencyKey,
    Timestamp,
    open_wire_object,
    strict_request_object,
)
from ai_stp_contracts.text_safety import validate_public_text
from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.ids import stable_id_pattern
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
type RequestTopic = Literal[
    "object_report",
    "service_request",
    "country_request",
    "component_complaint",
    "author_complaint",
    "ownership_transfer",
    "verification_request",
    "other",
]
type RequestLocale = Literal["ru", "en"]
type LifecycleAction = Literal["block", "hide", "restore"]
REQUEST_TOPICS: tuple[RequestTopic, ...] = (
    "object_report",
    "service_request",
    "country_request",
    "component_complaint",
    "author_complaint",
    "ownership_transfer",
    "verification_request",
    "other",
)
type ContentDigest = Annotated[str, Field(pattern=DIGEST_PATTERN)]
type Version = Annotated[str, Field(pattern=VERSION_PATTERN)]
type CountryCode = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]


class ServiceRequest(BaseModel):
    """Data needed for an operator to add a service manually."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    name: Annotated[str, Field(min_length=1, max_length=160)]
    primary_url: Annotated[str, Field(pattern=r"^https://", max_length=512)]
    description_ru: Annotated[str, Field(min_length=1, max_length=2000)]
    description_en: Annotated[str, Field(min_length=1, max_length=2000)]
    source_url: Annotated[str, Field(pattern=r"^https://", max_length=512)]
    country_codes: Annotated[list[CountryCode], Field(default_factory=list, max_length=249)]

    @field_validator("name", "description_ru", "description_en")
    @classmethod
    def public_text_safe(cls, value: str) -> str:
        return validate_public_text(value)


class CountryRequest(BaseModel):
    """Localized ISO country data requested for manual addition."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    code: Annotated[str, Field(pattern=r"^[A-Z]{2}$")]
    name_ru: Annotated[str, Field(min_length=1, max_length=160)]
    name_en: Annotated[str, Field(min_length=1, max_length=160)]

    @field_validator("name_ru", "name_en")
    @classmethod
    def public_text_safe(cls, value: str) -> str:
        return validate_public_text(value)


class ReportCaseCreateRequest(BaseModel):
    """POST /v1/requests body; object reports remain accepted at /v1/reports."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    topic: RequestTopic = "object_report"
    object_kind: ObjectKind | None = None
    stable_id: Annotated[str, Field(min_length=8, max_length=64)] | None = None
    version: Version | None = None
    content_digest: ContentDigest | None = None
    service: ServiceRequest | None = None
    country: CountryRequest | None = None
    subject: Annotated[str, Field(default="", max_length=160)] = ""
    message: Annotated[str, Field(default="", max_length=2000)] = ""
    evidence: Annotated[str, Field(default="", max_length=4000)] = ""
    recipient_account_id: Annotated[str, Field(pattern=stable_id_pattern("account"))] | None = None
    author_account_id: Annotated[str, Field(pattern=stable_id_pattern("account"))] | None = None
    locale: RequestLocale = "en"
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

    @model_validator(mode="after")
    def validate_topic_payload(self) -> ReportCaseCreateRequest:
        object_fields = (self.object_kind, self.stable_id, self.version, self.content_digest)
        catalog_fields = (self.service, self.country)
        extra_identity = (self.recipient_account_id, self.author_account_id)
        if self.topic == "object_report":
            if (
                any(value is None for value in object_fields)
                or any(catalog_fields)
                or any(extra_identity)
                or self.subject
            ):
                raise ValueError("object_report requires exact object fields only")
        elif self.topic == "service_request":
            if (
                self.service is None
                or self.country
                or any(value is not None for value in object_fields)
                or any(extra_identity)
                or self.subject
            ):
                raise ValueError("service_request requires service data only")
        elif self.topic == "country_request":
            if (
                self.country is None
                or self.service
                or any(value is not None for value in object_fields)
                or any(extra_identity)
                or self.subject
            ):
                raise ValueError("country_request requires country data only")
        elif self.topic == "component_complaint":
            if (
                self.stable_id is None
                or self.object_kind not in {None, "component"}
                or any(catalog_fields)
                or self.subject
            ):
                raise ValueError("component_complaint requires a component stable id")
        elif self.topic == "author_complaint":
            if (
                self.author_account_id is None
                or any(catalog_fields)
                or self.subject
                or self.recipient_account_id is not None
            ):
                raise ValueError("author_complaint requires an author account")
        elif self.topic == "ownership_transfer":
            if (
                self.stable_id is None
                or self.object_kind not in {None, "component"}
                or self.recipient_account_id is None
                or not self.message.strip()
                or any(catalog_fields)
                or self.subject
            ):
                raise ValueError(
                    "ownership_transfer requires the component line, recipient, and reason"
                )
        elif self.topic == "verification_request":
            if (
                self.author_account_id is None
                or any(catalog_fields)
                or self.subject
                or self.recipient_account_id is not None
            ):
                raise ValueError("verification_request requires the subject account")
        elif not self.subject.strip() or any(catalog_fields):
            raise ValueError("other requires a custom subject")
        if self.topic != "object_report" and self.vulnerability:
            raise ValueError("only object_report may be marked as a vulnerability")
        return self


class ReportCaseResponse(BaseModel):
    """One closed report case (reporter view — no secrets)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    case_id: Annotated[str, Field(min_length=8, max_length=64)]
    topic: RequestTopic = "object_report"
    object_kind: ObjectKind | Literal[""] = ""
    stable_id: str = ""
    version: Version | Literal[""] = ""
    state: ReportState
    vulnerability: bool = False
    locale: RequestLocale = "en"
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


class StaffAuthorVerificationRequest(BaseModel):
    """POST /v1/staff/author-verified body."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    subject_account_id: Annotated[str, Field(pattern=stable_id_pattern("account"))]
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
