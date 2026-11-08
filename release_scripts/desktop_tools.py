"""Check the exact Desktop SDK and prepare its verified Windows packaging layout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def check(root: Path = ROOT) -> None:
    package = json.loads((root / "apps/desktop/package.json").read_text())
    for name in ("tauri-tools.json", "tauri-tools-windows.json"):
        path = root / ".github" / name
        manifest = json.loads(path.read_text())
        check_manifest(manifest, package["devDependencies"]["@tauri-apps/cli"])
    configuration = root / ".github/tauri-tools-windows.conf.json"
    if not json.loads(configuration.read_text())["bundle"]["useLocalToolsDir"]:
        raise ValueError("Windows packaging must use the explicitly prepared tool directory")


def check_manifest(manifest: dict[str, Any], cli_version: str) -> None:
    version = manifest["tauri_cli_version"]
    if cli_version != version:
        raise ValueError("Tauri CLI must match the exact qualified packaging SDK")
    if f"/tauri-cli-v{version}/" not in manifest["source"]:
        raise ValueError("Packaging tool provenance must name the qualified SDK")
    names = [asset["file"] for asset in manifest["assets"]]
    if manifest["schema_version"] != 1 or len(names) != len(set(names)):
        raise ValueError("Packaging tools require a unique versioned asset inventory")
    print(f"Desktop packaging: Tauri {version}, {len(names)} exact public assets")


def relative_path(value: str) -> Path:
    path = PurePosixPath(value)
    if (
        not path.parts
        or "\\" in value
        or ":" in value
        or "\0" in value
        or path.is_absolute()
        or ".." in path.parts
    ):
        raise ValueError("Packaging paths must remain relative to their owned directory")
    return Path(*path.parts)


def extract_archive(archive: Path, destination: Path, prefix: str | None) -> None:
    """Validate the complete ZIP inventory before writing any member."""
    with zipfile.ZipFile(archive) as source:
        members = source.infolist()
        if len(members) > 10000 or sum(member.file_size for member in members) > 536870912:
            raise ValueError("Packaging archive exceeds its admitted inventory bound")
        selected: list[tuple[zipfile.ZipInfo, Path]] = []
        seen: set[str] = set()
        for member in members:
            relative = relative_path(member.filename)
            mode = stat.S_IFMT(member.external_attr >> 16)
            if mode not in (0, stat.S_IFDIR, stat.S_IFREG):
                raise ValueError("Packaging archive contains a link or special file")
            if prefix is not None:
                relative = relative.relative_to(relative_path(prefix))
            if relative == Path():
                continue
            key = relative.as_posix().casefold()
            if key in seen:
                raise ValueError("Packaging archive contains conflicting paths")
            seen.add(key)
            selected.append((member, relative))
        for member, relative in selected:
            target = destination / relative
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(member) as incoming, target.open("xb") as output:
                    shutil.copyfileobj(incoming, output)


def prepare_windows(directory: Path) -> None:
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("RUNNER_OS") != "Windows"
        or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
    ):
        raise ValueError("Packaging preparation requires a disposable hosted Windows runner")
    check()
    directory = directory.resolve(strict=True)
    if not directory.is_relative_to(Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)):
        raise ValueError("Downloaded tools must belong to this job's temporary directory")
    metadata = json.loads(
        subprocess.check_output(
            [
                "cargo",
                "metadata",
                "--locked",
                "--offline",
                "--no-deps",
                "--format-version",
                "1",
                "--manifest-path",
                str(ROOT / "apps/desktop/src-tauri/Cargo.toml"),
            ],
            text=True,
            timeout=30,
        )
    )
    target = Path(metadata["target_directory"]).resolve(strict=True)
    if not target.is_relative_to(Path(os.environ["GITHUB_WORKSPACE"]).resolve(strict=True)):
        raise ValueError("Hosted packaging tools must remain in the checkout's native target")
    tools = target / ".tauri"
    if tools.is_symlink():
        raise ValueError("Packaging tool directory cannot be a symlink")
    tools.mkdir(exist_ok=True)
    manifest = json.loads((ROOT / ".github/tauri-tools-windows.json").read_text())
    for asset in manifest["assets"]:
        source = directory / asset["file"]
        if source.is_symlink() or not source.is_file() or source.stat().st_size != asset["size"]:
            raise ValueError("Packaging asset is absent or its size changed")
        with source.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != asset["sha256"]:
                raise ValueError("Packaging asset differs from its admitted digest")
        if "extract_to" in asset:
            destination = tools / relative_path(asset["extract_to"])
            if destination.is_symlink():
                raise ValueError("Packaging tool target cannot be a symlink")
            with tempfile.TemporaryDirectory(dir=tools, prefix="prepare-") as temporary:
                staging = Path(temporary) / "tools"
                staging.mkdir()
                extract_archive(source, staging, asset.get("strip_prefix"))
                if destination.exists():
                    shutil.rmtree(destination)
                staging.rename(destination)
        else:
            destination = tools / relative_path(asset["install_to"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    print("Verified Windows packaging tools prepared in the SDK's native layout")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-windows", type=Path)
    arguments = parser.parse_args()
    if arguments.prepare_windows is not None:
        prepare_windows(arguments.prepare_windows)
    else:
        check()
