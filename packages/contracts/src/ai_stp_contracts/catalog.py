"""Anonymous public catalog payloads (issue #71, SPEC-005, SPEC-006, ADR-0016).

Components and setups are separate resources — `/v1/catalog/components` and
`/v1/catalog/setups` — rather than one polymorphic object route, because their
passports differ enough that a wire-level union costs more than it saves. The
consequence is deliberate and must be carried into the CLI: a cursor belongs to
one kind, so a search targets one kind per call.

Four properties here are safety rules, not style:

- `hidden` is not representable on the public wire, so a hidden object cannot be
  disclosed by a lifecycle value;
- no response carries a count of objects, so the size of a result set the caller
  may not fully read cannot be recovered by arithmetic;
- `author_verified` and `component_verified` are separate fields, neither is
  derived from the other (ADR-0016), and `authoritative` may not be claimed
  without both;
- the passport served on a public route must itself be published.

**What is deliberately *not* claimed:** public version numbers are not
contiguous. Hiding a version does not free its number (SPEC-005 keeps the bytes
and changes only the state), so `1.0, 1.2` is a legal answer and the gap at 1.1
is not evidence of anything a caller may act on. Pagination would not close it
and dropping `published_at` would cost real utility for one bit. The contract
states the non-contiguity instead of pretending it enumerates a dense sequence.

Search results are partitioned, not interleaved: SPEC-006 REQ-603 and ADR-0016
require experimental candidates to arrive in their own section and only on an
explicit request-scoped consent. Both lanes share one cursor sequence, so paging
still yields no duplicate and skips nothing.

Ordering is total and stable within one cursor sequence. The order is the
server's and the cursor carries the position — that is what makes it opaque.
"""

import re
from collections.abc import Sequence
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_stp_contracts.http import (
    PAGE_SIZE_DEFAULT,
    PAGE_SIZE_MAX,
    Cursor,
    PageInfo,
    PageSize,
    Timestamp,
    open_wire_object,
    strict_request_object,
)
from ai_stp_contracts.impact import (
    ComponentTokenMeasurement,
    ExactCoordinate,
    TokenEstimator,
)
from ai_stp_contracts.safety_checks import SafetyChecksSummary, SetupComponentChecks
from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_foundation.ids import stable_id_pattern
from ai_stp_foundation.versioning import VERSION_PATTERN
from ai_stp_passports.versions import (
    MAX_TAGS,
    ComponentType,
    ComponentVersionPassport,
    ProjectionKind,
    SetupVersionPassport,
    TagId,
)

type ComponentId = Annotated[str, Field(pattern=stable_id_pattern("component"))]
type SetupId = Annotated[str, Field(pattern=stable_id_pattern("setup"))]
type Version = Annotated[str, Field(pattern=VERSION_PATTERN)]
type PassportDigest = Annotated[str, Field(pattern=DIGEST_PATTERN)]
type Tags = Annotated[list[TagId], Field(min_length=1, max_length=MAX_TAGS)]
type DescriptionExcerpt = Annotated[str, Field(min_length=1, max_length=240)]

#: Published lifecycle states (SPEC-005). `hidden` exists in the model but is
#: **absent here on purpose**: a hidden object is not disclosed at all, so the
#: public wire has no value that could admit its existence.
type PublicLifecycle = Literal["active", "deprecated", "blocked"]

#: Catalog trust lanes (ADR-0016). `local_owner_or_pinned` is absent because it
#: describes an object the user already owns or pinned locally; it is a local
#: selection rule and never a property the catalog can assert about a published
#: object.
type CatalogTrustLane = Literal["authoritative", "experimental"]
type SupportTier = Literal["primary", "beta"]
type SupportState = Literal["verified", "stale", "missing", "not_verified"]
type SupportEvidenceResult = Literal[
    "passed", "warning", "failed", "degraded", "not_run", "expired"
]
type SupportEvidenceSource = Literal["provider_release_evidence"]
type SupportOperatingSystem = Literal["linux", "macos", "windows"]
type SupportArchitecture = Literal["x86_64", "arm64"]
type CatalogSort = Literal["relevance", "updated_at", "likes"]
type CatalogSortDirection = Literal["asc", "desc"]
type PageNumber = Annotated[int, Field(ge=1, le=10_000)]
type CatalogUpdatedDate = date
type ComponentMediaKind = Literal["image", "video", "youtube"]
type CountryCode = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]
#: Shared sentinel token. Meaning is facet-specific:
#: `service_domains=unspecified` matches an object with no linked service;
#: `country_codes=unspecified` matches an object linked to a service that has
#: no country. The two facets stay independent and combine with AND.
CATALOG_UNSPECIFIED_FILTER = "unspecified"
type CountryFilterValue = Annotated[
    str, Field(pattern=rf"^(?:[A-Z]{{2}}|{CATALOG_UNSPECIFIED_FILTER})$")
]


