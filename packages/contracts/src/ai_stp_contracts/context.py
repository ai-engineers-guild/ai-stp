"""Product context, capability projection, and project-link contracts.

The server owns authorization. These models only carry the bounded context and
the explanation a consumer needs to render one shared product surface
(SPEC-074..078, ADR-0175..0178).
"""

import json
import re
from collections.abc import Mapping
from typing import Annotated, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_stp_contracts.http import IdempotencyKey, Timestamp, open_wire_object, strict_request_object
from ai_stp_foundation.ids import is_valid_id, stable_id_pattern

ProductMode = Literal["local", "personal", "corporate"]
OrganizationKind = Literal["personal", "corporate"]
CapabilityId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,31}\.[a-z][a-z0-9_]{1,31}$")]
CapabilityUnavailableReason = Literal["unsupported", "dependency", "forbidden"]
OrganizationId = Annotated[str, Field(pattern=stable_id_pattern("organization"))]
RemoteProjectId = Annotated[str, Field(pattern=stable_id_pattern("remote_project"))]
ProviderProjectId = Annotated[str, Field(pattern=stable_id_pattern("provider_project"))]
ProjectLinkId = Annotated[str, Field(pattern=stable_id_pattern("project_link"))]
LinkPlanId = Annotated[str, Field(pattern=stable_id_pattern("link_plan"))]
UnlinkPlanId = Annotated[str, Field(pattern=stable_id_pattern("unlink_plan"))]
SyncPlanId = Annotated[str, Field(pattern=stable_id_pattern("sync_plan"))]
ProjectRevisionId = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
ProjectEventId = Annotated[str, Field(pattern=r"^[A-Za-z0-9._~-]{8,128}$")]
ProjectLinkProposalId = Annotated[str, Field(pattern=stable_id_pattern("proposal"))]

PROJECT_PROJECTION_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "remote_project_id",
        "index_digest",
        "toolchain_digest",
        "configuration_digest",
        "languages",
        "file_count",
        "index_state",
        "tombstone",
    }
)
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_PRIVATE_PROJECTION_KEY_PARTS = (
    "account",
    "credential",
    "content",
    "environment",
    "password",
    "path",
    "secret",
    "source",
    "token",
)


def _safe_project_projection(
    value: object, *, key: str = "", reject_identifiers: bool = False
) -> bool:
    """Reject private payloads hidden inside an otherwise allowed projection."""
    lowered = key.lower()
    if any(part in lowered for part in _PRIVATE_PROJECTION_KEY_PARTS):
        return False
    if reject_identifiers and (
        lowered == "id" or lowered.endswith("_id") or "identifier" in lowered
    ):
        return False
    if isinstance(value, Mapping):
        items = cast(Mapping[object, object], value).items()
        return all(
            isinstance(child_key, str)
            and _safe_project_projection(
                child_value, key=child_key, reject_identifiers=reject_identifiers
            )
            for child_key, child_value in items
        )
    if isinstance(value, list):
        items = cast(list[object], value)
        return all(
            _safe_project_projection(item, key=key, reject_identifiers=reject_identifiers)
            for item in items
        )
    if isinstance(value, str):
        return (
            len(value) <= 1024
            and "\x00" not in value
            and not value.startswith(("/", "\\"))
            and not re.match(r"^[A-Za-z]:[\\/]", value)
        )
    return value is None or isinstance(value, (bool, int, float))


def validate_public_project_data(
    value: object, *, reject_identifiers: bool = False, max_bytes: int = 8192
) -> None:
    """Validate bounded metadata before persisting or transmitting it."""
    if not _safe_project_projection(value, reject_identifiers=reject_identifiers):
        raise ValueError("project data contains private, path, or identifier data")
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("project data is not canonical JSON") from exc
    if len(encoded.encode("utf-8")) > max_bytes:
        raise ValueError("project data exceeds the size limit")


CAPABILITY_RESOURCES = frozenset(
    {
        "project",
        "technology",
        "landscape",
        "catalog_object",
        "organization",
        "member",
        "team",
        "assignment",
        "audit",
        "telemetry",
        "invitation",
        "saml",
        "deployment",
    }
)
CAPABILITY_ACTIONS = frozenset(
    {
        "create",
        "read",
        "update",
        "delete",
        "list",
        "link",
        "unlink",
        "publish",
        "assign",
        "revoke",
        "manage",
        "operate",
    }
)


def is_capability_id(value: str) -> bool:
    """Return whether a capability uses the closed resource.action vocabulary."""
    resource, _, action = value.partition(".")
    return resource in CAPABILITY_RESOURCES and action in CAPABILITY_ACTIONS


