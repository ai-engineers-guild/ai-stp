"""The bundle: one input, one digest — and every prohibited shape refused."""

import io
import re
import stat
import zipfile
from pathlib import Path

import pytest

from ai_stp_cli.local import bundle
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical

CONTRACT = Path("docs/contracts/harness-bundle.md")
SETUP_PASSPORT: dict[str, JsonValue] = {
    "schema_version": 1,
    "kind": "setup",
    "stable_id": "setup_01J0000000000000000000000A",
}

BUILD: dict[str, object] = {
    "setup_stable_id": "setup_01J0000000000000000000000A",
    "setup_version": "1.0",
    "setup_digest": digest_canonical(bundle.PASSPORT_DOMAIN, SETUP_PASSPORT),
    "harness_id": "claude-code",
    "declared_paths": frozenset[str](),
    "setup_passport": SETUP_PASSPORT,
    "composition_report": {"chosen": []},
    "conversion_report": {"entries": []},
    "input_digest": "sha256:" + "b" * 64,
}


def _compile(sources: tuple[bundle.Source, ...], **overrides: object) -> bundle.Bundle:
    return bundle.compile_bundle(sources, **{**BUILD, **overrides})  # pyright: ignore[reportArgumentType]


def _codes(compiled: bundle.Bundle) -> tuple[str, ...]:
    return tuple(item.code for item in compiled.refusals)


def test_a_plain_composition_compiles() -> None:
    compiled = _compile(
        (
            bundle.Source("skills/a.md", b"first", "component_a"),
            bundle.Source("skills/b.md", b"second", "component_b"),
        )
    )
    assert compiled.compiled
    assert [item.path for item in compiled.files] == ["skills/a.md", "skills/b.md"]
    assert compiled.digest.startswith("sha256:")
    assert compiled.artifact_digest.startswith("sha256:")
    assert compiled.archive.startswith(b"PK\x03\x04")


def test_the_archive_contains_the_complete_contract_layout_and_exact_bytes() -> None:
    source = bundle.Source("skills/café.md", b"exact bytes\n", "component_a")
    compiled = _compile((source,))

    with zipfile.ZipFile(io.BytesIO(compiled.archive)) as archive:
        assert archive.namelist() == [
            "bundle.json",
            "setup-passport.json",
            "composition-report.json",
            "conversion-report.json",
            "files/",
            "files/skills/café.md",
            "attestations/",
        ]
        assert archive.read("files/skills/café.md") == source.content
        for info in archive.infolist():
            assert info.date_time == bundle.ZIP_TIMESTAMP
            assert info.compress_type == zipfile.ZIP_STORED
        mode = archive.getinfo("files/skills/café.md").external_attr >> 16
        assert stat.S_IFMT(mode) == stat.S_IFREG
        assert stat.S_IMODE(mode) == bundle.MODE_FILE


# The acceptance criterion: one canonical input, one byte-identical bundle.
def test_the_digest_does_not_depend_on_the_order_the_sources_arrived_in() -> None:
    sources = (
        bundle.Source("z.md", b"last", "component_c"),
        bundle.Source("a.md", b"first", "component_a"),
        bundle.Source("m.md", b"middle", "component_b"),
    )
    forward = _compile(sources)
    backward = _compile(tuple(reversed(sources)))
    assert forward.digest == backward.digest
    assert forward.archive == backward.archive
    assert forward.artifact_digest == backward.artifact_digest
    assert forward.manifest == backward.manifest
    assert forward.files == backward.files


def test_compiling_twice_gives_the_same_digest() -> None:
    sources = (bundle.Source("a.md", b"content", "component_a"),)
    first = _compile(sources)
    second = _compile(sources)
    assert first.digest == second.digest
    assert first.archive == second.archive


def test_changing_one_byte_changes_the_digest() -> None:
    """The digest covers the manifest, which covers every file by content."""
    first = _compile((bundle.Source("a.md", b"content", "component_a"),))
    second = _compile((bundle.Source("a.md", b"contenu", "component_a"),))
    assert first.digest != second.digest
    assert first.artifact_digest != second.artifact_digest


