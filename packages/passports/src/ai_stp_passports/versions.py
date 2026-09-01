"""Component and setup version passports (docs/contracts/component-setup-passports.md).

Immutable snapshots extending the passport envelope with version identity:
exact source and artifact, closed component taxonomy, split dependencies,
declared access needs, conflicts, permissions and license. A setup belongs
to exactly one harness and has no variant axis (ADR-0014) — the model
rejects a ``variant_id`` even through the preserved-fields channel.

Mutable lifecycle state (deprecated/blocked/hidden) deliberately lives
outside these hashed bytes per SPEC-005: it never changes the snapshot.
"""

import re
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_foundation.ids import stable_id_pattern
from ai_stp_foundation.refs import ComponentRef, SetupRef, Version
from ai_stp_passports.envelope import PassportEnvelope
from ai_stp_passports.markdown import validate_safe_markdown

# Tag IDs follow the vocabulary form (docs/contracts/tag-vocabulary.md);
# 1..8 tags per version (ADR-0024).
TAG_PATTERN: Final[str] = r"^[a-z0-9]+(-[a-z0-9]+)*$"
MAX_TAGS: Final[int] = 8

# Capabilities come from the closed dotted dictionary (component-setup-passports.md).
CAPABILITY_PATTERN: Final[str] = r"^[a-z0-9]+(\.[a-z0-9-]+)+$"

ENV_NAME_PATTERN: Final[str] = r"^[A-Z][A-Z0-9_]*$"
COMMIT_PATTERN: Final[str] = r"^[0-9a-f]{40}$"

type TagId = Annotated[str, Field(pattern=TAG_PATTERN)]
type CapabilityId = Annotated[str, Field(pattern=CAPABILITY_PATTERN)]
type SupportedOs = Literal["linux", "macos", "windows"]

#: The closed component taxonomy (AGENTS.md, "Canonical terms"). Named so
#: the catalog wire contract reuses this one owner instead of restating the
#: eight values, which would be two normative copies free to drift apart.
type ComponentType = Literal[
    "instruction", "skill", "mcp", "hook", "command", "agent", "plugin", "setting"
]

#: How a component is packaged natively for its harness. `marketplace` is a
#: packaging projection, never a component kind (ADR-0015).
type ProjectionKind = Literal["marketplace", "plugin", "native_files", "package"]

_TRAVERSAL_RE: Final[re.Pattern[str]] = re.compile(r"(^|/)\.\.(/|$)")


def _relative_path(value: str) -> str:
    if not value or value.startswith("/") or _TRAVERSAL_RE.search(value):
        raise ValueError(f"path must be relative without traversal: {value!r}")
    return value


class GitSource(BaseModel):
    """Exact public origin: repository, commit and component root subpath."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    repository: Annotated[str, Field(pattern=r"^https://[^\s]+$")]
    commit: Annotated[str, Field(pattern=COMMIT_PATTERN)]
    path: str

    @model_validator(mode="after")
    def _safe_path(self) -> "GitSource":
        _relative_path(self.path)
        return self


class ArtifactRef(BaseModel):
    """Content-addressed artifact bytes: digest and size."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    size_bytes: Annotated[int, Field(ge=0)]


class EnvVarRequirement(BaseModel):
    """Required environment variable: name and purpose, never a value."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Annotated[str, Field(pattern=ENV_NAME_PATTERN)]
    purpose: str


class Permissions(BaseModel):
    """Declared file, network and process permissions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    filesystem: list[str] = Field(default_factory=list)
    network: list[str] = Field(default_factory=list)
    process: list[str] = Field(default_factory=list)


class Conflicts(BaseModel):
    """Declared conflicts by native surface."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    paths: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    hooks: list[str] = Field(default_factory=list)
    mcp: list[str] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=list)
    plugins: list[str] = Field(default_factory=list)


class LicenseInfo(BaseModel):
    """License identity and the redistribution decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    spdx_id: str
    redistribution_allowed: bool


class _VersionPassportBase(PassportEnvelope):
    """Shared identity fields of immutable version passports."""

    name: str
    description: str
    version: Version
    tags: Annotated[list[TagId], Field(min_length=1, max_length=MAX_TAGS)]
    source: GitSource | None = None
    artifact: ArtifactRef
    harness_id: HarnessId
    required_env: list[EnvVarRequirement] = Field(default_factory=list[EnvVarRequirement])
    requires_credentials: bool = False
    requires_authorization: Literal["none", "user_account", "external_service"] = "none"
    permissions: Permissions = Field(default_factory=Permissions)
    external_endpoints: list[Annotated[str, Field(pattern=r"^https://[^\s]+$")]] = Field(
        default_factory=list
    )
    license: LicenseInfo
    compatibility_evidence_refs: list[str] = Field(default_factory=list)

    @field_validator("description")
    @classmethod
    def _safe_description(cls, value: str) -> str:
        return validate_safe_markdown(value)

    @model_validator(mode="after")
    def _immutable_snapshot(self) -> "_VersionPassportBase":
        if self.parent_revision_ids:
            raise ValueError("an immutable version snapshot has no parent revisions")
        return self


