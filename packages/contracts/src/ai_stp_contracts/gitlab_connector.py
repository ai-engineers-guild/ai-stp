"""Authenticated, read-only GitLab Connector wire models (ADR-0224)."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_stp_contracts.http import IdempotencyKey, Timestamp, open_wire_object, strict_request_object
from ai_stp_contracts.publication import ContentDigest, PlanId

type GitLabProjectId = Annotated[int, Field(gt=0, le=9_007_199_254_740_991)]


class GitLabConnectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    purpose: Literal["source"] = "source"
    locale: Literal["en", "ru"] = "en"
    confirmed: Literal[True]


class GitLabConnectResponse(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    authorization_url: Annotated[str, Field(pattern=r"^https://")]
    expires_at: Timestamp


class GitLabDisconnectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    purpose: Literal["source"] = "source"
    confirmed: Literal[True]


class GitLabPlatformObject(BaseModel):
    """An ai-stp object published from the connected project."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    object_kind: Literal["component", "setup"]
    stable_id: Annotated[str, Field(min_length=1, max_length=64)]
    version: Annotated[str, Field(min_length=1, max_length=32)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    visibility: Literal["private", "public"]


class GitLabConnectorRepository(BaseModel):
    """Selected project metadata visible only to the connected account."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    project_id: GitLabProjectId
    namespace_id: GitLabProjectId
    path_with_namespace: Annotated[str, Field(min_length=3, max_length=256)]
    repository_url: Annotated[str, Field(pattern=r"^https://", max_length=512)]
    visibility: Literal["private", "internal", "public"] | None = None
    default_branch: Annotated[str | None, Field(max_length=128)] = None
    platform_objects: list[GitLabPlatformObject] = Field(default_factory=list[GitLabPlatformObject])


class GitLabConnectionStatus(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    purpose: Literal["source"]
    configured: bool
    gitlab_base_url: Annotated[str | None, Field(pattern=r"^https://")] = None
    state: Literal["disconnected", "connected", "reauthorization_required"]
    expires_at: Timestamp | None = None
    repositories: list[GitLabConnectorRepository] = Field(
        default_factory=list[GitLabConnectorRepository]
    )
    reason: str | None = None


class GitLabConnectorStatus(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    connections: list[GitLabConnectionStatus]


class GitLabSourcePrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    project_id: GitLabProjectId
    commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    subpath: Annotated[str, Field(min_length=1, max_length=512)]
    idempotency_key: IdempotencyKey


class GitLabSourcePrepared(BaseModel):
    """Opaque provenance and inventory; no private repository coordinate."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    source_binding_id: PlanId
    content_digest: ContentDigest
    size_bytes: Annotated[int, Field(gt=0)]
    artifact_inventory: Annotated[list[str], Field(min_length=1, max_length=1000)]
    source_visibility: Literal["private", "public"]
