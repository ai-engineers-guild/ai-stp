"""Catalog checks percent and pending/incomplete status (#270)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

# Results included in the public completion score. An unfinished planned check
# counts in the denominator while status/coverage still disclose incompleteness.
_COUNTABLE = frozenset({"passed", "failed", "warning", "not_run", "degraded", "running"})
# Results that mean a planned check never produced a verdict.
_INCOMPLETE = frozenset({"not_run", "degraded", "running"})
_SKIPPED = frozenset({"not_applicable", "skipped"})


def checks_passed_percent(bindings: Iterable[dict[str, Any]]) -> int | None:
    """Return the passed share of planned checks, or None when none were planned.

    Denominator: every planned check with a result other than skipped/not_applicable.
    Excludes not_applicable, skipped.
    Coverage completeness remains a separate status and boolean.
    """
    rows = list(bindings)
    countable = [r for r in rows if str(r.get("result")) in _COUNTABLE]
    if not countable:
        return None
    passed = sum(1 for r in countable if str(r.get("result")) == "passed")
    return round(100 * passed / len(countable))


def checks_status(bindings: Iterable[dict[str, Any]]) -> str:
    """High-level status: pending | incomplete | available | empty.

    - pending: mandatory planned check not finished (not_run/degraded/running)
    - incomplete: optional/external tools not_run (or other incomplete) after
      mandatory gates finished — coverage is not full
    - available: every planned check has a countable or skipped verdict
    - empty: no bindings
    """
    rows = list(bindings)
    if not rows:
        return "empty"
    if _is_pending(rows):
        return "pending"
    if _is_incomplete_coverage(rows):
        return "incomplete"
    if any(str(r.get("result")) in _COUNTABLE for r in rows):
        return "available"
    return "empty"


def coverage_complete(bindings: Iterable[dict[str, Any]]) -> bool:
    """True when no planned check is still not_run/degraded/running."""
    return not _is_pending(list(bindings)) and not _is_incomplete_coverage(list(bindings))


def _is_pending(rows: list[dict[str, Any]]) -> bool:
    """Mandatory gates still unfinished."""
    for row in rows:
        if not bool(row.get("mandatory", True)):
            continue
        if str(row.get("result")) in _SKIPPED:
            continue
        if str(row.get("result")) in _INCOMPLETE:
            return True
    return False


def _is_incomplete_coverage(rows: list[dict[str, Any]]) -> bool:
    """Any non-skipped check still not finished (includes optional tool missing)."""
    for row in rows:
        if str(row.get("result")) in _SKIPPED:
            continue
        if str(row.get("result")) in _INCOMPLETE:
            return True
    return False


def build_checks_summary(bindings: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Compact projection blob stored on catalog / returned by audit helpers."""
    rows = list(bindings)
    not_run = sum(1 for r in rows if str(r.get("result")) == "not_run")
    return {
        "schema_version": 1,
        "status": checks_status(rows),
        "checks_passed_percent": checks_passed_percent(rows),
        "coverage_complete": coverage_complete(rows),
        "passed": sum(1 for r in rows if str(r.get("result")) == "passed"),
        "failed": sum(1 for r in rows if str(r.get("result")) == "failed"),
        "warning": sum(1 for r in rows if str(r.get("result")) == "warning"),
        "not_run": not_run,
        "total_countable": sum(1 for r in rows if str(r.get("result")) in _COUNTABLE),
        "checks": [
            {
                "check_id": str(r.get("check_id")),
                "result": str(r.get("result")),
                "mandatory": bool(r.get("mandatory", True)),
                "source": str(r.get("source", "")),
                "family": str(r.get("family", "")),
                "reason": _public_reason(r),
            }
            for r in rows
        ],
    }


def _public_reason(row: dict[str, Any]) -> str | None:
    """Expose only a bounded machine reason, never raw scanner output or paths."""
    detail_raw = row.get("detail")
    if not isinstance(detail_raw, dict):
        return None
    detail = cast(dict[str, Any], detail_raw)
    reason = detail.get("reason")
    if not isinstance(reason, str) or not reason:
        return None
    safe = "".join(char for char in reason if char.isalnum() or char in {"_", "-", " "})
    return safe[:200] or None
