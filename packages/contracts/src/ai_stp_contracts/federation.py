"""Authority-safe descriptors for federated external sources (SPEC-045, SPEC-050)."""

from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_stp_contracts.github_evidence import GitHubArchiveEvidence
from ai_stp_contracts.http import Timestamp
from ai_stp_contracts.store_ports import (
    APM_CONTRACT_URL,
    SX_CONTRACT_URL,
    StorePortDescriptor,
)

#: Closed catalog metadata adapters (SPEC-050). Production fetch/projection
#: stays off until attribution and terms policy is verified.
CATALOG_METADATA_PROVIDERS: tuple[str, str, str] = (
    "skills_sh",
    "nori",
    "modelcontextprotocol",
)
CATALOG_METADATA_ADAPTERS_ENABLED_BY_DEFAULT: Literal[False] = False
CATALOG_OBSERVATION_MAX_RESPONSE_BYTES = 256 * 1024
CATALOG_OBSERVATION_MAX_JSON_DEPTH = 16
CATALOG_OBSERVATION_MAX_COLLECTION_ITEMS = 100
CATALOG_OBSERVATION_MAX_STRING_CODEPOINTS = 4096
CATALOG_OBSERVATION_MAX_REFERENCES = 8
CATALOG_ADAPTER_CONNECT_TIMEOUT_SECONDS = 2.0
CATALOG_ADAPTER_READ_TIMEOUT_SECONDS = 5.0
CATALOG_ADAPTER_CACHE_MAX_ENTRIES = 1000
CATALOG_ADAPTER_CACHE_TTL_SECONDS = 6 * 3600
CATALOG_ADAPTER_MAX_REQUESTS_PER_MINUTE = 60

_LOCAL_PROVIDERS = frozenset({"sx", "apm"})
_HTTPS_URL = r"^https://[^\s]+$"


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _reject_public_https(value: str, label: str) -> None:
    parsed = urlsplit(value)
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"{label} must carry no credentials, query or fragment")


class FederatedSourceDescriptor(_Closed):
    schema_version: Literal[1] = 1
    descriptor_version: Literal["federated-source/1"] = "federated-source/1"
    provider: Literal["sx", "apm", "github", "skills_sh", "nori", "modelcontextprotocol"]
    source_kind: Literal["local_port", "metadata_adapter"]
    canonical_url: Annotated[str, Field(pattern=_HTTPS_URL, max_length=2048)]
    external_identifier: Annotated[str, Field(min_length=1, max_length=512)]
    dedup_key: Annotated[str, Field(min_length=3, max_length=1024)]
    checked_at: Timestamp
    fetched_at: Timestamp | None
    expires_at: Timestamp | None = None
    terms_url: Annotated[str, Field(pattern=_HTTPS_URL, max_length=2048)] | None = None
    freshness: Literal["local_snapshot", "fresh", "stale", "unavailable"]
    external_state: Literal["present", "archived", "unavailable"]
    rate_limit_policy: Literal["not_applicable", "adapter_owned"]
    provenance: Literal["exact_local_snapshot", "official_remote_observation"]
    attribution: Annotated[str, Field(min_length=1, max_length=256)]
    authority: Literal["external_observation"] = "external_observation"
    author_verified: Literal[False] = False
    component_verified: Literal[False] = False
    registry_effect: Literal["none", "confirmed_private_draft_import"]
    target_write: Literal[False] = False

    @model_validator(mode="after")
    def _coherent_boundary(self) -> "FederatedSourceDescriptor":
        _reject_public_https(self.canonical_url, "canonical source URL")
        if self.terms_url is not None:
            _reject_public_https(self.terms_url, "terms URL")
        if self.dedup_key != f"{self.provider}:{self.external_identifier}":
            raise ValueError("dedup key must use exact provider and external identifier")
        local = self.source_kind == "local_port"
        if local != (self.provider in _LOCAL_PROVIDERS):
            raise ValueError("only SX and APM are local ports in descriptor version 1")
        if local and (self.expires_at is not None or self.terms_url is not None):
            raise ValueError("local snapshots do not carry remote expiry or terms URL")
        if local != (self.freshness == "local_snapshot"):
            raise ValueError("local ports alone use local snapshot freshness")
        if local != (self.provenance == "exact_local_snapshot"):
            raise ValueError("local ports alone use exact local snapshot provenance")
        if local != (self.registry_effect == "confirmed_private_draft_import"):
            raise ValueError("local ports alone may offer confirmed private draft import")
        if local and self.fetched_at is not None:
            raise ValueError("local snapshots do not invent a fetched time")
        if local != (self.rate_limit_policy == "not_applicable"):
            raise ValueError("only metadata adapters own a remote rate-limit policy")
        if local and self.external_state != "present":
            raise ValueError("a readable local snapshot is present")
        if not local and (self.freshness == "unavailable") != (self.fetched_at is None):
            raise ValueError("only unavailable remote observations omit fetched time")
        if not local and (self.external_state == "unavailable") != (
            self.freshness == "unavailable"
        ):
            raise ValueError("unavailable remote state and freshness must agree")
        return self


