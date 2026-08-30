"""Public SEO publication projection (SPEC-053, ADR-0131).

Field dictionaries live here. Behaviour belongs to SPEC-053; architecture
belongs to ADR-0131. Response models tolerate additive fields; request models
reject unknown keys.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_stp_contracts.http import (
    Cursor,
    PageInfo,
    PageSize,
    Timestamp,
    open_wire_object,
    strict_request_object,
)
from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.revisions import REVISION_ID_PATTERN

SEO_SCHEMA_VERSION: Final[int] = 1
SEO_TEMPLATE_VERSION: Final[str] = "seo-template-v4"
SEO_PROMPT_VERSION: Final[str] = "seo-prompt-v17"
SEO_MODEL_ALIAS: Final[str] = "seo-writer"
SEO_SITEMAP_SHARD_LIMIT: Final[int] = 50_000
SEO_OG_WIDTH: Final[int] = 1200
SEO_OG_HEIGHT: Final[int] = 630
SEO_LOCALES: Final[tuple[str, ...]] = ("ru", "en")
SEO_SNAPSHOT_DOMAIN: Final[str] = "ai-stp:seo-snapshot:v1"
SEO_PROFILE_DOMAIN: Final[str] = "ai-stp:seo-profile:v1"
ARTICLE_BODY_DOMAIN: Final[str] = "ai-stp:article-body:v1"

type SeoSubjectKind = Literal["component", "setup", "article", "service", "country"]
type SeoLocale = Literal["ru", "en"]
type SeoRobots = Literal["index,follow", "noindex,follow"]
type SeoGeneratorKind = Literal["template", "model"]
type SeoRevisionState = Literal[
    "building",
    "base_ready",
    "enriching",
    "validating",
    "active",
    "rejected",
    "failed",
    "stale",
]
type SeoIndexReason = Literal[
    "eligible",
    "not_public",
    "blocked",
    "hidden",
    "deprecated",
    "missing_primary_content",
    "missing_source",
    "empty_collection",
    "duplicate_canonical",
    "unavailable",
    "materialization_pending",
]
type SeoErrorCode = Literal[
    "AI_STP_SEO_FACTS_INVALID",
    "AI_STP_SEO_OUTPUT_INVALID",
    "AI_STP_SEO_ENRICHMENT_UNAVAILABLE",
    "AI_STP_SEO_SOURCE_STALE",
    "AI_STP_SEO_RENDER_FAILED",
]
type DigestValue = Annotated[str, Field(pattern=DIGEST_PATTERN)]
type RevisionId = Annotated[str, Field(pattern=REVISION_ID_PATTERN)]
type AbsoluteUrl = Annotated[str, Field(pattern=r"^https?://", max_length=2048)]
type SafeText160 = Annotated[str, Field(min_length=1, max_length=160)]
type SafeText200 = Annotated[str, Field(min_length=1, max_length=200)]
type SafeText320 = Annotated[str, Field(min_length=1, max_length=320)]

SEO_SUBJECT_KINDS: Final[tuple[SeoSubjectKind, ...]] = (
    "component",
    "setup",
    "article",
    "service",
    "country",
)
SEO_INDEX_REASONS: Final[tuple[SeoIndexReason, ...]] = (
    "eligible",
    "not_public",
    "blocked",
    "hidden",
    "deprecated",
    "missing_primary_content",
    "missing_source",
    "empty_collection",
    "duplicate_canonical",
    "unavailable",
    "materialization_pending",
)
SEO_REVISION_STATES: Final[tuple[SeoRevisionState, ...]] = (
    "building",
    "base_ready",
    "enriching",
    "validating",
    "active",
    "rejected",
    "failed",
    "stale",
)
FORBIDDEN_FACT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "password",
        "secret",
        "token",
        "api_key",
        "credential",
        "private_key",
        "authorization",
        "cookie",
        "email",
        "artifact_bytes",
        "artifact_body",
        "finding_body",
        "findings",
        "prompt",
        "raw_prompt",
        "raw_response",
    }
)


class SeoSubjectRef(BaseModel):
    """Identity of one SEO subject revision."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=open_wire_object)
    kind: SeoSubjectKind
    id: Annotated[str, Field(min_length=1, max_length=253)]
    source_revision: Annotated[str, Field(min_length=1, max_length=128)]
    source_digest: DigestValue


class SeoIndexDecision(BaseModel):
    """Deterministic index eligibility. Model output never supplies this."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=open_wire_object)
    eligible: bool
    reasons: Annotated[list[SeoIndexReason], Field(max_length=12)]

    @model_validator(mode="after")
    def _reasons_match_eligibility(self) -> SeoIndexDecision:
        if self.eligible:
            if self.reasons != ["eligible"]:
                raise ValueError("eligible decision stores only the eligible reason")
        elif not self.reasons or "eligible" in self.reasons:
            raise ValueError("ineligible decision stores only negative reasons")
        return self


class SeoLink(BaseModel):
    """One crawlable visible link."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=open_wire_object)
    rel: Annotated[str, Field(min_length=1, max_length=64)]
    href: AbsoluteUrl
    text: Annotated[str, Field(min_length=1, max_length=200)]
    kind: SeoSubjectKind | None = None
    subject_id: Annotated[str, Field(min_length=1, max_length=253)] | None = None


