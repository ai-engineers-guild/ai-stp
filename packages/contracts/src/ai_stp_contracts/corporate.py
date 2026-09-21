"""Corporate bootstrap, RBAC, project, and audit wire contracts (SPEC-079)."""

import re
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.json_schema import JsonSchemaValue

from ai_stp_contracts.http import IdempotencyKey, Timestamp, open_wire_object, strict_request_object
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_foundation.ids import stable_id_pattern
from ai_stp_foundation.versioning import VERSION_PATTERN

OrganizationId = Annotated[str, Field(pattern=stable_id_pattern("organization"))]
AccountId = Annotated[str, Field(pattern=stable_id_pattern("account"))]
JobTitleId = Annotated[str, Field(pattern=stable_id_pattern("job_title"))]
TeamId = Annotated[str, Field(pattern=stable_id_pattern("operation"))]
ProjectId = Annotated[str, Field(pattern=stable_id_pattern("remote_project"))]
TechnologyId = Annotated[str, Field(pattern=stable_id_pattern("technology"))]
CorporateRole = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_-]*$",
        description="Tenant-local role name.",
    ),
]
CorporateState = Literal["active", "suspended"]
AssignmentSubjectKind = Literal["employee", "team", "project", "technology", "organization"]
AssignmentSelector = Literal["exact", "latest"]
AssignmentState = Literal["current", "retired"]
DigestValue = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
JobTitleState = Literal["current", "retired"]
ProjectState = Literal["active", "archived"]
ProjectLifecycle = Literal["active", "deprecated", "archived", "deleted"]
ScopeKind = Literal[
    "system", "organization", "team", "project", "technology", "catalog_object", "telemetry"
]