def test_changing_the_setup_passport_changes_both_identities() -> None:
    source = (bundle.Source("a.md", b"content", "component_a"),)
    first = _compile(source)
    changed = {**SETUP_PASSPORT, "x": 1}
    second = _compile(
        source,
        setup_passport=changed,
        setup_digest=digest_canonical(bundle.PASSPORT_DOMAIN, changed),
    )
    assert first.digest != second.digest
    assert first.artifact_digest != second.artifact_digest


def test_a_setup_passport_that_does_not_match_its_reference_is_refused() -> None:
    compiled = _compile(
        (bundle.Source("a.md", b"content", "component_a"),),
        setup_passport={**SETUP_PASSPORT, "stable_id": "setup_other"},
    )
    assert _codes(compiled) == ("setup_passport_mismatch",)
    assert compiled.archive == b""


def test_the_manifest_carries_nothing_that_varies_between_machines() -> None:
    """Build time, local paths and explanations are absent by construction."""
    compiled = _compile((bundle.Source("a.md", b"content", "component_a"),))
    text = repr(compiled.manifest)
    assert "/home/" not in text
    assert "/tmp" not in text
    for forbidden in ("built_at", "created_at", "timestamp", "hostname", "explanation"):
        assert forbidden not in compiled.manifest


def test_the_manifest_names_the_builder_and_the_protocol() -> None:
    compiled = _compile((bundle.Source("a.md", b"content", "component_a"),))
    assert compiled.manifest["builder_version"] == bundle.BUILDER_VERSION
    assert compiled.manifest["protocol_version"] == bundle.PROTOCOL_VERSION
    assert compiled.manifest["input_digest"] == BUILD["input_digest"]


def test_both_reports_are_inside_the_hashed_manifest() -> None:
    """`REQ-609`: a bundle carries both, so both must be covered by the digest."""
    first = _compile(
        (bundle.Source("a.md", b"content", "component_a"),), composition_report={"chosen": ["x"]}
    )
    second = _compile(
        (bundle.Source("a.md", b"content", "component_a"),), composition_report={"chosen": ["y"]}
    )
    assert first.digest != second.digest


