#!/usr/bin/env python3
"""Переносимая установка git hooks для Windows/Linux/macOS."""

from __future__ import annotations

import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# pre-push вызывает `just check` напрямую: отдельный рецепт-алиас существовал бы
# только ради этой строки и был бы вторым именем одного поведения.
HOOKS = {
    "pre-commit": "just pre-commit\n",
    "pre-push": "just check\n",
}


def main() -> int:
    hooks_dir = ROOT / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    for name, command in HOOKS.items():
        path = hooks_dir / name
        path.write_text(f"#!/bin/sh\n{command}", encoding="utf-8", newline="\n")
        current = path.stat().st_mode
        path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print("хуки установлены")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
