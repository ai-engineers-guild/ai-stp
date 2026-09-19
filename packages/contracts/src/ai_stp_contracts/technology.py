"""Technology metadata and detector handoff, separate from canonical relations.

SPEC-081/082 and ADR-0182 own semantics. These contracts introduce no model call,
repository execution, or second project identity.
"""

from __future__ import annotations

import unicodedata
from pathlib import PurePosixPath
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.json_schema import JsonSchemaValue

from ai_stp_contracts.context import OrganizationId, RemoteProjectId
from ai_stp_contracts.corporate import AccountId, ProjectLifecycle
from ai_stp_contracts.http import (
    IdempotencyKey,
    Timestamp,
    open_wire_object,
    strict_request_object,
)
from ai_stp_foundation.ids import stable_id_pattern

TechnologyId = Annotated[str, Field(pattern=stable_id_pattern("technology"))]
TechnologyScanId = Annotated[str, Field(pattern=stable_id_pattern("scan"))]
CategoryId = Annotated[str, Field(pattern=stable_id_pattern("category"))]
RelationId = Annotated[str, Field(pattern=stable_id_pattern("relation"))]
TeamId = Annotated[str, Field(pattern=stable_id_pattern("operation"))]
TechnologyLifecycle = Literal["draft", "active", "deprecated", "archived"]
UsageReview = Literal["proposed", "confirmed", "rejected", "overridden", "retired"]
UsageContext = Literal["production", "development", "testing", "browser_support"]
EvidenceFreshness = Literal["current", "stale", "absent", "unknown"]
MappingVersion = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._+-]+$")]
TechnologySearch = Annotated[str, Field(min_length=1, max_length=200, pattern=r".*\S.*")]

INITIAL_CATEGORY_NAMES = (
    "Language",
    "Library",
    "Framework",
    "Runtime",
    "Browser",
    "Web API and standard",
    "DBMS",
    "Cache and key-value store",
    "Message broker and event platform",
    "Build and bundling tool",
    "Package manager",
    "Package and artifact registry",
    "Test framework",
    "Test runner and browser automation",
    "CI/CD system",
    "Job runner and execution agent",
    "Container and orchestration platform",
    "Operating system",
    "Cloud platform and managed service",
    "Web server and proxy",
    "Infrastructure provisioning and configuration tool",
    "Observability",
    "Identity and security infrastructure",
)
RESERVED_CATEGORY_NAMES = frozenset(
    {
        "harness",
        "setup",
        "component",
        "instruction",
        "mcp",
        "skill",
        "hook",
        "command",
        "agent",
        "plugin",
        "setting",
        "cli",
    }
)


