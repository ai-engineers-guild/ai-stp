"""Tenant-scoped GitLab discovery and provider identity observations."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_stp_contracts.context import ProviderProjectId
from ai_stp_contracts.corporate import OrganizationId
from ai_stp_contracts.http import IdempotencyKey, Timestamp, open_wire_object, strict_request_object
from ai_stp_contracts.technology import MappingVersion
from ai_stp_foundation.ids import stable_id_pattern


class GitLabMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    authorization_revision: Annotated[str, Field(min_length=1, max_length=128)]
    expected_revision: Annotated[int, Field(ge=0)]
    idempotency_key: IdempotencyKey


class GitLabEnrichRequest(GitLabMutationRequest):
    scan_id: Annotated[str, Field(pattern=stable_id_pattern("scan"))]
    mapping_version: MappingVersion


class GitLabRepositoryView(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    repository_id: Annotated[int, Field(ge=1)]
    namespace_id: Annotated[int, Field(ge=1)]
    path_with_namespace: Annotated[str, Field(min_length=3, max_length=200)]
    repository_url: Annotated[str, Field(min_length=12, max_length=512)]
    default_branch: Annotated[str | None, Field(max_length=128)] = None
    last_activity_at: Timestamp | None = None
    observed_revision: Annotated[str | None, Field(max_length=128)] = None
    observed_at: Timestamp | None = None
    provider_project_id: ProviderProjectId | None = None
    connected: bool = False
    identity_revision: Annotated[int | None, Field(ge=1)] = None


class GitLabRepositoryList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    total: Annotated[int, Field(ge=0)]
    items: Annotated[list[GitLabRepositoryView], Field(max_length=500)]
