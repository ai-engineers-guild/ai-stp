"""Target-bound assurance and portability projection contracts (SPEC-064)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_stp_contracts.http import Timestamp, open_wire_object, strict_request_object
from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_foundation.ids import stable_id_pattern
from ai_stp_foundation.versioning import VERSION_PATTERN
from ai_stp_passports.versions import (
    ImplementationMode,
    ProjectionKind,
    TargetScope,
    TechnicalSupport,
)

type AssessmentState = Literal["not_verified", "verified", "failed", "stale"]
type RecommendationState = Literal["recommended", "not_recommended", "ineffective"]
type MatchKind = Literal["exact", "claimed_portable"]
type CompatibilityMode = Literal["claimed_portable"]
type SupportedOs = Literal["linux", "macos", "windows"]
type SupportedArch = Literal["x86_64", "arm64"]
type ArtifactCheckResult = Literal["passed", "failed"]
type Digest = Annotated[str, Field(pattern=DIGEST_PATTERN)]
type Version = Annotated[str, Field(pattern=VERSION_PATTERN)]
type ComponentId = Annotated[str, Field(pattern=stable_id_pattern("component"))]
type AdaptationId = Annotated[str, Field(pattern=r"^adaptation_[0-9a-f]{64}$")]
type ClaimId = Annotated[str, Field(pattern=r"^claim_[0-9a-f]{64}$")]


class ArtifactObservationIdentity(BaseModel):
    """Complete reuse key for one byte-oriented safety observation."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    artifact_digest: Digest
    check_id: Annotated[str, Field(min_length=1, max_length=64)]
    scanner_id: Annotated[str, Field(min_length=1, max_length=64)]
    scanner_version: Annotated[str, Field(min_length=1, max_length=64)]
    policy_version: Annotated[str, Field(min_length=1, max_length=64)]
    operating_system: SupportedOs | None = None
    architecture: SupportedArch | None = None


class ArtifactObservation(BaseModel):
    """Reusable exact-byte observation. Compatibility results stay independent."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    identity: ArtifactObservationIdentity
    result: ArtifactCheckResult
    observed_at: Timestamp
    expires_at: Timestamp | None = None


class TargetAssessmentIdentity(BaseModel):
    """Full target key. Any field mismatch is a different assessment."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    component_stable_id: ComponentId
    version: Version
    passport_digest: Digest
    adaptation_id: AdaptationId
    harness_id: HarnessId
    scope: TargetScope
    projection_artifact_digest: Digest
    provider_id: Annotated[str, Field(min_length=1, max_length=128)]
    provider_version: Annotated[str, Field(min_length=1, max_length=64)]
    surface_profile_id: Annotated[str, Field(min_length=1, max_length=128)]
    surface_profile_digest: Digest
    target_scope: TargetScope
    harness_version: Annotated[str, Field(min_length=1, max_length=128)]
    operating_system: SupportedOs
    architecture: SupportedArch
    policy_version: Annotated[str, Field(min_length=1, max_length=64)]


class TargetAssessmentIngestRequest(BaseModel):
    """Authenticated platform evidence writer payload. Authors cannot issue verification."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    identity: TargetAssessmentIdentity
    stored_state: Literal["not_verified", "verified", "failed"]
    observations: Annotated[list[ArtifactObservation], Field(max_length=32)] = Field(
        default_factory=list[ArtifactObservation]
    )
    compatibility_result: Literal["passed", "failed", "not_run"] = "not_run"
    reason_code: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    evidence_refs: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=512)]], Field(max_length=16)
    ] = Field(default_factory=list)
    observed_at: Timestamp
    expires_at: Timestamp | None = None
    idempotency_key: Annotated[str, Field(min_length=16, max_length=128)]


class TargetAssessmentIngestResponse(BaseModel):
    """Latest-effective projection after an accepted or idempotent ingest."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    target_key_digest: Digest
    stored_state: Literal["not_verified", "verified", "failed"]
    effective_state: AssessmentState
    created: bool