class CorporateCatalogAssignmentRequest(BaseModel):
    """Assign a stable catalog line without granting access or installing it."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    subject_kind: AssignmentSubjectKind
    subject_id: Annotated[str, Field(min_length=1, max_length=64)]
    object_kind: Literal["setup", "component"]
    stable_id: Annotated[str, Field(min_length=1, max_length=64)]
    selector: AssignmentSelector = "exact"
    version: Annotated[str, Field(pattern=VERSION_PATTERN)] | None = None
    passport_digest: DigestValue | None = None
    harness: HarnessId | None = None
    state: AssignmentState = "current"
    expected_revision: Annotated[int, Field(ge=0)]
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey

    @model_validator(mode="after")
    def typed_coordinates(self) -> Self:
        subject_prefix = {
            "employee": "account",
            "team": "operation",
            "project": "remote_project",
            "technology": "technology",
            "organization": "organization",
        }[self.subject_kind]
        subject_pattern = stable_id_pattern(subject_prefix)
        if not re.fullmatch(subject_pattern, self.subject_id):
            raise ValueError("subject identity does not match its kind")
        if not re.fullmatch(stable_id_pattern(self.object_kind), self.stable_id):
            raise ValueError("catalog identity does not match its kind")
        if self.selector == "exact" and self.version is None:
            raise ValueError("an exact selector requires an immutable version")
        if self.selector == "latest":
            if self.version is not None:
                raise ValueError("a latest selector cannot pin a version")
            if self.passport_digest is not None:
                raise ValueError("a latest selector cannot pin a digest")
        if self.state == "retired" and self.expected_revision == 0:
            raise ValueError("retiring an assignment requires its current revision")
        return self


class CorporateCatalogAssignment(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    assignment_id: Annotated[str, Field(min_length=1, max_length=64)]
    organization_id: OrganizationId
    subject_kind: AssignmentSubjectKind
    subject_id: str
    object_kind: Literal["setup", "component"]
    stable_id: str
    selector: AssignmentSelector = "exact"
    version: Annotated[str, Field(pattern=VERSION_PATTERN)] | None = None
    passport_digest: DigestValue | None = None
    harness: HarnessId | None = None
    state: AssignmentState
    revision: Annotated[int, Field(ge=1)]
    source_team_id: Annotated[str, Field(pattern=stable_id_pattern("operation"))] | None = None
    display_name: str | None = None


class CorporateTeamCatalogObject(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    object_kind: Literal["setup", "component"]
    stable_id: str
    version: str | None = None
    relation: Literal["owner", "maintainer"]
    state: str
    revision: Annotated[int, Field(ge=1)]


class CorporateCatalogAssignmentQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    subject_kind: AssignmentSubjectKind
    subject_id: Annotated[str, Field(min_length=1, max_length=64)]
    include_retired: bool = False
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=256)] = 128


class CorporateCatalogAssignmentList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    items: list[CorporateCatalogAssignment]
    total: Annotated[int, Field(ge=0)]


class CorporateCatalogUsageQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    object_kind: Literal["setup", "component"]
    stable_id: Annotated[str, Field(min_length=1, max_length=64)]
    version: Annotated[str, Field(pattern=VERSION_PATTERN)] | None = None
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=256)] = 128

    @model_validator(mode="after")
    def typed_catalog_identity(self) -> Self:
        if not re.fullmatch(stable_id_pattern(self.object_kind), self.stable_id):
            raise ValueError("catalog identity does not match its kind")
        return self


class CorporateCatalogUsage(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    assignment_id: Annotated[str, Field(min_length=1, max_length=64)]
    object_kind: Literal["setup", "component"]
    stable_id: str
    selector: AssignmentSelector = "exact"
    version: Annotated[str, Field(pattern=VERSION_PATTERN)] | None = None
    subject_kind: Literal["employee", "team", "project", "technology"]
    subject_id: str
    subject_name: str
    source: Literal["direct", "effective"]
    source_team_id: Annotated[str, Field(pattern=stable_id_pattern("operation"))] | None = None


class CorporateCatalogUsageList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    items: list[CorporateCatalogUsage]
    total: Annotated[int, Field(ge=0)]


class CorporateEffectiveAssignmentQuery(BaseModel):
    """Authorized effective-assignment evaluation for one employee and catalog line."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    account_id: AccountId
    object_kind: Literal["setup", "component"]
    stable_id: Annotated[str, Field(min_length=1, max_length=64)]
    project_id: ProjectId | None = None
    technology_id: TechnologyId | None = None
    harness: HarnessId | None = None

    @model_validator(mode="after")
    def typed_catalog_identity(self) -> Self:
        if not re.fullmatch(stable_id_pattern(self.object_kind), self.stable_id):
            raise ValueError("catalog identity does not match its kind")
        return self


class CorporateEffectiveAssignmentCandidate(BaseModel):
    """One assignment row considered by the deterministic effective evaluation."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    assignment_id: Annotated[str, Field(min_length=1, max_length=64)]
    scope: AssignmentSubjectKind
    subject_id: str
    selector: AssignmentSelector
    version: Annotated[str, Field(pattern=VERSION_PATTERN)] | None = None
    harness: HarnessId | None = None
    state: AssignmentState
    revision: Annotated[int, Field(ge=1)]
    outcome: Literal["winner", "overridden", "revoked", "inapplicable"]
    resolved_version: Annotated[str, Field(pattern=VERSION_PATTERN)] | None = None
    resolved_digest: DigestValue | None = None


class CorporateEffectiveAssignment(BaseModel):
    """The winning assignment, its source, and the exact resolved coordinate."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    account_id: AccountId
    object_kind: Literal["setup", "component"]
    stable_id: str
    state: Literal["assigned", "revoked", "unassigned"]
    assignment_id: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    source_scope: AssignmentSubjectKind | None = None
    source_subject_id: str | None = None
    selector: AssignmentSelector | None = None
    version: Annotated[str, Field(pattern=VERSION_PATTERN)] | None = None
    passport_digest: DigestValue | None = None
    harness: HarnessId | None = None
    candidates: Annotated[list[CorporateEffectiveAssignmentCandidate], Field(max_length=256)] = []


