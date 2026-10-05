"""Authenticated, read-only GitLab Connector wire models (ADR-0224)."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_stp_contracts.auth import AccountId, DeviceId
from ai_stp_contracts.http import IdempotencyKey, Timestamp, open_wire_object, strict_request_object
from ai_stp_contracts.publication import ContentDigest, PlanId

type GitLabProjectId = Annotated[int, Field(gt=0, le=9_007_199_254_740_991)]
type ConnectorPurpose = Literal["source", "administration"]
type GitLabUsername = Annotated[
    str, Field(pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,254}[A-Za-z0-9])?$")
]


class GitLabConnectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    purpose: ConnectorPurpose = "source"
    locale: Literal["en", "ru"] = "en"
    confirmed: Literal[True]


class GitLabConnectResponse(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    authorization_url: Annotated[str, Field(pattern=r"^https://")]
    expires_at: Timestamp


class GitLabCallbackQuery(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    state: Annotated[str, Field(min_length=1, max_length=128)]
    code: Annotated[str | None, Field(max_length=1024)] = None


class GitLabDisconnectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    purpose: ConnectorPurpose = "source"
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

    purpose: ConnectorPurpose
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


class GitLabActionPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    action: Literal[
        "grant_access", "revoke_access", "make_public", "make_private", "create_repository"
    ]
    project_id: GitLabProjectId | None = None
    recipient: GitLabUsername | None = None
    access_level: Literal["guest", "reporter", "developer", "maintainer"] | None = None
    name: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    path: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$")] | None = None
    target_visibility: Literal["private", "internal", "public"] | None = None
    device_id: DeviceId
    idempotency_key: IdempotencyKey

    @model_validator(mode="after")
    def _action_fields(self) -> "GitLabActionPlanRequest":
        if self.action == "grant_access":
            if self.project_id is None or self.recipient is None or self.access_level is None:
                raise ValueError("access grant requires project, recipient and access_level")
        elif self.action == "revoke_access":
            if self.project_id is None or self.recipient is None:
                raise ValueError("access revocation requires project and recipient")
            if self.access_level is not None:
                raise ValueError("access revocation has no access_level")
        elif self.action == "create_repository":
            if self.name is None or self.path is None or self.target_visibility is None:
                raise ValueError("repository creation requires name, path and target_visibility")
            if self.project_id is not None or self.recipient is not None:
                raise ValueError("repository creation has no project or recipient")
        elif (
            self.project_id is None
            or self.recipient is not None
            or self.access_level is not None
            or self.name is not None
            or self.path is not None
            or self.target_visibility is not None
        ):
            raise ValueError("repository visibility has no recipient, level or create fields")
        return self


class GitLabActionPlanResponse(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    plan_id: PlanId
    plan_hash: ContentDigest
    action: Literal[
        "grant_access", "revoke_access", "make_public", "make_private", "create_repository"
    ]
    actor_id: AccountId
    device_id: DeviceId
    gitlab_base_url: Annotated[str, Field(pattern=r"^https://")]
    project_id: GitLabProjectId | None = None
    path_with_namespace: Annotated[str | None, Field(max_length=256)] = None
    previous_visibility: Literal["private", "internal", "public"] | None = None
    recipient: GitLabUsername | None = None
    access_level: Literal["guest", "reporter", "developer", "maintainer"] | None = None
    name: Annotated[str | None, Field(max_length=255)] = None
    path: Annotated[str | None, Field(max_length=255)] = None
    target_visibility: Literal["private", "internal", "public"] | None = None
    state: Literal["planned", "applied", "failed", "unknown"]
    result: (
        Literal["pending", "granted", "revoked", "public", "internal", "private", "created"] | None
    ) = None
    error_reason: str | None = None
    expires_at: Timestamp
    warning: Literal[
        "repository_and_history_public",
        "repository_private",
        "repository_internal",
        "repository_access",
        "repository_access_revoked",
        "repository_created",
    ]


class GitLabActionConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    plan_hash: ContentDigest
    confirmed: Literal[True]
    typed_project_path: Annotated[str, Field(max_length=256)] | None = None
    idempotency_key: IdempotencyKey
