"""Git-owned Official inventory contract (SPEC-056, ADR-0153)."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_stp_contracts.first_party import OWNER_ID as OFFICIAL_ACCOUNT_ID
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes
from ai_stp_foundation.harnesses import HARNESS_IDS
from ai_stp_foundation.identity import (
    IDENTITY_NORMALIZATION_VERSION,
    OFFICIAL_DISPLAY_NAME,
    OFFICIAL_HANDLE,
    canonical_slug,
    normalize_display_key,
    normalize_handle,
    submitted_display_name,
)
from ai_stp_foundation.ids import stable_id_pattern
from ai_stp_passports.versions import TAG_PATTERN

type SourceKind = Literal["git", "package"]
type ComponentType = Literal[
    "instruction", "skill", "mcp", "hook", "command", "agent", "plugin", "setting"
]
type UpdatePolicy = Literal["daily", "pinned", "disabled"]
type ProjectionKind = Literal["marketplace", "plugin", "native_files", "package"]
type TargetScope = Literal["global", "user_root", "project"]
type ProjectionShape = Literal["file", "tree"]
type PackageEcosystem = Literal["npm", "pypi", "crates.io", "go", "pub.dev"]

_SOURCE_ID_RE = r"^[a-z][a-z0-9-]{0,62}$"
_TRAVERSAL = r"(^|/)\.\.(/|$)"
_TAG_RE = TAG_PATTERN
BASELINE_CANONICAL_NAMES: Final[frozenset[str]] = frozenset(
    {
        "ponytail",
        "caveman",
        "grill-me",
        "context7-mcp",
        "serena-mcp",
        "ai-stp-skill",
    }
)
MANIFEST_DIGEST_DOMAIN: Final[str] = "ai-stp:official-manifest:v1"


class OfficialManifestEntry(BaseModel):
    """One reviewed Official component and its exact public source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: Annotated[str, Field(pattern=_SOURCE_ID_RE)]
    stable_id: Annotated[str, Field(pattern=stable_id_pattern("component"))]
    canonical_name: Annotated[str, Field(min_length=1, max_length=80)]
    display_name_en: Annotated[str, Field(min_length=1, max_length=80)]
    display_name_ru: Annotated[str, Field(min_length=1, max_length=80)]
    component_type: ComponentType
    kind: SourceKind
    enabled: bool
    update_policy: UpdatePolicy
    upstream_project_name: Annotated[str, Field(min_length=1, max_length=200)]
    upstream_maintainer: Annotated[str, Field(min_length=1, max_length=200)]
    reviewed_description: Annotated[str, Field(min_length=1, max_length=8000)]
    reviewed_license: Annotated[str, Field(min_length=1, max_length=64)]
    harness_id: str
    tags: Annotated[tuple[str, ...], Field(min_length=1, max_length=10)]
    target_scope: TargetScope
    projection_root: Annotated[str, Field(min_length=1, max_length=1024)]
    projection_shape: ProjectionShape
    projection_kind: ProjectionKind = "native_files"
    repository_url: Annotated[str, Field(max_length=512)] = ""
    tracked_ref: Annotated[str, Field(max_length=256)] = ""
    component_subpath: Annotated[str, Field(max_length=512)] = ""
    ecosystem: PackageEcosystem | None = None
    package_name: Annotated[str, Field(max_length=256)] | None = None
    package_version: Annotated[str, Field(max_length=256)] | None = None
    package_filename: Annotated[str, Field(max_length=256)] | None = None
    package_platform: Annotated[str, Field(max_length=64)] | None = None

    @field_validator("canonical_name")
    @classmethod
    def canonical_is_normalized_slug(cls, value: str) -> str:
        if canonical_slug(value) != value:
            raise ValueError("canonical_name must already be the unique normalized slug")
        return value

    @field_validator("display_name_en", "display_name_ru")
    @classmethod
    def display_spelling(cls, value: str) -> str:
        return submitted_display_name(value)

    @field_validator("harness_id")
    @classmethod
    def known_harness(cls, value: str) -> str:
        if value not in HARNESS_IDS:
            raise ValueError("harness_id is unknown")
        return value

    @field_validator("tags")
    @classmethod
    def vocabulary_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        import re

        pattern = re.compile(_TAG_RE)
        for tag in value:
            if pattern.fullmatch(tag) is None:
                raise ValueError("tag is not a vocabulary identifier")
        return value

    @field_validator("projection_root")
    @classmethod
    def safe_projection_root(cls, value: str) -> str:
        if value.startswith(("/", "~")) or any(
            part in {"", ".", ".."} for part in value.split("/")
        ):
            raise ValueError("projection_root is unsafe")
        return value

    @field_validator("repository_url")
    @classmethod
    def public_github_url(cls, value: str) -> str:
        if not value:
            return value
        if "://" in value and not value.startswith("https://github.com/"):
            raise ValueError("repository must be a public https://github.com URL")
        if "@" in value or "user:" in value.lower():
            raise ValueError("repository URL must not contain credentials")
        return value

    @model_validator(mode="after")
    def exact_source_present(self) -> OfficialManifestEntry:
        import re

        if self.kind == "git":
            if not self.repository_url or not self.tracked_ref or not self.component_subpath:
                raise ValueError("git entry requires repository, tracked ref, and component root")
            if self.component_subpath.startswith("/") or re.search(
                _TRAVERSAL, self.component_subpath
            ):
                raise ValueError("component subpath is empty or unsafe")
        else:
            if not self.ecosystem or not self.package_name or not self.package_version:
                raise ValueError("package entry requires ecosystem, name, and exact version")
        if self.enabled and self.update_policy == "disabled":
            raise ValueError("an enabled entry cannot use the disabled update policy")
        return self


