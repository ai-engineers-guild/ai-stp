"""One Desktop version reaches manifests and path packages without dependency resolution."""

from __future__ import annotations

import json
import shutil
import tomllib
from pathlib import Path

import pytest
from release_scripts.desktop_version import ROOT, projections, version

FILES = (
    "package.json",
    "src-tauri/tauri.conf.json",
    "core/Cargo.toml",
    "core/Cargo.lock",
    "src-tauri/Cargo.toml",
    "src-tauri/Cargo.lock",
)


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    for name in FILES:
        target = tmp_path / "apps/desktop" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "apps/desktop" / name, target)
    return tmp_path


def set_version(root: Path, value: str) -> None:
    path = root / "apps/desktop/package.json"
    data = json.loads(path.read_text())
    data["version"] = value
    path.write_text(json.dumps(data))


def test_projects_one_version_without_changing_external_packages_or_configuration(
    checkout: Path,
) -> None:
    set_version(checkout, "9.8.7")
    rendered = projections(checkout)
    assert len(rendered) == 5
    for path, text in rendered.items():
        before = path.read_text()
        if path.suffix == ".json":
            old, new = json.loads(before), json.loads(text)
            assert new.pop("version") == "9.8.7"
            old.pop("version")
            assert new == old
        else:
            old, new = tomllib.loads(before), tomllib.loads(text)
            if path.name == "Cargo.toml":
                assert new["package"].pop("version") == "9.8.7"
                old["package"].pop("version")
                assert new == old
            else:
                for previous, projected in zip(old["package"], new["package"], strict=True):
                    if previous["name"] in {"ai-stp-desktop", "ai-stp-desktop-core"}:
                        assert projected.pop("version") == "9.8.7"
                        previous.pop("version")
                    assert previous == projected
        path.write_text(text)
    assert all(path.read_text() == text for path, text in projections(checkout).items())


@pytest.mark.parametrize("value", ["v1.2.3", "1.2", "1.2.3-rc.1", "01.2.3", "1.2.3\n"])
def test_refuses_versions_that_native_release_packages_cannot_share(
    checkout: Path, value: str
) -> None:
    set_version(checkout, value)
    with pytest.raises(ValueError, match="stable"):
        version(checkout)


def test_refuses_ambiguous_lock_ownership_before_writing_any_projection(checkout: Path) -> None:
    set_version(checkout, "9.8.7")
    target = checkout / "apps/desktop/src-tauri/Cargo.lock"
    target.write_text(
        target.read_text() + '\n[[package]]\nname = "ai-stp-desktop"\nversion = "0.1.0"\n'
    )
    before = {name: (checkout / "apps/desktop" / name).read_bytes() for name in FILES}
    with pytest.raises(ValueError, match="ambiguous local package"):
        projections(checkout)
    assert before == {name: (checkout / "apps/desktop" / name).read_bytes() for name in FILES}


def test_only_the_package_section_owns_a_native_manifest_version(checkout: Path) -> None:
    target = checkout / "apps/desktop/core/Cargo.toml"
    target.write_text('[workspace.package]\nversion = "1.0.0"\n\n' + target.read_text())
    set_version(checkout, "9.8.7")
    parsed = tomllib.loads(projections(checkout)[target])
    assert parsed["workspace"]["package"]["version"] == "1.0.0"
    assert parsed["package"]["version"] == "9.8.7"
