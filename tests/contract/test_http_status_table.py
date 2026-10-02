"""The published status table must name every registered error code.

`docs/contracts/http-api.md` declares the stable-code-to-status mapping
closed: whatever `ERROR_CODES` registers is what the wire can carry, and a
code the table omits is a status the reader cannot predict for a real
error. The drift is silent in both directions — a new code lands in the
registry without a table edit, and a stale row survives a code's removal —
so the check compares the whole mapping, not a sample of it.
"""

from __future__ import annotations

import re
from pathlib import Path

from ai_stp_contracts.http import http_status_for
from ai_stp_foundation.errors import ERROR_CODES

TABLE = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "http-api.md"

#: One row of the closed mapping table: `| `400` | `AI_STP_…`, `AI_STP_…` |`.
_ROW = re.compile(r"^\|\s*`(?P<status>\d{3})`\s*\|(?P<codes>[^|]*)\|\s*$", re.MULTILINE)
_CODE = re.compile(r"`(AI_STP_[A-Z0-9_]+)`")


def _documented_mapping() -> dict[str, int]:
    section = TABLE.read_text(encoding="utf-8").split("## Errors", 1)[1].split("\n## ", 1)[0]
    mapping: dict[str, int] = {}
    for row in _ROW.finditer(section):
        status = int(row.group("status"))
        for code in _CODE.findall(row.group("codes")):
            assert code not in mapping, f"{code} is listed under two statuses"
            mapping[code] = status
    return mapping


def test_the_status_table_names_every_registered_code_exactly() -> None:
    # Missing rows, unknown codes and wrong statuses all land in the same
    # comparison; the diff names which side drifted.
    assert _documented_mapping() == {code: http_status_for(code) for code in ERROR_CODES}
