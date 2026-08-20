"""Vendor-neutral contracts for bounded local setup-store imports."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_passports.versions import ComponentType

StoreAdapter = Literal["sx", "apm"]
MappingState = Literal["component", "omitted"]

SX_CONTRACT_URL = (
    "https://github.com/sleuth-io/sx/blob/"
    "a74798be061fb125b0748f083f0418e058978a13/docs/manifest-spec.md"
)
APM_CONTRACT_URL = (
    "https://github.com/microsoft/apm/blob/"
    "3aa0365540e3d9ef4685740cea6a09094ff35377/src/apm_cli/deps/lockfile.py"
)


class StorePortDescriptor(BaseModel):
    """One compatible local store found under an explicitly named root."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    port_version: Literal["setup-store-port/1"] = "setup-store-port/1"
    adapter: StoreAdapter
    contract_version: Annotated[str, Field(min_length=1, max_length=32)]
    root: Annotated[str, Field(min_length=1)]
    manifest: Annotated[str, Field(min_length=1)]
    snapshot_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    cli_status: Literal["available", "absent", "not_required"]


class StorePortDiscovery(BaseModel):
    """All supported stores visible at one root, without importing them."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    root: Annotated[str, Field(min_length=1)]
    stores: list[StorePortDescriptor]
    diagnostics: list[str]


class StorePortMapping(BaseModel):
    """One external record and its explicit canonical conversion decision."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    external_id: Annotated[str, Field(min_length=1, max_length=512)]
    external_type: Annotated[str, Field(min_length=1, max_length=128)]
    external_version: Annotated[str | None, Field(max_length=128)] = None
    source_coordinate: Annotated[str, Field(min_length=1, max_length=2048)]
    source_digest: Annotated[str | None, Field(max_length=256)] = None
    local_content_digest: Annotated[str | None, Field(pattern=DIGEST_PATTERN)] = None
    state: MappingState
    component_type: ComponentType | None = None
    local_path: str | None = None
    omissions: list[str]
    preserved_metadata: dict[str, str]


class StorePortInspection(BaseModel):
    """Bounded conversion report for one immutable local snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    descriptor: StorePortDescriptor
    mappings: list[StorePortMapping]
    unknown_fields: list[str]
    diagnostics: list[str]


class StorePortImportPlan(BaseModel):
    """Exact no-side-effect import plan bound to its source snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    inspection: StorePortInspection
    importable_count: Annotated[int, Field(ge=0)]
    omitted_count: Annotated[int, Field(ge=0)]
    conflicts: list[str]
    trust_consequences: list[
        Literal[
            "local_only",
            "author_verified_false",
            "component_verified_false",
            "external_store_unchanged",
            "harness_target_unchanged",
        ]
    ]


class StorePortImportedObject(BaseModel):
    """One local object created by or reused for an exact external record."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    external_id: str
    stable_id: str
    revision_id: str
    state: Literal["imported", "already_imported"]


class StorePortImportResult(BaseModel):
    """Result of applying one still-current exact import plan."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    imported: list[StorePortImportedObject]
    external_store_changed: Literal[False] = False
    harness_target_changed: Literal[False] = False
