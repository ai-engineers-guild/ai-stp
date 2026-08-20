from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from docs_scripts.docs_lint import Linter

DOCUMENT = """---
description: "Проверка"
last_verified: "2026-08-03"
---

# Проверка

{body}
"""


class FreshnessTests(unittest.TestCase):
    def test_the_calendar_is_explicit_and_independent_of_the_process_timezone(self) -> None:
        linter = Linter(
            template_mode=False,
            max_age=90,
            current_date=date(2026, 8, 12),
        )

        linter.check_freshness(Path("document.md"), "2026-08-13")

        self.assertEqual([issue.code for issue in linter.issues], ["FR003"])

    def test_the_explicit_utc_day_accepts_that_same_day(self) -> None:
        linter = Linter(
            template_mode=False,
            max_age=90,
            current_date=date(2026, 8, 12),
        )

        linter.check_freshness(Path("document.md"), "2026-08-12")

        self.assertEqual(linter.issues, [])


class BacktickedDocumentTests(unittest.TestCase):
    """Имя документа в обратных кавычках обязано вести к существующему файлу.

    Правило появилось после двух висячих ссылок подряд: `cli-api-contract` в
    ADR-0013 и `contracts/component-setup-manifests.md` в ADR-0012. Оба
    документа были свёрнуты, ссылки остались, и проверка ссылок Markdown их не
    видела, потому что это были не ссылки.
    """

    def _issues(self, body: str, *, existing: tuple[str, ...] = ()) -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in existing:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("# Существует\n", encoding="utf-8")
            document = root / "section" / "document.md"
            document.parent.mkdir(parents=True, exist_ok=True)
            document.write_text(DOCUMENT.format(body=body), encoding="utf-8")

            linter = Linter(template_mode=False, max_age=10_000, root=root)
            linter.check_backticked_documents(document, document.read_text(encoding="utf-8"))
            return [issue.code for issue in linter.issues]

    def test_a_missing_document_is_reported(self) -> None:
        self.assertEqual(self._issues("См. `docs/contracts/absent.md`."), ["LN002"])

    def test_an_existing_document_passes(self) -> None:
        self.assertEqual(
            self._issues("См. `neighbour.md`.", existing=("neighbour.md",)),
            [],
        )

    def test_a_reference_from_the_section_above_passes(self) -> None:
        # An ADR naming `contracts/x.md` means `docs/contracts/x.md`, which
        # resolves one level up from `docs/adr/`.
        self.assertEqual(
            self._issues("См. `contracts/neighbour.md`.", existing=("contracts/neighbour.md",)),
            [],
        )

    def test_a_document_named_by_its_file_name_alone_passes(self) -> None:
        # Documents legitimately name a neighbour by file name, and CLAUDE.md
        # and SKILL.md are real files that do not live under `docs/`.
        self.assertEqual(
            self._issues("См. `tech-stack.md`.", existing=("elsewhere/deep/tech-stack.md",)),
            [],
        )

    def test_a_non_markdown_name_is_not_a_document_reference(self) -> None:
        # `bundle.json` and `ai-stp.component.yaml` are artifact names a
        # contract describes, not files of this repository.
        self.assertEqual(self._issues("Пакет содержит `bundle.json` и `setup.yaml`."), [])

    def test_a_reference_inside_a_fence_is_not_checked(self) -> None:
        self.assertEqual(self._issues("```text\n`docs/absent.md`\n```"), [])


class AdrIdentityTests(unittest.TestCase):
    def _issues(self, documents: dict[str, str]) -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "docs" / "adr"
            base.mkdir(parents=True)
            for name, heading in documents.items():
                (base / name).write_text(DOCUMENT.format(body=heading), encoding="utf-8")
            linter = Linter(template_mode=False, max_age=10_000, root=root)
            linter.check_adr_identities()
            return [issue.code for issue in linter.issues]

    def test_duplicate_number_is_rejected(self) -> None:
        self.assertEqual(
            self._issues(
                {
                    "ADR-0042-first.md": "# ADR-0042: Первое решение",
                    "ADR-0042-second.md": "# ADR-0042: Второе решение",
                }
            ),
            ["AD002"],
        )

    def test_heading_must_match_file_identity(self) -> None:
        self.assertEqual(
            self._issues({"ADR-0042-first.md": "# ADR-0043: Первое решение"}),
            ["AD004"],
        )

    def test_unique_matching_identities_pass(self) -> None:
        self.assertEqual(
            self._issues(
                {
                    "ADR-0042-first.md": "# ADR-0042: Первое решение",
                    "ADR-0043-second.md": "# ADR-0043: Второе решение",
                }
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