class FederatedSourceSet(_Closed):
    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1, max_length=256)]
    references: Annotated[list[FederatedSourceDescriptor], Field(max_length=100)]
    deduplication: Literal["exact_provider_external_identifier"] = (
        "exact_provider_external_identifier"
    )
    auto_merged: Literal[False] = False

    @model_validator(mode="after")
    def _unique_exact_references(self) -> "FederatedSourceSet":
        keys = [item.dedup_key for item in self.references]
        if len(keys) != len(set(keys)):
            raise ValueError("one exact external reference may appear only once")
        return self


class CatalogExternalCoordinate(_Closed):
    """Exact provider/external identifier pair; names and URLs do not create a link."""

    schema_version: Literal[1] = 1
    provider: Literal["skills_sh", "nori", "modelcontextprotocol"]
    external_identifier: Annotated[str, Field(min_length=1, max_length=512)]

    @property
    def dedup_key(self) -> str:
        return f"{self.provider}:{self.external_identifier}"


class CatalogMetadataObservation(_Closed):
    """Closed allowlist for one catalog metadata adapter observation (SPEC-050)."""

    schema_version: Literal[1] = 1
    provider: Literal["skills_sh", "nori", "modelcontextprotocol"]
    external_identifier: Annotated[str, Field(min_length=1, max_length=512)]
    dedup_key: Annotated[str, Field(min_length=3, max_length=1024)]
    source_url: Annotated[str, Field(pattern=_HTTPS_URL, max_length=2048)]
    attribution: Annotated[str, Field(min_length=1, max_length=256)]
    terms_url: Annotated[str, Field(pattern=_HTTPS_URL, max_length=2048)]
    fetched_at: Timestamp | None
    checked_at: Timestamp
    expires_at: Timestamp | None
    freshness: Literal["fresh", "stale", "unavailable"]
    display_name: Annotated[str, Field(min_length=1, max_length=4096)] | None = None
    summary: Annotated[str, Field(min_length=1, max_length=4096)] | None = None
    homepage_url: Annotated[str, Field(pattern=_HTTPS_URL, max_length=2048)] | None = None
    repository_url: Annotated[str, Field(pattern=_HTTPS_URL, max_length=2048)] | None = None
    published_at: Timestamp | None = None
    updated_at: Timestamp | None = None
    popularity_count: Annotated[int, Field(ge=0)] | None = None
    external_state: Literal["present", "archived", "unavailable"]
    authority: Literal["external_observation"] = "external_observation"
    author_verified: Literal[False] = False
    component_verified: Literal[False] = False
    registry_effect: Literal["none"] = "none"
    target_write: Literal[False] = False

    @model_validator(mode="after")
    def _closed_observation(self) -> "CatalogMetadataObservation":
        if self.dedup_key != f"{self.provider}:{self.external_identifier}":
            raise ValueError("dedup key must use exact provider and external identifier")
        _reject_public_https(self.source_url, "source URL")
        _reject_public_https(self.terms_url, "terms URL")
        for label, url in (
            ("homepage URL", self.homepage_url),
            ("repository URL", self.repository_url),
        ):
            if url is not None:
                _reject_public_https(url, label)
        if self.freshness == "unavailable" and self.external_state != "unavailable":
            raise ValueError("unavailable freshness must report unavailable external state")
        if self.freshness != "unavailable" and self.fetched_at is None:
            raise ValueError("fresh and stale observations must keep fetched time")
        if self.freshness != "unavailable" and self.expires_at is None:
            raise ValueError("fresh and stale observations must keep expiry")
        return self


