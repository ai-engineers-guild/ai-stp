#!/usr/bin/env python3
"""Рендер всех Mermaid-блоков через закреплённый repository-local mmdc."""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MMDC = (
    ROOT
    / "docs_scripts"
    / "node_modules"
    / ".bin"
    / ("mmdc.cmd" if sys.platform == "win32" else "mmdc")
)
BLOCK_RE = re.compile(r"^```mermaid\n(.*?)^```", re.S | re.M)

#: Каталоги, которые обход не должен считать документацией репозитория.
#: Git знает это сам; список нужен только пути без Git.
_WALK_EXCLUDED = frozenset({"node_modules", ".venv", ".next", ".git", ".site", "dist"})


def documents() -> list[Path]:
    """Markdown, который репозиторий действительно содержит.

    Ответ даёт Git, а не обход дерева. Обход находит и сборочный вывод: `.next`
    создаёт каталог с именем `agents.md`, и попытка прочитать его как файл
    роняла проверку. Список ignore пришлось бы дополнять под каждый новый
    инструмент сборки, тогда как Git уже знает этот ответ.

    Берутся отслеживаемые файлы и неотслеживаемые, не объявленные в ignore:
    новый локальный документ проходит проверку до первого `git add`.
    """
    try:
        listed = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "*.md"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as failure:
        # Вне рабочего дерева Git обход остаётся единственным источником, но он
        # находит и зависимости. Один раз это уже покрасило гейт: в контейнере
        # `git` отказал с `detected dubious ownership` — checkout принадлежит
        # другому uid, — обход подобрал 40 mermaid-блоков из README пакетов в
        # `docs_scripts/node_modules`, и проверка отчиталась о сорока
        # нерендерящихся блоках, ни один из которых не принадлежит репозиторию.
        #
        # Поэтому отказ Git печатается, а не проглатывается: молчаливая замена
        # источника меняет то, что вообще проверяется. И обход исключает
        # каталоги зависимостей — их содержимое не наше и чинить его нечем.
        print(f"ВНИМАНИЕ mermaid: git недоступен ({failure}); обход дерева", file=sys.stderr)
        return sorted(
            path
            for path in ROOT.rglob("*.md")
            if path.is_file() and not any(part in _WALK_EXCLUDED for part in path.parts)
        )
    return sorted({ROOT / name for name in listed.split("\0") if name and (ROOT / name).is_file()})


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")  # pyright: ignore[reportAttributeAccessIssue]

    if not MMDC.is_file():
        print("ОШИБКА mermaid: локальный mmdc не найден. Запусти just setup.")
        return 1

    failures = 0
    checked = 0
    with tempfile.TemporaryDirectory() as tmp_raw:
        tmp = Path(tmp_raw)
        for path in documents():
            text = path.read_text(encoding="utf-8")
            for index, block in enumerate(BLOCK_RE.findall(text), start=1):
                identity = hashlib.sha256(f"{path}:{index}".encode()).hexdigest()[:12]
                source = tmp / f"{identity}.mmd"
                output = tmp / f"{identity}.svg"
                source.write_text(block, encoding="utf-8")
                try:
                    result = subprocess.run(
                        [str(MMDC), "-i", str(source), "-o", str(output)],
                        capture_output=True,
                        text=True,
                        timeout=45,
                        check=False,
                    )
                except subprocess.TimeoutExpired:
                    failures += 1
                    print(f"ОШИБКА {path.relative_to(ROOT)}: блок {index} превысил 45 секунд")
                    continue
                checked += 1
                if result.returncode != 0:
                    failures += 1
                    details = (result.stderr or result.stdout)[-4000:].strip().splitlines()
                    reason = details[-1] if details else "неизвестная ошибка"
                    relative = path.relative_to(ROOT)
                    print(f"::error file={relative},title=mermaid::блок {index}: {reason}")
                    print(f"ОШИБКА {relative}: блок {index} не рендерится: {reason}")

    print(f"Проверено блоков: {checked}, не отрендерилось: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
