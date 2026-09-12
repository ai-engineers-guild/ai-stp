"""Corporate bootstrap, RBAC, project, and audit wire contracts (SPEC-079)."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_stp_contracts.http import IdempotencyKey, Timestamp, open_wire_object, strict_request_object
from ai_stp_foundation.ids import stable_id_pattern

OrganizationId = Annotated[str, Field(pattern=stable_id_pattern("organization"))]
AccountId = Annotated[str, Field(pattern=stable_id_pattern("account"))]
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
ProjectState = Literal["active", "archived"]
ScopeKind = Literal[
    "system", "organization", "team", "project", "technology", "catalog_object", "telemetry"
]


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


class CorporateMemberCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    account_id: AccountId | None = None
    email: Annotated[str | None, Field(min_length=3, max_length=320)] = None
    display_name: Annotated[str, Field(min_length=1, max_length=80)]
    role: CorporateRole
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey

    @model_validator(mode="after")
    def provisioned_identity_is_addressable(self) -> Self:
        if self.account_id is None and self.email is None:
            raise ValueError("email is required when account_id is omitted")
        return self


class CorporateMemberUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    role: CorporateRole
    state: CorporateState
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


class CorporateMemberList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    items: Annotated[list[CorporateMember], Field(max_length=256)]


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


class CorporateProjectView(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    project_id: str
    organization_id: OrganizationId
    name: str
    state: ProjectState
    revision: Annotated[int, Field(ge=1)]


class CorporateProjectList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    items: Annotated[list[CorporateProjectView], Field(max_length=256)]


class CorporateTeamCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    name: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(max_length=2000)] = ""
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
