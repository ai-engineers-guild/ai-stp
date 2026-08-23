"""Versioned component scaffold descriptors, plans, and applied results."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_passports.versions import ComponentType

AuthoringLanguage = Literal[
    "none", "python", "typescript", "javascript", "rust", "go", "dart-flutter"
]
AuthoringVariant = Literal["portable"] | HarnessId
AUTHORING_LANGUAGES: Final[tuple[AuthoringLanguage, ...]] = (
    "none",
    "python",
    "typescript",
    "javascript",
    "rust",
    "go",
    "dart-flutter",
)
AUTHORING_VARIANTS: Final[tuple[AuthoringVariant, ...]] = (
    "portable",
    "claude-code",
    "codex",
    "pi",
    "opencode",
    "grok-build",
)
DECLARATIVE_COMPONENT_TYPES: Final[frozenset[ComponentType]] = frozenset(
    {"instruction", "skill", "agent", "setting"}
)
AUTHORING_TYPE_LANGUAGE_MATRIX: Final[dict[ComponentType, tuple[AuthoringLanguage, ...]]] = {
    component_type: (
        ("none",) if component_type in DECLARATIVE_COMPONENT_TYPES else AUTHORING_LANGUAGES[1:]
    )
    for component_type in (
        "instruction",
        "skill",
        "mcp",
        "hook",
        "command",
        "agent",
        "plugin",
        "setting",
    )
}


class ComponentTemplateDescriptor(BaseModel):
    """Exact generator choice recorded inside every scaffold."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    template_version: Literal["component-scaffold/1"] = "component-scaffold/1"
    generator_version: Literal["ai-stp/1"] = "ai-stp/1"
    component_type: ComponentType
    language: AuthoringLanguage
    harness_variant: AuthoringVariant
    executable: bool

    @model_validator(mode="after")
    def type_language_pair_is_meaningful(self) -> Self:
        if self.language not in AUTHORING_TYPE_LANGUAGE_MATRIX[self.component_type]:
            raise ValueError("component type and authoring language are incompatible")
        if self.executable is (self.component_type in DECLARATIVE_COMPONENT_TYPES):
            raise ValueError("executable marker disagrees with the component type")
        return self


class ComponentScaffoldFile(BaseModel):
    """One exact regular file produced by a scaffold plan."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    path: Annotated[str, Field(min_length=1, max_length=512)]
    digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    byte_length: Annotated[int, Field(ge=0)]
    mode: Literal[384] = 384

    @field_validator("path")
    @classmethod
    def path_is_bounded_relative_posix(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            value.startswith(("/", "~"))
            or "\\" in value
            or any(part in {"", ".", ".."} for part in path.parts)
            or any(ord(character) < 32 for character in value)
        ):
            raise ValueError("scaffold file path must be relative POSIX without traversal")
        return path.as_posix()


class ComponentScaffoldPlan(BaseModel):
    """Content-addressed preview of a complete authoring directory."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    plan_id: Annotated[str, Field(pattern=r"^scaffold_plan_[0-9a-f]{24}$")]
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    output: Annotated[str, Field(min_length=1)]
    component_name: Annotated[str, Field(min_length=1, max_length=64)]
    descriptor: ComponentTemplateDescriptor
    files: Annotated[list[ComponentScaffoldFile], Field(min_length=6)]
    publication_ready: Literal[False] = False
    requires_exact_source_before_publication: Literal[True] = True

    @model_validator(mode="after")
    def file_paths_are_unique(self) -> Self:
        if len({item.path for item in self.files}) != len(self.files):
            raise ValueError("scaffold file paths must be unique")
        return self


class ComponentScaffoldResult(BaseModel):
    """Applied scaffold, bound to the exact preview digest."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    plan_id: Annotated[str, Field(min_length=1)]
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    output: Annotated[str, Field(min_length=1)]
    files_written: Annotated[int, Field(ge=6)]
    template_version: Literal["component-scaffold/1"] = "component-scaffold/1"
    generator_version: Literal["ai-stp/1"] = "ai-stp/1"