class PublicEvidenceRef(BaseModel):
    """Allowlisted public evidence pointer. No storage keys or raw reports."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    kind: Literal["policy", "profile", "digest", "url"]
    value: Annotated[str, Field(min_length=1, max_length=512)]
    observed_at: Timestamp | None = None
    expires_at: Timestamp | None = None


class AssuranceCounts(BaseModel):
    """Bounded card summary. Claims never increase the verified numerator."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    verified_targets: Annotated[int, Field(ge=0)] = 0
    assessed_targets: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def _verified_cannot_exceed_assessed(self) -> AssuranceCounts:
        if self.verified_targets > self.assessed_targets:
            raise ValueError("verified targets cannot exceed assessed targets")
        return self


class ExactTargetRow(BaseModel):
    """One exact adaptation/scope row in the public harness matrix."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    kind: Literal["exact"] = "exact"
    harness_id: HarnessId
    adaptation_id: AdaptationId
    scope: TargetScope
    implementation_mode: ImplementationMode
    projection_kind: ProjectionKind
    technical_support: TechnicalSupport
    technical_support_reason: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    supported_os: list[SupportedOs] = Field(default_factory=list[SupportedOs])
    supported_arch: list[SupportedArch] = Field(default_factory=list[SupportedArch])
    semantic_losses: list[str] = Field(default_factory=list)
    permissions_summary: list[str] = Field(default_factory=list)
    assessment_state: AssessmentState = "not_verified"
    freshness: Timestamp | None = None
    recommendation: RecommendationState = "ineffective"
    evidence_refs: list[PublicEvidenceRef] = Field(default_factory=list[PublicEvidenceRef])


class ClaimTargetRow(BaseModel):
    """One claim-only target. Never exact availability or install eligibility."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    kind: Literal["claimed_portable"] = "claimed_portable"
    harness_id: HarnessId
    claim_id: ClaimId
    transform_family: Annotated[str, Field(min_length=1, max_length=64)]
    transform_version: Version
    component_types: list[str] = Field(default_factory=list)
    scopes: list[TargetScope] = Field(default_factory=list[TargetScope])
    limitations: list[str] = Field(default_factory=list)
    issued_at: Timestamp
    expires_at: Timestamp | None = None
    evidence_refs: list[PublicEvidenceRef] = Field(default_factory=list[PublicEvidenceRef])
    risk_cli_command: Annotated[str, Field(min_length=1, max_length=512)] | None = None


class TargetMatrix(BaseModel):
    """Detail/version projection of exact rows and claim-only rows."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    exact: list[ExactTargetRow] = Field(default_factory=list[ExactTargetRow])
    claimed_portable: list[ClaimTargetRow] = Field(default_factory=list[ClaimTargetRow])


class CompatibilityFacets(BaseModel):
    """Separate exact and claimed-portable counts for the current public query."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    exact: Annotated[int, Field(ge=0)] = 0
    claimed_portable: Annotated[int, Field(ge=0)] = 0


class OwnerTargetGap(BaseModel):
    """Owner-safe coverage diagnostic. No foreign evidence or storage keys."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    harness_id: HarnessId
    scope: TargetScope | None = None
    state: AssessmentState
    reason_code: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    next_action: Annotated[str, Field(min_length=1, max_length=128)]
    claim_id: ClaimId | None = None
    expires_at: Timestamp | None = None


RISK_INSTALL_TEMPLATE = (
    "ai-stp component risk-install --id {stable_id} --version {version} "
    "--harness {harness_id} --claim-id {claim_id}"
)


def risk_install_command(*, stable_id: str, version: str, harness_id: str, claim_id: str) -> str:
    """Version-scoped local CLI command. Web never executes it."""
    return RISK_INSTALL_TEMPLATE.format(
        stable_id=stable_id, version=version, harness_id=harness_id, claim_id=claim_id
    )
