"""Shared first-party launch corpus integrity (issue #162)."""

import hashlib
import io
import json
import zipfile
from importlib.resources import files
from typing import cast

from ai_stp_contracts.first_party import (
    COMPONENT_FORMAT,
    PI_LAYOUT_VERSION,
    SETUP_FORMAT,
    VERSION,
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


def test_first_party_corpus_has_exact_real_component_and_setup_bytes() -> None:
    corpus = versions()
    assert len(corpus) == 127
    expected = {
        "antigravity": (
            "https://github.com/NDDev-OpenNetwork/antigravity-setup-system",
            "96e013e068f6fe2a87c4ae708ee700520ca06f12",
            "bb5e6e8cdbcd28cf91320365068250b8f4e4ebe7",
            2,
        ),
        "claude-code": (
            "https://github.com/NDDev-it-com/nddev-claude-app",
            "4082a42f4d92653ed379721b4cd08906e5059dd5",
            "c2cefd0aeaba92d3bb627e3dd2072d6b365fc03b",
            3,
        ),
        "codex": (
            "https://github.com/NDDev-it-com/nddev-codex-app",
            "138e876616ee16bea155d00a1589f4639c45addf",
            "865839268cf62f34404659dc39ff082b25647e52",
            29,
        ),
        "cursor": (
            "https://github.com/NDDev-OpenNetwork/cursor-setup-system",
            "27b07f2edaea248ceb7348d1d10a7f2d2b8d64d8",
            "02ef1e0cec37b0f4be65aecfdecc510d782ca14f",
            3,
        ),
        "grok-build": (
            "https://github.com/NDDev-it-com/nddev-grok-build-app",
            "307e5124a1919a2224692cc8d64c50f98364ef2b",
            "2acec9e28f0aaac9a6f12e92d4d14785c9aed891",
            1,
        ),
        "opencode": (
            "https://github.com/NDDev-it-com/nddev-opencode-app",
            "ecb1380f56124867520700f0ccf9b05801293863",
            "5fa135bc7e9423e24411dc7c2187597c1e30d4e1",
            6,
        ),
        "pi": (
            "https://github.com/NDDev-it-com/nddev-pi-app",
            "2fbb9d0dff2f28076868e4f0457d7ed48aa5263f",
            "5a9e00442a82589ca8b8a98a46e9f4804a3d2174",
            4,
        ),
    }

    for harness_id, (repository, commit, setup_blob, count) in expected.items():
        components = [
            item
            for item in corpus
            if item.kind == "component"
            and item.passport.harness_id == harness_id
            and item.passport.source is not None
            and item.passport.source.repository == repository
        ]
        setups = [
            item
            for item in corpus
            if item.kind == "setup"
            and item.passport.harness_id == harness_id
            and item.passport.source is not None
            and item.passport.source.repository == repository
        ]
        assert len(components) == count
        assert len(setups) == 1
        setup = setups[0]
        assert isinstance(setup.passport, SetupVersionPassport)
        for component in components:
            assert isinstance(component.passport, ComponentVersionPassport)
            assert component.passport.source is not None
            assert component.passport.source.repository == repository
            assert component.passport.source.commit == commit
            assert component.artifact_format in {
                "ai-stp-component-file/1",
                COMPONENT_FORMAT,
            }
            assert component.passport.artifact.digest == digest_bytes(
                "ai-stp:artifact:v1", component.artifact
            )
        assert setup.passport.source is not None
        assert setup.passport.source.repository == repository
        assert setup.passport.source.commit == commit
        assert setup.source_tree == setup_blob
        assert setup.artifact_format == SETUP_FORMAT
        assert setup.passport.artifact.digest == digest_bytes("ai-stp:artifact:v1", setup.artifact)
        assert [item.stable_id for item in setup.passport.components] == [
            component.passport.stable_id for component in components
        ]
        assert [item.passport_digest for item in setup.passport.components] == [
            component.passport_digest for component in components
        ]


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
    kinds = {
        harness["harness_id"]: {component["component_type"] for component in harness["components"]}
        for harness in document["harnesses"]
    }
    assert kinds == {
        "antigravity": {"plugin", "setting"},
        "claude-code": {"skill"},
        "codex": {"skill"},
        "cursor": {"instruction", "plugin", "setting"},
        "grok-build": {"plugin"},
        "opencode": {"agent", "command", "instruction", "plugin", "skill"},
        "pi": {"instruction", "plugin", "setting", "skill"},
    }

    role_payload = (
        files("ai_stp_contracts.first_party").joinpath("v1/role-sources.json").read_bytes()
    )
    role_document = json.loads(role_payload)
    assert role_payload == canonize(cast(JsonValue, role_document))
    role_component_ids = [
        component["stable_id"]
        for harness in role_document["harnesses"]
        for component in harness["components"]
    ]
    role_setup_ids = [
        setup["stable_id"] for harness in role_document["harnesses"] for setup in harness["setups"]
    ]
    assert len(role_component_ids) == len(set(role_component_ids)) == 60
    assert len(role_setup_ids) == len(set(role_setup_ids)) == 12
    assert not set(component_ids).intersection(role_component_ids)
    assert not set(setup_ids).intersection(role_setup_ids)


def test_role_families_are_distinct_exact_harness_specific_graphs() -> None:
    corpus = versions()
    expected_sources = {
        "claude-code": (
            "https://github.com/NDDev-it-com/rldyour-claudecode",
            "7c2ec4ed669ff8d2424d9e5a65f8329092b32cd7",
            "a9ed3c37b617534dc91988662979dc0f1d58ddc7",
        ),
        "codex": (
            "https://github.com/NDDev-it-com/rldyour-codex",
            "1080ef355569d5be00ae5b8126860983779cfbea",
            "967d182c0666ca90c0a01e91903f0358707d93d1",
        ),
    }
    expected_roles = {"backend", "frontend", "full-stack", "code-review", "security", "research"}
    setup_ids: set[str] = set()
    for harness_id, (repository, commit, source_blob) in expected_sources.items():
        components = {
            item.passport.stable_id: item
            for item in corpus
            if item.kind == "component"
            and item.passport.source is not None
            and item.passport.source.repository == repository
        }
        setups = [
            item
            for item in corpus
            if item.kind == "setup"
            and item.passport.source is not None
            and item.passport.source.repository == repository
        ]
        setup_passports: list[SetupVersionPassport] = []
        for setup in setups:
            assert isinstance(setup.passport, SetupVersionPassport)
            setup_passports.append(setup.passport)
        assert {passport.target_role for passport in setup_passports} == expected_roles
        graphs = {
            tuple(ref.stable_id for ref in passport.components) for passport in setup_passports
        }
        assert len(graphs) == len(expected_roles)
        for setup in setups:
            passport = setup.passport
            assert isinstance(passport, SetupVersionPassport)
            assert passport.harness_id == harness_id
            assert passport.source is not None
            assert passport.source.commit == commit
            assert passport.source.path == "config/rldyour-contract.json"
            assert setup.source_tree == source_blob
            assert passport.supported_tasks
            assert passport.install_evidence_ref == (
                "https://github.com/ai-engineers-guild/ai_stp/issues/186"
            )
            assert passport.launch_evidence_ref == passport.install_evidence_ref
            assert passport.stable_id not in setup_ids
            setup_ids.add(passport.stable_id)
            assert all(ref.stable_id in components for ref in passport.components)
            assert [ref.passport_digest for ref in passport.components] == [
                components[ref.stable_id].passport_digest for ref in passport.components
            ]


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

    grok_component, grok_setup = [
        item for item in versions() if item.passport.harness_id == "grok-build"
    ]
    assert grok_component.passport_digest == (
        "sha256:2f3d380c28826c6a347aa1413197d80fca44b8d978f6040fa564fa7949c1b6fe"
    )
    assert grok_setup.passport_digest == (
        "sha256:edbcfd69392c9c3824f615cdce8dc105291a047ae00152644f93b8d7a4820729"
    )


def test_pi_layout_version_is_relative_to_the_harness_home() -> None:
    """Pi 1.0 treated `agent/` as a directory inside `~/.pi/agent`.

    The target already ends in `agent`, so those passports resolved to
    `~/.pi/agent/agent/AGENTS.md`. Provider rules were fixed in place; the
    corpus cannot rewrite `1.0`. This is the `1.1` that names the same objects
    with paths relative to the home.
    """
    pi = [item for item in versions() if item.passport.harness_id == "pi"]
    others = [item for item in versions() if item.passport.harness_id != "pi"]
    assert {item.passport.version for item in pi} == {PI_LAYOUT_VERSION}
    assert {item.passport.version for item in others} == {VERSION}
    for item in pi:
        if item.kind != "component":
            continue
        passport = item.passport
        assert isinstance(passport, ComponentVersionPassport)
        assert passport.managed_paths
        assert all(not path.startswith("agent/") for path in passport.managed_paths), (
            passport.managed_paths
        )
        assert list(passport.managed_paths) == list(passport.conflicts.paths)