def normalize_technology_name(value: str) -> str:
    """Documented exact-name/alias normalization; punctuation retains meaning."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def safe_reference_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or any(character.isspace() or ord(character) < 32 for character in value)
    ):
        raise ValueError("reference URL must be HTTPS without credentials or query values")
    return value


class TechnologyCategoryMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    name: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(max_length=2000)] = ""

    @field_validator("name")
    @classmethod
    def governed_name(cls, value: str) -> str:
        normalized = normalize_technology_name(value)
        if not normalized or normalized in RESERVED_CATEGORY_NAMES:
            raise ValueError("category is empty or names a harness/component domain kind")
        return value


class TechnologyMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    name: Annotated[str, Field(min_length=1, max_length=200)]
    category_ids: Annotated[list[CategoryId], Field(min_length=1, max_length=32)]
    aliases: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=200)]], Field(max_length=64)
    ] = []
    description: Annotated[str, Field(max_length=4000)] = ""
    icon_url: Annotated[str | None, Field(max_length=2048)] = None
    official_urls: Annotated[
        list[Annotated[str, Field(max_length=2048)]], Field(max_length=16)
    ] = []

    @field_validator("name")
    @classmethod
    def nonempty_name(cls, value: str) -> str:
        if not normalize_technology_name(value):
            raise ValueError("technology name is empty")
        return value

    @field_validator("aliases")
    @classmethod
    def distinct_aliases(cls, values: list[str]) -> list[str]:
        normalized = [normalize_technology_name(value) for value in values]
        if any(not value for value in normalized) or len(set(normalized)) != len(normalized):
            raise ValueError("aliases must be nonempty and distinct after normalization")
        return values

    @field_validator("category_ids")
    @classmethod
    def distinct_categories(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("category references must be distinct")
        return values

    @field_validator("icon_url")
    @classmethod
    def safe_icon(cls, value: str | None) -> str | None:
        return safe_reference_url(value) if value is not None else None

    @field_validator("official_urls")
    @classmethod
    def safe_urls(cls, values: list[str]) -> list[str]:
        return [safe_reference_url(value) for value in values]


class TechnologyEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    source: Literal["manual", "declared", "configured", "observed", "forge_language"]
    path: Annotated[str | None, Field(max_length=1024)] = None
    reference: Annotated[str | None, Field(max_length=256, pattern=r"^[A-Za-z0-9._:/+-]+$")] = None
    observed_at: Timestamp
    source_revision: Annotated[str | None, Field(max_length=128, pattern=r"^[A-Za-z0-9._+-]+$")] = (
        None
    )
    confidence: Annotated[float | None, Field(ge=0, le=1)] = None
    detector_version: MappingVersion | None = None
    mapping_version: MappingVersion | None = None

    @field_validator("path")
    @classmethod
    def safe_relative_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        path = PurePosixPath(value)
        name = path.name.casefold()
        if (
            not value
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in value
            or ":" in value
            or any(ord(character) < 32 for character in value)
            or name.startswith(".env")
            or name.startswith("credentials")
            or name in {"id_rsa", "id_ed25519", "secrets.json", "tokens.json", "token.json"}
            or path.suffix.casefold() in {".pem", ".key", ".p12", ".pfx", ".ovpn"}
        ):
            raise ValueError("evidence path must be a non-secret repository-relative path")
        return value


class TechnologyUsageFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    context: UsageContext
    version: Annotated[str | None, Field(max_length=128)] = None
    version_kind: Literal["unknown", "declared_range", "observed_version"] = "unknown"
    evidence: Annotated[list[TechnologyEvidence], Field(max_length=64)] = []

    @model_validator(mode="after")
    def coherent_version(self) -> TechnologyUsageFact:
        if (self.version_kind == "unknown") != (self.version is None):
            raise ValueError("unknown versions have no value; known versions require a value")
        if self.version is not None and not self.version.strip():
            raise ValueError("version must not be empty")
        return self


class TechnologyObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    technology_id: TechnologyId
    fact: TechnologyUsageFact


class TechnologyScanHandoff(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    local_project_id: Annotated[str | None, Field(pattern=stable_id_pattern("project"))] = None
    organization_id: OrganizationId | None = None
    project_id: RemoteProjectId | None = None
    scan_id: Annotated[str, Field(pattern=stable_id_pattern("scan"))]
    scope: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._/-]+$")]
    complete: bool
    detector_version: MappingVersion
    mapping_version: MappingVersion
    observations: Annotated[list[TechnologyObservation], Field(max_length=4096)]

    @model_validator(mode="after")
    def explicit_identity(self) -> TechnologyScanHandoff:
        if (self.organization_id is None) != (self.project_id is None):
            raise ValueError("publication requires both organization and remote project identity")
        if self.project_id is None and self.local_project_id is None:
            raise ValueError("offline scans require a local project identity")
        return self


class TechnologyView(TechnologyMetadata):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    technology_id: TechnologyId
    owner_account_id: AccountId | None = None
    lifecycle: TechnologyLifecycle
    restore_lifecycle: Literal["draft", "active", "deprecated"] = "draft"
    revision: Annotated[int, Field(ge=1)]
    redirect_id: TechnologyId | None = None
    provenance: Annotated[str, Field(max_length=256)]


class TechnologyMutation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    authorization_revision: (
        Annotated[int, Field(ge=1)]
        | Annotated[
            str,
            Field(
                min_length=1,
                max_length=128,
                pattern=r"^corporate:organization_[A-Za-z0-9_-]+:[1-9][0-9]*:[1-9][0-9]*$",
            ),
        ]
    )
    expected_revision: Annotated[int, Field(ge=0)]
    idempotency_key: IdempotencyKey


class TechnologyWriteRequest(TechnologyMutation):
    metadata: TechnologyMetadata


class TechnologyMappingEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    kind: Literal["package", "image", "executable", "configuration", "alias"]
    coordinate: Annotated[
        str, Field(min_length=1, max_length=512, pattern=r"^[A-Za-z0-9._:/@+*-]+$")
    ]
    technology_id: TechnologyId
    provenance: Annotated[str, Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9._:/+-]+$")]

    @field_validator("coordinate")
    @classmethod
    def no_credentials(cls, value: str) -> str:
        if "://" in value and urlsplit(value).username is not None:
            raise ValueError("mapping coordinates must not contain credentials")
        return value


class TechnologyMappingRequest(TechnologyMutation):
    expected_revision: Annotated[int, Field(ge=0, le=0)] = 0
    entries: Annotated[list[TechnologyMappingEntry], Field(min_length=1, max_length=4096)]

    @field_validator("entries")
    @classmethod
    def distinct_entries(cls, values: list[TechnologyMappingEntry]) -> list[TechnologyMappingEntry]:
        keys = [(value.kind, value.coordinate, value.technology_id) for value in values]
        if len(keys) != len(set(keys)):
            raise ValueError("mapping entries must be distinct")
        return values


class TechnologyMappingView(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    organization_id: OrganizationId
    version: MappingVersion
    entries: list[TechnologyMappingEntry]
    digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


class TechnologyScanRequest(TechnologyMutation):
    handoff: TechnologyScanHandoff


class CategoryWriteRequest(TechnologyMutation):
    metadata: TechnologyCategoryMetadata


class TechnologySeedRequest(TechnologyMutation):
    expected_revision: Annotated[int, Field(ge=0, le=0)] = 0
    seed_version: Literal[1] = 1


class TechnologyLandscapePolicyRequest(TechnologyMutation):
    inactivity_months: Annotated[int, Field(ge=1, le=120)]


class TechnologyMergeRequest(TechnologyMutation):
    target_id: TechnologyId
    target_expected_revision: Annotated[int, Field(ge=1)]
    plan_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


class TechnologyMergePlanQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    target_id: TechnologyId


class TechnologyMergePlanView(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    organization_id: OrganizationId
    source: TechnologyView
    target: TechnologyView
    affected_project_count: Annotated[int, Field(ge=0)]
    affected_team_count: Annotated[int, Field(ge=0)]
    digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


class TechnologyMergeProjectEffect(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    project_id: RemoteProjectId
    source_relation_id: RelationId
    target_relation_id: RelationId
    target_action: Literal["create", "update"]


class TechnologyMergeTeamEffect(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    team_id: TeamId
    source_relation_id: RelationId
    target_relation_id: RelationId
    target_action: Literal["create", "update"]


class TechnologyMergeResult(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    source: TechnologyView
    target: TechnologyView
    project_effects: list[TechnologyMergeProjectEffect]
    team_effects: list[TechnologyMergeTeamEffect]


class TechnologyLandscapePolicyView(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    organization_id: OrganizationId
    inactivity_months: Annotated[int, Field(ge=1, le=120)]
    revision: Annotated[int, Field(ge=0)]


class ProjectActivityRequest(TechnologyMutation):
    repository_activity_at: Timestamp | None
    activity_override: Literal["active", "inactive"] | None
    source_availability: Literal["unknown", "available", "unavailable"] | None = None


def _source_availability_wire_object(schema: JsonSchemaValue) -> None:
    open_wire_object(schema)
    schema["required"] = [name for name in schema["required"] if name != "source_availability"]


class ProjectActivityView(BaseModel):
    model_config = ConfigDict(
        extra="allow", frozen=True, json_schema_extra=_source_availability_wire_object
    )
    project_id: RemoteProjectId
    organization_id: OrganizationId
    repository_activity_at: Timestamp | None
    activity_override: Literal["active", "inactive"] | None
    source_availability: Literal["unknown", "available", "unavailable"] | None = None
    revision: Annotated[int, Field(ge=1)]


class TechnologySeedResult(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    seed_version: Literal[1] = 1
    created_category_ids: list[CategoryId]
    retained_category_ids: list[CategoryId]
    created_technology_ids: list[TechnologyId]
    retained_technology_ids: list[TechnologyId]


class TechnologyLifecycleRequest(TechnologyMutation):
    lifecycle: TechnologyLifecycle


class TechnologyDecisionRequest(TechnologyMutation):
    lead_account_id: AccountId | None = None
    approved: bool
    adoption: Literal["none", "assess", "trial", "adopt", "hold"]


class ProjectTechnologyWriteRequest(TechnologyMutation):
    technology_id: TechnologyId
    fact: TechnologyUsageFact
    review: UsageReview = "confirmed"
    state: Literal["current", "retired"] = "current"


class ProjectTeamWriteRequest(TechnologyMutation):
    team_id: TeamId
    role: Literal["owner", "responsible", "contributor"]
    state: Literal["current", "retired"] = "current"
    replace_owner_relation_id: RelationId | None = None
    replace_owner_expected_revision: Annotated[int | None, Field(ge=1)] = None

    @model_validator(mode="after")
    def coherent_owner_replacement(self) -> ProjectTeamWriteRequest:
        if (self.replace_owner_relation_id is None) != (
            self.replace_owner_expected_revision is None
        ):
            raise ValueError("owner replacement requires identity and revision")
        if self.replace_owner_relation_id is not None and (
            self.role != "owner" or self.state != "current"
        ):
            raise ValueError("only a current owner assignment can replace an owner")
        return self


class TechnologyTeamWriteRequest(TechnologyMutation):
    team_id: TeamId
    state: Literal["current", "retired"] = "current"


class CategoryLifecycleRequest(TechnologyMutation):
    target: Literal["active", "archived"]


def _category_wire_object(schema: JsonSchemaValue) -> None:
    open_wire_object(schema)
    # ADR-0184: older snapshots do not assert a category state.
    schema["required"] = [name for name in schema["required"] if name != "state"]


class CategoryView(TechnologyCategoryMetadata):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=_category_wire_object)
    category_id: CategoryId
    revision: Annotated[int, Field(ge=1)]
    provenance: str
    state: Literal["active", "archived"] | None = None


class CategoryList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    items: list[CategoryView]


class TechnologyList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    items: list[TechnologyView]
    total: Annotated[int, Field(ge=0)]


class TechnologyListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    include_archived: bool = False
    query: TechnologySearch | None = None
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=256)] = 128


class UsageFactView(TechnologyUsageFact):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    review: UsageReview
    freshness: EvidenceFreshness


class ProjectTechnologyView(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    organization_id: OrganizationId
    relation_id: RelationId
    project_id: RemoteProjectId
    technology_id: TechnologyId
    state: Literal["current", "retired"]
    revision: Annotated[int, Field(ge=1)]
    facts: list[UsageFactView]


class ProjectTechnologyList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    items: list[ProjectTechnologyView]
    total: Annotated[int, Field(ge=0)] = 0


class TechnologyScanResult(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    organization_id: OrganizationId
    project_id: RemoteProjectId
    scan_id: Annotated[str, Field(pattern=stable_id_pattern("scan"))]
    project_revision: Annotated[int, Field(ge=1)]
    digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    usages: list[ProjectTechnologyView]
    disagreements: list[TechnologyObservation]
    created_relation_ids: list[RelationId]


class TechnologyScanView(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    handoff: TechnologyScanHandoff
    result: TechnologyScanResult


class ProjectTeamView(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    organization_id: OrganizationId
    relation_id: RelationId
    project_id: RemoteProjectId
    team_id: TeamId
    role: Literal["owner", "responsible", "contributor"]
    state: Literal["current", "retired"]
    revision: Annotated[int, Field(ge=1)]


class ProjectTeamList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    items: list[ProjectTeamView]
    total: Annotated[int, Field(ge=0)] = 0


class TechnologyTeamView(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    organization_id: OrganizationId
    relation_id: RelationId
    technology_id: TechnologyId
    team_id: TeamId
    state: Literal["current", "retired"]
    revision: Annotated[int, Field(ge=1)]


class TechnologyTeamList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    items: list[TechnologyTeamView]
    total: Annotated[int, Field(ge=0)] = 0


class EmployeeTechnologyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    account_id: AccountId
    technology_id: TechnologyId
    state: Literal["current", "retired"] = "current"
    expected_revision: Annotated[int, Field(ge=0)]
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey


class EmployeeTechnologyView(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    relation_id: RelationId
    account_id: AccountId
    technology_id: TechnologyId
    state: Literal["current", "retired"]
    revision: Annotated[int, Field(ge=1)]


class EmployeeTechnologyList(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    items: Annotated[list[EmployeeTechnologyView], Field(max_length=256)]
    total: Annotated[int, Field(ge=0)] = 0


class RelationshipListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    include_history: bool = False
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=256)] = 128


class TechnologyDecisionView(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    technology_id: TechnologyId
    revision: Annotated[int, Field(ge=1)]
    lead_account_id: AccountId | None = None
    approved: bool
    adoption: Literal["none", "assess", "trial", "adopt", "hold"]


class TechnologyLandscapeQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    view: Literal["table", "grouped", "radar", "relationships"] = "table"
    category_id: CategoryId | None = None
    query: TechnologySearch | None = None
    technology_id: TechnologyId | None = None
    project_id: RemoteProjectId | None = None
    team_id: TeamId | None = None
    lifecycle: TechnologyLifecycle | None = None
    project_lifecycle: ProjectLifecycle | None = None
    activity: Literal["active", "inactive", "unknown"] | None = None
    source_availability: Literal["unknown", "available", "unavailable"] | None = None
    adoption: Literal["none", "assess", "trial", "adopt", "hold"] | None = None
    context: UsageContext | None = None
    review: UsageReview | None = None
    freshness: EvidenceFreshness | None = None
    include_history: bool = False
    include_inactive: bool = False
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=256)] = 128
    project_offset: Annotated[int, Field(ge=0)] = 0
    project_limit: Annotated[int, Field(ge=1, le=256)] = 128


class LandscapeProjectView(BaseModel):
    model_config = ConfigDict(
        extra="allow", frozen=True, json_schema_extra=_source_availability_wire_object
    )
    project_id: RemoteProjectId
    name: str
    activity: Literal["active", "inactive", "unknown"]
    source_availability: Literal["unknown", "available", "unavailable"] | None = None
    usage: ProjectTechnologyView


class TechnologyLandscapeRow(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    technology: TechnologyView
    project_count: Annotated[int, Field(ge=0)]
    proposed_project_count: Annotated[int, Field(ge=0)]
    projects: list[LandscapeProjectView]
    decision: TechnologyDecisionView | None = None


class TechnologyLandscapeView(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    organization_id: OrganizationId
    evaluated_at: Timestamp
    inactivity_months: Annotated[int, Field(ge=1, le=120)]
    filters: TechnologyLandscapeQuery
    items: list[TechnologyLandscapeRow]
    total: Annotated[int, Field(ge=0)]