# Every prohibited shape from the contract.
@pytest.mark.parametrize(
    ("source", "code"),
    [
        (bundle.Source("/etc/passwd", b"x", "c"), "path_not_relative"),
        (bundle.Source("~/notes.md", b"x", "c"), "path_not_relative"),
        (bundle.Source("C:/notes.md", b"x", "c"), "path_not_relative"),
        (bundle.Source("../up.md", b"x", "c"), "path_escapes_target"),
        (bundle.Source("a/../b.md", b"x", "c"), "path_escapes_target"),
        (bundle.Source("", b"x", "c"), "path_empty_segment"),
        (bundle.Source("a//b.md", b"x", "c"), "path_empty_segment"),
        (bundle.Source("./a.md", b"x", "c"), "path_empty_segment"),
        (bundle.Source("bad\u0000name.md", b"x", "c"), "path_invalid_character"),
        (bundle.Source("bad\nname.md", b"x", "c"), "path_invalid_character"),
        (bundle.Source("x" * 256, b"x", "c"), "path_too_long"),
        # Windows portability. The owner chose one globally portable bundle, so
        # a digest means one installability everywhere rather than depending on
        # the host that materialises it. Each of these is a real filesystem
        # object on Linux and is either impossible or a *different* object on
        # Windows: `CON` and friends are reserved devices whatever the
        # extension, a trailing dot or space is silently stripped, and a colon
        # selects an NTFS alternate data stream instead of a file.
        (bundle.Source("skills/CON/SKILL.md", b"x", "c"), "path_not_portable"),
        (bundle.Source("con.md", b"x", "c"), "path_not_portable"),
        (bundle.Source("commands/PRN.json", b"x", "c"), "path_not_portable"),
        (bundle.Source("agents/COM1", b"x", "c"), "path_not_portable"),
        (bundle.Source("agents/lpt9.txt", b"x", "c"), "path_not_portable"),
        (bundle.Source("commands/build.", b"x", "c"), "path_not_portable"),
        (bundle.Source("settings/name ", b"x", "c"), "path_not_portable"),
        (bundle.Source("plugins/name:stream", b"x", "c"), "path_not_portable"),
        (bundle.Source("link", b"", "c", kind=bundle.KIND_SYMLINK), "link_not_allowed"),
        (bundle.Source("hard", b"", "c", kind=bundle.KIND_HARDLINK), "link_not_allowed"),
        (bundle.Source("dir", b"", "c", kind=bundle.KIND_DIRECTORY), "link_not_allowed"),
        (bundle.Source("dev", b"", "c", kind=bundle.KIND_SPECIAL), "special_file_not_allowed"),
        (bundle.Source(".env", b"x", "c"), "secret_in_bundle"),
        (bundle.Source("conf/.env.local", b"x", "c"), "secret_in_bundle"),
        (bundle.Source("keys/server.pem", b"x", "c"), "secret_in_bundle"),
        (bundle.Source("id_rsa", b"x", "c"), "secret_in_bundle"),
        (bundle.Source("a.md", b"x", "c", mode=0o777), "mode_not_allowed"),
        (bundle.Source("a.md", b"x", "c", mode=0o600), "mode_not_allowed"),
        (bundle.Source("a.md", b"x" * (bundle.MAX_FILE_BYTES + 1), "c"), "file_too_large"),
    ],
)
def test_every_prohibited_shape_is_refused(source: bundle.Source, code: str) -> None:
    compiled = _compile((source,))
    assert code in _codes(compiled)
    assert not compiled.compiled


def test_two_paths_that_normalise_to_one_are_refused() -> None:
    compiled = _compile(
        (
            bundle.Source("skills/a.md", b"first", "component_a"),
            bundle.Source("skills/a.md/", b"second", "component_b"),
        )
    )
    assert "path_duplicate" in _codes(compiled)


def test_two_paths_differing_only_by_case_are_refused() -> None:
    """A case-insensitive filesystem would install whichever arrived last."""
    compiled = _compile(
        (
            bundle.Source("skills/Review.md", b"first", "component_a"),
            bundle.Source("skills/review.md", b"second", "component_b"),
        )
    )
    assert "path_case_conflict" in _codes(compiled)


def test_a_path_outside_the_declared_managed_paths_is_refused() -> None:
    compiled = _compile(
        (bundle.Source("skills/rogue.md", b"x", "component_a"),),
        declared_paths=frozenset({"skills/allowed.md"}),
    )
    assert "path_undeclared" in _codes(compiled)


def test_declared_paths_that_match_are_allowed() -> None:
    compiled = _compile(
        (bundle.Source("skills/allowed.md", b"x", "component_a"),),
        declared_paths=frozenset({"skills/allowed.md"}),
    )
    assert compiled.compiled


def test_a_bundle_with_a_refusal_carries_no_manifest_and_no_digest() -> None:
    """`REQ-608`: a blocked bundle is not a partial one."""
    compiled = _compile(
        (
            bundle.Source("skills/a.md", b"fine", "component_a"),
            bundle.Source("../escape.md", b"bad", "component_b"),
        )
    )
    assert compiled.files == ()
    assert compiled.manifest == {}
    assert compiled.digest == ""
    assert compiled.archive == b""
    assert compiled.artifact_digest == ""


def test_every_reason_comes_back_rather_than_only_the_first() -> None:
    compiled = _compile(
        (
            bundle.Source("../a.md", b"x", "c"),
            bundle.Source("/b.md", b"x", "c"),
            bundle.Source(".env", b"x", "c"),
        )
    )
    assert len(compiled.refusals) == 3


