"""Exact first-party launch objects shared by the CLI and platform."""

from __future__ import annotations

from importlib.resources import files
from typing import Final, Literal, cast

from pydantic import BaseModel, ConfigDict

from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes, digest_canonical
from ai_stp_passports.envelope import seal_envelope, verify_revision_id
from ai_stp_passports.versions import ComponentVersionPassport, SetupVersionPassport

OWNER_ID: Final[str] = "account_01KZET6ZKJN7S72T5H4WDV62T0"
VERSION: Final[str] = "1.0"
PUBLISHED_AT: Final[str] = "2026-08-13T00:00:00.000Z"
COMPONENT_FORMAT: Final[str] = "ai-stp-component-tree/1"
COMPONENT_FILE_FORMAT: Final[str] = "ai-stp-component-file/1"
SETUP_FORMAT: Final[str] = "ai-stp-setup-definition/1"
PASSPORT_DIGEST_DOMAIN: Final[str] = "ai-stp:passport:v1"
ARTIFACT_DIGEST_DOMAIN: Final[str] = "ai-stp:artifact:v1"
ROLE_LIFECYCLE_EVIDENCE: Final[str] = "https://github.com/ai-engineers-guild/ai_stp/issues/186"

# Compatibility names for the first Grok Build pair. Consumers should prefer
# ``versions()`` and inspect each passport instead of depending on one member.
COMPONENT_ID: Final[str] = "component_01KZWSHE3V0T8KVJYFEKWJV63Y"
SETUP_ID: Final[str] = "setup_01KZWSHE3V0T8KVJYFEKWJV63Z"
SOURCE_REPOSITORY: Final[str] = "https://github.com/NDDev-it-com/nddev-grok-build-app"
SOURCE_COMMIT: Final[str] = "307e5124a1919a2224692cc8d64c50f98364ef2b"
SOURCE_TREE: Final[str] = "1db75b64678b476840fbe50f98a061dac6893ab2"
SETUP_SOURCE_BLOB: Final[str] = "2acec9e28f0aaac9a6f12e92d4d14785c9aed891"


