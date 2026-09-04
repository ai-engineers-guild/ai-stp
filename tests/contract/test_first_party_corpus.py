"""Shared first-party launch corpus integrity (issue #162)."""

import hashlib
import io
import json
import posixpath
import zipfile
from importlib.resources import files
from typing import cast

from release_scripts import build_first_party_corpus as builder

from ai_stp_cli.local import composition
from ai_stp_contracts.first_party import SETUP_FORMAT, versions
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes
from ai_stp_passports.envelope import verify_revision_id
from ai_stp_passports.projections import verify_projection
from ai_stp_passports.versions import ComponentVersionPassport, SetupVersionPassport


def _git_object(kind: str, payload: bytes) -> bytes:
    return hashlib.sha1(f"{kind} {len(payload)}\0".encode() + payload).digest()


def _git_tree(entries: dict[str, tuple[int, bytes]]) -> str:
    """Reconstruct the exact Git tree identity carried by one component ZIP."""
    root: dict[str, object] = {}
    for path, value in entries.items():
        cursor = root
        parts = path.split("/")
        for part in parts[:-1]:
            cursor = cast(dict[str, object], cursor.setdefault(part, {}))
        cursor[parts[-1]] = value

    def digest(tree: dict[str, object]) -> bytes:
        payload = bytearray()
        for name in sorted(tree, key=lambda item: item.encode()):
            value = tree[name]
            if isinstance(value, dict):
                mode = "40000"
                identity = digest(cast(dict[str, object], value))
            else:
                file_mode, content = cast(tuple[int, bytes], value)
                mode = "100755" if file_mode & 0o111 else "100644"
                identity = _git_object("blob", content)
            payload.extend(f"{mode} {name}\0".encode())
            payload.extend(identity)
        return _git_object("tree", bytes(payload))

    return digest(root).hex()


#: One live repository per harness. The commit is deliberately not pinned: the
#: corpus is rebuilt from each setup-system's `main`, so a pinned commit would
#: make this fail on somebody else's push rather than on a defect of ours.
REPOSITORIES = {
    "antigravity": "https://github.com/NDDev-OpenNetwork/antigravity-setup-system",
    "claude-code": "https://github.com/NDDev-OpenNetwork/claude-setup-system",
    "codex": "https://github.com/NDDev-OpenNetwork/codex-setup-system",
    "cursor": "https://github.com/NDDev-OpenNetwork/cursor-setup-system",
    "grok-build": "https://github.com/NDDev-OpenNetwork/grok-setup-system",
    "opencode": "https://github.com/NDDev-OpenNetwork/opencode-setup-system",
    "pi": "https://github.com/NDDev-OpenNetwork/pi-setup-system",
}


def _component_harness(passport: ComponentVersionPassport) -> str:
    assert len(passport.adaptations) == 1
    return passport.adaptations[0].harness_id


