"""Public content hub publication (SPEC-054, ADR-0132).

Field dictionaries live here. Behaviour belongs to SPEC-054; architecture
belongs to ADR-0132. Response models tolerate additive fields; request models
reject unknown keys.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_stp_contracts.http import open_wire_object, strict_request_object
from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.revisions import REVISION_ID_PATTERN

CONTENT_SCHEMA_VERSION: Final[int] = 1
CONTENT_REPOSITORY: Final[Literal["ai-engineers-guild/ai-stp"]] = "ai-engineers-guild/ai-stp"
CONTENT_TYPES: Final[tuple[str, ...]] = ("article", "blog_post", "changelog", "release_notes")
CONTENT_LOCALES: Final[tuple[str, ...]] = ("ru", "en")
CONTENT_SLUG_PATTERN: Final[str] = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
CONTENT_COMMIT_PATTERN: Final[str] = r"^[0-9a-f]{40}$"
CONTENT_DATE_PATTERN: Final[str] = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
CONTENT_BODY_MAX: Final[int] = 200_000
CONTENT_SNAPSHOT_MAX_ENTRIES: Final[int] = 10_000
ARTICLE_REVISION_DOMAIN: Final[str] = "ai-stp:article-revision:v1"
ARTICLE_ACTIVE_DOMAIN: Final[str] = "ai-stp:article-active:v1"
ARTICLE_SNAPSHOT_DOMAIN: Final[str] = "ai-stp:article-snapshot:v1"

type ContentType = Literal["article", "blog_post", "changelog", "release_notes"]
type ContentLocale = Literal["ru", "en"]
type ContentSourceKind = Literal["repository", "staff"]
type DigestValue = Annotated[str, Field(pattern=DIGEST_PATTERN)]
type RevisionId = Annotated[str, Field(pattern=REVISION_ID_PATTERN)]
type ContentSlug = Annotated[str, Field(pattern=CONTENT_SLUG_PATTERN, min_length=1, max_length=120)]
type ContentTitle = Annotated[str, Field(min_length=1, max_length=160)]
type ContentDescription = Annotated[str, Field(min_length=1, max_length=320)]
type ContentDate = Annotated[str, Field(pattern=CONTENT_DATE_PATTERN)]
type ContentTag = Annotated[str, Field(min_length=1, max_length=40)]
type ContentBody = Annotated[str, Field(min_length=1, max_length=CONTENT_BODY_MAX)]
type ContentCommit = Annotated[str, Field(pattern=CONTENT_COMMIT_PATTERN)]


class ContentLocaleQuery(BaseModel):
    """Locale selector for public content reads. No automatic fallback."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    locale: ContentLocale


class ContentSummary(BaseModel):
    """Public list item for one published localized article."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    type: ContentType
    slug: ContentSlug
    locale: ContentLocale
    title: ContentTitle
    description: ContentDescription
    published_at: ContentDate
    tags: Annotated[list[ContentTag], Field(max_length=12)]
    revision_id: RevisionId
    content_digest: DigestValue
    source_kind: ContentSourceKind


class ContentDetail(ContentSummary):
    """Public detail. Repository provenance is exact commit and path only."""

    body: ContentBody
    source_ref: ContentCommit | None
    source_path: Annotated[str, Field(min_length=1, max_length=512)] | None


class ContentListResponse(BaseModel):
    """Published repository and staff articles for one locale."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    etag: DigestValue
    items: list[ContentSummary]


class ContentRepositoryState(BaseModel):
    """Current repository import generation without entries."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    generation: Annotated[int, Field(ge=0)]
    snapshot_digest: DigestValue | None
    commit: ContentCommit | None


class ContentSnapshotEntry(BaseModel):
    """One published localized repository article in a snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    type: ContentType
    slug: ContentSlug
    locale: ContentLocale
    title: ContentTitle
    description: ContentDescription
    published_at: ContentDate
    tags: Annotated[list[ContentTag], Field(max_length=12)]
    body: ContentBody
    content_digest: DigestValue
    source_kind: Literal["repository"] = "repository"
    source_ref: ContentCommit
    source_path: Annotated[str, Field(min_length=1, max_length=512)]

    @model_validator(mode="after")
    def _unique_tags(self) -> ContentSnapshotEntry:
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("duplicate tags are rejected")
        return self


class ContentRepositoryImportRequest(BaseModel):
    """Full replacement of the repository-owned active article set."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    repository: Literal["ai-engineers-guild/ai-stp"] = CONTENT_REPOSITORY
    commit: ContentCommit
    snapshot_digest: DigestValue
    expected_generation: Annotated[int, Field(ge=0)]
    entries: Annotated[list[ContentSnapshotEntry], Field(max_length=CONTENT_SNAPSHOT_MAX_ENTRIES)]


class ContentRepositoryImportResponse(BaseModel):
    """Outcome of one repository snapshot import."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    generation: Annotated[int, Field(ge=0)]
    snapshot_digest: DigestValue
    created: Annotated[int, Field(ge=0)]
    activated: Annotated[int, Field(ge=0)]
    removed: Annotated[int, Field(ge=0)]
    unchanged: Annotated[int, Field(ge=0)]


class StaffContentTranslation(BaseModel):
    """One locale of a staff publication payload."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    title: ContentTitle
    description: ContentDescription
    published_at: ContentDate
    tags: Annotated[list[ContentTag], Field(max_length=12)]
    body: ContentBody

    @model_validator(mode="after")
    def _unique_tags(self) -> StaffContentTranslation:
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("duplicate tags are rejected")
        return self


class StaffContentTranslations(BaseModel):
    """Exact RU/EN pair. Any other locale set is unrepresentable."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    ru: StaffContentTranslation
    en: StaffContentTranslation


class StaffContentPublishRequest(BaseModel):
    """Atomic staff publication of one article identity."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    expected_active_digest: DigestValue | None
    translations: StaffContentTranslations


class StaffContentPublishResponse(BaseModel):
    """Staff publication result with the public article pair."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    article_id: Annotated[str, Field(min_length=1, max_length=160)]
    active_digest: DigestValue
    revision_ids: dict[ContentLocale, RevisionId]
    articles: dict[ContentLocale, ContentDetail]


class StaffContentUnpublishRequest(BaseModel):
    """Optimistic staff unpublish of both locales."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    expected_active_digest: DigestValue | None


class StaffContentUnpublishResponse(BaseModel):
    """Terminal unpublished staff article. Repeatable."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    article_id: Annotated[str, Field(min_length=1, max_length=160)]
    unpublished: Literal[True] = True
    active_digest: None = None
