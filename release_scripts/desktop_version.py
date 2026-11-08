"""Project the Desktop package version into native manifests and local lock entries."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STABLE_VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")
CRATES = {"core": "ai-stp-desktop-core", "src-tauri": "ai-stp-desktop"}


def version(root: Path) -> str:
    value = json.loads((root / "apps/desktop/package.json").read_text())["version"]
    if not isinstance(value, str) or not STABLE_VERSION.fullmatch(value):
        raise ValueError("Desktop releases require a stable major.minor.patch version")
    return value


def projections(root: Path) -> dict[Path, str]:
    """Validate every consumer before producing changes; dependencies keep their bytes."""
    target_version = version(root)
    desktop = root / "apps/desktop"
    output: dict[Path, str] = {}
    path = desktop / "src-tauri/tauri.conf.json"
    text = path.read_text(encoding="utf-8")
    config = json.loads(text)
    if not isinstance(config.get("version"), str):
        raise ValueError("Tauri must have its own version projection")
    output[path], count = re.subn(
        r'("version"\s*:\s*")[^"]*(")', rf"\g<1>{target_version}\g<2>", text
    )
    if count != 1:
        raise ValueError("ambiguous Tauri version projection")
    for directory, name in CRATES.items():
        path = desktop / directory / "Cargo.toml"
        text = path.read_text(encoding="utf-8")
        package = tomllib.loads(text)["package"]
        if package.get("name") != name or not isinstance(package.get("version"), str):
            raise ValueError(f"unexpected Desktop package in {path.relative_to(root)}")
        section = re.search(r"(?ms)^\[package\]\s*\n.*?(?=^\[|\Z)", text)
        if section is None:
            raise ValueError("cannot locate the native package section")
        projected_section, count = re.subn(
            r'(?m)^(version\s*=\s*")[^"]*(")',
            rf"\g<1>{target_version}\g<2>",
            section.group(),
        )
        projected = text[: section.start()] + projected_section + text[section.end() :]
        if count != 1 or tomllib.loads(projected)["package"]["version"] != target_version:
            raise ValueError("cannot locate an unambiguous native package version")
        output[path] = projected
        path = desktop / directory / "Cargo.lock"
        text = path.read_text(encoding="utf-8")
        packages = tomllib.loads(text)["package"]
        expected = {name} if directory == "core" else set(CRATES.values())
        for owned in expected:
            matches = [item for item in packages if item["name"] == owned]
            if len(matches) != 1 or "source" in matches[0]:
                raise ValueError(f"ambiguous local package {owned} in {path.relative_to(root)}")
            text, count = re.subn(
                rf'(?m)(^name = "{re.escape(owned)}"\nversion = ")[^"]*(")',
                rf"\g<1>{target_version}\g<2>",
                text,
            )
            if count != 1:
                raise ValueError(f"cannot locate lock entry for {owned}")
        output[path] = text
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--expected", help="Require the release tag's version")
    args = parser.parse_args()
    try:
        current = version(ROOT)
        if args.expected is not None and args.expected != current:
            raise ValueError(f"Desktop version {current} differs from release {args.expected}")
        output = projections(ROOT)
        drift = [path for path, text in output.items() if path.read_text(encoding="utf-8") != text]
        if args.check and drift:
            for path in drift:
                print(f"Desktop version drift: {path.relative_to(ROOT)}", file=sys.stderr)
            return 1
        if not args.check:
            for path in drift:
                path.write_text(output[path], encoding="utf-8", newline="\n")
        print(f"Desktop {current}: {len(output)} native version projections checked")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Desktop version refused: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
