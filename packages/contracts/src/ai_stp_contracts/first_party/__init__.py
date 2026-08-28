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
# Three constants stood here — `PI_LAYOUT_VERSION`, `CODEX_SKILLS_VERSION`,
# `CURSOR_LAYOUT_VERSION` — because a published `X.Y` is immutable and three
# families needed a corrected projection. They are gone with the objects they
# corrected: this corpus is built from a different repository and mints new
# stable identifiers, so every member is `1.0` and nothing here is a second
# attempt at an identifier somebody already holds.
PUBLISHED_AT: Final[str] = "2026-08-13T00:00:00.000Z"
COMPONENT_FORMAT: Final[str] = "ai-stp-component-tree/1"
COMPONENT_FILE_FORMAT: Final[str] = "ai-stp-component-file/1"
SETUP_FORMAT: Final[str] = "ai-stp-setup-definition/1"
PASSPORT_DIGEST_DOMAIN: Final[str] = "ai-stp:passport:v1"
ARTIFACT_DIGEST_DOMAIN: Final[str] = "ai-stp:artifact:v1"

# The compatibility names for the first Grok Build pair are gone: nothing
# outside this package imported them, and they named objects from a
# repository this corpus no longer draws on. `versions()` is the surface.


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
    #: Where the compiler projects this component, recorded by the builder
    #: from `composition.rule_for` rather than restated here. A second copy of
    #: that table lived in this module until 2026-08-29 and had already drifted
    #: from the first.
    native_path: str
    artifact_format: Literal["ai-stp-component-file/1", "ai-stp-component-tree/1"] = (
        COMPONENT_FORMAT
    )
    source_object_kind: Literal["blob", "tree"] = "tree"
    component_type: str
    projection_kind: str
    native_id: str | None = None
    name: str | None = None
    description: str | None = None


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


class _SourceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1]
    harnesses: tuple[_HarnessSource, ...]


#: Built by `release_scripts/build_first_party_corpus.py` from the seven live
#: `*-setup-system` repositories, at the commit each one's `main` carried when
#: it ran, with git's own tree and blob SHAs as provenance.
#:
#: The corpus it replaces cited five repositories that had been transferred to
#: a personal account and archived on 2026-08-25 — 120 of 126 objects. That was
#: not repairable in place: `source` and the commit are inside the
#: content-addressed passport and a published `X.Y` cannot be rewritten
#: (`REQ-2606`), so the only honest correction is different objects with new
#: identifiers. The old ones stay published and immutable; they are simply no
#: longer what this package carries.
#:
#: It cost catalogue size and the trade is deliberate: 126 objects pointing at
#: an archive become 40 with a living source. The 60 role components came from
#: `rldyour-claudecode` and `rldyour-codex`, both archived under the same
#: personal account, and there is no live repository to rebuild them from —
#: that, and not a modelling decision, is why the role corpus is gone.
def _sources() -> tuple[_HarnessSource, ...]:
    raw = files(__package__).joinpath("v1/corpus-sources.json").read_bytes()
    return _SourceManifest.model_validate_json(raw).harnesses


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
    source: _HarnessSource,
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
        "version": _version_for(source.harness_id),
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


def _version_for(harness_id: str) -> str:
    del harness_id
    return VERSION


def _component(
    source: _HarnessSource,
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
    native_path = component_source.native_path
    # Every family is built the same way now. Grok Build had a branch here from
    # when it was the only pair in the corpus and its single plugin declared no
    # conflicting path; it has four components from the same builder tree as the
    # other six harnesses, so a name and an empty conflict set written for one
    # object would have been applied to four.
    conflicts: dict[str, JsonValue] = {
        "paths": [native_path],
        "commands": [],
        "hooks": [],
        "mcp": [],
        "agents": [],
        "plugins": ([component_source.slug] if component_source.component_type == "plugin" else []),
    }
    body.update(
        {
            "name": (
                component_source.name or f"{_title(component_source.slug)} for {source.harness_id}"
            ),
            "description": (
                component_source.description
                or (
                    f"First-party {source.harness_id} {component_source.component_type} "
                    "from the exact NDDev Builder provider release."
                )
            ),
            "tags": ["code-review", "devops", "planning"],
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
                "version": component.passport.version,
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
                "version": _version_for(source.harness_id),
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
    body.update(
        cast(
            dict[str, JsonValue],
            {
                "name": f"NDDev Builder {source.harness_id} setup",
                "description": (
                    f"Exact first-party {source.harness_id} setup containing "
                    f"{len(components)} native NDDev Builder components."
                ),
                "tags": ["code-review", "devops", "planning"],
                "purpose": "Develop and validate native harness artifacts.",
                "target_role": "ai-harness-engineer",
                "supported_tasks": ["development", "validation", "release"],
                "components": refs,
                "ported_from": None,
                "related_setup_ids": [],
                "execution_profile": "full-auto",
                "supported_harness_versions": [],
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


def _build() -> tuple[FirstPartyVersion, ...]:
    corpus: list[FirstPartyVersion] = []
    for source in _sources():
        components = tuple(_component(source, item) for item in source.components)
        corpus.extend(components)
        corpus.append(_setup(source, components))
    return tuple(corpus)


CORPUS: Final[tuple[FirstPartyVersion, ...]] = _build()


def versions() -> tuple[FirstPartyVersion, ...]:
    """Return the ordered immutable corpus without sharing mutable containers."""

    return CORPUS