DistributionAction = Literal["assign", "revoke"]
DistributionTargetKind = Literal["employee", "project"]
DistributionTargetResult = Literal["applied", "skipped", "conflicted", "denied", "failed"]
DistributionLifecycle = Literal["pending", "installed", "outdated", "failed", "revoked"]


class CorporateDistributionRequest(BaseModel):
    """Preview or apply one bulk assign/revoke over a source assignment's targets."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    source_assignment_id: Annotated[str, Field(min_length=1, max_length=64)]
    action: DistributionAction
    dry_run: bool = False
    expected_revision: Annotated[int, Field(ge=1)]
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey


class CorporateDistributionTargetResult(BaseModel):
    """One resolved target's durable result and derived distribution state."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    target_kind: DistributionTargetKind
    target_id: str
    result: DistributionTargetResult
    state: DistributionLifecycle | None = None
    diagnostic: str | None = None
    overriding_assignment_id: Annotated[str, Field(min_length=1, max_length=64)] | None = None


class CorporateDistributionExclusion(BaseModel):
    """A member or project considered during expansion and excluded with a reason."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    target_kind: DistributionTargetKind
    target_id: str
    reason: str


class CorporateDistributionCounts(BaseModel):
    """Per-result totals across the resolved target set."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    applied: Annotated[int, Field(ge=0)] = 0
    skipped: Annotated[int, Field(ge=0)] = 0
    conflicted: Annotated[int, Field(ge=0)] = 0
    denied: Annotated[int, Field(ge=0)] = 0
    failed: Annotated[int, Field(ge=0)] = 0


class CorporateDistributionResult(BaseModel):
    """Preview or durable outcome of one bulk distribution request."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    distribution_id: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    organization_id: OrganizationId
    source_assignment_id: str
    action: DistributionAction
    dry_run: bool
    source_revision: Annotated[int, Field(ge=1)]
    targets: Annotated[list[CorporateDistributionTargetResult], Field(max_length=1024)] = []
    exclusions: Annotated[list[CorporateDistributionExclusion], Field(max_length=1024)] = []
    counts: CorporateDistributionCounts = CorporateDistributionCounts()


class CorporateDistributionStateQuery(BaseModel):
    """Bounded read of one source assignment's per-target distribution state."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    source_assignment_id: Annotated[str, Field(min_length=1, max_length=64)]
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=256)] = 128


class CorporateDistributionState(BaseModel):
    """Current derived distribution state for one member or project target."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    target_kind: DistributionTargetKind
    target_id: str
    result: DistributionTargetResult
    state: DistributionLifecycle | None = None
    operation_revision: Annotated[int, Field(ge=1)]
    diagnostic: str | None = None


class CorporateDistributionStateList(BaseModel):
    """Per-target distribution state for one source assignment."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    source_assignment_id: str
    source_revision: Annotated[int, Field(ge=1)]
    source_state: AssignmentState
    items: list[CorporateDistributionState]
    total: Annotated[int, Field(ge=0)]


PlanAction = Literal["install", "update", "remove", "none"]
PlanOutcome = Literal[
    "missing", "installed", "outdated", "revoked", "unassigned", "unsupported", "conflicting"
]


class CorporatePlanMaterializedItem(BaseModel):
    """One exact coordinate the caller reports as currently materialized."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    object_kind: Literal["setup", "component"]
    stable_id: Annotated[str, Field(min_length=1, max_length=64)]
    version: Annotated[str, Field(pattern=VERSION_PATTERN)]
    passport_digest: DigestValue | None = None

    @model_validator(mode="after")
    def typed_catalog_identity(self) -> Self:
        if not re.fullmatch(stable_id_pattern(self.object_kind), self.stable_id):
            raise ValueError("catalog identity does not match its kind")
        return self


class CorporateAssignmentPlanRequest(BaseModel):
    """Evaluate the deterministic install/update plan for one context (ADR-0196).

    The request names the authenticated employee context, the optional project
    and technology coordinates, the target harness, and the exact coordinates
    the caller reports as materialized. It never mutates assignments,
    distribution rows, or provider-owned state.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    account_id: AccountId
    harness: HarnessId
    project_id: ProjectId | None = None
    technology_id: TechnologyId | None = None
    materialized: Annotated[list[CorporatePlanMaterializedItem], Field(max_length=1024)] = []

    @model_validator(mode="after")
    def distinct_materialized(self) -> Self:
        keys = {(item.object_kind, item.stable_id) for item in self.materialized}
        if len(keys) != len(self.materialized):
            raise ValueError("materialized coordinates must be distinct per catalog line")
        return self