class SeoSection(BaseModel):
    """One visible kind-specific page section."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=open_wire_object)
    id: Annotated[str, Field(min_length=1, max_length=64)]
    heading: Annotated[str, Field(min_length=1, max_length=200)]
    body: Annotated[str, Field(min_length=1, max_length=8000)]
    provenance: Literal["template", "model"] = "template"


class SeoSocial(BaseModel):
    """Open Graph / Twitter preview facts."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=open_wire_object)
    title: SafeText160
    description: SafeText320
    image_url: AbsoluteUrl
    image_alt: Annotated[str, Field(min_length=1, max_length=200)]
    locale: SeoLocale


class SeoGenerator(BaseModel):
    """Provenance of one SEO revision. Model alias is operator-facing only."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=open_wire_object)
    kind: SeoGeneratorKind
    template_version: Annotated[str, Field(min_length=1, max_length=64)]
    prompt_version: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    model_alias: Annotated[str, Field(min_length=1, max_length=64)] | None = None


class SeoProfileDocument(BaseModel):
    """Closed profile document v1 stored on a revision."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    subject: SeoSubjectRef
    locale: SeoLocale
    canonical_url: AbsoluteUrl
    title: SafeText160
    description: SafeText320
    heading: SafeText200
    summary: Annotated[str, Field(min_length=1, max_length=4000)]
    taxonomy_tags: Annotated[list[str], Field(max_length=12)]
    search_intents: Annotated[list[str], Field(max_length=12)]
    alternates: dict[str, AbsoluteUrl]
    robots: SeoRobots
    index_decision: SeoIndexDecision
    breadcrumbs: Annotated[list[SeoLink], Field(max_length=12)]
    sections: Annotated[list[SeoSection], Field(max_length=24)]
    internal_links: Annotated[list[SeoLink], Field(max_length=48)]
    json_ld: dict[str, object]
    social: SeoSocial
    published_at: Timestamp
    modified_at: Timestamp
    generator: SeoGenerator


class SeoPublicProfile(BaseModel):
    """Anonymous read of the active SEO revision."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    revision_id: RevisionId
    snapshot_id: DigestValue
    generation: Annotated[int, Field(ge=0)]
    etag: DigestValue
    profile: SeoProfileDocument


class SeoSubjectQuery(BaseModel):
    """Locale selector for one subject read."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    locale: SeoLocale = "en"


class SeoSitemapUrl(BaseModel):
    """One eligible canonical URL in a sitemap shard."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=open_wire_object)
    loc: AbsoluteUrl
    lastmod: Timestamp
    alternates: dict[str, AbsoluteUrl]


class SeoSitemapShard(BaseModel):
    """One kind/locale shard of at most 50_000 URLs."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    generation: Annotated[int, Field(ge=0)]
    kind: SeoSubjectKind
    locale: SeoLocale
    page: Annotated[int, Field(ge=1)]
    urls: Annotated[list[SeoSitemapUrl], Field(max_length=SEO_SITEMAP_SHARD_LIMIT)]


class SeoIndexShardRef(BaseModel):
    loc: AbsoluteUrl
    lastmod: Timestamp


class SeoIndexResponse(BaseModel):
    """Sitemap index for the current SEO generation."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    generation: Annotated[int, Field(ge=0)]
    etag: DigestValue
    shards: list[SeoIndexShardRef]


class SeoCatalogQuery(BaseModel):
    """Paginated LLM catalog manifest query."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    locale: SeoLocale | None = None
    kind: SeoSubjectKind | None = None
    cursor: Cursor | None = None
    page_size: PageSize = 20


class SeoCatalogEntry(BaseModel):
    """One LLM catalog manifest row."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=open_wire_object)
    kind: SeoSubjectKind
    subject_id: Annotated[str, Field(min_length=1, max_length=253)]
    locale: SeoLocale
    canonical_url: AbsoluteUrl
    title: SafeText160
    description: SafeText320
    markdown_url: AbsoluteUrl
    revision_id: RevisionId
    modified_at: Timestamp


class SeoCatalogPage(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    generation: Annotated[int, Field(ge=0)]
    items: list[SeoCatalogEntry]
    page: PageInfo


class SeoRollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    locale: SeoLocale = "en"


class SeoRollbackResponse(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    subject_kind: SeoSubjectKind
    subject_id: Annotated[str, Field(min_length=1, max_length=253)]
    locale: SeoLocale
    revision_id: RevisionId
    generator_kind: SeoGeneratorKind


class SeoEnrichmentOutput(BaseModel):
    """Closed model output. Unknown fields fail the whole candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    title: SafeText160
    description: SafeText320
    summary: Annotated[str, Field(min_length=1, max_length=4000)]
    search_intents: Annotated[list[str], Field(max_length=12)]
    sections: Annotated[list[SeoSection], Field(max_length=24)]
    social_title: SafeText160
    social_description: SafeText320
    social_image_alt: Annotated[str, Field(min_length=1, max_length=200)]