class OfficialManifest(BaseModel):
    """Complete reviewed Official inventory for one repository revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    identity_normalization_version: Literal["identity-normalization/1"] = (
        IDENTITY_NORMALIZATION_VERSION  # type: ignore[assignment]
    )
    official_account_id: Annotated[str, Field(pattern=stable_id_pattern("account"))]
    official_handle: Annotated[str, Field(min_length=1, max_length=32)]
    official_display_name: Annotated[str, Field(min_length=1, max_length=80)]
    entries: Annotated[tuple[OfficialManifestEntry, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def globally_unique_and_protected(self) -> OfficialManifest:
        if self.official_account_id != OFFICIAL_ACCOUNT_ID:
            raise ValueError("official_account_id is not the seeded Official identity")
        if normalize_handle(self.official_handle) != OFFICIAL_HANDLE:
            raise ValueError("official_handle is not the protected Official handle")
        if normalize_display_key(self.official_display_name) != normalize_display_key(
            OFFICIAL_DISPLAY_NAME
        ):
            raise ValueError("official_display_name is not the protected Official spelling")
        source_ids: set[str] = set()
        stable_ids: set[str] = set()
        canonical: set[str] = set()
        en_names: set[str] = set()
        ru_names: set[str] = set()
        for entry in self.entries:
            if entry.source_id in source_ids:
                raise ValueError(f"duplicate Official source id: {entry.source_id}")
            if entry.stable_id in stable_ids:
                raise ValueError(f"duplicate Official stable id: {entry.stable_id}")
            key = normalize_display_key(entry.canonical_name)
            if key in canonical:
                raise ValueError(f"duplicate canonical name: {entry.canonical_name}")
            en_key = normalize_display_key(entry.display_name_en)
            ru_key = normalize_display_key(entry.display_name_ru)
            if en_key in en_names:
                raise ValueError(f"duplicate EN display name: {entry.display_name_en}")
            if ru_key in ru_names:
                raise ValueError(f"duplicate RU display name: {entry.display_name_ru}")
            source_ids.add(entry.source_id)
            stable_ids.add(entry.stable_id)
            canonical.add(key)
            en_names.add(en_key)
            ru_names.add(ru_key)
        present = {normalize_display_key(entry.canonical_name) for entry in self.entries}
        missing = BASELINE_CANONICAL_NAMES - present
        if missing:
            raise ValueError(f"manifest is missing required baseline entries: {sorted(missing)}")
        return self

    def digest(self) -> str:
        payload = self.model_dump(mode="json")
        return digest_bytes(MANIFEST_DIGEST_DOMAIN, canonize(payload))  # type: ignore[arg-type]


def load_official_manifest() -> OfficialManifest:
    """Load the checked-in Official inventory."""
    raw = (
        files("ai_stp_contracts").joinpath("official", "manifest.json").read_text(encoding="utf-8")
    )
    payload: JsonValue = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("official manifest must be an object")
    return OfficialManifest.model_validate(payload)
