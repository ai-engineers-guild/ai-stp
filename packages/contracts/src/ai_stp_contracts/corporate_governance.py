"""Corporate governance relations and effective permission projections."""

import re
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from ai_stp_contracts.corporate import (
    AccountId,
    CorporateAuditEntry,
    CorporateBinding,
    CorporatePermissionGrant,
    OrganizationId,
)
from ai_stp_contracts.corporate_catalog_ownership import CorporateCatalogOwnership
from ai_stp_contracts.http import IdempotencyKey, open_wire_object, strict_request_object
from ai_stp_contracts.model import ContractModel
from ai_stp_foundation.ids import stable_id_pattern
from ai_stp_foundation.versioning import VERSION_PATTERN

GovernanceObjectKind = Literal["setup", "component"]
MaintainerSubjectKind = Literal["employee", "team"]


class CorporateGovernanceTarget(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    object_kind: GovernanceObjectKind
    stable_id: Annotated[str, Field(min_length=1, max_length=64)]
    version: Annotated[str, Field(pattern=VERSION_PATTERN)]

    @model_validator(mode="after")
    def typed_identity(self) -> Self:
        if not re.fullmatch(stable_id_pattern(self.object_kind), self.stable_id):
            raise ValueError("catalog identity does not match its kind")
        return self


class CorporateCatalogMaintainerRequest(CorporateGovernanceTarget):
    schema_version: Literal[1] = 1
    subject_kind: MaintainerSubjectKind
    subject_id: Annotated[str, Field(min_length=1, max_length=64)]
    state: Literal["current", "retired"] = "current"
    expected_revision: Annotated[int, Field(ge=0)]
    authorization_revision: Annotated[int, Field(ge=1)]
    reason: Annotated[str, Field(min_length=1, max_length=200)] = "governance"
    idempotency_key: IdempotencyKey

    @model_validator(mode="after")
    def typed_subject(self) -> Self:
        prefix = "account" if self.subject_kind == "employee" else "operation"
        if not re.fullmatch(stable_id_pattern(prefix), self.subject_id):
            raise ValueError("maintainer identity does not match its kind")
        if self.state == "retired" and self.expected_revision == 0:
            raise ValueError("retiring a maintainer requires its current revision")
        return self


class CorporateCatalogMaintainer(ContractModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    object_kind: GovernanceObjectKind
    stable_id: str
    version: str
    subject_kind: MaintainerSubjectKind
    subject_id: str
    state: Literal["current", "retired"]
    revision: Annotated[int, Field(ge=1)]
    reason: str | None = None


class CorporateCatalogVerificationRequest(CorporateGovernanceTarget):
    schema_version: Literal[1] = 1
    state: Literal["verified", "revoked"]
    expected_revision: Annotated[int, Field(ge=0)]
    authorization_revision: Annotated[int, Field(ge=1)]
    reason: Annotated[str, Field(min_length=1, max_length=200)]
    idempotency_key: IdempotencyKey


class CorporateCatalogVerification(ContractModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    object_kind: GovernanceObjectKind
    stable_id: str
    version: str
    state: Literal["verified", "revoked"]
    revision: Annotated[int, Field(ge=1)]
    verified_by_account_id: AccountId | None = None
    reason: str | None = None


class CorporateCatalogLifecycleRequest(CorporateGovernanceTarget):
    schema_version: Literal[1] = 1
    state: Literal["visible", "hidden", "deprecated", "retired"]
    expected_revision: Annotated[int, Field(ge=0)]
    authorization_revision: Annotated[int, Field(ge=1)]
    reason: Annotated[str, Field(min_length=1, max_length=200)]
    idempotency_key: IdempotencyKey


class CorporateCatalogLifecycle(ContractModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    object_kind: GovernanceObjectKind
    stable_id: str
    version: str
    state: Literal["visible", "hidden", "deprecated", "retired"]
    revision: Annotated[int, Field(ge=1)]
    reason: str | None = None


class CorporateCatalogGovernanceQuery(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    include_retired: bool = False
    include_history: bool = False


class CorporateCatalogGovernanceView(ContractModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    object_kind: GovernanceObjectKind
    stable_id: str
    version: Annotated[str, Field(pattern=VERSION_PATTERN)]
    ownership: CorporateCatalogOwnership
    maintainers: list[CorporateCatalogMaintainer] = Field(
        default_factory=list[CorporateCatalogMaintainer]
    )
    verification: CorporateCatalogVerification | None = None
    lifecycle: CorporateCatalogLifecycle | None = None
    history: list[CorporateAuditEntry] = Field(default_factory=list[CorporateAuditEntry])
    available_actions: list[str] = Field(default_factory=list[str])


class CorporatePermissionDefinition(ContractModel):
    """One action the server actually checks, with the scopes it honors."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    name: str
    resource: str
    action: str
    scopes: list[
        Literal["organization", "team", "project", "technology", "catalog_object", "member"]
    ]
    group: str
    create_parent: str | None = None
    implementation: Literal["enforced"] = "enforced"


class CorporatePermissionSource(ContractModel):
    """One record that actually contributes a permission at this scope."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    kind: Literal["binding", "grant"]
    source_id: str
    role: str | None = None
    origin: str | None = None
    scope_kind: str
    scope_id: str


class CorporateEffectivePermission(ContractModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    permission: str
    scope_kind: Literal["organization", "team", "project", "technology", "catalog_object", "member"]
    scope_id: str
    sources: list[str] = Field(default_factory=list)
    source_records: list[CorporatePermissionSource] = Field(
        default_factory=list[CorporatePermissionSource]
    )


class CorporatePermissionMatrix(ContractModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    authorization_revision: Annotated[int, Field(ge=1)]
    definitions: list[CorporatePermissionDefinition] = Field(
        default_factory=list[CorporatePermissionDefinition]
    )
    effective: list[CorporateEffectivePermission] = Field(
        default_factory=list[CorporateEffectivePermission]
    )


class CorporateMemberPrivateGrant(ContractModel):
    """Read-only projection of a private major-line AccessGrant (SPEC-002) for
    the employee-access view — never a source of corporate permissions."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    grant_id: str
    object_kind: GovernanceObjectKind
    stable_id: str
    major: Annotated[int, Field(ge=0)]
    state: Literal["active", "revoked"]
    issuer_account_id: AccountId


class CorporateMemberAccessQuery(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    scope_kind: Literal[
        "organization", "team", "project", "technology", "catalog_object", "member"
    ] = "organization"
    scope_id: Annotated[str | None, Field(min_length=1, max_length=64)] = None


class CorporateMemberAccess(ContractModel):
    """Everything that grants one member access, split by independent source:
    role bindings, direct scoped allows, private major-line grants, and the
    evaluator's effective set at the requested scope with per-source records."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    account_id: AccountId
    scope_kind: Literal["organization", "team", "project", "technology", "catalog_object", "member"]
    scope_id: str
    bindings: list[CorporateBinding] = Field(default_factory=list[CorporateBinding])
    grants: list[CorporatePermissionGrant] = Field(default_factory=list[CorporatePermissionGrant])
    private_grants: list[CorporateMemberPrivateGrant] = Field(
        default_factory=list[CorporateMemberPrivateGrant]
    )
    effective: list[CorporateEffectivePermission] = Field(
        default_factory=list[CorporateEffectivePermission]
    )
    authorization_revision: Annotated[int, Field(ge=1)]
