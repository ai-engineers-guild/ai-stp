"""Local components: passports, quality, native discovery, source search,
scaffolds, consent, recorded versions and Skill packages.
"""

from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from ai_stp_contracts.auth import AccountId
from ai_stp_contracts.http import Timestamp, open_wire_object
from ai_stp_contracts.model import ContractModel
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_passports.versions import ComponentType


class PassportView(ContractModel):
    """One local passport at its current head.

    A view, not the passport itself: the envelope and its facts are owned by
    `packages/passports` and `passport-envelope.md`. What this adds is the local
    position — which revision is current, and what it descends from — because an
    agent deciding whether to write needs to know what it would be writing on
    top of.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    #: Every passport kind, matching `ai_stp_passports.envelope.PassportKind`.
    #: One view rather than one per kind: they are the same shape — an identity,
    #: a position in a revision chain, and facts — and separate models would be
    #: the same fields maintained five times. The set is the *whole* set on
    #: purpose; a subset of it silently rejects a passport the envelope accepts,
    #: which is a failure this has already had twice.
    kind: Literal["developer", "device", "project", "component", "setup"]
    stable_id: Annotated[str, Field(min_length=1)]
    revision_id: Annotated[str, Field(min_length=1)]
    parent_revision_ids: list[str]
    created_at: Timestamp

    #: The owner as this installation records it. Before sign-in that is a
    #: locally minted identifier and not an account the platform knows
    #: (`ADR-0060`); `#75` transfers ownership as an ordinary revision.
    owner_id: AccountId

    #: Facts at this revision, exactly as the envelope holds them.
    facts: dict[str, JsonValue]


class ComponentPassportValidation(ContractModel):
    """Whether one local component head is complete enough to publish.

    This is a local structural verdict, not permission to write to the cloud.
    Publication still requires its own authenticated exact plan after the
    platform contract exists.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    revision_id: Annotated[str, Field(min_length=1)]
    for_publication: Literal[True] = True
    ready: bool
    missing_fields: list[str]
    invalid_fields: list[str]


class ComponentQualityCheck(ContractModel):
    """One deterministic authoring hint, never a verification result."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    code: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")]
    status: Literal["passed", "hint"]
    fields: list[Annotated[str, Field(min_length=1, max_length=64)]] = []
    message: Annotated[str, Field(min_length=1, max_length=240)]


class ComponentQualityDimension(ContractModel):
    """Mechanical checks grouped under one author-facing quality dimension."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    dimension: Literal["safety", "clarity", "reusability", "completeness", "actionability"]
    status: Literal["passed", "hint"]
    checks: Annotated[list[ComponentQualityCheck], Field(min_length=1)]

    @model_validator(mode="after")
    def status_matches_checks(self) -> Self:
        expected = "passed" if all(item.status == "passed" for item in self.checks) else "hint"
        if self.status != expected:
            raise ValueError("quality dimension status disagrees with its checks")
        if len({item.code for item in self.checks}) != len(self.checks):
            raise ValueError("quality check codes must be unique within a dimension")
        return self


class ComponentQualityReport(ContractModel):
    """Optional mechanical guidance separated from trust and publication readiness."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    profile_version: Literal["mechanical/1"] = "mechanical/1"
    stable_id: Annotated[str, Field(min_length=1)]
    revision_id: Annotated[str, Field(min_length=1)]
    component_type: ComponentType
    informational_only: Literal[True] = True
    affects_publication_readiness: Literal[False] = False
    affects_component_verified: Literal[False] = False
    affects_trust_lane: Literal[False] = False
    dimensions: Annotated[list[ComponentQualityDimension], Field(min_length=5, max_length=5)]

    @model_validator(mode="after")
    def all_dimensions_are_present_once(self) -> Self:
        expected = {"safety", "clarity", "reusability", "completeness", "actionability"}
        if {item.dimension for item in self.dimensions} != expected:
            raise ValueError("quality report must contain every dimension exactly once")
        return self


class ComponentPassportSuggestion(ContractModel):
    """One exact fact copied from named immutable evidence, awaiting confirmation."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    field: Annotated[str, Field(min_length=1, max_length=64)]
    value: JsonValue
    source_refs: Annotated[list[str], Field(min_length=1, max_length=8)]
    requires_confirmation: Literal[True] = True