class OrganizationSummary(BaseModel):
    """A remote organization available to the authenticated account."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    kind: OrganizationKind
    display_name: Annotated[str, Field(min_length=1, max_length=200)]
    membership_revision: Annotated[int, Field(ge=1)]


class OrganizationListResponse(BaseModel):
    """Organizations the current account may explicitly select."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    items: Annotated[list[OrganizationSummary], Field(max_length=256)]


class CapabilityProjection(BaseModel):
    """Bounded server projection used by one shared UI.

    ``capabilities`` is an allowlist, not an authorization token. Every mutation
    still rechecks the current membership and policy revision on the server.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    mode: ProductMode
    context_kind: ProductMode
    organization_id: OrganizationId | None
    authorization_revision: Annotated[str, Field(min_length=1, max_length=128)]
    issued_at: Timestamp
    generated_at: Timestamp
    expires_at: Timestamp
    capabilities: Annotated[list[CapabilityId], Field(max_length=256)]
    unavailable: Annotated[dict[CapabilityId, CapabilityUnavailableReason], Field(max_length=256)]

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, value: list[str]) -> list[str]:
        if value != sorted(value) or len(value) != len(set(value)):
            raise ValueError("capabilities must be sorted and duplicate-free")
        if any(not is_capability_id(item) for item in value):
            raise ValueError("capability is not in the closed resource.action vocabulary")
        return value

    @model_validator(mode="after")
    def validate_projection(self) -> "CapabilityProjection":
        if self.mode != self.context_kind:
            raise ValueError("mode and context_kind must match")
        if (self.mode == "local") != (self.organization_id is None):
            raise ValueError("local context must be organization-free")
        if set(self.capabilities) & set(self.unavailable):
            raise ValueError("a capability cannot be available and unavailable")
        if any(not is_capability_id(item) for item in self.unavailable):
            raise ValueError("unavailable capability is not in the closed vocabulary")
        encoded = json.dumps(
            self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if len(encoded) > 16 * 1024:
            raise ValueError("capability projection exceeds 16 KiB")
        return self

    @property
    def available(self) -> list[str]:
        """Compatibility accessor for clients written before SPEC-076."""
        return self.capabilities


class ActiveContext(BaseModel):
    """The context that owns the current request or UI state."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    mode: ProductMode
    organization_id: OrganizationId | None
    capabilities: CapabilityProjection

    @model_validator(mode="after")
    def validate_context_projection(self) -> "ActiveContext":
        if (
            self.mode != self.capabilities.mode
            or self.organization_id != self.capabilities.organization_id
        ):
            raise ValueError("active context and capability projection must agree")
        return self


class ProjectLinkPlanRequest(BaseModel):
    """Request a server-authored exact link plan without changing state."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    local_project_id: Annotated[str, Field(pattern=stable_id_pattern("project"))]
    remote_project_id: RemoteProjectId
    provider_project_id: ProviderProjectId | None = None
    local_revision: Annotated[str, Field(min_length=1, max_length=128)]
    remote_revision: Annotated[str, Field(min_length=1, max_length=128)]
    provider_revision: Annotated[str | None, Field(max_length=128)] = None
    authorization_revision: Annotated[str, Field(min_length=1, max_length=128)]
    idempotency_key: IdempotencyKey


class ProviderProjectObservationRequest(BaseModel):
    """Provider identity evidence; it never creates a project link."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    provider_project_id: ProviderProjectId
    provider_kind: Annotated[str, Field(min_length=1, max_length=32)]
    installation_id: Annotated[str, Field(min_length=1, max_length=128)]
    namespace_id: Annotated[str, Field(min_length=1, max_length=256)]
    immutable_repository_id: Annotated[str, Field(min_length=1, max_length=128)]
    current_url: Annotated[str, Field(min_length=1, max_length=512)]
    observed_name: Annotated[str, Field(min_length=1, max_length=200)]
    authorization_revision: Annotated[str, Field(min_length=1, max_length=128)]


class ProjectLinkProposalRequest(BaseModel):
    """Non-authoritative link evidence awaiting an explicit link plan."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    local_project_id: Annotated[str, Field(pattern=stable_id_pattern("project"))]
    remote_project_id: RemoteProjectId
    provider_project_id: ProviderProjectId | None = None
    evidence: dict[str, object]
    authorization_revision: Annotated[str, Field(min_length=1, max_length=128)]


class ProjectLinkPlanResponse(BaseModel):
    """The exact server-authored link decision awaiting confirmation."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    plan_id: LinkPlanId
    organization_id: OrganizationId
    local_project_id: Annotated[str, Field(pattern=stable_id_pattern("project"))]
    remote_project_id: RemoteProjectId
    provider_project_id: ProviderProjectId | None
    local_revision: Annotated[str, Field(min_length=1, max_length=128)]
    remote_revision: Annotated[str, Field(min_length=1, max_length=128)]
    provider_revision: Annotated[str | None, Field(max_length=128)]
    authorization_revision: Annotated[str, Field(min_length=1, max_length=128)]
    plan_digest: Annotated[str, Field(min_length=71, max_length=71)]
    expires_at: Timestamp


