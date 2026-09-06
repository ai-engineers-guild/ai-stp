"""Exact first-party launch objects shared by the CLI and platform."""

from __future__ import annotations

import io
import zipfile
from importlib.resources import files
from pathlib import PurePosixPath
from typing import Final, Literal, cast

from pydantic import BaseModel, ConfigDict

from ai_stp_foundation.canonical import JsonValue, canonize, from_json_bytes
from ai_stp_foundation.digests import digest_bytes, digest_canonical
from ai_stp_foundation.provider_surfaces import provider_surface
from ai_stp_passports.envelope import seal_envelope, verify_revision_id
from ai_stp_passports.projections import build_projection
from ai_stp_passports.versions import (
    ComponentVersionPassport,
    ScopeAdaptation,
    SetupVersionPassport,
    seal_adaptation,
)

OWNER_ID: Final[str] = "account_01KZET6ZKJN7S72T5H4WDV62T0"
# Three constants stood here — `PI_LAYOUT_VERSION`, `CODEX_SKILLS_VERSION`,
# `CURSOR_LAYOUT_VERSION` — because a published `X.Y` is immutable and three
# families needed a corrected projection. They were replaced by a single `1.0`
# for every member, argued from a premise that was true when written: the corpus
# had just been rebuilt from a different repository and minted fresh identifiers,
# so nothing here was a second attempt at an id somebody already held.
#
# Identity continuity made that false without changing the sentence. Measured
# against the deployed catalogue on 2026-08-30: 40 of 98 objects were held
# identities standing at `1.0`, already published, and all 40 had different
# passport bytes. A constant cannot express that, because the answer differs per
# object: what moved needs a new version and what did not must keep its own.
#
# So the version is recorded per object by the builder and read from the
# manifest here. There is no corpus-wide constant left to drift.
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


class FirstPartyCatalogMember(BaseModel):
    """One component identity a catalog projection may vendor without minting ids."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    stable_id: str
    version: str
    passport_digest: str
    adaptation_id: str


class FirstPartyCatalogIdentity(BaseModel):
    """Compact first-party catalog identity derived from corpus passports (A14).

    A provider local catalog historically recorded an id and a description.
    This object is the identity set a compiled bundle already carries, so the
    two channels can agree without inventing identifiers at install time.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    harness_id: str
    posture: str
    setup_id: str
    setup_version: str
    setup_passport_digest: str
    component_refs: tuple[FirstPartyCatalogMember, ...]


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
    #: This object's own version, not a corpus-wide constant. A published `X.Y`
    #: is immutable, so an object whose passport changed must go out as a new
    #: one while its unchanged siblings keep theirs.
    version: str = "1.0"


class _HarnessSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    harness_id: str
    setup_id: str
    setup_version: str = "1.0"
    #: The published axis: `minimal`, `baseline`, `full-auto`, `nddev-builder`,
    #: read from `setup.json`'s own `"id"` by the builder. `ADR-0130`.
    posture: str
    repository: str
    commit: str
    setup_path: str
    setup_blob: str
    #: Published prose, carried whole and never composed here. `full-auto` runs
    #: to thousands of characters and is load-bearing safety context — it names
    #: things like the sandbox key reaching nothing on native Windows — so a
    #: browse card may clamp it and an install surface may not.
    setup_description: str
    #: An empty list is a statement, not an omission: five of the seven
    #: `minimal` setups set no product keys, so there is nothing to source.
    setup_sources: tuple[str, ...] = ()
    evidence_ref: str
    #: What the provider declares, asked of the released binary at build time.
    #: These were `["linux"]` and `["x86_64"]` written into the setup body until
    #: 2026-08-29, understating all seven at once — every provider declares three
    #: systems and two architectures.
    supported_os: tuple[str, ...]
    supported_arch: tuple[str, ...]
    components: tuple[_ComponentSource, ...]


class _SourceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1]
    harnesses: tuple[_HarnessSource, ...]


