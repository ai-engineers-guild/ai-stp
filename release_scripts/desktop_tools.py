"""Check that the qualified Linux packaging tools match the exact Desktop SDK."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(root: Path = ROOT) -> None:
    manifest = json.loads((root / ".github/tauri-tools.json").read_text())
    package = json.loads((root / "apps/desktop/package.json").read_text())
    version = manifest["tauri_cli_version"]
    if package["devDependencies"]["@tauri-apps/cli"] != version:
        raise ValueError("Tauri CLI must match the exact qualified packaging SDK")
    if f"/tauri-cli-v{version}/" not in manifest["source"]:
        raise ValueError("Packaging tool provenance must name the qualified SDK")
    names = [asset["file"] for asset in manifest["assets"]]
    if manifest["schema_version"] != 1 or len(names) != len(set(names)):
        raise ValueError("Packaging tools require a unique versioned asset inventory")
    for asset in manifest["assets"]:
        if asset.get("executable") is not True:
            raise ValueError("The native packaging tools must retain executable mode")
    print(f"Desktop Linux packaging: Tauri {version}, {len(names)} exact public assets")


if __name__ == "__main__":
    check()
