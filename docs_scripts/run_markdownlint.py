#!/usr/bin/env python3
"""Запуск закреплённого repository-local markdownlint-cli2."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "docs_scripts"
CONFIG = SCRIPTS / ".markdownlint-cli2.jsonc"
BINARY = (
    SCRIPTS
    / "node_modules"
    / ".bin"
    / ("markdownlint-cli2.cmd" if sys.platform == "win32" else "markdownlint-cli2")
)


def main() -> int:
    if not BINARY.is_file():
        print(
            "ОШИБКА markdownlint: локальный binary не найден. Запусти just setup.", file=sys.stderr
        )
        return 1
    return subprocess.call(
        [str(BINARY), "--config", str(CONFIG), "**/*.md"],
        cwd=ROOT,
    )


if __name__ == "__main__":
    raise SystemExit(main())
