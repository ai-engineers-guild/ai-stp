"""Shared first-party launch corpus integrity (issue #162)."""

import hashlib
import io
import json
import zipfile
from importlib.resources import files
from typing import cast

from release_scripts import build_first_party_corpus as builder

from ai_stp_cli.local import composition
from ai_stp_contracts.first_party import (
    COMPONENT_FORMAT,
    SETUP_FORMAT,
    versions,
)
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes
from ai_stp_passports.envelope import verify_revision_id
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
    assert {item.passport.harness_id for item in setups} == set(REPOSITORIES)

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
        assert item.passport.source.repository == REPOSITORIES[item.passport.harness_id]
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
            if item.passport.harness_id == setup.passport.harness_id
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
        rule = composition.rule_for(passport.component_type, passport.harness_id)
        assert rule is not None, (passport.harness_id, passport.component_type)
        managed = list(passport.managed_paths)
        assert len(managed) == 1
        path = managed[0]
        if rule.shape == "file":
            assert path == rule.relative
        else:
            assert path.startswith(f"{rule.relative}/")
            assert path.count("/") == rule.relative.count("/") + 1
        assert passport.projection_kind == rule.projection_kind


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


def test_a_republished_object_carries_a_new_version_and_a_new_one_does_not() -> None:
    """A single corpus-wide version stood here and was true only while nothing was reused.

    Three per-family constants — `pi` 1.1, `codex` 1.1, `cursor` 1.1 — existed
    because a published `X.Y` is immutable (`REQ-2606`) and three families had a
    projection corrected. They were replaced by one `1.0` for every member, on
    the argument that a rebuild from a different repository mints fresh
    identifiers and so nothing could be a second attempt at an id somebody held.

    Identity continuity made that false without changing the sentence. Measured
    against the deployed catalogue on 2026-08-30: 40 of 98 objects were held
    identities standing at `1.0`, already published, and all 40 had different
    passport bytes.

    So the assertion is no longer "one version" — it is that both cases exist and
    neither has swallowed the other. A corpus with a single version now means
    either nothing was ever republished or nothing new was ever added, and both
    would be worth failing on.
    """
    seen = {item.passport.version for item in versions()}
    assert seen == {"1.0", "1.1"}, seen

    held = {item.passport.stable_id for item in versions() if item.passport.version != "1.0"}
    # Exactly the objects the previous corpus published, and nothing else: a new
    # object's first version is `1.0` (`versions.FIRST_VERSION`), and a bump it
    # did not earn would put it in the catalogue as a second attempt at itself.
    assert len(held) == 40, len(held)


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


def test_first_party_component_archives_are_closed_and_match_their_manifests() -> None:
    for component in (item for item in versions() if item.kind == "component"):
        if component.artifact_format == "ai-stp-component-file/1":
            assert _git_object("blob", component.artifact).hex() == component.source_tree
            continue
        assert component.artifact_format == COMPONENT_FORMAT
        with zipfile.ZipFile(io.BytesIO(component.artifact)) as archive:
            names = archive.namelist()
            assert names == sorted(names)
            assert names[0] == "component.json"
            assert any(name.endswith("plugin.json") or name.endswith("SKILL.md") for name in names)
            manifest = json.loads(archive.read("component.json"))
            assert archive.read("component.json") == canonize(cast(JsonValue, manifest))
            declared = {f"files/{item['path']}" for item in manifest["files"]}
            assert set(names) == {"component.json", *declared}
            git_entries: dict[str, tuple[int, bytes]] = {}
            for item in manifest["files"]:
                payload = archive.read(f"files/{item['path']}")
                assert len(payload) == item["byte_length"]
                assert digest_bytes("ai-stp:artifact:v1", payload) == item["digest"]
                git_entries[item["path"]] = (item["mode"], payload)
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
