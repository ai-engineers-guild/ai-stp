"""Closed input contract for confirmed local component draft enrichment."""

from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_stp_foundation.harnesses import HarnessId
from ai_stp_foundation.refs import ComponentRef
from ai_stp_passports.markdown import validate_safe_markdown
from ai_stp_passports.versions import (
    CapabilityId,
    ComponentType,
    Conflicts,
    EnvVarRequirement,
    GitSource,
    LicenseInfo,
    Permissions,
    ProjectionKind,
    TagId,
)

MAX_COMPONENT_PATCH_LIST_ITEMS: Final[int] = 256
_TRAVERSAL: Final[tuple[str, ...]] = ("../", "/..", "\\..", "..\\")

type BoundedComponentText = Annotated[str, Field(min_length=1, max_length=512)]


class ComponentPassportPatch(BaseModel):
    """Partial declared facts; omitted differs from explicit null."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    description: Annotated[str, Field(min_length=1, max_length=20_000)] | None = None
    tags: Annotated[list[TagId], Field(min_length=1, max_length=8)] | None = None
    source: GitSource | None = None
    harness_id: HarnessId | None = None
    component_type: ComponentType | None = None
    projection_kind: ProjectionKind | None = None
    provides_capabilities: (
        Annotated[list[CapabilityId], Field(max_length=MAX_COMPONENT_PATCH_LIST_ITEMS)] | None
    ) = None
    requires_components: (
        Annotated[list[ComponentRef], Field(max_length=MAX_COMPONENT_PATCH_LIST_ITEMS)] | None
    ) = None
    requires_capabilities: (
        Annotated[list[CapabilityId], Field(max_length=MAX_COMPONENT_PATCH_LIST_ITEMS)] | None
    ) = None
    required_env: (
        Annotated[list[EnvVarRequirement], Field(max_length=MAX_COMPONENT_PATCH_LIST_ITEMS)] | None
    ) = None
    requires_credentials: bool | None = None
    requires_authorization: Literal["none", "user_account", "external_service"] | None = None
    permissions: Permissions | None = None
    external_endpoints: (
        Annotated[list[BoundedComponentText], Field(max_length=MAX_COMPONENT_PATCH_LIST_ITEMS)]
        | None
    ) = None
    license: LicenseInfo | None = None
    conflicts: Conflicts | None = None
    managed_paths: (
        Annotated[list[BoundedComponentText], Field(max_length=MAX_COMPONENT_PATCH_LIST_ITEMS)]
        | None
    ) = None
    native_ids: (
        Annotated[list[BoundedComponentText], Field(max_length=MAX_COMPONENT_PATCH_LIST_ITEMS)]
        | None
    ) = None
    entry_points: (
        Annotated[list[BoundedComponentText], Field(max_length=MAX_COMPONENT_PATCH_LIST_ITEMS)]
        | None
    ) = None
    runtime_requirements: (
        Annotated[list[BoundedComponentText], Field(max_length=MAX_COMPONENT_PATCH_LIST_ITEMS)]
        | None
    ) = None
    harness_variants: (
        Annotated[list[BoundedComponentText], Field(max_length=MAX_COMPONENT_PATCH_LIST_ITEMS)]
        | None
    ) = None
    supported_harness_versions: (
        Annotated[list[BoundedComponentText], Field(max_length=MAX_COMPONENT_PATCH_LIST_ITEMS)]
        | None
    ) = None

    @field_validator("description")
    @classmethod
    def safe_description(cls, value: str | None) -> str | None:
        return None if value is None else validate_safe_markdown(value)

    @model_validator(mode="after")
    def supplied_values_are_explicit_and_safe(self) -> ComponentPassportPatch:
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"declared field {name!r} may not be null")
        if self.source is not None and not self.source.repository.startswith("https://github.com/"):
            raise ValueError("publication source must be an exact GitHub HTTPS repository")
        for path in self.managed_paths or []:
            if (
                path.startswith(("/", "\\"))
                or path == ".."
                or any(marker in path for marker in _TRAVERSAL)
            ):
                raise ValueError("managed paths must be relative without traversal")
        return self