class ComponentPassportSuggestions(ContractModel):
    """Read-only enrichment candidates for one exact component revision."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    revision_id: Annotated[str, Field(min_length=1)]
    suggestions: list[ComponentPassportSuggestion]
    unresolved_fields: list[str]


class NativeComponentProvenance(ContractModel):
    """Allowlisted origin evidence for one native discovery candidate."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    kind: Literal["filesystem", "github", "package"]
    state: Literal["local", "exact", "observed"]
    repository: (
        Annotated[
            str,
            Field(pattern=r"^https://github\.com/[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9_.-]+$"),
        ]
        | None
    ) = None
    revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")] | None = None
    subpath: Annotated[str, Field(min_length=1)] | None = None
    package_name: Annotated[str, Field(min_length=1)] | None = None
    package_version: Annotated[str, Field(min_length=1)] | None = None
    digest: Annotated[str, Field(pattern=r"^(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})$")] | None = (
        None
    )
    evidence: list[Annotated[str, Field(min_length=1)]] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_origin(self) -> Self:
        if self.kind == "github":
            if (
                self.state != "exact"
                or self.repository is None
                or not self.repository.startswith("https://github.com/")
                or self.revision is None
            ):
                raise ValueError("GitHub provenance requires an exact repository and revision")
        elif self.kind == "package":
            if (
                self.state != "observed"
                or self.package_name is None
                or any(
                    value is not None for value in (self.repository, self.revision, self.subpath)
                )
            ):
                raise ValueError("package provenance requires observed package identity only")
        elif self.state != "local" or any(
            value is not None
            for value in (
                self.repository,
                self.revision,
                self.subpath,
                self.package_name,
                self.package_version,
                self.digest,
            )
        ):
            raise ValueError("filesystem provenance may contain only local layout evidence")
        return self


class NativeDiscoveryDiagnostic(ContractModel):
    """A safe reason an optional provenance adapter could not classify input."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    code: Literal[
        "missing_manifest",
        "invalid_manifest",
        "unsupported_manifest",
        "invalid_record",
        "missing_source_entry",
        "bounded_limit",
        "unreadable",
    ]
    source: Annotated[str, Field(min_length=1)]
    reason: Annotated[str, Field(min_length=1)]


class ExternalSourceIdentity(ContractModel):
    """A parsed external source intent or separately proven exact identity."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    kind: Literal["published", "github", "github/exact", "local", "collection"]
    canonical: Annotated[str, Field(min_length=1, max_length=2048)]
    owner: str | None = None
    repository: str | None = None
    ref: str | None = None
    subpath: str | None = None
    selector: str | None = None
    local_path: str | None = None
    collection_owner: str | None = None
    collection_handle: str | None = None
    provenance_proven: bool = False


class SourceSearchCandidate(ContractModel):
    """One name-query hit. Source, catalog status, and trust stay separate."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    name: Annotated[str, Field(min_length=1, max_length=256)]
    source: Literal["catalog", "package", "git"]
    exact_coordinate: Annotated[str, Field(min_length=1, max_length=1024)]
    catalog_status: Literal["catalog", "not_in_catalog"]
    trust_lane: Literal["authoritative", "experimental", "local_owner_or_pinned"]
    author_verified: bool
    component_verified: bool
    stable_id: str | None = None


class SourceSearchResult(ContractModel):
    """Name-only discovery. The resolver never selects a candidate."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    query: Annotated[str, Field(min_length=1, max_length=512)]
    registry_discovery: bool
    resolution: Literal["unresolved", "needs_selection", "resolved", "failed"]
    selected: SourceSearchCandidate | None = None
    candidates: list[SourceSearchCandidate]


class ComponentScaffoldView(ContractModel):
    """One safely created component authoring template."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    component_type: ComponentType
    component_name: Annotated[str, Field(min_length=1)]
    output: Annotated[str, Field(min_length=1)]
    byte_length: Annotated[int, Field(gt=0)]


class ComponentTemplateView(ContractModel):
    """A deterministic concrete projection of one authoring template."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    harness_id: HarnessId
    component_name: Annotated[str, Field(min_length=1)]
    component_root: Annotated[str, Field(min_length=1)]
    source_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    rendered_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    placeholders: list[str]
    content: Annotated[str, Field(max_length=65536)]