def test_the_refusal_order_is_stable() -> None:
    sources = (
        bundle.Source("../a.md", b"x", "c"),
        bundle.Source("/b.md", b"x", "c"),
        bundle.Source(".env", b"x", "c"),
    )
    assert _codes(_compile(sources)) == _codes(_compile(tuple(reversed(sources))))


def test_too_many_files_is_refused_rather_than_truncated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bundle, "MAX_FILES", 2)
    compiled = _compile(tuple(bundle.Source(f"{name}.md", b"x", "c") for name in ("a", "b", "c")))
    assert "too_many_files" in _codes(compiled)
    assert compiled.files == ()


def test_a_bundle_over_the_total_bound_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bundle, "MAX_BUNDLE_BYTES", 8)
    compiled = _compile(
        (bundle.Source("a.md", b"12345", "c"), bundle.Source("b.md", b"12345", "c"))
    )
    assert "bundle_too_large" in _codes(compiled)


def test_archive_overhead_counts_toward_the_bundle_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bundle, "MAX_BUNDLE_BYTES", 1024)
    compiled = _compile((bundle.Source("a.md", b"x", "c"),))
    assert _codes(compiled) == ("bundle_too_large",)
    assert compiled.archive == b""


@pytest.mark.parametrize("mode", [bundle.MODE_FILE, bundle.MODE_EXECUTABLE])
def test_the_two_allowed_modes_compile(mode: int) -> None:
    compiled = _compile((bundle.Source("a.md", b"x", "component_a", mode=mode),))
    assert compiled.compiled
    assert compiled.files[0].mode == mode


def test_a_path_is_normalised_to_one_spelling() -> None:
    assert bundle.normalise("skills\\a.md") == "skills/a.md"
    assert bundle.normalise("skills/a.md/") == "skills/a.md"


def test_two_unicode_spellings_of_one_name_are_one_path() -> None:
    """One name on a macOS filesystem, two on a Linux one, unless folded."""
    composed = "skills/caf\u00e9.md"
    decomposed = "skills/cafe\u0301.md"
    assert bundle.normalise(composed) == bundle.normalise(decomposed)
    assert "path_duplicate" in _codes(
        _compile(
            (
                bundle.Source(composed, b"first", "component_a"),
                bundle.Source(decomposed, b"second", "component_b"),
            )
        )
    )


def test_a_link_is_refused_on_its_kind_and_not_on_its_bytes() -> None:
    """A symlink and the file it points at have the same bytes."""
    same = b"content"
    assert _compile((bundle.Source("a.md", same, "component_a"),)).compiled
    assert "link_not_allowed" in _codes(
        _compile((bundle.Source("a.md", same, "component_a", kind=bundle.KIND_SYMLINK),))
    )
    assert "link_not_allowed" in _codes(
        _compile((bundle.Source("a.md", same, "component_a", kind=bundle.KIND_HARDLINK),))
    )


# Documentation and code are two statements of one closed set.
def test_the_refusal_registry_matches_the_contract() -> None:
    written = set(re.findall(r"^\| `([a-z_]+)` \|", CONTRACT.read_text("utf-8"), re.MULTILINE))
    assert written == bundle.REFUSALS


def test_the_declared_limits_match_the_contract() -> None:
    text = CONTRACT.read_text("utf-8")
    assert f"максимум файлов: {bundle.MAX_FILES}" in text
    assert "0644 и 0755" in text


@pytest.mark.parametrize(
    "path",
    [
        # Near neighbours of the reserved names, which must stay valid. The
        # rule is the whole basename before its extension, not a substring:
        # refusing these would make the guard cost real names.
        "console.md",
        "commands/connect.json",
        "auxiliary.md",
        "skills/nullable/SKILL.md",
        "com10.txt",
        "prnt.md",
        "a.con",
    ],
)
def test_a_name_that_merely_resembles_a_reserved_device_stays_valid(path: str) -> None:
    assert bundle._path_problem(path) is None, path  # pyright: ignore[reportPrivateUsage]
