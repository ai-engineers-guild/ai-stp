"""The two language lines of the user documentation describe the same product.

Russian is the source: `docs/documentation/maintenance.md` makes prose Russian,
and the user documentation was written that way first. English exists because
the product's own web surface is bilingual — `en.json` and `ru.json` are both
complete and routing is by `[locale]` — so documentation in one language was
the odd surface out (`#26`).

Two lines drift the moment one gains a page the other does not. That is what
this refuses. It does not check meaning: nothing mechanical can, and claiming
otherwise would be worse than saying so.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

#: Written as code points rather than as letters: a rule about Cyrillic that
#: contains Cyrillic trips the linter's ambiguous-character check, and the
#: character it would flag is exactly what the rule is looking for.
CYRILLIC: Final[re.Pattern[str]] = re.compile("[\u0410-\u044f\u0401\u0451]")

ROOT = Path(__file__).resolve().parents[2]
RU: Final[Path] = ROOT / "docs-user-facing" / "docs" / "ru"
EN: Final[Path] = ROOT / "docs-user-facing" / "docs" / "en"


def _pages(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in root.rglob("*.md")}


def test_both_languages_carry_the_same_pages() -> None:
    """A page in one line and not the other is a hole a reader falls into."""
    russian, english = _pages(RU), _pages(EN)
    assert russian, "the Russian user documentation is missing"
    missing = sorted(russian - english)
    extra = sorted(english - russian)
    assert not missing, f"the English line has no counterpart for: {missing}"
    assert not extra, f"the English line has pages Russian does not: {extra}"


def test_no_legacy_user_facing_source_trees_remain() -> None:
    """Every renderer must consume the canonical root instead of a tracked copy."""
    legacy = (
        ROOT / "user-docs",
        ROOT / "user-docs-en",
        ROOT / "apps" / "web" / "content" / "user-docs",
        ROOT / "apps" / "web" / "content" / "hub",
        ROOT / "apps" / "platform" / "src" / "ai_stp_platform" / "legal" / "en",
        ROOT / "apps" / "platform" / "src" / "ai_stp_platform" / "legal" / "ru",
    )
    assert not [path.relative_to(ROOT) for path in legacy if path.exists()]


def test_every_page_declares_a_description_in_its_own_language() -> None:
    """`description` becomes the meta tag and the search snippet.

    Copying the Russian one across is the cheapest way to look translated
    while shipping Russian to an English reader, so the English side must not
    contain Cyrillic here.
    """
    wrong: list[str] = []
    for path in sorted(EN.rglob("*.md")):
        head = path.read_text(encoding="utf-8").split("---", 2)
        assert len(head) >= 3, f"{path.relative_to(ROOT)} has no frontmatter"
        declared = re.search(r'description:\s*"([^"]*)"', head[1])
        if declared is None:
            wrong.append(f"{path.relative_to(ROOT)}: no description")
        elif CYRILLIC.search(declared.group(1)):
            wrong.append(f"{path.relative_to(ROOT)}: description is still Russian")
    assert not wrong, "\n".join(wrong)


def test_the_english_line_is_actually_english() -> None:
    """Prose, not only frontmatter — an untranslated page is the failure mode.

    Identifiers, commands and product names stay Latin in both lines, so a
    Cyrillic character in the English tree is always a leftover. Counted
    rather than forbidden outright by line, because one stray character in a
    quoted example should not be a gate failure while a whole untranslated
    page must be.
    """
    wrong = [
        f"{path.relative_to(ROOT)}: {len(CYRILLIC.findall(path.read_text(encoding='utf-8')))}"
        f" Cyrillic characters"
        for path in sorted(EN.rglob("*.md"))
        if len(CYRILLIC.findall(path.read_text(encoding="utf-8"))) > 8
    ]
    assert not wrong, "these English pages still carry Russian prose:\n" + "\n".join(wrong)


def test_the_two_builds_are_declared_and_ordered() -> None:
    """Russian cleans the site directory; English writes `en/` inside it.

    Reversing them ships one language and hides it behind a green build, which
    is why the order is asserted rather than trusted to a comment.
    """
    for name in ("justfile", "Dockerfile.user-docs"):
        text = (ROOT / name).read_text(encoding="utf-8")
        russian = text.find("user-mkdocs.yml")
        english = text.find("user-mkdocs.en.yml")
        assert russian != -1, f"{name} no longer builds the Russian line"
        assert english != -1, f"{name} does not build the English line"
        assert russian < english, (
            f"{name} builds English before Russian; the Russian build cleans the "
            "site directory and would delete it"
        )