class NativeComponent(ContractModel):
    """One native component found on this machine (`SPEC-005` REQ-517).

    Reported without its content being read. `holds_secret` is decided from the
    path's *name*: opening a file to learn whether it holds a credential is the
    harm REQ-518 exists to prevent, so the flag says "named as one", never
    "contains one".
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    component_type: ComponentType
    native_role: Literal["mcp_client_config", "mcp_server"] | None = None

    #: `None` for a cross-harness convention such as a project `AGENTS.md`,
    #: which belongs to no single harness.
    harness_id: str | None = None
    scope: Literal["global", "project"]
    candidate_id: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    layout_source: Annotated[str, Field(min_length=1)]
    source_path: Annotated[str, Field(min_length=1)]
    provenance: NativeComponentProvenance
    entry_points: list[Annotated[str, Field(min_length=1)]] = Field(default_factory=list)
    transport_capabilities: list[Literal["stdio", "http"]] = Field(
        default_factory=list[Literal["stdio", "http"]]
    )
    evidence_refs: list[Annotated[str, Field(min_length=1)]] = Field(default_factory=list)

    #: `None` when the entry could not be measured, which includes every
    #: directory. Discovery never opens a file to find out.
    byte_length: int | None = None
    holds_secret: bool = False
    reason: Annotated[str, Field(min_length=1)]

    #: The stable_id this path is already registered as, when the local
    #: registry's `component_source_binding` answers the same key adoption
    #: would record. `None` means unregistered — including when no registry
    #: exists yet. The only join a reader should make; `source_path` is a
    #: display string, not a key.
    registered_stable_id: Annotated[str, Field(min_length=1)] | None = None


class NativeComponents(ContractModel):
    """Everything discovery found, and nothing it changed (`REQ-518`)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1

    #: The explicit project root. When set, discovery does not add global homes.
    project: str | None = None
    complete: bool
    continuation: str | None = None
    components: list[NativeComponent]
    diagnostics: list[NativeDiscoveryDiagnostic] = Field(
        default_factory=list[NativeDiscoveryDiagnostic]
    )


class PathInventoryObject(ContractModel):
    """One logical object in an explicit-root inventory (`SPEC-005` REQ-534)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    object_kind: Literal["component", "setup"]
    relation: Literal["independent", "embedded_member", "generated_projection", "duplicate"]
    origin: Literal["passport", "native"]
    object_id: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    relative_path: Annotated[str, Field(min_length=1, max_length=2048)]
    component_type: ComponentType | None = None
    name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    harness_id: str | None = None
    passport_path: Annotated[str, Field(min_length=1, max_length=2048)] | None = None
    generated_from: Annotated[str, Field(min_length=1, max_length=2048)] | None = None
    stable_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None


class PathInventory(ContractModel):
    """Passport-first inventory of one explicit root. Observation only (`REQ-518`)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    root: Annotated[str, Field(min_length=1)]
    complete: bool
    continuation: str | None = None
    objects: list[PathInventoryObject]
    diagnostics: list[NativeDiscoveryDiagnostic] = Field(
        default_factory=list[NativeDiscoveryDiagnostic]
    )


class ConsentRecord(ContractModel):
    """One durable consent to unverified objects (`unverified-consent.md`).

    `fingerprint` is what the candidate required when the user agreed, and it is
    stored rather than recomputed: the whole mechanism is "does this now need
    more than it did then", which cannot be answered without the older answer.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    consent_id: Annotated[str, Field(min_length=1)]

    #: The `unverified_consent` sync entity this record answers to — derived
    #: from scope and target, so it is identical on every device of the
    #: account. `sync push --id` takes it.
    sync_entity_id: Annotated[str, Field(min_length=1)]

    #: Three forms and no fourth. "Everything unverified, forever" does not
    #: exist: `task` names the authorized full-auto profile, not a wildcard.
    scope: Literal["publisher", "object_major", "task"]
    target: Annotated[str, Field(min_length=1)]
    decided_by: Annotated[str, Field(min_length=1)]
    origin: Annotated[str, Field(min_length=1)]
    created_at: Annotated[str, Field(min_length=1)]
    revoked_at: str | None = None
    fingerprint: dict[str, JsonValue] = {}

    #: The objects the fingerprint was taken from. Empty means the record
    #: observed no shape at all, which is not the same as a shape that needed
    #: nothing, and does not cover anything.
    observed: list[str] = []


class ConsentSummary(ContractModel):
    """Every consent still in force."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    records: list[ConsentRecord]


