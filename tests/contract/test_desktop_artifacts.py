"""Only complete, unchanged installers from the qualified source can reach publication."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from release_scripts.desktop_artifacts import seal, verify

SOURCE = "a" * 40
VERSION = "1.2.3"
INSTALLERS = {
    "Linux": [
        "deb/ai-stp_1.2.3_amd64.deb",
        "rpm/ai-stp-1.2.3-1.x86_64.rpm",
        "appimage/ai-stp_1.2.3_amd64.AppImage",
    ],
    "macOS": ["dmg/ai-stp_1.2.3_aarch64.dmg"],
    "Windows": ["msi/ai-stp_1.2.3_x64_en-US.msi", "nsis/ai-stp_1.2.3_x64-setup.exe"],
}


@pytest.fixture
def bundles(tmp_path: Path) -> Path:
    combined = tmp_path / "bundles"
    for platform, names in INSTALLERS.items():
        directory = tmp_path / platform
        for name in names:
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("qualified installer fixture: " + name).encode())
        seal(directory, platform, SOURCE, VERSION)
        shutil.copytree(directory, combined, dirs_exist_ok=True)
    return combined


def test_stages_exactly_the_six_qualified_installers_with_checksums(
    bundles: Path, tmp_path: Path
) -> None:
    output = tmp_path / "release"
    originals = {
        Path(name).name: (bundles / name).read_bytes()
        for names in INSTALLERS.values()
        for name in names
    }
    verify(bundles, output, SOURCE, VERSION)
    assert {path.name for path in output.iterdir()} == set(originals) | {"SHA256SUMS"}
    for name, data in originals.items():
        assert (output / name).read_bytes() == data
        assert (
            f"{hashlib.sha256(data).hexdigest()}  {name}\n" in (output / "SHA256SUMS").read_text()
        )


@pytest.mark.parametrize(
    "change",
    [
        "tampered",
        "missing_platform",
        "wrong_source",
        "wrong_version",
        "duplicate",
        "traversal",
        "extra",
        "symlink",
        "collision",
    ],
)
def test_refuses_changed_or_unqualified_payloads_before_staging(
    bundles: Path, tmp_path: Path, change: str
) -> None:
    manifest = bundles / "qualified-desktop-Linux.json"
    data = json.loads(manifest.read_text())
    installer = bundles / INSTALLERS["Linux"][0]
    if change == "tampered":
        installer.write_bytes(installer.read_bytes() + b"changed")
    elif change == "missing_platform":
        (bundles / "qualified-desktop-macOS.json").unlink()
    elif change == "wrong_source":
        data["source_commit"] = "b" * 40
    elif change == "wrong_version":
        data["version"] = "1.2.4"
    elif change == "duplicate":
        data["files"].append(data["files"][0])
    elif change == "traversal":
        data["files"][0]["path"] = "../outside.deb"
    elif change == "extra":
        (bundles / "extra_1.2.3_amd64.deb").write_bytes(b"unqualified")
    elif change == "symlink":
        outside = tmp_path / "outside"
        outside.write_bytes(installer.read_bytes())
        installer.unlink()
        installer.symlink_to(outside)
    else:
        other = bundles / "another" / installer.name
        other.parent.mkdir()
        shutil.copyfile(installer, other)
    manifest.write_text(json.dumps(data))
    output = tmp_path / "release"
    with pytest.raises(ValueError):
        verify(bundles, output, SOURCE, VERSION)
    assert not output.exists()


def test_cannot_seal_a_partial_platform_or_stale_package_version(tmp_path: Path) -> None:
    (tmp_path / "ai-stp_1.2.3_amd64.deb").write_bytes(b"fixture")
    with pytest.raises(ValueError, match="inventory"):
        seal(tmp_path, "Linux", SOURCE, VERSION)
    with pytest.raises(ValueError, match="version"):
        seal(tmp_path, "Linux", SOURCE, "1.2.4")


def test_diagnostic_packages_without_acceptance_manifests_cannot_be_published(
    bundles: Path, tmp_path: Path
) -> None:
    for manifest in bundles.glob("qualified-desktop-*.json"):
        manifest.unlink()
    with pytest.raises(ValueError, match="three qualified"):
        verify(bundles, tmp_path / "release", SOURCE, VERSION)


def test_refuses_to_mix_an_existing_output_with_a_new_publication(
    bundles: Path, tmp_path: Path
) -> None:
    output = tmp_path / "release"
    output.mkdir()
    (output / "retained-file").write_bytes(b"preserve")
    with pytest.raises(FileExistsError):
        verify(bundles, output, SOURCE, VERSION)
    assert (output / "retained-file").read_bytes() == b"preserve"


def test_manifest_paths_remain_relative_to_their_artifact_after_transport(tmp_path: Path) -> None:
    combined = tmp_path / "downloaded"
    for platform, names in INSTALLERS.items():
        directory = combined / platform
        for name in names:
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode())
        seal(directory, platform, SOURCE, VERSION)
    assert len(verify(combined, tmp_path / "release", SOURCE, VERSION)) == 6
