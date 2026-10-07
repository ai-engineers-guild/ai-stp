"""Probe the CLI resource tree after bundling, without installing the application."""

from __future__ import annotations

import os
import platform
import subprocess
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
        if not executable.is_file() or not (executable.parent / "_internal").is_dir():
            raise RuntimeError(f"incomplete packaged CLI tree at {executable.parent}")
        env = {**os.environ, "AI_STP_SIDECAR_EXE": str(executable)}
        subprocess.run(
            ["bash", str(repo / "apps/desktop/scripts/test-bundled-sidecar.sh")],
            env=env,
            check=True,
            timeout=300,
        )
        print(f"Packaged CLI resource probe passed: {platform.system()}")


if __name__ == "__main__":
    main()
