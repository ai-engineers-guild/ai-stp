"""Every reviewer finding has one durable disposition and an explicit owner."""

import re
from pathlib import Path

STATUS = Path(__file__).parents[2] / "docs" / "engineering" / "audit-remediation-status.md"

EXPECTED = {
    "RVR-P1-001",
    "RVR-P2-002",
    "RVR-P2-003",
    "RVR-P2-004",
    "RVR-P2-005",
    "RVR-P2-006",
    "RVR-P2-007",
    "RVR-P2-008",
    "RVR-P2-009",
    "RVR-P3-010",
    "RVR-P3-011",
}
DISPOSITIONS = {"confirmed", "modified", "rejected", "blocked"}
ROW = re.compile(
    r"^\| `(?P<id>RVR-P[123]-\d{3})` \| `(?P<disposition>\w+)` \|",
    re.MULTILINE,
)


def test_every_audit_finding_has_exactly_one_allowed_disposition() -> None:
    text = STATUS.read_text(encoding="utf-8")
    found = ROW.findall(text)
    identifiers = [identifier for identifier, _disposition in found]

    assert set(identifiers) == EXPECTED
    assert len(identifiers) == len(set(identifiers))
    assert {disposition for _identifier, disposition in found} <= DISPOSITIONS


def test_every_finding_names_remaining_evidence_and_an_owner() -> None:
    text = STATUS.read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith("| `RVR-")]

    assert len(rows) == len(EXPECTED)
    for row in rows:
        assert "Owner:" in row, row
        cells = row.split("|")
        assert len(cells) == 6, row
        assert cells[4].strip(), row