class CorporateAssignmentPlanItem(BaseModel):
    """One catalog line's effective assignment and the planned action."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    object_kind: Literal["setup", "component"]
    stable_id: str
    state: Literal["assigned", "revoked", "unassigned"]
    outcome: PlanOutcome
    action: PlanAction
    assignment_id: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    source_scope: AssignmentSubjectKind | None = None
    source_subject_id: str | None = None
    selector: AssignmentSelector | None = None
    version: Annotated[str, Field(pattern=VERSION_PATTERN)] | None = None
    passport_digest: DigestValue | None = None
    harness: HarnessId | None = None
    installed_version: Annotated[str, Field(pattern=VERSION_PATTERN)] | None = None
    installed_passport_digest: DigestValue | None = None
    diagnostic: str | None = None
    candidates: Annotated[list[CorporateEffectiveAssignmentCandidate], Field(max_length=256)] = []


class CorporateAssignmentPlan(BaseModel):
    """The deterministic install/update plan for one context (ADR-0196).

    Items are sorted by object kind and stable identity; the response carries
    no wall-clock field so identical policy and materialized inputs produce an
    identical plan.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    account_id: AccountId
    harness: HarnessId
    project_id: ProjectId | None = None
    technology_id: TechnologyId | None = None
    items: Annotated[list[CorporateAssignmentPlanItem], Field(max_length=1024)] = []
    total: Annotated[int, Field(ge=0)] = 0


class CorporateBootstrapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    organization_name: Annotated[str, Field(min_length=1, max_length=200)]
    superadmin_account_id: AccountId
    idempotency_key: IdempotencyKey


