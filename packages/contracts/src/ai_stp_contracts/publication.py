"""Publication plan and validation wire payloads (SPEC-026, SPEC-007)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_stp_assurance.attestation import SIGNATURE_PATTERN
from ai_stp_contracts.auth import AccountId, DeviceId
from ai_stp_contracts.http import (
    IdempotencyKey,
    Timestamp,
    open_wire_object,
    strict_request_object,
)
from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_foundation.ids import stable_id_pattern
from ai_stp_foundation.refs import ComponentRef, SetupRef
from ai_stp_foundation.versioning import VERSION_PATTERN

type ObjectKind = Literal["component", "setup"]
type PlanState = Literal[
    "draft",
    "ready",
    "validating",
    "publish_planned",
    "published",
    "failed",
    "cancelled",
    "stale",
]
type EvidenceSource = Literal[
    "author_attested",
    "platform_digest_verified",
    "platform_structure_verified",
    "platform_safety_scan",
    "provider_installation_tested",
    "runtime_tested",
]
type CheckResult = Literal["passed", "warning", "failed", "degraded", "not_run", "expired"]
type ContentDigest = Annotated[str, Field(pattern=DIGEST_PATTERN)]
type Version = Annotated[str, Field(pattern=VERSION_PATTERN)]
type PlanId = Annotated[str, Field(min_length=8, max_length=64)]
type PolicyVersion = Annotated[str, Field(min_length=1, max_length=32)]


class AuthorAttestation(BaseModel):
    """Full closed author attestation on the /v1 wire (ADR-0092)."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    object_digest: ContentDigest
    subject: ComponentRef | SetupRef
    check_id: Annotated[str, Field(min_length=1, max_length=64)]
    policy_version: PolicyVersion
    tool_versions: Annotated[dict[str, str], Field(default_factory=dict)]
    harness_id: HarnessId
    harness_version: Annotated[str, Field(min_length=1, max_length=64)]
    provider_version: Annotated[str, Field(min_length=1, max_length=64)]
    test_case_ids: Annotated[list[str], Field(min_length=1, max_length=64)]
    result: Literal["passed", "failed"]
    account_id: Annotated[str, Field(pattern=stable_id_pattern("account"))]
    device_id: DeviceId
    attested_at: Timestamp
    #: Ed25519 signature over attestation_digest; never logged.
    signature: Annotated[str, Field(pattern=SIGNATURE_PATTERN)]


class PublicationPlanCreateRequest(BaseModel):
    """POST /v1/publications/plans body."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    object_kind: ObjectKind
    stable_id: Annotated[str, Field(min_length=8, max_length=64)]
    version: Version
    content_digest: ContentDigest
    policy_version: PolicyVersion = "1"
    passport: dict[str, object]
    attestations: Annotated[list[AuthorAttestation], Field(default_factory=list, max_length=32)]
    idempotency_key: IdempotencyKey
    device_id: DeviceId


class EvidenceBindingView(BaseModel):
    """One accepted evidence binding on a snapshot."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    check_id: str
    result: CheckResult
    source: EvidenceSource
    expires_at: Timestamp | None = None

    #: Why this check did not pass, in terms the publisher can act on. Absent
    #: when it passed, because there is nothing to explain.
    #:
    #: It exists because a refusal without one is a dead end. A whole corpus was
    #: rejected on a single check whose only wire representation was the word
    #: `failed`, and the cause — a scanner timing out — was recoverable only by
    #: reading the platform's source. `SafetyCheckEntry` already carried a
    #: `reason`; the response a publisher actually reads did not.
    #:
    #: Never findings themselves: a rule identifier and a count say what to look
    #: at without putting scanned content on a wire that reaches a client.
    reason: Annotated[str, Field(max_length=200)] | None = None


class PublicationPlanResponse(BaseModel):
    """Plan create/status/confirm response."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    plan_id: PlanId
    plan_hash: Annotated[str, Field(min_length=16, max_length=128)]
    state: PlanState
    object_kind: ObjectKind
    stable_id: str
    version: Version
    content_digest: ContentDigest
    policy_version: PolicyVersion
    actor_id: AccountId
    device_id: DeviceId
    expires_at: Timestamp
    component_verified: bool = False
    evidence: Annotated[list[EvidenceBindingView], Field(default_factory=list)]
    effects: Annotated[list[str], Field(default_factory=list)]


class PublicationConfirmRequest(BaseModel):
    """POST /v1/publications/plans/{plan_id}/confirm body."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    plan_hash: Annotated[str, Field(min_length=16, max_length=128)]
    confirmed: Literal[True] = True
    idempotency_key: IdempotencyKey
