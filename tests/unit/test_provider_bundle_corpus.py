"""Provider conformance uses literal, content-addressed hostile ZIP artifacts."""

import hashlib
import json
import os
import stat
import zipfile
from pathlib import Path
from typing import cast

from ai_stp_cli.local import bundle
from ai_stp_cli.provider import bundle_corpus, protocol
from ai_stp_foundation.canonical import JsonValue, from_json_bytes
from ai_stp_passports import SetupVersionPassport


def _manifest(path: Path) -> dict[str, JsonValue]:
    with zipfile.ZipFile(path) as archive:
        return cast(dict[str, JsonValue], json.loads(archive.read("bundle.json")))


def _names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return archive.namelist()


def test_corpus_paths_and_bindings_name_the_literal_zip_bytes() -> None:
    held_paths: list[Path] = []
    with bundle_corpus.materialized(
        protocol_version=protocol.VERSION, harness_id="claude-code"
    ) as corpus:
        bindings = (corpus.valid, *(case.binding for case in corpus.malicious))
        for binding in bindings:
            held_paths.append(binding.path)
            payload = binding.path.read_bytes()
            assert binding.path.is_absolute()
            assert binding.path.name == hashlib.sha256(payload).hexdigest() + ".zip"
            assert binding.artifact_digest == "sha256:" + hashlib.sha256(payload).hexdigest()
            assert binding.bundle_size == len(payload)
            if os.name != "nt":
                assert binding.path.stat().st_mode & 0o777 == 0o600
            assert _manifest(binding.path)["bundle_digest"] == binding.bundle_digest
    assert all(not path.exists() for path in held_paths)


def test_valid_corpus_artifact_has_the_canonical_member_shape() -> None:
    with (
        bundle_corpus.materialized(
            protocol_version=protocol.VERSION, harness_id="claude-code"
        ) as corpus,
        zipfile.ZipFile(corpus.valid.path) as archive,
    ):
        assert archive.namelist() == [
            "bundle.json",
            "setup-passport.json",
            "composition-report.json",
            "conversion-report.json",
            "files/",
            "files/config.md",
            "attestations/",
        ]
        manifest = cast(dict[str, JsonValue], json.loads(archive.read("bundle.json")))
        assert manifest["protocol_version"] == protocol.VERSION
        assert manifest["harness_id"] == "claude-code"
        passport = SetupVersionPassport.model_validate(
            from_json_bytes(archive.read("setup-passport.json"))
        )
        assert passport.harness_id == "claude-code"
        assert archive.read("files/config.md") == b"safe\n"


def test_malicious_corpus_encodes_each_attack_in_the_zip_or_manifest() -> None:
    with bundle_corpus.materialized(
        protocol_version=protocol.VERSION, harness_id="claude-code"
    ) as corpus:
        cases = {case.name: case.binding.path for case in corpus.malicious}

        assert "files/../outside.md" in _names(cases["path_escapes_target"])
        assert "/etc/passwd" in _names(cases["path_not_relative"])
        duplicate = _names(cases["path_duplicate"])
        assert duplicate.count("files/hostile.md") == 2

        with zipfile.ZipFile(cases["symbolic_link_not_allowed"]) as archive:
            mode = archive.getinfo("files/hostile.md").external_attr >> 16
            assert stat.S_ISLNK(mode)
        with zipfile.ZipFile(cases["special_file_not_allowed"]) as archive:
            mode = archive.getinfo("files/hostile.md").external_attr >> 16
            assert stat.S_ISFIFO(mode)

        hardlink = cast(
            list[dict[str, JsonValue]], _manifest(cases["hard_link_not_allowed"])["files"]
        )
        assert hardlink[0]["kind"] == "hardlink"
        limited = cast(list[dict[str, JsonValue]], _manifest(cases["limit_exceeded"])["files"])
        assert limited[0]["byte_length"] == bundle.MAX_FILE_BYTES + 1
        unknown = cast(
            list[dict[str, JsonValue]], _manifest(cases["unknown_native_surface"])["files"]
        )
        assert unknown[0]["surface"] == "unknown"
        mismatched = cast(list[dict[str, JsonValue]], _manifest(cases["digest_mismatch"])["files"])
        assert mismatched[0]["digest"] == "sha256:" + "0" * 64
        assert (
            _manifest(cases["unsupported_protocol_version"])["protocol_version"]
            == protocol.VERSION + 1
        )
