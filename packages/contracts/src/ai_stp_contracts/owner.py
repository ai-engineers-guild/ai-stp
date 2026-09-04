"""Owner and staff workspace read models (SPEC-027, ADR-0068)."""

from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_stp_contracts.http import (
    Cursor,
    PageInfo,
    PageSize,
    Timestamp,
    open_wire_object,
    strict_request_object,
)
from ai_stp_contracts.text_safety import validate_public_text
from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.versioning import VERSION_PATTERN

type ObjectKind = Literal["component", "setup"]
type CountryCode = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]


class OwnerExternalProductCreateRequest(BaseModel):
    """Create one globally deduplicated service from the owner Web UI."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    name: Annotated[str, Field(min_length=1, max_length=160)]
    primary_url: Annotated[str, Field(min_length=8, max_length=512)]
    description: Annotated[str, Field(min_length=1, max_length=320)] | None = None
    source_url: Annotated[str, Field(pattern=r"^https://", max_length=512)] | None = None
    country_codes: Annotated[list[CountryCode], Field(max_length=249)] = Field(default_factory=list)

    @field_validator("name", "description")
    @classmethod
    def public_text_safe(cls, value: str | None) -> str | None:
        return None if value is None else validate_public_text(value)


class OwnerExternalProductAttachRequest(BaseModel):
    """Replace mutable service relations for every version of an owned object."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    canonical_domains: Annotated[list[str], Field(max_length=32)] = Field(default_factory=list)


type LifecycleState = Literal[
    "draft",
    "active",
    "deprecated",
    "blocked",
    "hidden",
    "published",
    "ready",
    "validating",
    "publish_planned",
    "failed",
    "stale",
    "cancelled",
]
type TrustLane = Literal["authoritative", "experimental"]
type ContentDigest = Annotated[str, Field(pattern=DIGEST_PATTERN)]
type Version = Annotated[str, Field(pattern=VERSION_PATTERN)]


class OwnerObjectSummary(BaseModel):
    """One owned object in the owner workspace list."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    object_kind: ObjectKind
    stable_id: Annotated[str, Field(min_length=8, max_length=64)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    latest_version: Version | None = None
    visibility: Literal["public", "private"]
    lifecycle_state: LifecycleState
    trust_lane: TrustLane | None = None
    author_verified: bool = False
    component_verified: bool = False
    updated_at: Timestamp


class OwnerObjectListResponse(BaseModel):
    """Paginated owner objects."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    items: Annotated[list[OwnerObjectSummary], Field(default_factory=list)]
    page: PageInfo


class OwnerObjectListQuery(BaseModel):
    """GET /v1/owner/objects query."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    cursor: Cursor | None = None
    page_size: PageSize = 20
    object_kind: ObjectKind | None = None


class OwnerVersionSummary(BaseModel):
    """One owned exact version in object detail."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    version: Version
    content_digest: ContentDigest | None = None
    lifecycle_state: LifecycleState
    visibility: Literal["public", "private"]
    trust_lane: TrustLane | None = None
    author_verified: bool = False
    component_verified: bool = False
    install_eligible: bool = False
    published_at: Timestamp | None = None
    can_start_publication: bool = False


class OwnerObjectDetail(BaseModel):
    """Owner object detail with versions."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    object_kind: ObjectKind
    stable_id: Annotated[str, Field(min_length=8, max_length=64)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    versions: Annotated[list[OwnerVersionSummary], Field(default_factory=list)]


# SPEC-035 component media upload bounds (author gallery, not profile avatar).
COMPONENT_MEDIA_MAX_BYTES: Final = 25 * 1024 * 1024
COMPONENT_MEDIA_ALLOWED_MIME: Final = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "video/mp4",
        "video/webm",
    }
)
COMPONENT_MEDIA_PUBLIC_PREFIX: Final = "/v1/media/component/"


def validate_component_media_upload(
    *, content_type: str, size_bytes: int
) -> Literal["image", "video"]:
    """Accept allowlisted image/video payloads within the 25 MiB bound (REQ-3506)."""
    if content_type not in COMPONENT_MEDIA_ALLOWED_MIME:
        raise ValueError("unsupported component media mime type")
    if size_bytes <= 0 or size_bytes > COMPONENT_MEDIA_MAX_BYTES:
        raise ValueError("component media size out of bounds")
    return "image" if content_type.startswith("image/") else "video"


def is_component_media_public_url(url: str) -> bool:
    """True when URL is a same-origin storage delivery path for uploaded media."""
    if not url.startswith(COMPONENT_MEDIA_PUBLIC_PREFIX):
        return False
    media_id = url[len(COMPONENT_MEDIA_PUBLIC_PREFIX) :]
    return bool(media_id) and "/" not in media_id and len(media_id) <= 64


class OwnerPresentationMedia(BaseModel):
    """One safe mutable media item shown on a component catalog page."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    kind: Literal["image", "video", "youtube"]
    url: Annotated[str, Field(min_length=1, max_length=2048)]
    alt: Annotated[str, Field(min_length=1, max_length=240)]
    caption: Annotated[str, Field(default="", max_length=500)] = ""

    @model_validator(mode="after")
    def validate_source(self) -> OwnerPresentationMedia:
        if self.kind == "youtube":
            if len(self.url) != 11 or not self.url.replace("-", "").replace("_", "").isalnum():
                raise ValueError("youtube media requires an 11-character video id")
            return self
        if is_component_media_public_url(self.url) or self.url.startswith(
            "https://raw.githubusercontent.com/"
        ):
            return self
        raise ValueError(
            "image and video media require uploaded storage path or pinned GitHub raw URL"
        )


