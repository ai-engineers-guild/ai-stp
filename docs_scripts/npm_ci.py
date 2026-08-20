#!/usr/bin/env python3
"""Запуск npm ci без shell-проблем с путём к npm на Windows."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "docs_scripts"


def main() -> int:
    npm = shutil.which("npm")
    if not npm:
        print("ОШИБКА npm: npm не найден. Установи Node.js/npm.", file=sys.stderr)
        return 1
    return subprocess.call([npm, "ci"], cwd=SCRIPTS)


if __name__ == "__main__":
    raise SystemExit(main())
