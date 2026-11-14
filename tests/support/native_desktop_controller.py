"""Check native Desktop controllers with their actual platform compiler/parser."""

from __future__ import annotations

import os
import subprocess

from tests.support.native_runner import disposable_runner


def main() -> None:
    """Expose compiler/parser diagnostics before packaging and authentication."""
    disposable_runner()
    assert os.environ["RUNNER_OS"] in {"macOS", "Windows"}
    if os.environ["RUNNER_OS"] == "macOS":
        arguments = [
            "swiftc",
            "-typecheck",
            ".github/scripts/qualify-installed-macos-desktop.swift",
        ]
    else:
        arguments = [
            "pwsh",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "$tokens = $null; $errors = $null; "
            "[void][System.Management.Automation.Language.Parser]::ParseFile("
            "(Join-Path (Get-Location) '.github/scripts/qualify-installed-windows-desktop.ps1'),"
            "[ref]$tokens,[ref]$errors); "
            "if ($errors.Count) { $errors | ForEach-Object { Write-Error $_ }; exit 1 }",
        ]
    subprocess.run(arguments, check=True, timeout=120)


if __name__ == "__main__":
    main()