class RecordedVersion(ContractModel):
    """One immutable `X.Y` version (`SPEC-005` REQ-503, REQ-504).

    The number and the digest travel together because that pairing is the whole
    guarantee: one number stands for one hash, and an exact reference means
    something only while that holds.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    passport_digest: Annotated[str, Field(min_length=1)]
    revision_id: Annotated[str, Field(min_length=1)]
    created_at: Annotated[str, Field(min_length=1)]


class VersionLine(ContractModel):
    """Every recorded version of one object, and what comes next.

    `next_minor` is computed from what is stored rather than remembered, so two
    machines with the same history propose the same number. There is no
    `next_major`: `REQ-507` makes that a decision, and a field offering it would
    read as a suggestion to take it.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    versions: list[RecordedVersion]
    next_minor: Annotated[str, Field(pattern=r"^\d+\.\d+$")]

    #: Set on a fork. Held by the copy, never written on the original.
    forked_from: str | None = None
    forked_from_version: str | None = None

    #: Whether this may be published, and why not when it may not (`REQ-522` to
    #: `REQ-524`). Answered at the fork rather than at publication, so an
    #: unmodified clone is a rule the caller meets early instead of a surprise.
    publishable: bool | None = None
    publish_reason: str | None = None


class SearchHit(ContractModel):
    """One local object a search matched, and the lane it is in (`ADR-0016`)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    revision_id: Annotated[str, Field(min_length=1)]

    #: Three lanes and no fourth. Nothing promotes a candidate between them:
    #: `experimental` never becomes `authoritative`, automatically or by an
    #: agent's decision, and `local_owner_or_pinned` is installable without ever
    #: being displayed as platform-confirmed.
    lane: Literal["authoritative", "local_owner_or_pinned", "experimental"]
    reason: Annotated[str, Field(min_length=1)]
    fields: dict[str, JsonValue] = {}


class LocalSearchResults(ContractModel):
    """What a local search found, one section per trust lane.

    Separate lists rather than one labelled list: `SPEC-006` REQ-603 requires
    the unverified candidates to come back as a *separate section*, and a caller
    rendering a flat list of rows has already lost the distinction it asks for.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    authoritative: list[SearchHit]
    local_owner_or_pinned: list[SearchHit]
    experimental: list[SearchHit]

    #: Why the experimental section holds what it holds. "Nothing matched" and
    #: "nothing was allowed" are different answers and an empty list is both.
    experimental_reason: Annotated[str, Field(min_length=1)]

    #: Whether the result was cut at the bound. Silence here would read as
    #: "that is all there is".
    truncated: bool = False


class SkillPackageFinding(ContractModel):
    """One deviation from the Agent Skills Specification (`#455`)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1

    #: Stable, so a caller branches on the code rather than on the sentence.
    code: Annotated[str, Field(pattern=r"^SK[0-9]{3}$")]
    summary: Annotated[str, Field(min_length=1)]

    #: The field or path it is about. Never empty: a finding nobody can locate
    #: is a finding that has not been reported.
    at: Annotated[str, Field(min_length=1)]


class SkillPackageReport(ContractModel):
    """Whether a directory is a conforming skill package (`#455`).

    Checked against <https://agentskills.io/specification>, which exists
    independently of this estate — which is why `skill` is the kind where a
    validator can be right or wrong about something other than our own opinion.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    path: Annotated[str, Field(min_length=1)]

    #: `skill`, `plugin`, or `unknown`. A plugin under `skills/` is a
    #: well-formed something else, not a skill missing its entry point.
    packaged_as: Literal["skill", "plugin", "unknown"]

    conforms: bool
    findings: list[SkillPackageFinding] = []

    name: str = ""
    description: str = ""

    #: Directories the specification names as conventions, and the ones this
    #: estate adds. Neither list is a defect: the standard permits any content
    #: beyond `SKILL.md`.
    standard_directories: list[str] = []
    extension_directories: list[str] = []
    other_entries: list[str] = []