def test_every_first_party_object_names_the_live_repository_of_its_harness() -> None:
    """The corpus this replaced cited an estate transferred and archived.

    120 of its 126 objects named repositories that had moved to a personal
    account on 2026-08-25. Nothing was broken by it — the bytes are embedded and
    the recorded tree still identifies them — but a redirect is not a
    correction, and `source` sits inside a content-addressed passport, so it was
    never editable. These are different objects with new identifiers, built from
    the seven live setup-systems.
    """
    corpus = versions()
    components = [item for item in corpus if item.kind == "component"]
    setups = [item for item in corpus if item.kind == "setup"]

    assert len(corpus) == len(components) + len(setups)
    assert {
        item.passport.harness_id
        for item in setups
        if isinstance(item.passport, SetupVersionPassport)
    } == set(REPOSITORIES)

    # One setup per harness *per posture*, and the pair is asserted rather than
    # the count. `len(setups) == len(REPOSITORIES)` held while one posture of
    # four was imported, and a count would have been satisfied by any 28 —
    # including 28 of the same posture.
    setup_passports = [
        item.passport for item in setups if isinstance(item.passport, SetupVersionPassport)
    ]
    assert len(setup_passports) == len(setups)
    pairs = {(passport.harness_id, passport.posture) for passport in setup_passports}
    assert pairs == {(harness, posture) for harness in REPOSITORIES for posture in builder.POSTURES}
    assert len(setups) == len(pairs)

    # No setup carries a role, because no source publishes one. The invented
    # `ai-harness-engineer` rendered on every card until `ADR-0130`.
    assert {passport.target_role for passport in setup_passports} == {None}

    for item in corpus:
        assert item.passport.source is not None
        harness_id = (
            item.passport.harness_id
            if isinstance(item.passport, SetupVersionPassport)
            else _component_harness(item.passport)
        )
        assert item.passport.source.repository == REPOSITORIES[harness_id]
        assert len(item.passport.source.commit) == 40
        assert set(item.passport.source.commit) <= set("0123456789abcdef")
        assert item.passport.artifact.digest == digest_bytes("ai-stp:artifact:v1", item.artifact)

    for setup in setups:
        assert isinstance(setup.passport, SetupVersionPassport)
        assert setup.artifact_format == SETUP_FORMAT
        # By harness **and** posture. Selecting on the harness alone held while
        # one posture was imported and silently made every setup of a harness
        # claim all four postures' components once four were.
        members = [
            item
            for item in components
            if isinstance(item.passport, ComponentVersionPassport)
            and _component_harness(item.passport) == setup.passport.harness_id
            and item.passport.source is not None
            and item.passport.source.path.split("/", 1)[0] == setup.passport.posture
        ]
        assert members
        assert [item.stable_id for item in setup.passport.components] == [
            item.passport.stable_id for item in members
        ]
        assert [item.passport_digest for item in setup.passport.components] == [
            item.passport_digest for item in members
        ]
        # Every member of a setup carries the commit its setup does: one repository
        # read once, not seven reads that happened to agree.
        assert {item.passport.source.commit for item in members if item.passport.source} == {
            setup.passport.source.commit if setup.passport.source else None
        }


def test_the_corpus_projects_where_the_compiler_projects() -> None:
    """The pairing that has drifted three times, asserted instead of assumed.

    This module carried its own copy of the projection table until 2026-08-29,
    and by then it disagreed with `PROVIDER_RULES` — cursor's plugin was
    `plugins/local` in one and `plugins` in the other. A corpus whose managed
    path is not the path the compiler will write installs verified and invisible,
    which is exactly what happened to 61 codex skills.

    So the corpus records what the rule produced, and this is what checks it.
    """
    for item in versions():
        if item.kind != "component":
            continue
        passport = item.passport
        assert isinstance(passport, ComponentVersionPassport)
        adaptation = passport.adaptations[0]
        scope = adaptation.scope_adaptations[0]
        rule = composition.rule_for(
            passport.component_type, adaptation.harness_id, scope=scope.scope
        )
        assert rule is not None, (adaptation.harness_id, passport.component_type)
        for member in scope.members:
            if rule.shape == "file":
                assert member.path == rule.relative
            else:
                assert member.path.startswith(f"{rule.relative}/")
        assert scope.projection_kind == rule.projection_kind


def test_a_setup_publishes_the_platform_set_its_provider_declared() -> None:
    """The claim came from a literal until 2026-08-29 and understated all seven.

    `"supported_os": ["linux"]` and `"supported_arch": ["x86_64"]` were written
    into the setup body, while every one of the seven providers declares three
    operating systems and two architectures. So each published setup told a
    reader it could not be installed on the two systems it works on — for as
    long as the value had existed, because nothing ever compared it to the
    provider that owns it.

    The builder now asks the released binary and records the answer beside the
    commit; this is what stops the literal coming back. There is deliberately no
    fallback in the builder: a default that stands in when the question cannot be
    asked is the copy returning under another name.
    """
    document = json.loads(
        files("ai_stp_contracts.first_party").joinpath("v1/corpus-sources.json").read_bytes()
    )
    declared = {
        item["harness_id"]: (tuple(item["supported_os"]), tuple(item["supported_arch"]))
        for item in document["harnesses"]
    }
    assert set(declared) == set(REPOSITORIES)

    for item in versions():
        if item.kind != "setup":
            continue
        passport = item.passport
        assert isinstance(passport, SetupVersionPassport)
        systems, machines = declared[passport.harness_id]
        assert tuple(passport.supported_os) == systems, passport.harness_id
        assert tuple(passport.supported_arch) == machines, passport.harness_id
        assert systems and machines


