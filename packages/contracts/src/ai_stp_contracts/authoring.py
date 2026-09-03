"""Versioned component and setup scaffold descriptors, plans, and applied results."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.harnesses import HARNESS_ID_ORDER, HarnessId
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
#: Derived from `HARNESS_ID_ORDER`, not listed. The listed version named five
#: harnesses while `AuthoringVariant` already resolved to seven through
#: `HarnessId`: the type accepted `cursor` and `antigravity` and this tuple
#: refused them, so `component scaffold` answered "the scaffold language or
#: harness variant is unsupported" for two supported harnesses.
AUTHORING_VARIANTS: Final[tuple[AuthoringVariant, ...]] = ("portable", *HARNESS_ID_ORDER)
DECLARATIVE_COMPONENT_TYPES: Final[frozenset[ComponentType]] = frozenset(
    {"instruction", "skill", "command", "agent", "setting"}
)
AUTHORING_TYPE_LANGUAGE_MATRIX: Final[dict[ComponentType, tuple[AuthoringLanguage, ...]]] = {
    "instruction": ("none",),
    "skill": ("none",),
    "mcp": AUTHORING_LANGUAGES[1:],
    # A hook handler must be directly runnable after installation. Rust and Go
    # source need a build step, which the scaffold and provider are forbidden
    # to invent or execute.
    "hook": ("python", "typescript", "javascript", "dart-flutter"),
    "command": ("none",),
    "agent": ("none",),
    "plugin": AUTHORING_LANGUAGES[1:],
    "setting": ("none",),
}

type ComponentTemplateVersion = Literal[
    "component-scaffold/1", "component-scaffold/2", "component-scaffold/3"
]
type ComponentGeneratorVersion = Literal["ai-stp/1", "ai-stp/2", "ai-stp/3"]
type SetupTemplateVersion = Literal["setup-scaffold/1"]
type SetupGeneratorVersion = Literal["ai-stp/1"]
type GitInitReason = Literal["existing_worktree", "missing_identity", "git_unavailable"]


class PortableHookHandler(BaseModel):
    """One command handler in the portable hook source model."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    command: Annotated[str, Field(min_length=1, max_length=512)]


class PortableHookSource(BaseModel):
    """Lossless hook intent projected into one harness-native manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    event: Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")]
    order: Annotated[int, Field(ge=0, le=65535)] = 0
    failure: Literal["block"] = "block"
    handler: PortableHookHandler


class ComponentTemplateDescriptor(BaseModel):
    """Exact generator choice recorded inside every scaffold."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    template_version: ComponentTemplateVersion = "component-scaffold/3"
    generator_version: ComponentGeneratorVersion = "ai-stp/3"
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
            or path.parts[0] == ".git"
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
    template_version: ComponentTemplateVersion = "component-scaffold/3"
    generator_version: ComponentGeneratorVersion = "ai-stp/3"
    git_initialized: bool
    git_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40,64}$")] | None = None
    git_reason: GitInitReason | None = None


class SetupMemberDescriptor(BaseModel):
    """One nested component named by setup scaffold."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    component_type: ComponentType
    name: Annotated[str, Field(min_length=1, max_length=64)]
    language: AuthoringLanguage


class SetupTemplateDescriptor(BaseModel):
    """Exact generator choice recorded inside every setup scaffold."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    template_version: SetupTemplateVersion = "setup-scaffold/1"
    generator_version: SetupGeneratorVersion = "ai-stp/1"
    harness_id: HarnessId
    setup_name: Annotated[str, Field(min_length=1, max_length=64)]
    members: list[SetupMemberDescriptor] = Field(default_factory=list[SetupMemberDescriptor])


class SetupScaffoldPlan(BaseModel):
    """Content-addressed preview of a complete setup authoring directory."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    plan_id: Annotated[str, Field(pattern=r"^setup_scaffold_[0-9a-f]{24}$")]
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    output: Annotated[str, Field(min_length=1)]
    setup_name: Annotated[str, Field(min_length=1, max_length=64)]
    descriptor: SetupTemplateDescriptor
    files: Annotated[list[ComponentScaffoldFile], Field(min_length=6)]
    publication_ready: Literal[False] = False
    requires_exact_source_before_publication: Literal[True] = True

    @model_validator(mode="after")
    def file_paths_are_unique(self) -> Self:
        if len({item.path for item in self.files}) != len(self.files):
            raise ValueError("scaffold file paths must be unique")
        return self


class SetupScaffoldResult(BaseModel):
    """Applied setup scaffold, bound to the exact preview digest."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    plan_id: Annotated[str, Field(min_length=1)]
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    output: Annotated[str, Field(min_length=1)]
    files_written: Annotated[int, Field(ge=6)]
    template_version: SetupTemplateVersion = "setup-scaffold/1"
    generator_version: SetupGeneratorVersion = "ai-stp/1"
    git_initialized: bool
    git_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40,64}$")] | None = None
    git_reason: GitInitReason | None = None
