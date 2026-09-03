"""Catalog checks percent and pending/incomplete status (#270)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, cast

# Finished verdicts. The public score is passed / (passed + failed + warning).
_VERDICT = frozenset({"passed", "failed", "warning"})
# Results that mean a planned check never produced a verdict.
_INCOMPLETE = frozenset({"not_run", "degraded", "running"})
_SKIPPED = frozenset({"not_applicable", "skipped"})


def checks_passed_percent(bindings: Iterable[dict[str, Any]]) -> int | None:
    """Return the passed share of finished verdicts, or None when none exist.

    Denominator: passed + failed + warning.
    Excludes not_applicable, skipped, not_run, degraded, and running.
    Coverage completeness remains a separate status and boolean.
    """
    rows = list(bindings)
    passed = sum(1 for r in rows if str(r.get("result")) == "passed")
    failed = sum(1 for r in rows if str(r.get("result")) == "failed")
    warning = sum(1 for r in rows if str(r.get("result")) == "warning")
    return verdict_percent(passed, failed, warning)


def verdict_percent(passed: int, failed: int, warning: int) -> int | None:
    """Card percent from stored aggregate counts (same formula as row scan)."""
    denom = passed + failed + warning
    if denom <= 0:
        return None
    return round(100 * passed / denom)


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
    if any(str(r.get("result")) in _VERDICT for r in rows):
        return "available"
    return "empty"


def coverage_complete(bindings: Iterable[dict[str, Any]]) -> bool:
    """True when no planned check is still not_run/degraded/running."""
    return not _is_pending(list(bindings)) and not _is_incomplete_coverage(list(bindings))


def is_user_facing_row(row: Mapping[str, Any]) -> bool:
    """Whether a check belongs on the catalog card and detail list.

    Finished verdicts always show. Optional unfinished/skipped checks stay on
    the machine audit list only. A mandatory unfinished check stays visible
    because it still blocks publication (REQ-723).
    """
    result = str(row.get("result"))
    if result in _VERDICT:
        return True
    return result in _INCOMPLETE and bool(row.get("mandatory", True))


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
    """Compact projection blob stored on catalog / returned by audit helpers.

    The stored ``checks`` list is the full snapshot, including optional
    unfinished rows. Public catalog projection filters that list at read time.
    """
    rows = list(bindings)
    passed = sum(1 for r in rows if str(r.get("result")) == "passed")
    failed = sum(1 for r in rows if str(r.get("result")) == "failed")
    warning = sum(1 for r in rows if str(r.get("result")) == "warning")
    not_run = sum(1 for r in rows if str(r.get("result")) == "not_run")
    return {
        "schema_version": 1,
        "status": checks_status(rows),
        "checks_passed_percent": verdict_percent(passed, failed, warning),
        "coverage_complete": coverage_complete(rows),
        "passed": passed,
        "failed": failed,
        "warning": warning,
        "not_run": not_run,
        "total_countable": passed + failed + warning,
        "checks": [
            {
                "check_id": str(r.get("check_id")),
                "result": str(r.get("result")),
                "mandatory": bool(r.get("mandatory", True)),
                "source": str(r.get("source", "")),
                "family": str(r.get("family", "")),
                "reason": _public_reason(r),
                "finding_summary": r.get("finding_summary"),
            }
            for r in rows
        ],
    }


def _public_reason(row: dict[str, Any]) -> str | None:
    """Expose only a bounded machine reason, never raw scanner output."""
    direct = row.get("reason")
    if isinstance(direct, str) and direct:
        return direct[:200]
    detail_raw = row.get("detail")
    if not isinstance(detail_raw, dict):
        return None
    detail = cast(dict[str, Any], detail_raw)
    reason = detail.get("reason")
    if not isinstance(reason, str) or not reason:
        return None
    safe = "".join(char for char in reason if char.isalnum() or char in {"_", "-", " "})
    return safe[:200] or None
