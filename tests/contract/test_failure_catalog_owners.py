"""Every failure-catalog owner must still exist as a path, ADR, spec, or code."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "docs" / "engineering" / "failure-catalog.md"
_ADR = re.compile(r"^ADR-\d{4}$")
_SPEC = re.compile(r"^SPEC-\d{3}$")
_REQ = re.compile(r"^REQ-\d+$")
_TICK = re.compile(r"`([^`]+)`")


def _owner_cells() -> list[str]:
    rows: list[str] = []
    in_table = False
    for line in CATALOG.read_text(encoding="utf-8").splitlines():
        if line.startswith("| Lesson |"):
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) >= 3:
                rows.append(cells[2])
            continue
        if in_table:
            break
    if not rows:
        raise AssertionError("failure catalog has no owner rows")
    return rows


def _exists(owner: str) -> bool:
    if owner == "this catalog":
        return CATALOG.is_file()
    if _ADR.fullmatch(owner):
        return any((ROOT / "docs" / "adr").glob(f"{owner}*.md"))
    if _SPEC.fullmatch(owner):
        return any((ROOT / "specs" / "active").glob(f"{owner}-*.md"))
    if _REQ.fullmatch(owner):
        return any(
            owner in path.read_text(encoding="utf-8")
            for path in (ROOT / "specs" / "active").glob("*.md")
        )
    path = ROOT / owner
    if "/" in owner or owner.endswith((".md", ".py", ".toml")):
        return path.is_file()
    return any(
        owner in candidate.read_text(encoding="utf-8")
        for candidate in (
            ROOT / "docs" / "contracts" / "eligibility-constraints.md",
            ROOT / "apps" / "cli" / "src" / "ai_stp_cli" / "errors.py",
        )
        if candidate.is_file()
    )


def test_every_failure_catalog_owner_still_exists() -> None:
    missing: list[str] = []
    for cell in _owner_cells():
        owners = _TICK.findall(cell)
        if not owners:
            missing.append(f"unquoted owner cell: {cell}")
            continue
        for owner in owners:
            if not _exists(owner):
                missing.append(owner)
    assert missing == []
