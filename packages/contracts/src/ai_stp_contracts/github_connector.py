"""Authenticated GitHub Connector wire models (SPEC-072)."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_stp_contracts.auth import AccountId, DeviceId
from ai_stp_contracts.http import IdempotencyKey, Timestamp, open_wire_object, strict_request_object
from ai_stp_contracts.publication import ContentDigest, PlanId

type ConnectorPurpose = Literal["source", "administration"]
type RepositoryId = Annotated[int, Field(gt=0, le=9_007_199_254_740_991)]
type GitHubUsername = Annotated[
    str, Field(pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
]


class GitHubConnectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    purpose: ConnectorPurpose = "source"
    locale: Literal["en", "ru"] = "en"
    mode: Literal["install", "authorize"] = "install"
    confirmed: Literal[True]


class GitHubConnectResponse(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    authorization_url: Annotated[str, Field(pattern=r"^https://github\.com/")]
    expires_at: Timestamp


class GitHubCallbackQuery(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    state: Annotated[str, Field(min_length=1, max_length=128)]
    code: Annotated[str | None, Field(max_length=1024)] = None
    setup_action: Annotated[str | None, Field(max_length=32)] = None


class GitHubDisconnectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    purpose: ConnectorPurpose = "source"
    confirmed: Literal[True]


class GitHubPlatformObject(BaseModel):
    """An ai-stp object published from the connected repository."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    object_kind: Literal["component", "setup"]
    stable_id: Annotated[str, Field(min_length=1, max_length=64)]
    version: Annotated[str, Field(min_length=1, max_length=32)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    visibility: Literal["private", "public"]


class GitHubRepository(BaseModel):
    """Selected repository metadata visible only to the connected account."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    installation_id: RepositoryId
    repository_id: RepositoryId
    owner_id: RepositoryId
    full_name: Annotated[str, Field(pattern=r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$", max_length=256)]
    html_url: Annotated[str, Field(pattern=r"^https://github\.com/[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")]
    owner_type: Literal["User", "Organization"]
    private: bool
    can_administer: bool
    permission: Literal["read", "administration"]
    platform_objects: list[GitHubPlatformObject] = Field(default_factory=list[GitHubPlatformObject])


class GitHubInstallation(BaseModel):
    """One connected personal or organization GitHub App installation."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    installation_id: RepositoryId
    account_id: RepositoryId
    account_login: GitHubUsername
    account_type: Literal["User", "Organization"]
    account_html_url: Annotated[str, Field(pattern=r"^https://github\.com/[A-Za-z0-9-]+$")]
    repository_selection: Literal["all", "selected"]
    repositories: list[GitHubRepository] = Field(default_factory=list[GitHubRepository])


class GitHubConnectionStatus(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    purpose: ConnectorPurpose
    configured: bool
    state: Literal["disconnected", "pending_approval", "connected", "reauthorization_required"]
    expires_at: Timestamp | None = None
    repositories: list[GitHubRepository] = Field(default_factory=list[GitHubRepository])
    installations: list[GitHubInstallation] = Field(default_factory=list[GitHubInstallation])
    reason: str | None = None


class GitHubConnectorStatus(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    connections: list[GitHubConnectionStatus]


class GitHubSourcePrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    installation_id: RepositoryId
    repository_id: RepositoryId
    commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    subpath: Annotated[str, Field(min_length=1, max_length=512)]
    idempotency_key: IdempotencyKey


class GitHubSourcePrepared(BaseModel):
    """Opaque provenance and inventory; no private repository coordinate."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    source_binding_id: PlanId
    content_digest: ContentDigest
    size_bytes: Annotated[int, Field(gt=0)]
    artifact_inventory: Annotated[list[str], Field(min_length=1, max_length=1000)]
    source_visibility: Literal["private", "public"]


class GitHubActionPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    action: Literal["invite_collaborator", "make_public", "make_private"]
    installation_id: RepositoryId
    repository_id: RepositoryId
    recipient: GitHubUsername | None = None
    permission: Literal["pull", "push"] | None = None
    device_id: DeviceId
    idempotency_key: IdempotencyKey

    @model_validator(mode="after")
    def _invitation(self) -> "GitHubActionPlanRequest":
        if self.action == "invite_collaborator":
            if self.recipient is None or self.permission is None:
                raise ValueError("invitation requires an exact recipient and permission")
        elif self.recipient is not None or self.permission is not None:
            raise ValueError("repository visibility has no recipient or permission")
        return self


class GitHubActionPlanResponse(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    plan_id: PlanId
    plan_hash: ContentDigest
    action: Literal["invite_collaborator", "make_public", "make_private"]
    actor_id: AccountId
    device_id: DeviceId
    repository: GitHubRepository
    recipient: GitHubUsername | None = None
    permission: Literal["pull", "push"] | None = None
    state: Literal["planned", "applied", "failed", "unknown"]
    result: Literal["pending", "accepted", "public", "private"] | None = None
    error_reason: str | None = None
    expires_at: Timestamp
    warning: Literal[
        "personal_repository_write_access",
        "repository_and_history_public",
        "repository_private",
        "repository_access",
    ]


class GitHubActionConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    plan_hash: ContentDigest
    confirmed: Literal[True]
    typed_repository_name: Annotated[str, Field(max_length=256)] | None = None
    idempotency_key: IdempotencyKey
