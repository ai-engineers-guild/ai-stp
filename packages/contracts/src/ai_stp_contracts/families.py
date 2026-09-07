"""Setup family public and owner contracts (SPEC-065, ADR-0165)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_stp_contracts.assurance import AssessmentState, RecommendationState
from ai_stp_contracts.http import (
    IdempotencyKey,
    open_wire_object,
    strict_request_object,
)
from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_foundation.ids import stable_id_pattern
from ai_stp_foundation.refs import SetupRef
from ai_stp_foundation.versioning import VERSION_PATTERN
from ai_stp_passports.versions import ImplementationMode, ProjectionKind, TechnicalSupport

type FamilyId = Annotated[str, Field(pattern=stable_id_pattern("family"))]
type SetupId = Annotated[str, Field(pattern=stable_id_pattern("setup"))]
type ComponentId = Annotated[str, Field(pattern=stable_id_pattern("component"))]
type Version = Annotated[str, Field(pattern=VERSION_PATTERN)]
type Digest = Annotated[str, Field(pattern=DIGEST_PATTERN)]
type AlignmentState = Literal["aligned", "diverged", "unknown", "missing"]
type FamilyCreatedFrom = Literal["recast", "owner", "staff_migration", "migration"]
type FamilyMatchKind = Literal["family", "member_harness", "alignment"]


class SetupFamilyMember(BaseModel):
    """One accessible family member. Public reads omit inaccessible identity."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    name: Annotated[str, Field(min_length=1, max_length=200)]
    stable_id: SetupId
    harness_id: HarnessId
    latest_version: Version | None = None
    exact_version: Version | None = None
    passport_digest: Digest | None = None
    alignment: AlignmentState
    ported_from: SetupRef | None = None


class SetupFamilyPublic(BaseModel):
    """Public navigational family projection. Never installable content."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    family_id: FamilyId
    name: Annotated[str, Field(min_length=1, max_length=200)]
    baseline: SetupRef
    current_member: SetupFamilyMember | None = None
    members: Annotated[list[SetupFamilyMember], Field(max_length=7)] = Field(
        default_factory=list[SetupFamilyMember]
    )
    created_from: FamilyCreatedFrom


class SetupFamilyOwner(SetupFamilyPublic):
    """Owner family projection with revision and safe diagnostics."""

    revision: Annotated[int, Field(ge=1)]
    diagnostics: Annotated[list[str], Field(max_length=32)] = Field(default_factory=list)
    allowed_actions: Annotated[list[str], Field(max_length=16)] = Field(default_factory=list)


class SetupFamilyCreateRequest(BaseModel):
    """Idempotent authorized family creation with an exact baseline and members."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    name: Annotated[str, Field(min_length=1, max_length=200)]
    baseline: SetupRef
    members: Annotated[list[SetupId], Field(min_length=2, max_length=7)]
    expected_revision: Literal[0] = 0
    idempotency_key: IdempotencyKey
    reason: Annotated[str, Field(min_length=1, max_length=200)] = "owner_create"

    @model_validator(mode="after")
    def _baseline_is_a_member(self) -> SetupFamilyCreateRequest:
        if self.baseline.stable_id not in self.members:
            raise ValueError("family baseline must be one of the members")
        if len(self.members) != len(set(self.members)):
            raise ValueError("family members must be unique")
        return self


class SetupFamilyPatchRequest(BaseModel):
    """Expected-revision mutation of name, baseline, or membership."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    expected_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey
    name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    baseline: SetupRef | None = None
    add_members: Annotated[list[SetupId], Field(max_length=7)] = Field(default_factory=list)
    remove_members: Annotated[list[SetupId], Field(max_length=7)] = Field(default_factory=list)
    reason: Annotated[str, Field(min_length=1, max_length=200)] = "owner_update"

    @model_validator(mode="after")
    def _has_a_mutation(self) -> SetupFamilyPatchRequest:
        if (
            self.name is None
            and self.baseline is None
            and not self.add_members
            and not self.remove_members
        ):
            raise ValueError("family patch must change name, baseline, or membership")
        if len(self.add_members) != len(set(self.add_members)):
            raise ValueError("added members must be unique")
        if len(self.remove_members) != len(set(self.remove_members)):
            raise ValueError("removed members must be unique")
        overlap = set(self.add_members).intersection(self.remove_members)
        if overlap:
            raise ValueError("a member cannot be added and removed in one patch")
        return self


class SelectedAdaptation(BaseModel):
    """The one adaptation selected for the viewed setup harness."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    adaptation_id: Annotated[str, Field(pattern=r"^adaptation_[0-9a-f]{64}$")]
    harness_id: HarnessId
    implementation_mode: ImplementationMode
    projection_kind: ProjectionKind
    technical_support: TechnicalSupport
    scopes: list[str] = Field(default_factory=list)
    assessment_state: AssessmentState = "not_verified"
    recommendation: RecommendationState = "ineffective"
    limitations: list[str] = Field(default_factory=list)


class SetupCompositionMember(BaseModel):
    """Exact component pin plus the selected adaptation for this setup harness."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: ComponentId
    version: Version
    passport_digest: Digest
    selected_adaptation: SelectedAdaptation