def reject_reversed_updated_range(updated_from: date | None, updated_to: date | None) -> None:
    """Refuse a reversed inclusive calendar-day window."""
    if updated_from is not None and updated_to is not None and updated_from > updated_to:
        raise ValueError("updated_from must be on or before updated_to")


def normalize_search_text(q: str | None) -> str | None:
    """Trim `q`. Whitespace-only is absent, not a match-all term."""
    if q is None:
        return None
    stripped = q.strip()
    return stripped or None


def unique_sorted(values: Sequence[str]) -> list[str]:
    """Trim, drop blanks, de-duplicate, and sort for filters and signatures."""
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in values:
        token = raw.strip()
        if not token or token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    ordered.sort()
    return ordered


def merged_or_values(singular: str | None, values: Sequence[str] | None) -> list[str]:
    """Union a legacy singular filter with its list form (OR semantics)."""
    items: list[str] = list(values or [])
    if singular:
        items.append(singular)
    return unique_sorted(items)


class ExternalProductObject(BaseModel):
    """Public catalog object attached to a service."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    object_kind: Literal["component", "setup"]
    stable_id: Annotated[str, Field(min_length=8, max_length=64)]
    name: Annotated[str, Field(min_length=1, max_length=200)]


class ExternalProductSummary(BaseModel):
    """Curated external service, keyed by its registrable domain."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    name: Annotated[str, Field(min_length=1, max_length=160)]
    canonical_domain: Annotated[str, Field(min_length=3, max_length=253)]
    primary_url: Annotated[str, Field(pattern=r"^https://", max_length=512)]
    description: Annotated[str, Field(min_length=1, max_length=320)] | None = None
    source_url: Annotated[str, Field(pattern=r"^https://", max_length=512)] | None = None
    country_codes: Annotated[list[CountryCode], Field(max_length=249)] = Field(default_factory=list)


class ExternalProductDetail(ExternalProductSummary):
    objects: list[ExternalProductObject] = Field(default_factory=list[ExternalProductObject])


