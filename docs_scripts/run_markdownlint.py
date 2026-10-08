#!/usr/bin/env python3
"""Run the pinned repository-local markdownlint-cli2 binary."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "docs_scripts"
CONFIG = SCRIPTS / ".markdownlint-cli2.jsonc"
# npm installs a `.cmd` shim on Windows; Bun installs a `.exe` one.
_BINARY_NAMES = (
    ("markdownlint-cli2.cmd", "markdownlint-cli2.exe")
    if sys.platform == "win32"
    else ("markdownlint-cli2",)
)
BINARY = next(
    (
        SCRIPTS / "node_modules" / ".bin" / name
        for name in _BINARY_NAMES
        if (SCRIPTS / "node_modules" / ".bin" / name).is_file()
    ),
    SCRIPTS / "node_modules" / ".bin" / _BINARY_NAMES[0],
)


def main() -> int:
    if not BINARY.is_file():
        print("ERROR markdownlint: local binary not found. Run just setup.", file=sys.stderr)
        return 1
    return subprocess.call(
        [str(BINARY), "--config", str(CONFIG), "**/*.md"],
        cwd=ROOT,
    )


if __name__ == "__main__":
    raise SystemExit(main())
