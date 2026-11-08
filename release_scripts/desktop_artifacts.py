"""Seal qualified Desktop installers and verify their exact bytes before publication."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path, PurePosixPath
from typing import Any

from release_scripts.desktop_version import ROOT, version

PLATFORMS = {"Linux": {".deb", ".rpm", ".AppImage"}, "macOS": {".dmg"}, "Windows": {".msi", ".exe"}}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def installer_files(directory: Path, release_version: str) -> list[Path]:
    extensions = set.union(*PLATFORMS.values())
    files = sorted(path for path in directory.rglob("*") if path.suffix in extensions)
    for path in files:
        if (
            path.is_symlink()
            or not path.is_file()
            or not path.resolve(strict=True).is_relative_to(directory.resolve(strict=True))
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", path.name)
            or not re.search(rf"(?:^|[-_]){re.escape(release_version)}(?:[-_]|$)", path.stem)
        ):
            raise ValueError(f"invalid installer path or version: {path.name}")
    if len({path.name for path in files}) != len(files):
        raise ValueError("installer basenames collide")
    return files


def require_source(source: str) -> None:
    if not re.fullmatch(r"[a-f0-9]{40}", source):
        raise ValueError("a full source commit is required")


def seal(directory: Path, platform: str, source: str, release_version: str) -> Path:
    require_source(source)
    files = installer_files(directory, release_version)
    expected = PLATFORMS[platform]
    if len(files) != len(expected) or {path.suffix for path in files} != expected:
        raise ValueError(f"{platform} installer inventory is incomplete or ambiguous")
    document = {
        "schema_version": 1,
        "source_commit": source,
        "version": release_version,
        "platform": platform,
        "files": [
            {"path": path.relative_to(directory).as_posix(), "sha256": sha256(path)}
            for path in files
        ],
    }
    target = directory / f"qualified-desktop-{platform}.json"
    target.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return target


def verify(directory: Path, output: Path, source: str, release_version: str) -> list[Path]:
    require_source(source)
    files = installer_files(directory, release_version)
    expected_files: set[Path] = set()
    manifests = sorted(directory.rglob("qualified-desktop-*.json"))
    if len(manifests) != len(PLATFORMS) or {path.name for path in manifests} != {
        f"qualified-desktop-{name}.json" for name in PLATFORMS
    }:
        raise ValueError("all three qualified platform manifests are required")
    for manifest in manifests:
        if manifest.is_symlink():
            raise ValueError("a platform manifest cannot be a symlink")
        document: Any = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("a platform manifest must be an object")
        platform = document.get("platform")
        if (
            document.get("schema_version") != 1
            or not isinstance(platform, str)
            or platform not in PLATFORMS
            or manifest.name != f"qualified-desktop-{platform}.json"
            or document.get("source_commit") != source
            or document.get("version") != release_version
            or not isinstance(document.get("files"), list)
        ):
            raise ValueError("a platform manifest differs from the qualified source or version")
        selected: list[Path] = []
        for entry in document["files"]:
            if not isinstance(entry, dict):
                raise ValueError("an installer entry must be an object")
            relative = entry.get("path")
            if (
                not isinstance(relative, str)
                or "\\" in relative
                or PurePosixPath(relative).is_absolute()
                or ".." in PurePosixPath(relative).parts
                or PurePosixPath(relative).as_posix() != relative
            ):
                raise ValueError("a manifest path must be canonical and relative")
            path = manifest.parent / relative
            if path not in files or path in expected_files or sha256(path) != entry.get("sha256"):
                raise ValueError("an installer is missing, duplicated or has changed bytes")
            selected.append(path)
            expected_files.add(path)
        if (
            len(selected) != len(PLATFORMS[platform])
            or {path.suffix for path in selected} != PLATFORMS[platform]
        ):
            raise ValueError("a manifest does not contain its complete platform inventory")
    if set(files) != expected_files:
        raise ValueError("unqualified installers are present")
    # Validate every byte before creating an output. An existing output refuses
    # rather than mixing a previous run into the publication payload.
    output.mkdir(parents=True, exist_ok=False)
    for path in files:
        shutil.copyfile(path, output / path.name)
    (output / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in files),
        encoding="utf-8",
    )
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["seal", "verify"])
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--platform", choices=PLATFORMS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        current = version(ROOT)
        if args.action == "seal":
            if not args.platform:
                raise ValueError("sealing requires the platform owner")
            seal(args.directory, args.platform, args.source, current)
        else:
            if not args.output:
                raise ValueError("verification requires a new output directory")
            verify(args.directory, args.output, args.source, current)
        print(f"Desktop {current}: {args.action} passed for source {args.source}")
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(f"Desktop artifact admission refused: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
