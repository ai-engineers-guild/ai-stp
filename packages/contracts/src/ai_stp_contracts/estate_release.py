"""Immutable estate release record (`docs/contracts/estate-release.md`)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_stp_contracts.http import Timestamp
from ai_stp_foundation.digests import DIGEST_PATTERN

SCHEMA_ID = "ai-stp-estate-release/1"
SOFTWARE_SLICE = "software"
LAUNCH_SLICE = "launch"
_FLOATING = frozenset({"latest", "main", "master", "head"})
REQUIRED_LEGS: tuple[tuple[str, str], ...] = (
    ("linux", "x86_64"),
    ("linux", "arm64"),
    ("macos", "x86_64"),
    ("macos", "arm64"),
    ("windows", "x86_64"),
    ("windows", "arm64"),
)
REQUIRED_PROVIDERS: tuple[str, ...] = (
    "github.com/NDDev-OpenNetwork/claude-setup-system",
    "github.com/NDDev-OpenNetwork/codex-setup-system",
    "github.com/NDDev-OpenNetwork/cursor-setup-system",
    "github.com/NDDev-OpenNetwork/grok-setup-system",
    "github.com/NDDev-OpenNetwork/pi-setup-system",
    "github.com/NDDev-OpenNetwork/opencode-setup-system",
    "github.com/NDDev-OpenNetwork/antigravity-setup-system",
)


class EstateConsumer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    repository: Annotated[str, Field(min_length=1)]
    commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    tag: str = ""
    release_url: str = ""


class EstateDistribution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(min_length=1)]
    filename: Annotated[str, Field(min_length=1)]
    digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]


class EstateNativeArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    filename: Annotated[str, Field(min_length=1)]
    digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]


class EstateProvider(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    repository: Annotated[str, Field(min_length=1)]
    commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    tag: Annotated[str, Field(min_length=1)]
    native_artifacts: list[EstateNativeArtifact] = []
    wheels: list[EstateDistribution] = []


class EstateEvidenceRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    slice: Annotated[str, Field(min_length=1)]
    os: Annotated[str, Field(min_length=1)]
    arch: Annotated[str, Field(min_length=1)]
    run_id: str = ""
    consumer_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    provider_tag: Annotated[str, Field(min_length=1)]
    result: Literal["passed", "failed", "skipped", "inconclusive"]
    provider: str = ""


class EstateWeb(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    image_digest: str = ""


class EstateProviderKit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Annotated[str, Field(min_length=1)]
    digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]


class EstateRelease(BaseModel):
    """One cut of the consumer bound to exact provider evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_id: Literal["ai-stp-estate-release/1"]
    record_id: Annotated[str, Field(min_length=1)]
    created_at: Timestamp
    consumer: EstateConsumer
    distributions: list[EstateDistribution]
    providers: list[EstateProvider]
    evidence: list[EstateEvidenceRow]
    known_limitations: list[str] = []
    verdict: Literal["complete", "incomplete", "failed"]
    required_slices: list[str] = []
    web: EstateWeb | None = None
    provider_kit: EstateProviderKit | None = None
    checksums_digest: str = ""
    sbom_digest: str = ""
    record_provenance: str = ""

    @model_validator(mode="after")
    def _closed_refs(self) -> EstateRelease:
        _forbid_floating(self.consumer.tag)
        _forbid_floating(self.consumer.release_url)
        for provider in self.providers:
            _forbid_floating(provider.tag)
        return self


def computed_verdict(record: EstateRelease) -> Literal["complete", "incomplete", "failed"]:
    """Recompute the verdict. The stored field is a claim, not the decision."""
    if any(row.result == "failed" for row in record.evidence):
        return "failed"
    if not record.required_slices or not record.distributions:
        return "incomplete"
    if {item.name for item in record.distributions} != {"ai-stp-cli"}:
        return "incomplete"
    if {item.repository for item in record.providers} != set(REQUIRED_PROVIDERS):
        return "incomplete"
    if SOFTWARE_SLICE not in record.required_slices:
        return "incomplete"
    if LAUNCH_SLICE not in record.required_slices:
        return "incomplete"
    tag_by_provider = {item.repository: item.tag for item in record.providers}
    recorded_tags = set(tag_by_provider.values())
    wanted: set[tuple[str, ...]] = set()
    for slice_name in record.required_slices:
        if slice_name == LAUNCH_SLICE:
            wanted.update(
                (LAUNCH_SLICE, repository, os_name, arch)
                for repository in REQUIRED_PROVIDERS
                for os_name, arch in REQUIRED_LEGS
            )
            continue
        wanted.update((slice_name, os_name, arch) for os_name, arch in REQUIRED_LEGS)
    observed: set[tuple[str, ...]] = set()
    for row in record.evidence:
        if row.slice == LAUNCH_SLICE:
            if not row.provider:
                continue
            key: tuple[str, ...] = (row.slice, row.provider, row.os, row.arch)
        else:
            key = (row.slice, row.os, row.arch)
        if key not in wanted:
            continue
        if row.consumer_commit != record.consumer.commit:
            return "incomplete"
        if row.slice == LAUNCH_SLICE:
            expected_tag = tag_by_provider.get(row.provider)
            if expected_tag is None or row.provider_tag != expected_tag:
                return "incomplete"
        elif row.provider_tag not in recorded_tags:
            return "incomplete"
        if row.result != "passed":
            return "incomplete"
        observed.add(key)
    if observed != wanted:
        return "incomplete"
    return "complete"


def _forbid_floating(value: str) -> None:
    if not value:
        return
    lowered = value.casefold()
    if lowered in _FLOATING or any(f"/{mark}" in lowered for mark in _FLOATING):
        raise ValueError(f"floating reference is not an estate identity: {value}")
