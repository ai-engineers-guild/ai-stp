"""Read-only managed manifest drift details (SPEC-008 REQ-843)."""

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import managed_diff


def _digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _bundle(path: Path, files: dict[str, bytes], *, surfaces: tuple[str, ...] = ()) -> None:
    records = [
        {"path": name, "digest": _digest(payload), "byte_length": len(payload), "mode": 420}
        for name, payload in sorted(files.items())
    ]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "bundle.json",
            json.dumps(
                {
                    "managed_paths": sorted(files),
                    "files": records,
                    "conversion_report": {
                        "entries": [{"native_surface": surface} for surface in surfaces]
                    },
                }
            ),
        )
        for name, payload in files.items():
            archive.writestr(f"files/{name}", payload)


def test_compare_reports_modified_added_and_deleted_inside_managed_roots(tmp_path: Path) -> None:
    archive = tmp_path / "bundle.zip"
    _bundle(
        archive,
        {
            "skills/review/SKILL.md": b"expected\n",
            "skills/old/SKILL.md": b"old\n",
            "AGENTS.md": b"rules\n",
        },
        surfaces=("skills", "AGENTS.md"),
    )
    target = tmp_path / "target"
    changed = target / "skills" / "review" / "SKILL.md"
    changed.parent.mkdir(parents=True)
    changed.write_bytes(b"changed\n")
    added = target / "skills" / "extra.md"
    added.write_bytes(b"extra\n")
    (target / "AGENTS.md").write_bytes(b"rules\n")
    unrelated = target / "notes.txt"
    unrelated.write_bytes(b"outside the managed roots\n")

    changes = managed_diff.compare(target, managed_diff.bundle_manifest(archive))

    assert [(item.code, item.path) for item in changes] == [
        ("added", "skills/extra.md"),
        ("deleted", "skills/old/SKILL.md"),
        ("modified", "skills/review/SKILL.md"),
    ]
    assert all(not item.path.startswith(str(tmp_path)) for item in changes)
    assert unrelated.read_bytes() == b"outside the managed roots\n"


def test_nested_native_surfaces_exclude_runtime_siblings(tmp_path: Path) -> None:
    archive = tmp_path / "bundle.zip"
    files = {
        "antigravity-cli/settings.json": b"settings\n",
        "config/plugins/baseline/plugin.json": b"plugin\n",
    }
    _bundle(archive, files, surfaces=("antigravity-cli/settings.json", "config/plugins"))
    target = tmp_path / "target"
    for name, payload in {
        **files,
        "antigravity-cli/settings.json": b"first-run preferences\n",
        "antigravity-cli/logs/runtime.log": b"unmanaged\n",
        "antigravity-cli/conversations/session.db": b"unmanaged\n",
        "config/config.json": b"unmanaged\n",
        "config/plugins/baseline/extra.md": b"added\n",
    }.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    manifest = managed_diff.bundle_manifest(archive)
    assert manifest.roots == ("antigravity-cli/settings.json", "config/plugins")
    changes = managed_diff.compare(target, manifest)
    assert [(item.code, item.path) for item in changes] == [
        ("added", "config/plugins/baseline/extra.md"),
        ("modified", "antigravity-cli/settings.json"),
    ]


def test_no_projection_evidence_only_compares_exact_files(tmp_path: Path) -> None:
    archive = tmp_path / "bundle.zip"
    _bundle(archive, {"runtime/settings.json": b"settings\n"})
    target = tmp_path / "target"
    (target / "runtime").mkdir(parents=True)
    (target / "runtime/settings.json").write_bytes(b"settings\n")
    (target / "runtime/private.log").write_bytes(b"unmanaged\n")

    assert managed_diff.compare(target, managed_diff.bundle_manifest(archive)) == ()