class ComponentVersionPassport(_VersionPassportBase):
    """Immutable component version passport."""

    # Narrowing the envelope kind to one literal is safe on a frozen model.
    kind: Literal["component"] = "component"  # pyright: ignore[reportIncompatibleVariableOverride]
    component_type: ComponentType
    projection_kind: ProjectionKind
    variant_id: Annotated[str, Field(pattern=stable_id_pattern("variant"))] | None = None
    provides_capabilities: list[CapabilityId] = Field(default_factory=list)
    requires_components: list[ComponentRef] = Field(default_factory=list[ComponentRef])
    requires_capabilities: list[CapabilityId] = Field(default_factory=list)
    conflicts: Conflicts = Field(default_factory=Conflicts)
    managed_paths: list[str] = Field(default_factory=list)
    native_ids: list[str] = Field(default_factory=list)
    #: Additional harnesses this version names. Empty means only `harness_id`.
    harness_ids: Annotated[list[HarnessId], Field(max_length=7)] = Field(
        default_factory=list[HarnessId]
    )
    supported_os: list[SupportedOs] = Field(default_factory=list[SupportedOs])

    @model_validator(mode="after")
    def _safe_managed_paths(self) -> "ComponentVersionPassport":
        for path in self.managed_paths:
            _relative_path(path)
        if self.harness_ids and self.harness_id not in self.harness_ids:
            raise ValueError("harness_ids must include harness_id")
        return self


class SetupVersionPassport(_VersionPassportBase):
    """Immutable setup version passport with one native harness and projections."""

    # Narrowing the envelope kind to one literal is safe on a frozen model.
    kind: Literal["setup"] = "setup"  # pyright: ignore[reportIncompatibleVariableOverride]
    purpose: str
    #: Optional, and `ADR-0130` says why: a role is a claim about content that no
    #: vendor page can source, so a required field forced whoever imported a
    #: setup to invent one. Three of the four places that fill it already put
    #: something that is not a role there.
    target_role: str | None = None
    #: The published axis the setups of one harness differ along — `minimal`,
    #: `baseline`, `full-auto`, `nddev-builder` — taken from `setup.json`'s own
    #: `"id"`. `None` for a setup that has no such axis: a locally discovered
    #: one, or a conformance bundle.
    #:
    #: **`full-auto` here is not `execution_profile` below.** One word, two
    #: independent axes: a posture is a statement about how much the harness
    #: configuration asks and sandboxes, and the execution profile is about how
    #: this CLI runs. Reading either as the other is the mistake `AGENTS.md`
    #: names about the three automation axes.
    posture: str | None = None
    supported_tasks: list[str] = Field(default_factory=list)
    #: May be empty, and that is a composition rather than an absence. A setup
    #: declaring no components is a harness managed with declared-empty content:
    #: installing it projects nothing and leaves the target *managed*, so a file
    #: appearing later is drift. Removal leaves the target unmanaged and watches
    #: nothing, which is a different state and keeps its own verb.
    #:
    #: The bound used to be one, stated in this field and in no normative
    #: document — the kind of rule that is only discovered by being hit. See
    #: `ADR-0124` and `REQ-630`.
    components: list[ComponentRef]
    ported_from: SetupRef | None = None
    related_setup_ids: list[Annotated[str, Field(pattern=stable_id_pattern("setup"))]] = Field(
        default_factory=list
    )
    execution_profile: Literal["full-auto"] = "full-auto"
    supported_harness_versions: list[str] = Field(default_factory=list)
    #: Windows is here because refusing it in the type was the wrong place for
    #: the refusal. Whether a target can actually be written is a fact about the
    #: provider, and `install` already reads that: it compares this machine's
    #: operating system against the provider's declared `supported_os` and
    #: refuses there, by name, with the provider as the reason. A vocabulary
    #: that pre-judged it made a setup unable to *say* what it supports, which
    #: is a different and worse thing than being unable to install it.
    supported_os: list[SupportedOs] = Field(default_factory=list[SupportedOs])
    supported_arch: list[Literal["x86_64", "arm64"]] = Field(
        default_factory=list[Literal["x86_64", "arm64"]]
    )
    composition_report_ref: str | None = None
    conversion_report_ref: str | None = None
    install_evidence_ref: str | None = None
    launch_evidence_ref: str | None = None

    @model_validator(mode="after")
    def _no_variant_axis(self) -> "SetupVersionPassport":
        extras = self.model_extra or {}
        if "variant_id" in extras:
            raise ValueError("a setup has no variant axis (ADR-0014)")
        return self
