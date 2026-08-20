from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from docs_scripts.spec_lint import SpecLinter

GOOD_SPEC = """---
description: \"Проверка\"
last_verified: \"2026-08-03\"
---

# SPEC-001: Проверка

## Цель

Наблюдаемый результат.

## Границы

Входит одно поведение; другое не входит.

## Термины

`Object` — проверяемый объект.

## Требования

- `REQ-001`: Объект имеет стабильный идентификатор.

## Состояния и ошибки

`ready` и `failed` различаются.

## Безопасность и приватность

Секреты не обрабатываются.

## Совместимость и миграция

Версия схемы обязательна.

## Критерии приёмки

| Требование | Исполнимый oracle |
|---|---|
| `REQ-001` | Unit test проверяет стабильность. |
"""


class SpecLintTests(unittest.TestCase):
    def make_root(self, text: str) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name)
        directory = root / "specs" / "active"
        directory.mkdir(parents=True)
        (directory / "SPEC-001-example.md").write_text(text, encoding="utf-8")
        return root

    def test_complete_spec_passes(self) -> None:
        linter = SpecLinter(self.make_root(GOOD_SPEC))
        linter.run()
        self.assertEqual([], linter.issues)

    def test_missing_acceptance_mapping_fails(self) -> None:
        broken = GOOD_SPEC.replace(
            "| `REQ-001` | Unit test проверяет стабильность. |", "| - | Нет связи. |"
        )
        linter = SpecLinter(self.make_root(broken))
        linter.run()
        self.assertIn("SP09", {issue.code for issue in linter.issues})

    def test_missing_required_section_fails(self) -> None:
        broken = GOOD_SPEC.replace(
            "## Совместимость и миграция\n\nВерсия схемы обязательна.\n\n", ""
        )
        linter = SpecLinter(self.make_root(broken))
        linter.run()
        self.assertIn("SP06", {issue.code for issue in linter.issues})


if __name__ == "__main__":
    unittest.main()
