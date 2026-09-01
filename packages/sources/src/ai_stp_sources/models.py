"""SourceIntent and SourceSnapshot (SPEC-057 REQ-5701)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.ids import stable_id_pattern
from ai_stp_foundation.versioning import VERSION_PATTERN

SourceKind = Literal["catalog", "git", "package", "path"]
PackageEcosystem = Literal["npm", "pypi", "crates.io", "go", "pub.dev"]


class CatalogIntent(BaseModel):
    """Exact catalog identity. Trust is not asserted here."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["catalog"] = "catalog"
    stable_id: Annotated[str, Field(pattern=stable_id_pattern("component"))]
    version: Annotated[str, Field(pattern=VERSION_PATTERN)]
    passport_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    variant_id: Annotated[str, Field(pattern=stable_id_pattern("variant"))] | None = None


class GitIntent(BaseModel):
    """GitHub repository, authoring ref, and component subpath."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["git"] = "git"
    repository_url: Annotated[str, Field(min_length=1, max_length=512)]
    tracked_ref: Annotated[str, Field(min_length=1, max_length=256)]
    subpath: Annotated[str, Field(min_length=1, max_length=512)]


class PackageIntent(BaseModel):
    """Allowlisted ecosystem, package name, and exact version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["package"] = "package"
    ecosystem: PackageEcosystem
    name: Annotated[str, Field(min_length=1, max_length=256)]
    version: Annotated[str, Field(min_length=1, max_length=256)]
    filename: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    platform: Annotated[str, Field(min_length=1, max_length=64)] | None = None


class PathIntent(BaseModel):
    """Bounded local path relative to a confirmed root."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["path"] = "path"
    relative_path: Annotated[str, Field(min_length=1, max_length=512)]


type SourceIntent = CatalogIntent | GitIntent | PackageIntent | PathIntent


class NpmEvidence(BaseModel):
    """npm registry observation: tarball, scripts, and lock or declared deps."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ecosystem: Literal["npm"] = "npm"
    integrity: str | None = None
    entry_point: str | None = None
    lifecycle_scripts: dict[str, str] = Field(default_factory=dict)
    repository: str | None = None
    lockfile_name: str | None = None
    declared_dependencies: dict[str, str] = Field(default_factory=dict)


class PypiEvidence(BaseModel):
    """PyPI observation: one chosen distribution file and digest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ecosystem: Literal["pypi"] = "pypi"
    filename: Annotated[str, Field(min_length=1, max_length=256)]
    platform: Annotated[str, Field(min_length=1, max_length=64)]
    registry_sha256: Annotated[str, Field(min_length=64, max_length=64)]
    requires_dist: tuple[str, ...] = ()


class CratesEvidence(BaseModel):
    """crates.io observation: crate checksum and Cargo.lock or resolved graph."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ecosystem: Literal["crates.io"] = "crates.io"
    registry_checksum: Annotated[str, Field(min_length=64, max_length=64)]
    lockfile_name: str | None = None
    resolved_graph: dict[str, str] = Field(default_factory=dict)


class GoEvidence(BaseModel):
    """Go module observation: proxy zip hash and sumdb checksum."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ecosystem: Literal["go"] = "go"
    module: Annotated[str, Field(min_length=1, max_length=256)]
    zip_hash: Annotated[str, Field(min_length=1, max_length=128)]
    sumdb_hash: Annotated[str, Field(min_length=1, max_length=128)]


class PubEvidence(BaseModel):
    """pub.dev observation: archive checksum and pubspec.lock or resolved graph."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ecosystem: Literal["pub.dev"] = "pub.dev"
    registry_sha256: Annotated[str, Field(min_length=64, max_length=64)]
    lockfile_name: str | None = None
    resolved_graph: dict[str, str] = Field(default_factory=dict)


type PackageEvidence = NpmEvidence | PypiEvidence | CratesEvidence | GoEvidence | PubEvidence


class SourceSnapshot(BaseModel):
    """Exact resolved source. Verification axes stay false (ADR-0083)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: SourceKind
    canonical_coordinate: Annotated[str, Field(min_length=1, max_length=1024)]
    exact_identity: Annotated[str, Field(min_length=1, max_length=256)]
    archive_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)] | None = None
    component_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)] | None = None
    subpath: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    repository_url: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    github_owner: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    github_name: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    github_repo_id: int | None = None
    observed_license: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    files: dict[str, bytes] = Field(default_factory=dict)
    package_evidence: PackageEvidence | None = None
    fetched_at: datetime | None = None
    author_verified: Literal[False] = False
    component_verified: Literal[False] = False
    target_write: Literal[False] = False

    @model_validator(mode="after")
    def _axes_stay_false(self) -> SourceSnapshot:
        if self.author_verified or self.component_verified or self.target_write:
            raise ValueError("source snapshots never grant verification or target-write")
        return self