class _ScopePolicy(BaseModel):
    """Explicit scope assignment for every harness in this corpus generation."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1]
    harness_scopes: dict[str, Literal["global", "user_root", "project"]]


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


def _scopes() -> dict[str, Literal["global", "user_root", "project"]]:
    raw = files(__package__).joinpath("v1/scope-policy.json").read_bytes()
    return _ScopePolicy.model_validate_json(raw).harness_scopes


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
    version: str,
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
        "version": version,
        "source": {
            "repository": source.repository,
            "commit": source.commit,
            "path": source_path,
        },
        "artifact": {
            "digest": digest_bytes(ARTIFACT_DIGEST_DOMAIN, artifact),
            "size_bytes": len(artifact),
        },
        "required_env": [],
        "requires_credentials": False,
        "requires_authorization": "none",
        "permissions": {"filesystem": [], "network": [], "process": []},
        "external_endpoints": [],
        "license": {"spdx_id": "AGPL-3.0-or-later", "redistribution_allowed": True},
        "compatibility_evidence_refs": [source.evidence_ref],
    }


def _component_name(slug: str, harness_id: str, posture: str) -> str:
    """The file's own name, the harness, and the posture it belongs to.

    The slug used to be title-cased on `-` boundaries, which produced
    `Agents.Md for pi` and `Nddev Setup.Md for pi`. A slug is a **filename in
    somebody else's tree**, not a phrase: `AGENTS.md` is what that ecosystem
    calls the file, and title-casing it invents a name that exists in no source
    — the same defect as `ADR-0130`'s invented role, one size smaller.

    The posture is here because the same slug now appears in up to four setups
    of one harness as four separate objects, and a catalogue of four identically
    named cards is a list nobody can choose from.
    """
    return f"{slug} — {harness_id} {posture}"


def _source_members(
    component_source: _ComponentSource,
    artifact: bytes,
) -> tuple[tuple[str, bytes, int], ...]:
    """Decode the captured source artifact into explicit native projection files."""
    if component_source.artifact_format == COMPONENT_FILE_FORMAT:
        return ((component_source.native_path, artifact, 0o644),)
    with zipfile.ZipFile(io.BytesIO(artifact), mode="r") as archive:
        manifest = from_json_bytes(archive.read("component.json"))
        if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
            raise RuntimeError("a first-party component tree manifest is invalid")
        answer: list[tuple[str, bytes, int]] = []
        manifest_files = cast(list[JsonValue], manifest["files"])
        for raw in manifest_files:
            if not isinstance(raw, dict):
                raise RuntimeError("a first-party component tree member is invalid")
            member = cast(dict[str, JsonValue], raw)
            path = member.get("path")
            mode = member.get("mode")
            if not isinstance(path, str) or not isinstance(mode, int) or isinstance(mode, bool):
                raise RuntimeError("a first-party component tree member identity is invalid")
            native_path = str(PurePosixPath(component_source.native_path, path))
            answer.append((native_path, archive.read(f"files/{path}"), mode))
        return tuple(answer)


def _adaptation(
    source: _HarnessSource,
    component_source: _ComponentSource,
    source_artifact: bytes,
) -> tuple[bytes, JsonValue]:
    """Build one native, scope-explicit adaptation and its canonical projection."""
    members = _source_members(component_source, source_artifact)
    surface = provider_surface(source.harness_id, _scopes()[source.harness_id])  # type: ignore[arg-type, index]
    native_id = component_source.native_id or component_source.slug
    member_documents: list[JsonValue] = [
        {
            "path": path,
            "object_type": "file",
            "mode": mode,
            "content_artifact": {
                "digest": digest_bytes(ARTIFACT_DIGEST_DOMAIN, content),
                "size_bytes": len(content),
            },
            "native_ids": [native_id],
            "content_format": "application/octet-stream",
            "parser_id": None,
            "ownership": "whole",
            "ownership_key": None,
            "write_semantics": "replace",
            "withdrawal_semantics": "remove_path",
        }
        for path, content, mode in members
    ]
    scope_document: dict[str, JsonValue] = {
        "scope": _scopes()[source.harness_id],
        "projection_format": "ai-stp-adaptation-projection/1",
        "projection_artifact": {"digest": "sha256:" + "0" * 64, "size_bytes": 1},
        "provider_component_kind": component_source.component_type,
        "projection_kind": component_source.projection_kind,
        "required_surface": {
            "profile_id": surface.profile_id,
            "profile_digest": surface.profile_digest,
            "bundle_format": surface.bundle_format,
        },
        "permissions": {"filesystem": [], "network": [], "process": []},
        "members": member_documents,
        "supported_harness_versions": [],
        "supported_os": list(source.supported_os),
        "supported_arch": list(source.supported_arch),
        "technical_support": "supported",
        "technical_support_reason": None,
        "semantic_losses": [],
    }
    contents = {path: content for path, content, _mode in members}
    provisional = ScopeAdaptation.model_validate(scope_document)
    projection = build_projection(provisional, contents)
    scope_document["projection_artifact"] = {
        "digest": digest_bytes(ARTIFACT_DIGEST_DOMAIN, projection),
        "size_bytes": len(projection),
    }
    scope = ScopeAdaptation.model_validate(scope_document)
    projection = build_projection(scope, contents)
    adaptation = seal_adaptation(
        {
            "harness_id": source.harness_id,
            "implementation_mode": "native",
            "source_artifact": None,
            "transform": None,
            "logical_component_type": component_source.component_type,
            "scope_adaptations": [cast(JsonValue, scope.model_dump(mode="json"))],
        }
    )
    return projection, cast(JsonValue, adaptation.model_dump(mode="json"))


def _component(
    source: _HarnessSource,
    component_source: _ComponentSource,
) -> FirstPartyVersion:
    source_artifact = (
        files(__package__).joinpath(f"v1/{component_source.artifact_name}").read_bytes()
    )
    artifact, adaptation = _adaptation(source, component_source, source_artifact)
    body = _common(
        source,
        kind="component",
        stable_id=component_source.stable_id,
        source_path=component_source.source_path,
        artifact=artifact,
        version=component_source.version,
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
                component_source.name
                or _component_name(component_source.slug, source.harness_id, source.posture)
            ),
            "description": (
                component_source.description
                or (
                    f"First-party {source.harness_id} {component_source.component_type}, "
                    f"exactly as the {source.posture} setup publishes it."
                )
            ),
            "tags": ["code-review", "devops", "planning"],
            "component_type": component_source.component_type,
            "origin_harness_id": source.harness_id,
            "adaptations": [adaptation],
            "provides_capabilities": [],
            "requires_components": [],
            "requires_capabilities": [],
            "conflicts": conflicts,
            "artifact_format": "ai-stp-adaptation-projection/1",
            "source_tree": component_source.source_tree,
        }
    )
    passport = cast(ComponentVersionPassport, _sealed(body, ComponentVersionPassport))
    return FirstPartyVersion(
        kind="component",
        passport=passport,
        passport_digest=_passport_digest(passport),
        artifact=artifact,
        artifact_format="ai-stp-adaptation-projection/1",
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
                "version": source.setup_version,
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
        version=source.setup_version,
    )
    # The vendor pages the posture was read from, after the repository. They are
    # what says this configuration is valid for this harness, which is what this
    # field is for, and both setup pages render it — so `sources` reaching the
    # catalogue means reaching a reader, not only the manifest. An empty list
    # stays empty: five of the seven `minimal` setups set no product keys, so
    # there is nothing to source, and that is a statement rather than a gap.
    body["compatibility_evidence_refs"] = [
        source.evidence_ref,
        *(ref for ref in source.setup_sources if ref != source.evidence_ref),
    ]
    body.update(
        cast(
            dict[str, JsonValue],
            {
                "harness_id": source.harness_id,
                # Name and description come from the source. They were composed
                # here until 2026-08-30, and the composition said "NDDev Builder"
                # about all four postures because only one was ever read.
                "name": f"{source.harness_id} {source.posture}",
                "description": source.setup_description,
                "tags": ["code-review", "devops", "planning"],
                "purpose": source.setup_description,
                # No `target_role`. A role is a claim about content that no
                # vendor page can source, and the publishing side does not
                # publish roles — by decision, not omission. This field held
                # `ai-harness-engineer`, a string that appears in no file of
                # theirs and rendered on every card as a claim about their
                # artifact. `ADR-0130`.
                "target_role": None,
                "posture": source.posture,
                "supported_tasks": ["development", "validation", "release"],
                "components": refs,
                "ported_from": None,
                "related_setup_ids": [],
                "execution_profile": "full-auto",
                "supported_harness_versions": [],
                "supported_os": list(source.supported_os),
                "supported_arch": list(source.supported_arch),
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


def family(harness_id: str, posture: str) -> tuple[FirstPartyVersion, ...]:
    """One published setup and exactly its own members.

    A setup is a `(harness_id, posture)` since `ADR-0130`, so selecting on the
    harness alone returns four setups and all four postures' components. Every
    caller that wanted "the grok-build setup and its parts" wanted this, and got
    the right answer only while one posture of four was imported.

    Membership is read off the component's own source path, whose first segment
    is the posture directory the bytes came from — the same fact the setup's
    pins carry, taken from the side that cannot disagree with itself.
    """
    found = tuple(
        item
        for item in versions()
        if (
            item.passport.harness_id == harness_id
            if isinstance(item.passport, SetupVersionPassport)
            else any(
                adaptation.harness_id == harness_id for adaptation in item.passport.adaptations
            )
        )
        and (
            item.passport.posture == posture
            if isinstance(item.passport, SetupVersionPassport)
            else item.passport.source is not None
            and item.passport.source.path.split("/", 1)[0] == posture
        )
    )
    # An empty family is refused rather than returned. Every caller is about to
    # loop over this, and a filter that selects nothing produces output
    # identical to one that selects correctly — the loop runs zero times and
    # whatever it asserts is never asked. That exact defect shipped here: a test
    # selecting setups by a role no setup carried looped over an empty list and
    # stayed green for as long as it existed.
    #
    # Refusing at the boundary is stronger than asking each caller to check,
    # because a caller that forgets is invisible and this is not.
    if not found:
        raise LookupError(f"the first-party corpus has no {harness_id} objects in {posture!r}")
    return found


def catalog_identity(harness_id: str, posture: str) -> FirstPartyCatalogIdentity:
    """Return the catalog identity already sealed in the corpus for this pair."""
    members = family(harness_id, posture)
    setup = next(item for item in members if item.kind == "setup")
    if not isinstance(setup.passport, SetupVersionPassport):
        raise LookupError(f"{harness_id} {posture} has no setup passport")
    refs: list[FirstPartyCatalogMember] = []
    for item in members:
        if item.kind != "component":
            continue
        if not isinstance(item.passport, ComponentVersionPassport):
            raise LookupError(f"{item.passport.stable_id} is not a component passport")
        refs.append(
            FirstPartyCatalogMember(
                stable_id=item.passport.stable_id,
                version=item.passport.version,
                passport_digest=item.passport_digest,
                adaptation_id=item.passport.adaptations[0].adaptation_id,
            )
        )
    return FirstPartyCatalogIdentity(
        harness_id=setup.passport.harness_id,
        posture=setup.passport.posture or posture,
        setup_id=setup.passport.stable_id,
        setup_version=setup.passport.version,
        setup_passport_digest=setup.passport_digest,
        component_refs=tuple(refs),
    )


def catalog_identities() -> tuple[FirstPartyCatalogIdentity, ...]:
    """One identity per published first-party setup, in corpus order."""
    return tuple(
        catalog_identity(item.passport.harness_id, item.passport.posture or "")
        for item in versions()
        if item.kind == "setup" and isinstance(item.passport, SetupVersionPassport)
    )
