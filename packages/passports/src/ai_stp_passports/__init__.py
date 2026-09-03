"""Passport envelope and facts (docs/contracts/passport-envelope.md).

Owns the five passport kinds, the fact model with its two independent axes
and the content-addressed revision sealing of mutable passports. Persisted
passports preserve unknown optional fields within the supported major
version, so round-trips never drop data that a newer writer added.
"""

from ai_stp_passports.envelope import (
    IMMUTABLE_KINDS,
    MUTABLE_KINDS,
    PASSPORT_KINDS,
    PassportEnvelope,
    derive_revision_id,
    seal_envelope,
    verify_revision_id,
)
from ai_stp_passports.facts import Fact
from ai_stp_passports.markdown import (
    DESCRIPTION_FORMAT,
    MAX_DESCRIPTION_BYTES,
    MAX_DESCRIPTION_LINES,
    MAX_EXCERPT_CODEPOINTS,
    RENDERER_VERSION,
    MarkdownPolicyError,
    SafeMarkdownProjection,
    project_safe_markdown,
    validate_safe_markdown,
)
from ai_stp_passports.versions import (
    ArtifactRef,
    ComponentAdaptation,
    ComponentVersionPassport,
    Conflicts,
    EnvVarRequirement,
    GitSource,
    LicenseInfo,
    Permissions,
    ProjectedMember,
    ProviderSurfaceRef,
    ScopeAdaptation,
    SetupVersionPassport,
    TransformRef,
    seal_adaptation,
)

__all__ = [
    "DESCRIPTION_FORMAT",
    "IMMUTABLE_KINDS",
    "MAX_DESCRIPTION_BYTES",
    "MAX_DESCRIPTION_LINES",
    "MAX_EXCERPT_CODEPOINTS",
    "MUTABLE_KINDS",
    "PASSPORT_KINDS",
    "RENDERER_VERSION",
    "ArtifactRef",
    "ComponentAdaptation",
    "ComponentVersionPassport",
    "Conflicts",
    "EnvVarRequirement",
    "Fact",
    "GitSource",
    "LicenseInfo",
    "MarkdownPolicyError",
    "PassportEnvelope",
    "Permissions",
    "ProjectedMember",
    "ProviderSurfaceRef",
    "SafeMarkdownProjection",
    "ScopeAdaptation",
    "SetupVersionPassport",
    "TransformRef",
    "derive_revision_id",
    "project_safe_markdown",
    "seal_adaptation",
    "seal_envelope",
    "validate_safe_markdown",
    "verify_revision_id",
]
