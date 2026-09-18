"""Corporate governance relations and effective permission projections."""

import re
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_stp_contracts.corporate import AccountId, CorporateAuditEntry, OrganizationId
from ai_stp_contracts.corporate_catalog_ownership import CorporateCatalogOwnership
from ai_stp_contracts.http import IdempotencyKey, open_wire_object, strict_request_object
from ai_stp_foundation.ids import stable_id_pattern
from ai_stp_foundation.versioning import VERSION_PATTERN

GovernanceObjectKind = Literal["setup", "component"]
MaintainerSubjectKind = Literal["employee", "team"]


class CorporateGovernanceTarget(BaseModel):
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


class CorporateCatalogMaintainer(BaseModel):
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


class CorporateCatalogVerification(BaseModel):
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


class CorporateCatalogLifecycle(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    object_kind: GovernanceObjectKind
    stable_id: str
    version: str
    state: Literal["visible", "hidden", "deprecated", "retired"]
    revision: Annotated[int, Field(ge=1)]
    reason: str | None = None


class CorporateCatalogGovernanceQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    include_retired: bool = False
    include_history: bool = False


class CorporateCatalogGovernanceView(BaseModel):
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


class CorporatePermissionDefinition(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    name: str
    scopes: list[Literal["organization", "team", "project", "technology", "catalog_object"]]
    group: str


class CorporateEffectivePermission(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    permission: str
    scope_kind: Literal["organization", "team", "project", "technology", "catalog_object"]
    scope_id: str
    sources: list[str] = Field(default_factory=list)


class CorporatePermissionMatrix(BaseModel):
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
