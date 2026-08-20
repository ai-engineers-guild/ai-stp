#!/usr/bin/env python3
"""Report the redistribution terms embedded in every tracked font file.

A font is the one binary a repository routinely carries that can forbid its own
presence. The terms are inside the file — `name` table records 0, 7, 13 and 14 —
so this is a fact the repository can check rather than a thing someone has to
remember having checked once.

This is deliberately not part of `just check`. Whether a restricted font may stay
is a licensing decision with a cost attached, and a gate that fails today would
be this script choosing for the owner. It exits non-zero only with `--strict`,
which is what a release gate would use once that decision is made.

Run: `just fonts-licence` or `python docs_scripts/font_licence_audit.py`.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: `name` table records that carry ownership or permission.
NAME_IDS = {0: "copyright", 7: "trademark", 13: "licence", 14: "licence_url"}

FONT_SUFFIXES = {".woff", ".woff2", ".ttf", ".otf", ".eot"}

#: Wording that denies the two things a public repository does by existing.
#: Matched case-insensitively against the copyright and licence records.
DENIALS = (
    r"all rights reserved",
    r"may not be (?:copied|distributed|redistributed|shared)",
    r"must not be (?:copied|distributed|redistributed|shared)",
    r"no use of this font is allowed",
    r"excludes[^.]*redistribut",
    r"excludes[^.]*storing on publicly available servers",
    r"not (?:be )?redistribut",
    r"prohibit[^.]*(?:redistribut|shar)",
)

#: Wording that grants redistribution outright. Checked first: a permissive
#: licence still says "all rights reserved" in its copyright line, and reading
#: the denial first would misfile every OFL face.
#:
#: The licence URL is part of this evidence, not decoration. Subsetting a font
#: for the web strips the licence text in record 13 while keeping the URL in
#: record 14, so for the files a site actually ships the URL is often the only
#: statement of terms left in the file.
GRANTS = (
    r"\bSIL Open Font License\b",
    r"\bOFL\b",
    r"scripts\.sil\.org/OFL",
    r"openfontlicense\.org",
    r"\bApache License\b",
    r"apache\.org/licenses",
    r"\bMIT License\b",
    r"opensource\.org/licenses/MIT",
    r"\bpublic domain\b",
    r"\bCC0\b",
    r"creativecommons\.org/publicdomain",
)


@dataclass(frozen=True)
class FontVerdict:
    """One tracked font and what its own metadata says about redistribution."""

    path: str
    family: str
    verdict: str
    evidence: str

    @property
    def restricted(self) -> bool:
        return self.verdict == "restricted"


def tracked_fonts() -> list[Path]:
    """Every font git tracks. Untracked files cannot be redistributed by us."""
    listed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted(
        ROOT / name
        for name in listed.split("\0")
        if name and Path(name).suffix.lower() in FONT_SUFFIXES
    )


def _records(path: Path) -> dict[str, str]:
    # Imported here so the module loads without the dependency present. It is
    # supplied by the recipe through `uv run --with` and never enters the
    # project lockfile: an audit run by hand should not weigh on every install.
    from fontTools.ttLib import TTFont  # pyright: ignore[reportMissingImports]

    font = TTFont(path)
    found: dict[str, str] = {}
    for record in font["name"].names:
        key = NAME_IDS.get(record.nameID) or ("family" if record.nameID == 1 else None)
        if key is None or key in found:
            continue
        try:
            found[key] = record.toUnicode().strip()
        except UnicodeDecodeError:
            continue
    return found


def classify(path: Path) -> FontVerdict:
    """Decide from the file's own words, never from its filename."""
    relative = str(path.relative_to(ROOT))
    try:
        found = _records(path)
    except Exception as exc:
        # A font this script cannot parse is itself a reportable state: an
        # unreadable file is not evidence that its terms permit anything.
        return FontVerdict(relative, "?", "unreadable", f"{type(exc).__name__}: {exc}")

    family = found.get("family", "?")
    haystack = " ".join(
        found.get(key, "") for key in ("copyright", "licence", "licence_url", "trademark")
    )
    if not haystack.strip():
        return FontVerdict(relative, family, "undeclared", "no copyright or licence record")

    for pattern in GRANTS:
        match = re.search(pattern, haystack, re.IGNORECASE)
        if match:
            return FontVerdict(relative, family, "permissive", match.group(0))
    for pattern in DENIALS:
        match = re.search(pattern, haystack, re.IGNORECASE)
        if match:
            return FontVerdict(relative, family, "restricted", match.group(0))
    return FontVerdict(relative, family, "undeclared", haystack[:120])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero when a tracked font forbids redistribution",
    )
    args = parser.parse_args(argv)

    fonts = tracked_fonts()
    if not fonts:
        print("No tracked font files.")
        return 0

    verdicts = [classify(path) for path in fonts]
    width = max(len(v.path) for v in verdicts)
    for verdict in verdicts:
        print(f"{verdict.verdict:11} {verdict.path:<{width}}  {verdict.family}")
        if verdict.verdict != "permissive":
            print(f"{'':11} {'':<{width}}  ↳ {verdict.evidence}")

    restricted = [v for v in verdicts if v.restricted]
    undeclared = [v for v in verdicts if v.verdict == "undeclared"]
    print()
    print(f"tracked: {len(verdicts)}  restricted: {len(restricted)}  undeclared: {len(undeclared)}")

    if restricted:
        print()
        print(
            "A restricted font is tracked. This repository becomes public at first\n"
            "release and is AGPL-3.0-or-later, which obliges source distribution —\n"
            "both are what these licences exclude. Resolve by licensing "
            "redistribution,\nserving the file from outside the repository at build time, or "
            "replacing the\nface. See docs/engineering/quality-gates.md."
        )
    if args.strict and restricted:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