def test_republished_objects_advance_without_flattening_version_lines() -> None:
    """A corpus-wide profile cutover advances every independently evolving line."""
    seen = {item.passport.version for item in versions()}
    assert all(int(version.split(".", 1)[1]) >= 1 for version in seen), seen
    assert len(seen) > 1, seen


def test_first_party_source_manifest_is_canonical_closed_and_unique() -> None:
    payload = files("ai_stp_contracts.first_party").joinpath("v1/corpus-sources.json").read_bytes()
    document = json.loads(payload)
    assert payload == canonize(cast(JsonValue, document))
    assert set(document) == {"schema_version", "harnesses"}
    assert document["schema_version"] == 1
    component_ids = [
        component["stable_id"]
        for harness in document["harnesses"]
        for component in harness["components"]
    ]
    setup_ids = [harness["setup_id"] for harness in document["harnesses"]]
    assert len(component_ids) == len(set(component_ids))
    assert len(setup_ids) == len(set(setup_ids))
    assert not set(component_ids) & set(setup_ids)
    assert {harness["harness_id"] for harness in document["harnesses"]} == set(REPOSITORIES)

    # `role-sources.json` was the other half and is gone. Its 60 components and
    # 12 setups came from two repositories archived under a personal account,
    # and there is no live source to rebuild them from — so they are withdrawn
    # rather than re-seeded from an archive.
    assert not files("ai_stp_contracts.first_party").joinpath("v1/role-sources.json").is_file()


def test_first_party_component_archives_are_closed_and_match_their_adaptations() -> None:
    for component in (item for item in versions() if item.kind == "component"):
        assert isinstance(component.passport, ComponentVersionPassport)
        adaptation = component.passport.adaptations[0]
        scope = adaptation.scope_adaptations[0]
        assert component.artifact_format == "ai-stp-adaptation-projection/1"
        verify_projection(scope, component.artifact)
        with zipfile.ZipFile(io.BytesIO(component.artifact)) as archive:
            rule = composition.rule_for(
                component.passport.component_type, adaptation.harness_id, scope=scope.scope
            )
            assert rule is not None
            git_entries: dict[str, tuple[int, bytes]] = {}
            common_root = posixpath.commonpath([member.path for member in scope.members])
            if len(scope.members) == 1:
                common_root = posixpath.dirname(common_root)
                for member in scope.members:
                    payload = archive.read(member.path)
                    if (
                        len(scope.members) == 1
                        and _git_object("blob", payload).hex() == component.source_tree
                    ):
                        assert _git_object("blob", payload).hex() == component.source_tree
                    else:
                        relative = member.path.removeprefix(f"{common_root}/")
                        git_entries[relative] = (member.mode, payload)
                if git_entries:
                    assert _git_tree(git_entries) == component.source_tree


def test_first_party_passports_are_complete_public_immutable_snapshots() -> None:
    for item in versions():
        passport = item.passport
        assert passport.visibility == "public"
        assert passport.source is not None
        assert passport.source.path
        assert passport.tags
        assert passport.license.spdx_id == "AGPL-3.0-or-later"
        assert passport.license.redistribution_allowed is True
        assert passport.compatibility_evidence_refs
        assert verify_revision_id(passport)
        assert item.passport_digest == digest_bytes(
            "ai-stp:passport:v1",
            canonize(cast(JsonValue, passport.model_dump(mode="json"))),
        )