class CorporateOrganization(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    display_name: str
    state: Literal["active", "suspended"]
    authorization_revision: Annotated[int, Field(ge=1)]


class CorporateMemberCatalogAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    object_kind: Literal["component"]
    stable_id: Annotated[str, Field(min_length=1, max_length=64)]
    version: Annotated[str, Field(pattern=VERSION_PATTERN)]


class CorporateMemberCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    account_id: AccountId | None = None
    email: Annotated[str | None, Field(min_length=3, max_length=320)] = None
    display_name: Annotated[str, Field(min_length=1, max_length=80)]
    role: CorporateRole
    team_ids: Annotated[list[str], Field(max_length=64)] = Field(default_factory=list)
    project_ids: Annotated[list[ProjectId], Field(max_length=64)] = Field(default_factory=list)
    catalog_assignments: Annotated[
        list[CorporateMemberCatalogAssignment], Field(max_length=64)
    ] = []
    job_title_id: JobTitleId | None = None
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey

    @model_validator(mode="after")
    def provisioned_identity_is_addressable(self) -> Self:
        if self.account_id is None and self.email is None:
            raise ValueError("email is required when account_id is omitted")
        return self


class CorporateMemberProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    display_name: Annotated[str, Field(min_length=1, max_length=80)]
    expected_revision: Annotated[int, Field(ge=1)]
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey

    @model_validator(mode="after")
    def nonblank_name(self) -> Self:
        if not self.display_name.strip():
            raise ValueError("display name must not be blank")
        return self


class CorporateMemberUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    role: CorporateRole
    state: CorporateState
    job_title_id: JobTitleId | None = None
    expected_revision: Annotated[int, Field(ge=1)]
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey


class CorporateDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    expected_revision: Annotated[int, Field(ge=1)]
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey


class CorporateDeleteResult(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    resource_id: str


class CorporateMember(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    account_id: AccountId
    display_name: str | None
    role: CorporateRole
    state: CorporateState
    revision: Annotated[int, Field(ge=1)]
    job_title_id: JobTitleId | None = None
    job_title_name: str | None = None
    available_actions: Annotated[list[str], Field(max_length=128)] = []


class CorporateMemberList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    items: Annotated[list[CorporateMember], Field(max_length=256)]


class CorporateJobTitleCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    name: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str, Field(max_length=2000)] = ""
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey


class CorporateJobTitleUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    name: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str, Field(max_length=2000)] = ""
    state: JobTitleState
    expected_revision: Annotated[int, Field(ge=1)]
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey


class CorporateJobTitleView(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    job_title_id: JobTitleId
    organization_id: OrganizationId
    name: str
    normalized_name: str
    description: str = ""
    state: JobTitleState
    revision: Annotated[int, Field(ge=1)]


class CorporateJobTitleList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    items: Annotated[list[CorporateJobTitleView], Field(max_length=256)]


class CorporateBindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    account_id: AccountId
    role: CorporateRole
    scope_kind: ScopeKind
    scope_id: Annotated[str, Field(min_length=1, max_length=64)] = "*"
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey


class CorporateBinding(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    binding_id: str
    principal_type: Literal["user", "service_principal"] = "user"
    account_id: AccountId | None = None
    service_principal_id: str | None = None
    role: CorporateRole
    scope_kind: ScopeKind
    scope_id: str
    state: Literal["active", "revoked"]
    revision: Annotated[int, Field(ge=1)]


class CorporateBindingUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    role: CorporateRole
    scope_kind: ScopeKind
    scope_id: Annotated[str, Field(min_length=1, max_length=64)] = "*"
    state: Literal["active", "revoked"]
    expected_revision: Annotated[int, Field(ge=1)]
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey


class CorporateBindingList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    items: Annotated[list[CorporateBinding], Field(max_length=256)]


class CorporateRoleCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    name: CorporateRole
    parent_role: CorporateRole | None = None
    permissions: Annotated[list[str], Field(max_length=128)] = Field(default_factory=list)
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey


class CorporateRoleUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    parent_role: CorporateRole | None = None
    permissions: Annotated[list[str], Field(max_length=128)]
    expected_revision: Annotated[int, Field(ge=1)]
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey


class CorporateRoleView(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    name: CorporateRole
    parent_role: CorporateRole | None
    permissions: Annotated[list[str], Field(max_length=128)]
    revision: Annotated[int, Field(ge=1)]


class CorporateRoleList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    items: Annotated[list[CorporateRoleView], Field(max_length=256)]


class CorporateProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    name: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(max_length=2000)] = ""
    owner_team_id: TeamId | None = None
    technology_ids: Annotated[list[TechnologyId], Field(max_length=64)] = Field(
        default_factory=list
    )
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey


class CorporateProjectUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    name: Annotated[str, Field(min_length=1, max_length=200)]
    state: ProjectState
    expected_revision: Annotated[int, Field(ge=1)]
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey


def _project_wire_object(schema: JsonSchemaValue) -> None:
    open_wire_object(schema)
    # ADR-0183: absence means an older writer, never an invented lifecycle.
    schema["required"] = [
        name for name in schema["required"] if name not in {"lifecycle", "restore_lifecycle"}
    ]


class CorporateProjectView(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=_project_wire_object)
    schema_version: Literal[1] = 1
    project_id: str
    organization_id: OrganizationId
    name: str
    state: ProjectState
    lifecycle: ProjectLifecycle | None = None
    restore_lifecycle: Literal["active", "deprecated"] | None = None
    revision: Annotated[int, Field(ge=1)]
    available_actions: Annotated[list[str], Field(max_length=128)] = []


class CorporateProjectLifecycleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    target: Literal["active", "deprecated", "archived", "restore"]
    expected_revision: Annotated[int, Field(ge=1)]
    authorization_revision: (
        Annotated[int, Field(ge=1)]
        | Annotated[
            str,
            Field(
                min_length=1,
                max_length=128,
                pattern=r"^corporate:organization_[A-Za-z0-9_-]+:[1-9][0-9]*:[1-9][0-9]*$",
            ),
        ]
    )
    idempotency_key: IdempotencyKey


class CorporateProjectList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    items: Annotated[list[CorporateProjectView], Field(max_length=256)]


class CorporateTeamCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    name: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(max_length=2000)] = ""
    lead_account_id: AccountId | None = None
    employee_ids: Annotated[list[AccountId], Field(max_length=256)] = Field(default_factory=list)
    project_ids: Annotated[list[ProjectId], Field(max_length=64)] = Field(default_factory=list)
    technology_ids: Annotated[list[TechnologyId], Field(max_length=64)] = Field(
        default_factory=list
    )
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey


class CorporateTeamView(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    team_id: str
    organization_id: OrganizationId
    name: str
    description: Annotated[str, Field(max_length=2000)] = ""
    state: Literal["active", "archived"]
    revision: Annotated[int, Field(ge=1)]
    members: Annotated[list[CorporateMember], Field(max_length=256)] = []
    lead_account_ids: Annotated[list[AccountId], Field(max_length=256)] = []
    project_ids: Annotated[list[str], Field(max_length=256)] = []
    technology_ids: Annotated[list[str], Field(max_length=256)] = []
    assignments: Annotated[list[CorporateCatalogAssignment], Field(max_length=256)] = []
    effective_assignments: Annotated[list[CorporateCatalogAssignment], Field(max_length=256)] = []
    effective_permissions: Annotated[list[str], Field(max_length=256)] = []
    available_actions: Annotated[list[str], Field(max_length=128)] = []
    governance_history: Annotated[list[dict[str, object]], Field(max_length=256)] = []
    owned_catalog_objects: Annotated[list[CorporateTeamCatalogObject], Field(max_length=256)] = []
    maintained_catalog_objects: Annotated[
        list[CorporateTeamCatalogObject], Field(max_length=256)
    ] = []


class CorporateTeamUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    name: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(max_length=2000)] = ""
    state: Literal["active", "archived"]
    expected_revision: Annotated[int, Field(ge=1)]
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey


class CorporateTeamList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    items: Annotated[list[CorporateTeamView], Field(max_length=256)]


class CorporateServicePrincipalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    name: Annotated[str, Field(min_length=1, max_length=200)]
    role: CorporateRole
    scope_kind: ScopeKind = "organization"
    scope_id: Annotated[str, Field(min_length=1, max_length=64)] = "*"
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey


class CorporateServicePrincipalUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    state: CorporateState
    expected_revision: Annotated[int, Field(ge=1)]
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey


class CorporateServicePrincipalView(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    service_principal_id: str
    organization_id: OrganizationId
    name: str
    state: CorporateState
    revision: Annotated[int, Field(ge=1)]
    binding: CorporateBinding


class CorporateServicePrincipalList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    items: Annotated[list[CorporateServicePrincipalView], Field(max_length=256)]


class CorporateMembershipAssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    account_id: AccountId
    team_id: Annotated[str | None, Field(max_length=64)] = None
    project_id: Annotated[str | None, Field(max_length=64)] = None
    team_role: Literal["lead", "staff"] = "staff"
    operation: Literal["assign", "remove"] = "assign"
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey


class CorporateMembershipAssignment(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    account_id: AccountId
    team_id: str | None
    project_id: str | None
    team_role: Literal["lead", "staff"]
    operation: Literal["assign", "remove"] = "assign"
    bindings: Annotated[list[CorporateBinding], Field(max_length=2)]


class CorporateContext(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization: CorporateOrganization
    member: CorporateMember
    bindings: Annotated[list[CorporateBinding], Field(max_length=256)]
    projects: Annotated[list[CorporateProjectView], Field(max_length=256)]
    teams: Annotated[list[CorporateTeamView], Field(max_length=256)]
    capabilities: Annotated[list[str], Field(max_length=256)]


class CorporateAuditEntry(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    audit_id: int
    actor_account_id: str | None
    actor_type: Literal["user", "service_principal", "system"]
    actor_id: str | None
    effective_role_bindings: list[dict[str, str]]
    action: str
    target_table: str
    target_id: str
    outcome: Literal["succeeded", "denied", "failed"]
    reason: str | None
    request_id: str | None
    payload: dict[str, object]
    created_at: Timestamp


class CorporateAuditList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    items: Annotated[list[CorporateAuditEntry], Field(max_length=256)]
    next_before_created_at: Timestamp | None = None
    next_before_id: int | None = None


class CorporateAuditExport(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    exported_at: Timestamp
    items: Annotated[list[CorporateAuditEntry], Field(max_length=10000)]


class CorporateAuditQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    before_id: Annotated[int | None, Field(ge=1)] = None
    before_created_at: Timestamp | None = None
    actor_account_id: AccountId | None = None
    action: Annotated[str | None, Field(min_length=1, max_length=128)] = None
    target_id: Annotated[str | None, Field(min_length=1, max_length=128)] = None
    created_from: Timestamp | None = None
    created_to: Timestamp | None = None


class CorporateOverviewNode(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    kind: Literal["project", "team", "employee"]
    id: Annotated[str, Field(min_length=1, max_length=64)]
    name: str
    lead_account_ids: list[AccountId] = []
    assignments: list[CorporateCatalogAssignment] = []
    assignments_readable: bool = False

    @model_validator(mode="after")
    def typed_identity(self) -> Self:
        prefix = {"project": "remote_project", "team": "operation", "employee": "account"}[
            self.kind
        ]
        if not re.fullmatch(stable_id_pattern(prefix), self.id):
            raise ValueError("overview identity does not match its kind")
        if self.kind != "team" and self.lead_account_ids:
            raise ValueError("only teams expose team leads")
        return self


class CorporateOverviewEdge(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    parent_id: str
    child_id: str
    kind: Literal["project_team", "team_employee"]
    role: Literal["owner", "responsible", "contributor", "lead", "staff"]


class CorporateOverview(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization: CorporateOrganization
    nodes: list[CorporateOverviewNode]
    edges: list[CorporateOverviewEdge]

    @model_validator(mode="after")
    def coherent_graph(self) -> Self:
        nodes = {node.id: node for node in self.nodes}
        if len(nodes) != len(self.nodes):
            raise ValueError("overview nodes must have distinct identities")
        seen: set[tuple[str, str]] = set()
        for edge in self.edges:
            parent, child = nodes.get(edge.parent_id), nodes.get(edge.child_id)
            if parent is None or child is None:
                raise ValueError("overview edges require visible anchors")
            expected = ("project", "team") if edge.kind == "project_team" else ("team", "employee")
            if (parent.kind, child.kind) != expected:
                raise ValueError("overview edge kinds must preserve hierarchy")
            roles = (
                {"owner", "responsible", "contributor"}
                if edge.kind == "project_team"
                else {"lead", "staff"}
            )
            if edge.role not in roles or (edge.parent_id, edge.child_id) in seen:
                raise ValueError("overview edge role or identity is invalid")
            seen.add((edge.parent_id, edge.child_id))
        for node in self.nodes:
            if any(
                assignment.organization_id != self.organization.organization_id
                or assignment.subject_id != node.id
                for assignment in node.assignments
            ):
                raise ValueError("overview assignments require the same tenant and subject")
        return self
