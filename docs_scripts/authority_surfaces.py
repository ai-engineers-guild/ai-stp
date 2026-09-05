"""Inventory of agent-facing authority prose, and the contradictions it forbids.

`ADR-0150` / `ADR-0159` close the remaining human stops. Installed skills,
AGENTS files, and agent docs must not demand a pause for in-task work
(experimental composition, unknown engineering facts, a second confirm on a
plan digest). This module names the surfaces and the forbidden phrases.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

ROOT: Final[Path] = Path(__file__).resolve().parents[1]

#: Remaining stops from `skills/canonical/ai-stp/references/decisions.md`.
REMAINING_STOPS: Final[tuple[str, ...]] = (
    "visibility or access of an existing",
    "someone else's",
    "system privileges",
    "without recovery",
)

#: Named patterns that demand a pause ADR-0150 already removed.
CONTRADICTIONS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("ask_the_owner", re.compile(r"\bask the owner before\b", re.I)),
    (
        "experimental_needs_decision",
        re.compile(r"experimental.{0,160}need a separate user decision", re.I | re.S),
    ),
    (
        "unverified_author_needs_decision",
        re.compile(r"unverified-author.{0,80}separate user decision", re.I),
    ),
    (
        "experimental_lane_stop",
        re.compile(
            r"consent to the `experimental` lane or selection of an object "
            r"from an unverified author",
            re.I,
        ),
    ),
    (
        "ask_before_invocation",
        re.compile(r"must ask the user before invocation", re.I),
    ),
    (
        "ask_unknown_fields",
        re.compile(r"asks about unknown required fields", re.I),
    ),
    (
        "public_version_as_stop",
        re.compile(r"a public version, major version line, visibility change", re.I),
    ),
)

IN_TASK_APPLY: Final[tuple[tuple[str, ...], ...]] = (
    ("component", "scaffold", "apply"),
    ("setup", "compose", "apply"),
    ("setup", "update", "apply"),
    ("select", "confirm"),
    ("install", "apply"),
    ("component", "version", "release"),
)


@dataclass(frozen=True)
class Finding:
    """One forbidden pause in one inventoried file."""

    path: str
    line: int
    kind: str
    excerpt: str


def inventory(root: Path = ROOT) -> tuple[Path, ...]:
    """Every agent-facing surface this check owns, in a stable order."""
    required = (
        root / "AGENTS.md",
        root / ".claude" / "CLAUDE.md",
        root / "skills" / "canonical" / "ai-stp" / "SKILL.md",
        root / "skills" / "canonical" / "ai-stp" / "references" / "decisions.md",
        root / "docs" / "agent" / "interaction-policy.md",
        root / "docs" / "agent" / "integration-skill.md",
        root / "docs" / "agent" / "machine-help.md",
    )
    globs = (
        "skills/canonical/ai-stp/**/*.md",
        "skills/projections/**/*.md",
        "apps/cli/src/ai_stp_cli/skills/**/*.md",
        "docs/agent/*.md",
        "packages/contracts/src/ai_stp_contracts/first_party/v1/*instruction*.md",
    )
    found: set[Path] = set()
    for path in required:
        found.add(path)
    for pattern in globs:
        found.update(root.glob(pattern))
    return tuple(sorted(path for path in found if path.is_file()))


def scan(paths: Iterable[Path], *, root: Path = ROOT) -> tuple[Finding, ...]:
    """Return every contradiction in the given files."""
    findings: list[Finding] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        relative = _relative(path, root)
        for kind, pattern in CONTRADICTIONS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                excerpt = match.group(0).replace("\n", " ")
                findings.append(Finding(relative, line, kind, excerpt))
    return tuple(findings)


def scan_tree(root: Path = ROOT) -> tuple[Finding, ...]:
    return scan(inventory(root), root=root)


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