class ProjectLinkRequest(BaseModel):
    """Confirm one exact server-authored link plan."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    plan_id: LinkPlanId
    plan_digest: Annotated[str, Field(min_length=71, max_length=71)]
    authorization_revision: Annotated[str, Field(min_length=1, max_length=128)]
    idempotency_key: IdempotencyKey


class ProjectLinkResponse(BaseModel):
    """The durable link and its last observed endpoint revisions."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    link_id: ProjectLinkId
    plan_id: LinkPlanId
    plan_digest: Annotated[str, Field(min_length=71, max_length=71)]
    organization_id: OrganizationId
    local_project_id: Annotated[str, Field(pattern=stable_id_pattern("project"))]
    remote_project_id: RemoteProjectId
    provider_project_id: ProviderProjectId | None
    state: Literal["linked", "unlinked", "conflict"]
    local_revision: Annotated[str, Field(min_length=1, max_length=128)]
    remote_revision: Annotated[str, Field(min_length=1, max_length=128)]
    provider_revision: Annotated[str | None, Field(max_length=128)]
    conflict_server_revision: ProjectRevisionId | None = None
    conflict_client_revision: ProjectRevisionId | None = None
    conflict_common_ancestor: ProjectRevisionId | None = None
    revision: Annotated[int, Field(ge=1)]
    updated_at: Timestamp


class ProjectUnlinkRequest(BaseModel):
    """Confirm one exact server-authored unlink plan."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    plan_id: UnlinkPlanId
    plan_digest: Annotated[str, Field(min_length=71, max_length=71)]
    authorization_revision: Annotated[str, Field(min_length=1, max_length=128)]
    idempotency_key: IdempotencyKey


class ProjectUnlinkPlanRequest(BaseModel):
    """Request a no-side-effect plan for unlinking one exact link revision."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    link_id: ProjectLinkId
    expected_link_revision: Annotated[int, Field(ge=1)]
    authorization_revision: Annotated[str, Field(min_length=1, max_length=128)]
    idempotency_key: IdempotencyKey


class ProjectUnlinkPlanResponse(BaseModel):
    """The exact server-authored unlink decision awaiting confirmation."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    plan_id: UnlinkPlanId
    link_id: ProjectLinkId
    organization_id: OrganizationId
    local_project_id: Annotated[str, Field(pattern=stable_id_pattern("project"))]
    remote_project_id: RemoteProjectId
    provider_project_id: ProviderProjectId | None
    expected_link_revision: Annotated[int, Field(ge=1)]
    local_revision: Annotated[str, Field(min_length=1, max_length=128)]
    remote_revision: Annotated[str, Field(min_length=1, max_length=128)]
    provider_revision: Annotated[str | None, Field(max_length=128)]
    authorization_revision: Annotated[str, Field(min_length=1, max_length=128)]
    plan_digest: Annotated[str, Field(min_length=71, max_length=71)]
    expires_at: Timestamp


class ProjectSyncPlanRequest(BaseModel):
    """Request a deterministic sync plan for an existing explicit link."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    link_id: ProjectLinkId
    expected_link_revision: Annotated[int, Field(ge=1)]
    local_revision: Annotated[str, Field(min_length=1, max_length=128)]
    remote_revision: Annotated[str, Field(min_length=1, max_length=128)]
    provider_revision: Annotated[str | None, Field(max_length=128)] = None
    authorization_revision: Annotated[str, Field(min_length=1, max_length=128)]
    idempotency_key: IdempotencyKey


class ProjectSyncPlanResponse(BaseModel):
    """A no-side-effect sync decision, or a conflict requiring user choice."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    plan_id: SyncPlanId
    link_id: ProjectLinkId
    state: Literal["ready", "conflict", "applied", "failed", "unknown"]
    action: Literal["noop", "local_to_remote", "remote_to_local", "merge_required"]
    expected_link_revision: Annotated[int, Field(ge=1)]
    local_revision: Annotated[str, Field(min_length=1, max_length=128)]
    remote_revision: Annotated[str, Field(min_length=1, max_length=128)]
    provider_revision: Annotated[str | None, Field(max_length=128)]
    remote_identity_revision: Annotated[int, Field(ge=1)]
    provider_identity_revision: Annotated[int | None, Field(ge=1)]
    conflict_code: (
        Literal[
            "local_changed",
            "remote_changed",
            "both_changed",
            "provider_mismatch",
            "remote_missing",
            "stale_revision",
        ]
        | None
    )
    common_ancestor_revision: Annotated[str | None, Field(max_length=128)] = None
    plan_digest: Annotated[str, Field(min_length=71, max_length=71)]
    expires_at: Timestamp


class ProjectSyncApplyRequest(BaseModel):
    """Apply one exact, previously-created non-conflicting sync plan."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    plan_digest: Annotated[str, Field(min_length=71, max_length=71)]
    expected_link_revision: Annotated[int, Field(ge=1)]
    authorization_revision: Annotated[str, Field(min_length=1, max_length=128)]
    idempotency_key: IdempotencyKey