class CatalogMetadataObservationSet(_Closed):
    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1, max_length=256)]
    version: Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+$")]
    references: Annotated[
        list[CatalogMetadataObservation], Field(max_length=CATALOG_OBSERVATION_MAX_REFERENCES)
    ]
    deduplication: Literal["exact_provider_external_identifier"] = (
        "exact_provider_external_identifier"
    )
    auto_merged: Literal[False] = False

    @model_validator(mode="after")
    def _unique_exact_references(self) -> "CatalogMetadataObservationSet":
        keys = [item.dedup_key for item in self.references]
        if len(keys) != len(set(keys)):
            raise ValueError("one exact external reference may appear only once")
        return self


def describe_store_port(
    port: StorePortDescriptor, *, checked_at: Timestamp
) -> FederatedSourceDescriptor:
    """Project one exact local snapshot into the shared authority boundary."""
    canonical_url = SX_CONTRACT_URL if port.adapter == "sx" else APM_CONTRACT_URL
    return FederatedSourceDescriptor(
        provider=port.adapter,
        source_kind="local_port",
        canonical_url=canonical_url,
        external_identifier=port.snapshot_digest,
        dedup_key=f"{port.adapter}:{port.snapshot_digest}",
        checked_at=checked_at,
        fetched_at=None,
        freshness="local_snapshot",
        external_state="present",
        rate_limit_policy="not_applicable",
        provenance="exact_local_snapshot",
        attribution=f"{port.adapter}:{port.contract_version}",
        registry_effect="confirmed_private_draft_import",
    )


def describe_github_evidence(
    evidence: GitHubArchiveEvidence, *, checked_at: Timestamp
) -> FederatedSourceDescriptor:
    """Project one GitHub observation without promoting its trust."""
    external_identifier = (
        f"repository:{evidence.repository_id}"
        if evidence.repository_id is not None
        else f"coordinate:{evidence.source_repository}"
    )
    return FederatedSourceDescriptor(
        provider="github",
        source_kind="metadata_adapter",
        canonical_url=evidence.source_repository,
        external_identifier=external_identifier,
        dedup_key=f"github:{external_identifier}",
        checked_at=checked_at,
        fetched_at=evidence.fetched_at,
        freshness=evidence.freshness,
        external_state="present"
        if evidence.repository_state == "active"
        else evidence.repository_state,
        rate_limit_policy="adapter_owned",
        provenance="official_remote_observation",
        attribution=evidence.attribution,
        registry_effect="none",
    )


def describe_catalog_metadata(
    observation: CatalogMetadataObservation, *, checked_at: Timestamp | None = None
) -> FederatedSourceDescriptor:
    """Project one catalog adapter observation without promoting its trust."""
    unavailable = observation.freshness == "unavailable"
    return FederatedSourceDescriptor(
        provider=observation.provider,
        source_kind="metadata_adapter",
        canonical_url=observation.source_url,
        external_identifier=observation.external_identifier,
        dedup_key=observation.dedup_key,
        checked_at=checked_at if checked_at is not None else observation.checked_at,
        fetched_at=None if unavailable else observation.fetched_at,
        expires_at=None if unavailable else observation.expires_at,
        terms_url=observation.terms_url,
        freshness=observation.freshness,
        external_state=observation.external_state,
        rate_limit_policy="adapter_owned",
        provenance="official_remote_observation",
        attribution=observation.attribution,
        registry_effect="none",
    )