class OwnerPresentationUpdateRequest(BaseModel):
    """Mutable component presentation only; never changes passport identity."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    bio: Annotated[str, Field(max_length=2000)] = ""
    media: Annotated[list[OwnerPresentationMedia], Field(default_factory=list, max_length=5)]

    @field_validator("bio")
    @classmethod
    def public_bio_safe(cls, value: str) -> str:
        return validate_public_text(value, allow_empty=True)


class OwnerPresentationResponse(BaseModel):
    """Current mutable component presentation for its owner."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=8, max_length=64)]
    bio: Annotated[str, Field(max_length=2000)] = ""
    media: Annotated[list[OwnerPresentationMedia], Field(default_factory=list, max_length=5)]


class OwnerEvidenceRow(BaseModel):
    """One evidence binding for owner version view."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    check_id: Annotated[str, Field(min_length=1, max_length=64)]
    result: Annotated[str, Field(min_length=1, max_length=32)]
    source: Annotated[str, Field(min_length=1, max_length=64)]
    expires_at: Timestamp | None = None


class OwnerVersionDetail(BaseModel):
    """Exact owned version for publication entry and evidence display."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    object_kind: ObjectKind
    stable_id: Annotated[str, Field(min_length=8, max_length=64)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    version: Version
    content_digest: ContentDigest | None = None
    lifecycle_state: LifecycleState
    visibility: Literal["public", "private"]
    trust_lane: TrustLane | None = None
    author_verified: bool = False
    component_verified: bool = False
    install_eligible: bool = False
    published_at: Timestamp | None = None
    can_start_publication: bool = False
    open_publication_plan_id: Annotated[str, Field(default="", max_length=64)] = ""
    evidence: Annotated[list[OwnerEvidenceRow], Field(default_factory=list)]
    description: Annotated[str, Field(default="", max_length=2000)] = ""


class StaffReportSummary(BaseModel):
    """One staff worklist case."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    case_id: Annotated[str, Field(min_length=8, max_length=64)]
    topic: Literal[
        "object_report",
        "service_request",
        "country_request",
        "component_complaint",
        "author_complaint",
        "ownership_transfer",
        "verification_request",
        "other",
    ] = "object_report"
    object_kind: ObjectKind | Literal[""] = ""
    stable_id: Annotated[str, Field(max_length=64)] = ""
    version: Version | Literal[""] = ""
    state: Annotated[str, Field(min_length=1, max_length=32)]
    vulnerability: bool = False
    created_at: Timestamp
    content_digest: ContentDigest | None = None


class StaffReportListResponse(BaseModel):
    """Staff worklist (allowlist only)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    items: Annotated[list[StaffReportSummary], Field(default_factory=list)]
    page: PageInfo


class StaffReportListQuery(BaseModel):
    """GET /v1/staff/reports query."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    cursor: Cursor | None = None
    page_size: PageSize = 20


class StaffReportDetail(BaseModel):
    """Staff case detail without reporter identity."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    case_id: Annotated[str, Field(min_length=8, max_length=64)]
    topic: Literal[
        "object_report",
        "service_request",
        "country_request",
        "component_complaint",
        "author_complaint",
        "ownership_transfer",
        "verification_request",
        "other",
    ] = "object_report"
    object_kind: ObjectKind | Literal[""] = ""
    stable_id: Annotated[str, Field(max_length=64)] = ""
    version: Version | Literal[""] = ""
    state: Annotated[str, Field(min_length=1, max_length=32)]
    vulnerability: bool = False
    created_at: Timestamp
    content_digest: ContentDigest | None = None
    error_code: Annotated[str, Field(default="", max_length=64)] = ""
    harness_id: Annotated[str, Field(default="", max_length=64)] = ""
    request_payload: dict[str, object] = Field(default_factory=dict)


#: What an owner may do to the lifecycle of their own published version.
#:
#: Not `block`, `hide` or `restore-from-hidden`: those are moderation, they are
#: named by `SPEC-026` `REQ-2617` as staff actions with a reason and an audit
#: event, and an author moderating their own object would be a different
#: decision with a different authority behind it.
type OwnerLifecycleAction = Literal["deprecate", "undeprecate"]


class OwnerLifecycleRequest(BaseModel):
    """POST a lifecycle transition on an exact owned version (`SPEC-007`).

    `deprecated` was declared in the state vocabulary, listed in three models
    and offered by a CLI hint, and written by nothing: the staff route accepts
    only `block`, `hide` and `restore`, and every owner version route was a
    read. Two successive plans carried "deprecate the old corpus" as pending
    work against a verb that did not exist.

    The author holds this one because deprecation is a statement about the
    object's own future rather than about its acceptability, and because the
    evidence that motivates it — `SPEC-044` archive observation — already
    reaches the author as a proposal.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    action: OwnerLifecycleAction
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    idempotency_key: Annotated[str, Field(min_length=16, max_length=128)]


class OwnerLifecycleResponse(BaseModel):
    """The state the version is in after the transition."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(min_length=1)]
    lifecycle: LifecycleState
    applied: bool


class OwnerStartPublicationRequest(BaseModel):
    """POST start publication plan from an exact owned version (no browser passport)."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    device_id: Annotated[str, Field(min_length=8, max_length=64)]
    idempotency_key: Annotated[str, Field(min_length=16, max_length=128)]
    policy_version: Annotated[str, Field(default="1", min_length=1, max_length=32)] = "1"


class CliOwnerObjectListView(OwnerObjectListResponse):
    """CLI owner list view, separate from the HTTP schema boundary."""


class CliOwnerObjectDetailView(OwnerObjectDetail):
    """CLI owner object view, separate from the HTTP schema boundary."""


class CliOwnerVersionDetailView(OwnerVersionDetail):
    """CLI exact owner version view, separate from the HTTP schema boundary."""