class ExternalProductListResponse(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    items: list[ExternalProductSummary] = Field(default_factory=list[ExternalProductSummary])


class CountrySummary(BaseModel):
    """Stable country roof; localized display name belongs to Web."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    code: CountryCode
    services_count: Annotated[int, Field(ge=0)] = 0
    objects_count: Annotated[int, Field(ge=0)] = 0


class CountryDetail(CountrySummary):
    services: list[ExternalProductSummary] = Field(default_factory=list[ExternalProductSummary])
    objects: list[ExternalProductObject] = Field(default_factory=list[ExternalProductObject])


class CountryListResponse(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    items: list[CountrySummary] = Field(default_factory=list[CountrySummary])


class ComponentMediaItem(BaseModel):
    """Safe public component media projection (SPEC-035)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    id: Annotated[str, Field(min_length=1, max_length=64)]
    kind: ComponentMediaKind
    url: Annotated[str, Field(min_length=1, max_length=2048)]
    thumbnail_url: Annotated[str, Field(min_length=1, max_length=2048)] | None = None
    alt: Annotated[str, Field(min_length=1, max_length=240)]
    caption: Annotated[str, Field(max_length=500)] | None = None
    source_label: Annotated[str, Field(min_length=1, max_length=80)]

    @model_validator(mode="after")
    def _source_shape_is_safe(self) -> "ComponentMediaItem":
        if self.kind == "youtube":
            if not re.fullmatch(r"[A-Za-z0-9_-]{11}", self.url):
                raise ValueError("youtube media must carry an 11-character video id")
        elif not self.url.startswith(("/v1/media/", "https://raw.githubusercontent.com/")):
            raise ValueError(
                "public media URL must be signed storage delivery or pinned GitHub raw"
            )
        return self


class CatalogPageInfo(BaseModel):
    """Exact public web page metadata; never used for private enumeration."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    mode: Literal["page"]
    next_cursor: None
    page_size: PageSize
    page_number: PageNumber
    total_items: Annotated[int, Field(ge=0)]
    total_pages: Annotated[int, Field(ge=0)]
    previous_page: PageNumber | None
    next_page: PageNumber | None


class CatalogSupportEvidence(BaseModel):
    """Safe public summary of one provider support check (SPEC-033, ADR-0072)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    check_id: Annotated[str, Field(min_length=1, max_length=64)]
    policy_version: Annotated[str, Field(min_length=1, max_length=64)]
    result: SupportEvidenceResult
    source: SupportEvidenceSource
    provider_id: Annotated[str, Field(min_length=1, max_length=128)]
    provider_version: Annotated[str, Field(min_length=1, max_length=64)]
    release_reference: Annotated[str, Field(pattern=r"^(?:[0-9a-f]{40,64}|sha256:[0-9a-f]{64})$")]
    operating_system: SupportOperatingSystem
    architecture: SupportArchitecture
    mandatory: bool = True
    observed_at: Timestamp
    expires_at: Timestamp | None = None


class CatalogSupport(BaseModel):
    """Provider support status, separate from object trust and verification."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    tier: SupportTier
    state: SupportState
    evidence: Annotated[list[CatalogSupportEvidence], Field(max_length=32)] = Field(
        default_factory=list[CatalogSupportEvidence]
    )

    @model_validator(mode="after")
    def _verified_requires_mandatory_passes(self) -> "CatalogSupport":
        mandatory = [row for row in self.evidence if row.mandatory]
        if self.state == "verified" and (
            not mandatory or any(row.result != "passed" for row in mandatory)
        ):
            raise ValueError("support state 'verified' requires mandatory passed evidence")
        return self


class GitHubMetadata(BaseModel):
    """Best-effort on-demand stars and archive state (SPEC-049)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stars: Annotated[int, Field(ge=0)] | None = None
    archived: bool | None = None


class CatalogUsageMetrics(BaseModel):
    """Server aggregate of public detail views and completed artifact bytes.

    Absence of this object means the feature is off or the value is unavailable,
    not zero. Download is not install success.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    detail_views_count: Annotated[int, Field(ge=0)]
    artifact_downloads_count: Annotated[int, Field(ge=0)]


#: Default anti-abuse window, dedup retention and secret rotation (SPEC-051).
USAGE_METRICS_DEFAULT_WINDOW_SECONDS = 60 * 60
USAGE_METRICS_DEFAULT_RETENTION_SECONDS = 25 * 60 * 60
USAGE_METRICS_DEFAULT_SECRET_ROTATION_SECONDS = 24 * 60 * 60
USAGE_METRICS_WINDOW_MIN_SECONDS = 5 * 60
USAGE_METRICS_WINDOW_MAX_SECONDS = 24 * 60 * 60
USAGE_METRICS_RETENTION_MAX_SECONDS = 7 * 24 * 60 * 60
USAGE_METRICS_ENABLED_BY_DEFAULT: Literal[False] = False


class CatalogTrust(BaseModel):
    """Why a published version may appear in results, and on whose evidence.

    The two verification flags are independent axes (ADR-0016) and neither may
    be computed from the other. `authoritative` additionally requires both, and
    that implication is enforced below — enforcing it is not the same as
    deriving one axis from the other, and a client must still read the flags.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    trust_lane: CatalogTrustLane
    author_verified: bool
    component_verified: bool

    @model_validator(mode="after")
    def _authoritative_requires_both_axes(self) -> "CatalogTrust":
        if self.trust_lane == "authoritative" and not (
            self.author_verified and self.component_verified
        ):
            raise ValueError(
                "trust_lane 'authoritative' requires author_verified and component_verified"
            )
        return self


class VersionListEntry(BaseModel):
    """One offered version of an object, as listed on its card.

    "Offered", not "every": a hidden version is absent, which is why the list
    makes no contiguity claim.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    version: Version
    passport_digest: PassportDigest
    lifecycle: PublicLifecycle
    trust: CatalogTrust
    support: CatalogSupport
    published_at: Timestamp
    #: Safety scan summary for this version (#270); None when never scanned.
    checks: SafetyChecksSummary | None = None


class ComponentSummary(BaseModel):
    """Search-result card for a component.

    Naming is mechanical rather than a judgement call: a field without a prefix
    identifies the **object**, and every `latest_` field is a fact of its latest
    offered **version**, copied from that version's passport. There is no
    object-level passport (ADR-0012), so a card cannot carry an object-level
    `name` or `tags` however stable they look in practice — and a test ties
    every `latest_` field back to a real passport field so the rule cannot rot.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: ComponentId
    publisher_id: Annotated[str, Field(min_length=1, max_length=128)]
    owner_account_id: Annotated[str, Field(default="", max_length=64)] = ""
    owner_handle: Annotated[str, Field(default="", max_length=32)] = ""
    canonical_name: Annotated[str, Field(default="", max_length=80)] = ""
    display_name: Annotated[str, Field(default="", max_length=80)] = ""
    display_locale: Literal["ru", "en", ""] = ""
    likes_count: Annotated[int, Field(ge=0)] = 0
    github_stars: Annotated[int, Field(ge=0)] | None = None
    latest_requirements_count: Annotated[int, Field(ge=0)] = 0
    latest_requires_credentials: bool = False
    updated_at: Timestamp
    latest_version: Version
    latest_name: str
    #: Deterministic plain-text `safe_markdown_v1` excerpt, never raw Markdown or HTML.
    latest_description: DescriptionExcerpt
    latest_harness_id: HarnessId
    #: Every harness the latest version names; includes `latest_harness_id`.
    latest_harness_ids: Annotated[list[HarnessId], Field(max_length=6)] = Field(
        default_factory=list[HarnessId]
    )
    latest_component_type: ComponentType
    latest_projection_kind: ProjectionKind
    latest_tags: Tags
    latest_lifecycle: PublicLifecycle
    latest_trust: CatalogTrust
    latest_support: CatalogSupport
    latest_published_at: Timestamp
    #: Latest version safety checks projection (#270).
    latest_checks: SafetyChecksSummary | None = None
    #: Public usage aggregate; omitted when the feature is disabled.
    usage_metrics: CatalogUsageMetrics | None = None


class SetupSummary(BaseModel):
    """Search-result card for a setup. A setup has no variant axis (ADR-0014).

    `latest_harness_id` keeps the prefix even though a setup belongs to one
    harness from creation: the value is still read out of the version passport,
    and one rule with no exceptions is cheaper to verify than a rule with one.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: SetupId
    publisher_id: Annotated[str, Field(min_length=1, max_length=128)]
    likes_count: Annotated[int, Field(ge=0)] = 0
    github_stars: Annotated[int, Field(ge=0)] | None = None
    latest_requirements_count: Annotated[int, Field(ge=0)] = 0
    latest_requires_credentials: bool = False
    updated_at: Timestamp
    latest_version: Version
    latest_name: str
    #: Deterministic plain-text `safe_markdown_v1` excerpt, never raw Markdown or HTML.
    latest_description: DescriptionExcerpt
    latest_harness_id: HarnessId
    latest_harness_ids: Annotated[list[HarnessId], Field(max_length=7)] = Field(
        default_factory=list[HarnessId]
    )
    latest_purpose: str
    #: Optional for the same reason the passport field is (`ADR-0130`): a role
    #: has no source, so first-party setups carry none and the card shows the
    #: absence rather than an invented value.
    latest_target_role: str | None = None
    #: The published axis a user chooses along — `minimal`, `baseline`,
    #: `full-auto`, `nddev-builder`. `None` for a setup with no such axis.
    latest_posture: str | None = None
    latest_tags: Tags
    latest_lifecycle: PublicLifecycle
    latest_trust: CatalogTrust
    latest_support: CatalogSupport
    latest_published_at: Timestamp
    #: Latest version safety checks projection (#270).
    latest_checks: SafetyChecksSummary | None = None
    #: Public usage aggregate; omitted when the feature is disabled.
    usage_metrics: CatalogUsageMetrics | None = None


class CatalogReactionState(BaseModel):
    """Private state of the current account's reaction."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    liked: bool
    likes_count: Annotated[int, Field(ge=0)]


class LikedCatalogItem(BaseModel):
    """One public catalog projection selected by the current account."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    object_kind: Literal["component", "setup"]
    summary: ComponentSummary | SetupSummary


class CatalogReactionList(BaseModel):
    """Private list of objects liked by the current account."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    items: list[LikedCatalogItem] = Field(default_factory=list[LikedCatalogItem])


class ComponentSearchRequest(BaseModel):
    """Query for `/v1/catalog/components`.

    Strict on purpose (`strict_request_object`): an unknown parameter is a
    dropped filter, not forward compatibility.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    q: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    tags: Annotated[list[TagId], Field(max_length=MAX_TAGS)] = Field(default_factory=list[TagId])
    harness_id: HarnessId | None = None
    component_type: ComponentType | None = None
    harness_ids: Annotated[list[HarnessId], Field(max_length=6)] = Field(
        default_factory=list[HarnessId]
    )
    component_types: Annotated[list[ComponentType], Field(max_length=9)] = Field(
        default_factory=list[ComponentType]
    )
    authors: Annotated[list[str], Field(max_length=20)] = Field(default_factory=list[str])
    verified_only: bool = False
    sort: CatalogSort = "relevance"
    sort_direction: CatalogSortDirection = "desc"
    support_tier: SupportTier | None = None
    support_state: SupportState | None = None
    service_domain: Annotated[str, Field(min_length=3, max_length=253)] | None = None
    country_code: CountryCode | None = None
    service_domains: Annotated[list[str], Field(max_length=20)] = Field(
        default_factory=list[str],
        description=(
            "External service domains. The sentinel unspecified matches objects "
            "with no linked service."
        ),
    )
    country_codes: Annotated[list[CountryFilterValue], Field(max_length=20)] = Field(
        default_factory=list[CountryFilterValue],
        description=(
            "ISO country codes implied by linked services. The sentinel "
            "unspecified matches a linked service that has no country, not an "
            "object without a service."
        ),
    )
    updated_from: CatalogUpdatedDate | None = None
    updated_to: CatalogUpdatedDate | None = None
    cursor: Cursor | None = None
    page: PageNumber | None = None
    page_size: PageSize = PAGE_SIZE_DEFAULT

    #: Request-scoped consent for the experimental lane (SPEC-006 REQ-603,
    #: ADR-0029). It is a property of this call, never a stored preference:
    #: `search.include_unverified` was deliberately removed from the CLI config,
    #: because open-ended consent to everything unverified is not offered.
    include_experimental: bool = False
    #: Whether the browse listing offers superseded versions. Off by default:
    #: `deprecated` stays fully representable — by id, by exact version, and by
    #: setting this — which is what `REQ-2107` requires, while a listing is a
    #: recommendation and a superseded version is not one. One set answered both
    #: questions until 2026-08-30, when the catalogue's first page was 19
    #: deprecated setups and one active.
    include_deprecated: bool = False

    @field_validator("q", mode="before")
    @classmethod
    def _blank_q_is_absent(cls, value: object) -> object:
        return normalize_search_text(value) if isinstance(value, str) else value

    @field_validator(
        "tags",
        "harness_ids",
        "component_types",
        "authors",
        "service_domains",
        "country_codes",
        mode="after",
    )
    @classmethod
    def _canonical_multi_value_filters(cls, value: list[str]) -> list[str]:
        return unique_sorted(value)

    @model_validator(mode="after")
    def _updated_range_is_ordered(self) -> "ComponentSearchRequest":
        reject_reversed_updated_range(self.updated_from, self.updated_to)
        return self


class SetupSearchRequest(BaseModel):
    """Query for `/v1/catalog/setups`."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    q: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    tags: Annotated[list[TagId], Field(max_length=MAX_TAGS)] = Field(default_factory=list[TagId])
    harness_id: HarnessId | None = None
    harness_ids: Annotated[list[HarnessId], Field(max_length=6)] = Field(
        default_factory=list[HarnessId]
    )
    authors: Annotated[list[str], Field(max_length=20)] = Field(default_factory=list[str])
    verified_only: bool = False
    sort: CatalogSort = "relevance"
    sort_direction: CatalogSortDirection = "desc"
    support_tier: SupportTier | None = None
    support_state: SupportState | None = None
    service_domain: Annotated[str, Field(min_length=3, max_length=253)] | None = None
    country_code: CountryCode | None = None
    service_domains: Annotated[list[str], Field(max_length=20)] = Field(
        default_factory=list[str],
        description=(
            "External service domains. The sentinel unspecified matches objects "
            "with no linked service."
        ),
    )
    country_codes: Annotated[list[CountryFilterValue], Field(max_length=20)] = Field(
        default_factory=list[CountryFilterValue],
        description=(
            "ISO country codes implied by linked services. The sentinel "
            "unspecified matches a linked service that has no country, not an "
            "object without a service."
        ),
    )
    updated_from: CatalogUpdatedDate | None = None
    updated_to: CatalogUpdatedDate | None = None
    cursor: Cursor | None = None
    page: PageNumber | None = None
    page_size: PageSize = PAGE_SIZE_DEFAULT
    include_experimental: bool = False
    #: Whether the browse listing offers superseded versions. Off by default:
    #: `deprecated` stays fully representable — by id, by exact version, and by
    #: setting this — which is what `REQ-2107` requires, while a listing is a
    #: recommendation and a superseded version is not one. One set answered both
    #: questions until 2026-08-30, when the catalogue's first page was 19
    #: deprecated setups and one active.
    include_deprecated: bool = False

    @field_validator("q", mode="before")
    @classmethod
    def _blank_q_is_absent(cls, value: object) -> object:
        return normalize_search_text(value) if isinstance(value, str) else value

    @field_validator(
        "tags",
        "harness_ids",
        "authors",
        "service_domains",
        "country_codes",
        mode="after",
    )
    @classmethod
    def _canonical_multi_value_filters(cls, value: list[str]) -> list[str]:
        return unique_sorted(value)

    @model_validator(mode="after")
    def _updated_range_is_ordered(self) -> "SetupSearchRequest":
        reject_reversed_updated_range(self.updated_from, self.updated_to)
        return self


class ComponentListResponse(BaseModel):
    """One page of component search results, partitioned by trust lane."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1

    #: Authoritative candidates. Bounded like `experimental`, and their sum is
    #: bounded too: `page_size` is only the server's self-report, while these
    #: arrays decide what the client actually buffers.
    items: Annotated[list[ComponentSummary], Field(max_length=PAGE_SIZE_MAX)]

    #: Experimental candidates, returned as their own section rather than mixed
    #: into `items` (SPEC-006 REQ-603). Empty unless the request carried
    #: `include_experimental`. An empty authoritative lane beside a populated
    #: experimental one is an honest answer, not an error.
    experimental: Annotated[list[ComponentSummary], Field(max_length=PAGE_SIZE_MAX)] = Field(
        default_factory=list[ComponentSummary]
    )
    page: PageInfo | CatalogPageInfo

    @model_validator(mode="after")
    def _page_is_bounded_across_both_lanes(self) -> "ComponentListResponse":
        _reject_oversized_page(len(self.items), len(self.experimental))
        return self


class SetupListResponse(BaseModel):
    """One page of setup search results, partitioned by trust lane."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    items: Annotated[list[SetupSummary], Field(max_length=PAGE_SIZE_MAX)]
    experimental: Annotated[list[SetupSummary], Field(max_length=PAGE_SIZE_MAX)] = Field(
        default_factory=list[SetupSummary]
    )
    page: PageInfo | CatalogPageInfo

    @model_validator(mode="after")
    def _page_is_bounded_across_both_lanes(self) -> "SetupListResponse":
        _reject_oversized_page(len(self.items), len(self.experimental))
        return self


def _reject_oversized_page(authoritative: int, experimental: int) -> None:
    """Bound a page across both lanes, not per lane.

    Two arrays each capped at the maximum would let one page carry twice it,
    which is the bound the client's memory actually cares about.
    """
    total = authoritative + experimental
    if total > PAGE_SIZE_MAX:
        raise ValueError(f"page carries {total} objects across both lanes, over {PAGE_SIZE_MAX}")


class ComponentDetail(BaseModel):
    """Exact read of one public component and the versions it offers."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    summary: ComponentSummary
    versions: Annotated[list[VersionListEntry], Field(min_length=1)]
    media: Annotated[list[ComponentMediaItem], Field(max_length=5)] = Field(
        default_factory=list[ComponentMediaItem]
    )
    #: ISO country codes implied by linked services; never an exclusivity claim.
    country_codes: Annotated[list[CountryCode], Field(max_length=249)] = Field(
        default_factory=list[CountryCode]
    )
    services: Annotated[list[ExternalProductSummary], Field(max_length=32)] = Field(
        default_factory=list[ExternalProductSummary]
    )


class SetupDetail(BaseModel):
    """Exact read of one public setup and the versions it offers."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    summary: SetupSummary
    versions: Annotated[list[VersionListEntry], Field(min_length=1)]
    #: ISO country codes implied by linked services; never an exclusivity claim.
    country_codes: Annotated[list[CountryCode], Field(max_length=249)] = Field(
        default_factory=list[CountryCode]
    )
    services: Annotated[list[ExternalProductSummary], Field(max_length=32)] = Field(
        default_factory=list[ExternalProductSummary]
    )
    #: Per-member checks of the latest version. On the detail read only: this
    #: list used to sit inside `summary.latest_checks`, which is also the card
    #: `registry search` returns, and every released client refused a card
    #: carrying a name it did not know.
    component_checks: Annotated[list[SetupComponentChecks], Field(max_length=500)]


def _require_published(visibility: str) -> None:
    """Refuse a passport that is not published.

    The passport models are shared with the local registry, where `visibility`
    is `private` by default and legitimately so. On an anonymous public route
    that default is a disclosure channel: a mis-scoped query returns a private
    passport carrying the source repository, the exact commit and subpath, the
    names of required environment variables, external endpoints and the owner
    id, and nothing marks it as something the caller should never have seen.
    The contract cannot fix the server's authorization, but it can refuse to
    represent the mistake.
    """
    if visibility != "public":
        raise ValueError(f"the public catalog cannot represent a {visibility!r} passport")


class ComponentVersionResponse(BaseModel):
    """Exact read of one immutable component version.

    The passport is the description of the version (ADR-0012): there is no
    separate manifest entity. `passport_digest` is served alongside it so the
    client can verify the bytes it cached independently of the transport.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    passport: ComponentVersionPassport
    passport_digest: PassportDigest
    lifecycle: PublicLifecycle
    trust: CatalogTrust
    support: CatalogSupport
    published_at: Timestamp
    checks: SafetyChecksSummary | None = None
    #: Public usage aggregate; omitted when the feature is disabled.
    usage_metrics: CatalogUsageMetrics | None = None

    @model_validator(mode="after")
    def _passport_is_published(self) -> "ComponentVersionResponse":
        _require_published(self.passport.visibility)
        return self


class SetupVersionResponse(BaseModel):
    """Exact read of one immutable setup version."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    passport: SetupVersionPassport
    passport_digest: PassportDigest
    lifecycle: PublicLifecycle
    trust: CatalogTrust
    support: CatalogSupport
    published_at: Timestamp
    checks: SafetyChecksSummary | None = None
    #: Per-member checks of this exact version. Beside `checks` rather than
    #: inside it: `SafetyChecksSummary` is also the card `registry search`
    #: returns, and a name added there is refused by every released client.
    component_checks: Annotated[list[SetupComponentChecks], Field(max_length=500)]
    #: Public usage aggregate; omitted when the feature is disabled.
    usage_metrics: CatalogUsageMetrics | None = None

    @model_validator(mode="after")
    def _passport_is_published(self) -> "SetupVersionResponse":
        _require_published(self.passport.visibility)
        return self


class SetupContextBudgetQuery(BaseModel):
    """Optional estimator choice for one exact setup context budget."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    estimator_profile: Literal["ai-stp:utf8-bytes/1", "ai-stp:unicode-chars-div4/1"] = (
        "ai-stp:unicode-chars-div4/1"
    )


class SetupContextBudget(BaseModel):
    """Absolute context estimate of one visible exact setup (SPEC-049)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    coordinate: ExactCoordinate
    estimator: TokenEstimator
    always_tokens: Annotated[int, Field(ge=0)]
    conditional_tokens: Annotated[int, Field(ge=0)]
    total_tokens: Annotated[int, Field(ge=0)]
    unavailable_components: Annotated[int, Field(ge=0)]
    status: Literal["ready", "unavailable", "invalid_graph"]
    components: list[ComponentTokenMeasurement]


class ComponentContextBudget(BaseModel):
    """Context estimate of one visible exact component (SPEC-049)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    coordinate: ExactCoordinate
    estimator: TokenEstimator
    component_type: str
    loading: Literal["always", "conditional"] | None = None
    tokens: Annotated[int, Field(ge=0)] | None = None
    utf8_bytes: Annotated[int, Field(ge=0)] | None = None
    status: Literal["exact", "estimated", "unavailable", "not_applicable"]
    reason: str | None = None
