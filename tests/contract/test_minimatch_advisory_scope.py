"""Corrected upstream ranges retire the old disposition instead of extending it."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
from scripts.safety.check_advisory_scope import MINIMATCH_ADVISORY, validate_minimatch_scope

ROOT = Path(__file__).resolve().parents[2]


def test_corrected_range_needs_no_source_disposition() -> None:
    assert not (ROOT / "apps/web/osv-scanner.toml").exists()
    assert not validate_minimatch_scope({})


@pytest.mark.parametrize(
    "entry",
    [
        {"id": MINIMATCH_ADVISORY},
        {"id": MINIMATCH_ADVISORY, "ignoreUntil": date(2026, 11, 10), "reason": "old review"},
        {"id": MINIMATCH_ADVISORY, "ignoreUntil": date(2027, 1, 1), "reason": "new deadline"},
    ],
)
def test_retired_assessment_cannot_be_reintroduced(entry: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="obsolete"):
        validate_minimatch_scope({"IgnoredVulns": [entry]})


def test_other_advisories_keep_their_own_validation() -> None:
    assert not validate_minimatch_scope({"IgnoredVulns": [{"id": "another-advisory"}]})


@pytest.mark.parametrize("entries", [None, "not an inventory", ["not an entry"]])
def test_malformed_configuration_is_refused(entries: Any) -> None:
    with pytest.raises(ValueError, match="invalid"):
        validate_minimatch_scope({"IgnoredVulns": entries})
