from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from docs_scripts.docs_lint import Linter

DOCUMENT = """---
description: "Check"
last_verified: "2026-08-03"
---

# Check

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


class LanguageTests(unittest.TestCase):
    def test_english_documentation_passes_in_every_area(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            linter = Linter(template_mode=False, max_age=90, root=root)

            for path in (
                root / "specs" / "active" / "SPEC-001-example.md",
                root / "docs" / "adr" / "ADR-0001-example.md",
                root / "docs" / "contracts" / "example.md",
                root / "docs" / "architecture" / "example.md",
                root / "docs" / "agent" / "example.md",
                root / "docs" / "documentation" / "example.md",
                root / "docs" / "product" / "example.md",
            ):
                linter.check_language(path, "This migrated document is written in English.")

            self.assertEqual(linter.issues, [])

    def test_russian_prose_fails(self) -> None:
        linter = Linter(template_mode=False, max_age=90)

        linter.check_language(
            Path("docs/example.md"),
            "\u042d\u0442\u0430 "
            "\u0441\u0442\u0440\u043e\u043a\u0430 "
            "\u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430\u0446\u0438\u0438 "
            "\u043f\u043e\u043b\u043d\u043e\u0441\u0442\u044c\u044e "
            "\u043d\u0430\u043f\u0438\u0441\u0430\u043d\u0430 "
            "\u043d\u0430 \u0440\u0443\u0441\u0441\u043a\u043e\u043c "
            "\u044f\u0437\u044b\u043a\u0435 \u0434\u043b\u044f "
            "\u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438.",
        )

        self.assertEqual([issue.code for issue in linter.issues], ["EN001"])


class BacktickedDocumentTests(unittest.TestCase):
    """A backticked document name must point to an existing file.

    The rule followed two consecutive dangling references: `cli-api-contract`
    in ADR-0013 and `contracts/component-setup-manifests.md` in ADR-0012. Both
    documents were folded, the references remained, and the Markdown link
    checker missed them because they were not links.
    """

    def _issues(self, body: str, *, existing: tuple[str, ...] = ()) -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in existing:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("# Exists\n", encoding="utf-8")
            document = root / "section" / "document.md"
            document.parent.mkdir(parents=True, exist_ok=True)
            document.write_text(DOCUMENT.format(body=body), encoding="utf-8")

            linter = Linter(template_mode=False, max_age=10_000, root=root)
            linter.check_backticked_documents(document, document.read_text(encoding="utf-8"))
            return [issue.code for issue in linter.issues]

    def test_a_missing_document_is_reported(self) -> None:
        self.assertEqual(self._issues("See `docs/contracts/absent.md`."), ["LN002"])

    def test_an_existing_document_passes(self) -> None:
        self.assertEqual(
            self._issues("See `neighbour.md`.", existing=("neighbour.md",)),
            [],
        )

    def test_a_reference_from_the_section_above_passes(self) -> None:
        # An ADR naming `contracts/x.md` means `docs/contracts/x.md`, which
        # resolves one level up from `docs/adr/`.
        self.assertEqual(
            self._issues("See `contracts/neighbour.md`.", existing=("contracts/neighbour.md",)),
            [],
        )

    def test_a_document_named_by_its_file_name_alone_passes(self) -> None:
        # Documents legitimately name a neighbour by file name, and CLAUDE.md
        # and SKILL.md are real files that do not live under `docs/`.
        self.assertEqual(
            self._issues("See `tech-stack.md`.", existing=("elsewhere/deep/tech-stack.md",)),
            [],
        )

    def test_a_non_markdown_name_is_not_a_document_reference(self) -> None:
        # `bundle.json` and `ai-stp.component.yaml` are artifact names a
        # contract describes, not files of this repository.
        self.assertEqual(self._issues("The package contains `bundle.json` and `setup.yaml`."), [])

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
                    "ADR-0042-first.md": "# ADR-0042: First decision",
                    "ADR-0042-second.md": "# ADR-0042: Second decision",
                }
            ),
            ["AD002"],
        )

    def test_heading_must_match_file_identity(self) -> None:
        self.assertEqual(
            self._issues({"ADR-0042-first.md": "# ADR-0043: First decision"}),
            ["AD004"],
        )

    def test_unique_matching_identities_pass(self) -> None:
        self.assertEqual(
            self._issues(
                {
                    "ADR-0042-first.md": "# ADR-0042: First decision",
                    "ADR-0043-second.md": "# ADR-0043: Second decision",
                }
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