@pytest.mark.parametrize("surface", ["config/plugins", "config/plugins/base/plugin.json"])
def test_nested_surface_never_follows_a_linked_parent(tmp_path: Path, surface: str) -> None:
    archive = tmp_path / "bundle.zip"
    _bundle(archive, {"config/plugins/base/plugin.json": b"expected\n"}, surfaces=(surface,))
    target = tmp_path / "target"
    target.mkdir()
    outside = tmp_path / "outside"
    (outside / "plugins/base").mkdir(parents=True)
    (outside / "plugins/base/plugin.json").write_bytes(b"expected\n")
    (target / "config").symlink_to(outside, target_is_directory=True)

    changes = managed_diff.compare(target, managed_diff.bundle_manifest(archive))
    assert [(item.code, item.path, item.observed_digest) for item in changes] == [
        ("modified", "config/plugins/base/plugin.json", "unsafe")
    ]


def test_overlapping_surfaces_compare_each_namespace_once(tmp_path: Path) -> None:
    archive = tmp_path / "bundle.zip"
    _bundle(
        archive,
        {"config/plugins/base/plugin.json": b"expected\n"},
        surfaces=("config/plugins", "config/plugins/base", "config/plugins/base/plugin.json"),
    )
    assert managed_diff.bundle_manifest(archive).roots == ("config/plugins",)


@pytest.mark.parametrize(
    "surface", [".", "../outside", "config/../private", "C:/private", "/private", "config//plugins"]
)
def test_bundle_manifest_refuses_unsafe_conversion_surfaces(tmp_path: Path, surface: str) -> None:
    archive = tmp_path / "bundle.zip"
    _bundle(archive, {"config/plugins/base/plugin.json": b"expected\n"}, surfaces=(surface,))
    with pytest.raises(CliFailure):
        managed_diff.bundle_manifest(archive)


def test_compare_does_not_follow_links_or_change_the_target(tmp_path: Path) -> None:
    archive = tmp_path / "bundle.zip"
    _bundle(archive, {"skills/review/SKILL.md": b"expected\n"})
    target = tmp_path / "target"
    outside = tmp_path / "outside.md"
    outside.write_bytes(b"secret\n")
    linked = target / "skills" / "review" / "SKILL.md"
    linked.parent.mkdir(parents=True)
    linked.symlink_to(outside)

    changes = managed_diff.compare(target, managed_diff.bundle_manifest(archive))

    assert [(item.code, item.path) for item in changes] == [("modified", "skills/review/SKILL.md")]
    assert changes[0].observed_digest == "unsafe"
    assert outside.read_bytes() == b"secret\n"


def test_compare_treats_a_linked_managed_root_as_unsafe_without_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "bundle.zip"
    _bundle(archive, {"skills/review/SKILL.md": b"expected\n"})
    target = tmp_path / "target"
    target.mkdir()
    outside = tmp_path / "outside"
    (outside / "review").mkdir(parents=True)
    (outside / "review" / "SKILL.md").write_bytes(b"expected\n")
    (target / "skills").symlink_to(outside, target_is_directory=True)

    changes = managed_diff.compare(target, managed_diff.bundle_manifest(archive))

    assert [(item.code, item.path, item.observed_digest) for item in changes] == [
        ("modified", "skills/review/SKILL.md", "unsafe")
    ]


@pytest.mark.parametrize(
    "manifest",
    [
        {"managed_paths": ["../escape"], "files": []},
        {
            "managed_paths": ["a"],
            "files": [{"path": "a", "digest": "latest"}],
        },
        {"managed_paths": ["a"], "files": []},
        {
            "managed_paths": ["a", "a/b"],
            "files": [
                {"path": "a", "digest": _digest(b"a")},
                {"path": "a/b", "digest": _digest(b"b")},
            ],
        },
        {
            "managed_paths": ["config/plugins", "config/plugins/file"],
            "files": [
                {"path": "config/plugins", "digest": _digest(b"a")},
                {"path": "config/plugins/file", "digest": _digest(b"b")},
            ],
        },
    ],
)
def test_bundle_manifest_fails_closed_on_invalid_records(tmp_path: Path, manifest: object) -> None:
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as held:
        held.writestr("bundle.json", json.dumps(manifest))

    with pytest.raises(CliFailure):
        managed_diff.bundle_manifest(archive)