class FirstPartyVersion(BaseModel):
    """One immutable passport together with the exact bytes it identifies."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal["component", "setup"]
    passport: ComponentVersionPassport | SetupVersionPassport
    passport_digest: str
    artifact: bytes
    artifact_format: str
    source_tree: str


class _ComponentSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    stable_id: str
    slug: str
    source_path: str
    source_tree: str
    artifact_name: str
    artifact_format: Literal["ai-stp-component-file/1", "ai-stp-component-tree/1"] = (
        COMPONENT_FORMAT
    )
    source_object_kind: Literal["blob", "tree"] = "tree"
    component_type: str
    projection_kind: str
    native_id: str | None = None
    name: str | None = None
    description: str | None = None
    tags: tuple[str, ...] = ()


class _HarnessSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    harness_id: str
    setup_id: str
    repository: str
    commit: str
    setup_path: str
    setup_blob: str
    evidence_ref: str
    components: tuple[_ComponentSource, ...]


class _RoleSetupSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    stable_id: str
    slug: str
    name: str
    description: str
    purpose: str
    target_role: str
    supported_tasks: tuple[str, ...]
    tags: tuple[str, ...]
    component_slugs: tuple[str, ...]


class _RoleHarnessSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    harness_id: str
    repository: str
    commit: str
    source_path: str
    source_blob: str
    evidence_ref: str
    components: tuple[_ComponentSource, ...]
    setups: tuple[_RoleSetupSource, ...]


class _SourceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1]
    harnesses: tuple[_HarnessSource, ...]


class _RoleSourceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1]
    harnesses: tuple[_RoleHarnessSource, ...]


def _sources() -> tuple[_HarnessSource, ...]:
    raw = files(__package__).joinpath("v1/corpus-sources.json").read_bytes()
    return _SourceManifest.model_validate_json(raw).harnesses


def _role_sources() -> tuple[_RoleHarnessSource, ...]:
    raw = files(__package__).joinpath("v1/role-sources.json").read_bytes()
    return _RoleSourceManifest.model_validate_json(raw).harnesses


def _sealed(
    body: dict[str, JsonValue],
    model: type[ComponentVersionPassport] | type[SetupVersionPassport],
) -> ComponentVersionPassport | SetupVersionPassport:
    envelope = seal_envelope(body)
    passport = model.model_validate(envelope.model_dump(mode="json"))
    if not verify_revision_id(passport):
        raise RuntimeError("a first-party passport has a non-canonical revision id")
    return passport


def _passport_digest(passport: ComponentVersionPassport | SetupVersionPassport) -> str:
    return digest_bytes(
        PASSPORT_DIGEST_DOMAIN,
        canonize(cast(JsonValue, passport.model_dump(mode="json"))),
    )


def _common(
    source: _HarnessSource | _RoleHarnessSource,
    *,
    kind: str,
    stable_id: str,
    source_path: str,
    artifact: bytes,
) -> dict[str, JsonValue]:
    return {
        "schema_version": 1,
        "kind": kind,
        "stable_id": stable_id,
        "owner_id": OWNER_ID,
        "created_at": PUBLISHED_AT,
        "visibility": "public",
        "parent_revision_ids": [],
        "facts": {},
        "version": VERSION,
        "source": {
            "repository": source.repository,
            "commit": source.commit,
            "path": source_path,
        },
        "artifact": {
            "digest": digest_bytes(ARTIFACT_DIGEST_DOMAIN, artifact),
            "size_bytes": len(artifact),
        },
        "harness_id": source.harness_id,
        "required_env": [],
        "requires_credentials": False,
        "requires_authorization": "none",
        "permissions": {"filesystem": [], "network": [], "process": []},
        "external_endpoints": [],
        "license": {"spdx_id": "AGPL-3.0-or-later", "redistribution_allowed": True},
        "compatibility_evidence_refs": [source.evidence_ref],
    }


def _title(slug: str) -> str:
    return " ".join(part.upper() if part in {"mcp"} else part.title() for part in slug.split("-"))


def _native_path(harness_id: str, component: _ComponentSource) -> str:
    if harness_id == "pi":
        return {
            "instruction": "agent/AGENTS.md",
            "setting": "agent/settings.json",
            "skill": f"agent/skills/{component.slug}",
            "plugin": f"agent/packages/{component.slug}",
        }[component.component_type]
    if harness_id == "opencode":
        return {
            "instruction": "AGENTS.md",
            "setting": "opencode.json",
            "skill": f"skills/{component.slug}",
            "agent": f"agents/{component.slug}",
            "command": f"commands/{component.slug}",
            "plugin": f"plugins/{component.slug}",
        }[component.component_type]
    if harness_id == "cursor":
        return {
            "instruction": "AGENTS.md",
            "setting": "cli-config.json",
            "plugin": f"plugins/{component.slug}",
        }[component.component_type]
    if component.component_type == "plugin":
        return f"plugins/{component.slug}"
    if harness_id == "codex":
        return f".agents/skills/{component.slug}"
    return f"skills/{component.slug}"


def _component(
    source: _HarnessSource | _RoleHarnessSource,
    component_source: _ComponentSource,
) -> FirstPartyVersion:
    artifact = files(__package__).joinpath(f"v1/{component_source.artifact_name}").read_bytes()
    body = _common(
        source,
        kind="component",
        stable_id=component_source.stable_id,
        source_path=component_source.source_path,
        artifact=artifact,
    )
    kind_title = "plugin" if component_source.component_type == "plugin" else "skill"
    native_path = _native_path(source.harness_id, component_source)
    grok = source.harness_id == "grok-build"
    role_component = bool(component_source.tags)
    conflicts: dict[str, JsonValue] = {
        "paths": [] if grok else [native_path],
        "commands": [],
        "hooks": [],
        "mcp": [],
        "agents": [],
        "plugins": ([component_source.slug] if component_source.component_type == "plugin" else []),
    }
    body.update(
        {
            "name": (
                "NDDev Builder for Grok Build"
                if grok
                else component_source.name
                or f"{_title(component_source.slug)} for {source.harness_id}"
            ),
            "description": (
                (
                    "Grok Build-native plugin with focused skills and an agent for creating, "
                    "checking and releasing harness artifacts."
                )
                if grok
                else component_source.description
                if role_component
                else (
                    f"First-party {source.harness_id} {kind_title} from the exact "
                    "NDDev Builder provider release."
                )
            ),
            "tags": (
                list(component_source.tags)
                if role_component
                else ["code-review", "devops", "planning"]
            ),
            "component_type": component_source.component_type,
            "projection_kind": component_source.projection_kind,
            "variant_id": None,
            "provides_capabilities": [],
            "requires_components": [],
            "requires_capabilities": [],
            "conflicts": conflicts,
            "managed_paths": [native_path],
            "native_ids": [component_source.native_id or component_source.slug],
            "harness_ids": [],
            "supported_os": [],
            "artifact_format": component_source.artifact_format,
            "source_tree": component_source.source_tree,
        }
    )
    passport = cast(ComponentVersionPassport, _sealed(body, ComponentVersionPassport))
    return FirstPartyVersion(
        kind="component",
        passport=passport,
        passport_digest=_passport_digest(passport),
        artifact=artifact,
        artifact_format=component_source.artifact_format,
        source_tree=component_source.source_tree,
    )


def _setup(source: _HarnessSource, components: tuple[FirstPartyVersion, ...]) -> FirstPartyVersion:
    refs: list[JsonValue] = [
        cast(
            JsonValue,
            {
                "stable_id": component.passport.stable_id,
                "variant_id": None,
                "version": VERSION,
                "passport_digest": component.passport_digest,
            },
        )
        for component in components
    ]
    selection_digest = digest_canonical(
        "ai-stp:selection-snapshot:v1",
        cast(JsonValue, {"harness_id": source.harness_id, "components": refs}),
    )
    artifact = canonize(
        cast(
            JsonValue,
            {
                "schema_version": 1,
                "format": SETUP_FORMAT,
                "stable_id": source.setup_id,
                "version": VERSION,
                "harness_id": source.harness_id,
                "input_digest": selection_digest,
                "components": refs,
            },
        )
    )
    body = _common(
        source,
        kind="setup",
        stable_id=source.setup_id,
        source_path=source.setup_path,
        artifact=artifact,
    )
    grok = source.harness_id == "grok-build"
    body.update(
        cast(
            dict[str, JsonValue],
            {
                "name": (
                    "NDDev Builder Grok Build setup"
                    if grok
                    else f"NDDev Builder {source.harness_id} setup"
                ),
                "description": (
                    (
                        "Full-auto Grok Build setup carrying the exact NDDev Builder plugin for "
                        "harness artifact development and validation."
                    )
                    if grok
                    else (
                        f"Exact first-party {source.harness_id} setup containing "
                        f"{len(components)} native NDDev Builder components."
                    )
                ),
                "tags": ["code-review", "devops", "planning"],
                "purpose": (
                    "Develop and validate native Grok Build artifacts."
                    if grok
                    else "Develop and validate native harness artifacts."
                ),
                "target_role": "ai-harness-engineer",
                "supported_tasks": ["development", "validation", "release"],
                "components": refs,
                "ported_from": None,
                "related_setup_ids": [],
                "execution_profile": "full-auto",
                "supported_harness_versions": ["1.0.0"] if grok else [],
                "supported_os": ["linux"],
                "supported_arch": ["x86_64"],
                "composition_report_ref": source.evidence_ref,
                "conversion_report_ref": source.evidence_ref,
                "install_evidence_ref": source.evidence_ref,
                "launch_evidence_ref": source.evidence_ref,
                "artifact_format": SETUP_FORMAT,
                "member_metadata_complete": True,
            },
        )
    )
    passport = cast(SetupVersionPassport, _sealed(body, SetupVersionPassport))
    return FirstPartyVersion(
        kind="setup",
        passport=passport,
        passport_digest=_passport_digest(passport),
        artifact=artifact,
        artifact_format=SETUP_FORMAT,
        source_tree=source.setup_blob,
    )


def _role_setup(
    source: _RoleHarnessSource,
    setup_source: _RoleSetupSource,
    components_by_slug: dict[str, FirstPartyVersion],
) -> FirstPartyVersion:
    components = tuple(components_by_slug[slug] for slug in setup_source.component_slugs)
    refs: list[JsonValue] = [
        cast(
            JsonValue,
            {
                "stable_id": component.passport.stable_id,
                "variant_id": None,
                "version": VERSION,
                "passport_digest": component.passport_digest,
            },
        )
        for component in components
    ]
    selection_digest = digest_canonical(
        "ai-stp:selection-snapshot:v1",
        cast(JsonValue, {"harness_id": source.harness_id, "components": refs}),
    )
    artifact = canonize(
        cast(
            JsonValue,
            {
                "schema_version": 1,
                "format": SETUP_FORMAT,
                "stable_id": setup_source.stable_id,
                "version": VERSION,
                "harness_id": source.harness_id,
                "input_digest": selection_digest,
                "components": refs,
            },
        )
    )
    body = _common(
        source,
        kind="setup",
        stable_id=setup_source.stable_id,
        source_path=source.source_path,
        artifact=artifact,
    )
    body.update(
        cast(
            dict[str, JsonValue],
            {
                "name": setup_source.name,
                "description": setup_source.description,
                "tags": list(setup_source.tags),
                "purpose": setup_source.purpose,
                "target_role": setup_source.target_role,
                "supported_tasks": list(setup_source.supported_tasks),
                "components": refs,
                "ported_from": None,
                "related_setup_ids": [],
                "execution_profile": "full-auto",
                "supported_harness_versions": [],
                "supported_os": ["linux"],
                "supported_arch": ["x86_64"],
                "composition_report_ref": source.evidence_ref,
                "conversion_report_ref": source.evidence_ref,
                "install_evidence_ref": ROLE_LIFECYCLE_EVIDENCE,
                "launch_evidence_ref": ROLE_LIFECYCLE_EVIDENCE,
                "artifact_format": SETUP_FORMAT,
                "member_metadata_complete": True,
            },
        )
    )
    passport = cast(SetupVersionPassport, _sealed(body, SetupVersionPassport))
    return FirstPartyVersion(
        kind="setup",
        passport=passport,
        passport_digest=_passport_digest(passport),
        artifact=artifact,
        artifact_format=SETUP_FORMAT,
        source_tree=source.source_blob,
    )


def _build() -> tuple[FirstPartyVersion, ...]:
    corpus: list[FirstPartyVersion] = []
    for source in _sources():
        components = tuple(_component(source, item) for item in source.components)
        corpus.extend(components)
        corpus.append(_setup(source, components))
    for source in _role_sources():
        components = tuple(_component(source, item) for item in source.components)
        corpus.extend(components)
        components_by_slug = {
            item.slug: component
            for item, component in zip(source.components, components, strict=True)
        }
        corpus.extend(_role_setup(source, setup, components_by_slug) for setup in source.setups)
    return tuple(corpus)


CORPUS: Final[tuple[FirstPartyVersion, ...]] = _build()


def versions() -> tuple[FirstPartyVersion, ...]:
    """Return the ordered immutable corpus without sharing mutable containers."""

    return CORPUS
