"""Probe the CLI resource tree after bundling, without installing the application."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path


def only(paths: list[Path], label: str) -> Path:
    if len(paths) != 1:
        raise RuntimeError(f"expected one {label}, found {len(paths)}")
    return paths[0]


def main() -> None:
    repo = Path(__file__).resolve().parents[3]
    bundles = repo / "apps/desktop/src-tauri/target/release/bundle"
    with tempfile.TemporaryDirectory(prefix="ai-stp-packaged-cli-") as temporary:
        extracted = Path(temporary)
        if platform.system() == "Darwin":
            app = only(list((bundles / "macos").glob("*.app")), "macOS app")
            resource_root = app / "Contents/Resources"
        elif os.name == "nt":
            msi = only(list((bundles / "msi").glob("*.msi")), "Windows MSI")
            # Administrative extraction writes the package's files under the
            # temporary target; it does not install or register the application.
            subprocess.run(
                ["msiexec.exe", "/a", str(msi), "/qn", f"TARGETDIR={extracted}"],
                check=True,
                timeout=180,
            )
            binary = only(list(extracted.rglob("ai-stp-desktop-cli.exe")), "MSI CLI")
            resource_root = binary.parent.parent
        else:
            deb = only(list((bundles / "deb").glob("*.deb")), "Linux deb")
            subprocess.run(["dpkg-deb", "-x", str(deb), str(extracted)], check=True, timeout=120)
            resource_root = extracted / "usr/lib/ai-stp-desktop"

        name = "ai-stp-desktop-cli.exe" if os.name == "nt" else "ai-stp-desktop-cli"
        executable = resource_root / "cli" / name
        manifest = json.loads((executable.parent / "sidecar.json").read_text())
        if (
            not executable.is_file()
            or manifest.get("runtime") != "rust"
            or manifest.get("executable") != executable.name
            or manifest.get("sha256") != hashlib.sha256(executable.read_bytes()).hexdigest()
            or {path.name for path in executable.parent.iterdir()}
            != {executable.name, "sidecar.json"}
        ):
            raise RuntimeError(f"invalid packaged Rust CLI resource at {executable.parent}")
        env = {**os.environ, "AI_STP_SIDECAR_EXE": str(executable)}
        subprocess.run(
            [
                sys.executable,
                str(repo / "release_scripts/run_bash.py"),
                str(repo / "apps/desktop/scripts/test-bundled-sidecar.sh"),
            ],
            env=env,
            check=True,
            timeout=300,
        )
        print(f"Packaged CLI resource probe passed: {platform.system()}")


if __name__ == "__main__":
    main()