class ProjectRevisionPushRequest(BaseModel):
    """One explicit content-addressed project revision push."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    event_id: ProjectEventId
    revision_id: ProjectRevisionId
    parent_revision_ids: Annotated[list[ProjectRevisionId], Field(max_length=2)]
    operation: Literal["upsert", "tombstone"]
    content_digest: ProjectRevisionId
    projection: dict[str, object]
    expected_head_revision_id: ProjectRevisionId | None = None
    authorization_revision: Annotated[str, Field(min_length=1, max_length=128)]
    idempotency_key: IdempotencyKey

    @field_validator("projection")
    @classmethod
    def validate_projection_fields(cls, value: dict[str, object]) -> dict[str, object]:
        unknown = set(value) - PROJECT_PROJECTION_FIELDS
        if unknown:
            raise ValueError("project projection contains fields outside the public allowlist")
        if value.get("schema_version", 1) != 1:
            raise ValueError("project projection schema_version must be 1")
        if "kind" in value and value["kind"] != "project":
            raise ValueError("project projection kind must be project")
        if "remote_project_id" in value and (
            not isinstance(value["remote_project_id"], str)
            or not is_valid_id(value["remote_project_id"], "remote_project")
        ):
            raise ValueError("project projection remote_project_id is invalid")
        for digest_name in ("index_digest", "toolchain_digest", "configuration_digest"):
            digest = value.get(digest_name)
            if digest_name in value and (
                not isinstance(digest, str) or _DIGEST_RE.fullmatch(digest) is None
            ):
                raise ValueError(f"project projection {digest_name} is invalid")
        if "file_count" in value and (
            not isinstance(value["file_count"], int) or value["file_count"] < 0
        ):
            raise ValueError("project projection file_count is invalid")
        try:
            validate_public_project_data(value)
        except ValueError as exc:
            raise ValueError("project projection contains private or path data") from exc
        return value

    @model_validator(mode="after")
    def validate_revision_shape(self) -> "ProjectRevisionPushRequest":
        if len(self.parent_revision_ids) != len(set(self.parent_revision_ids)):
            raise ValueError("parent_revision_ids must be unique")
        if self.operation == "tombstone" and not self.parent_revision_ids:
            raise ValueError("tombstone requires a parent")
        if self.operation == "tombstone" and not self.projection.get("tombstone", False):
            raise ValueError("tombstone projection must declare tombstone=true")
        return self


class ProjectRevisionReceipt(BaseModel):
    """Durable result of one project revision push."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    event_id: ProjectEventId
    state: Literal["accepted", "conflict", "rejected", "superseded"]
    revision_id: ProjectRevisionId | None
    server_head_revision_id: ProjectRevisionId | None
    client_head_revision_id: ProjectRevisionId | None
    common_ancestor_revision_id: ProjectRevisionId | None
    error_code: str | None


class ProjectRevisionPushResponse(BaseModel):
    """Result of a project revision push."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    receipt: ProjectRevisionReceipt


class ProjectRevisionView(BaseModel):
    """Redacted project revision returned by pull."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    revision_id: ProjectRevisionId
    parent_revision_ids: Annotated[list[ProjectRevisionId], Field(max_length=2)]
    operation: Literal["upsert", "tombstone"]
    content_digest: ProjectRevisionId
    projection: dict[str, object]
    actor_account_id: Annotated[str, Field(min_length=1, max_length=64)]
    device_id: Annotated[str, Field(min_length=1, max_length=64)]
    created_at: Timestamp


class ProjectRevisionPullResponse(BaseModel):
    """Bounded pull of the tenant-scoped project ledger."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    head_revision_id: ProjectRevisionId | None
    items: Annotated[list[ProjectRevisionView], Field(max_length=256)]


class ProjectConflictResolutionRequest(ProjectRevisionPushRequest):
    """Explicit two-parent merge; it never happens during ordinary push."""

    @model_validator(mode="after")
    def require_two_parents(self) -> "ProjectConflictResolutionRequest":
        if len(self.parent_revision_ids) != 2:
            raise ValueError("conflict resolution requires exactly two parents")
        return self
