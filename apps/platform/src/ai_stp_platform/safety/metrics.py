"""In-process safety_* metrics for worker/API diagnostics.

No Prometheus dependency: counters live in process memory and are emitted as
structured log events. Snapshots feed doctor/readiness optional diagnostics
and unit tests. Thread-safe via a lock.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ai_stp_platform.logging import get_logger

_log = get_logger("safety.metrics")
_lock = threading.Lock()


@dataclass
class _State:
    scan_total: int = 0
    scan_cache_hit_total: int = 0
    scan_duration_ms_sum: int = 0
    scan_duration_ms_max: int = 0
    check_result_total: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    finding_total: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    cli_timeout_total: int = 0
    cli_missing_total: int = 0
    sandbox_mode_total: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    last_scan_at: float | None = None


_state = _State()


def reset_metrics() -> None:
    """Clear all counters (tests)."""
    global _state
    with _lock:
        _state = _State()


def record_scan(
    *,
    profile: str,
    wall_ms: int,
    cache_hit: bool,
    outcomes: list[Any],
) -> None:
    """Record one suite completion."""
    with _lock:
        _state.scan_total += 1
        if cache_hit:
            _state.scan_cache_hit_total += 1
        _state.scan_duration_ms_sum += max(0, int(wall_ms))
        _state.scan_duration_ms_max = max(_state.scan_duration_ms_max, int(wall_ms))
        _state.last_scan_at = time.time()
        for outcome in outcomes:
            result = str(getattr(outcome, "result", "unknown"))
            _state.check_result_total[result] += 1
            for finding in getattr(outcome, "findings", []) or []:
                family = str(getattr(finding, "family", "unknown"))
                sev = str(getattr(finding, "severity", "info"))
                key = f"{family}:{sev}"
                _state.finding_total[key] += 1

    _log.info(
        "safety_scan",
        metric="safety_scan_total",
        profile=profile,
        wall_ms=wall_ms,
        cache_hit=cache_hit,
        outcome_count=len(outcomes),
    )


def record_cli_result(*, code: int, duration_ms: int, sandbox_mode: str) -> None:
    """Record one external CLI invocation."""
    with _lock:
        _state.sandbox_mode_total[sandbox_mode] += 1
        if code == 124:
            _state.cli_timeout_total += 1
        elif code == 127:
            _state.cli_missing_total += 1
    if code in {124, 127}:
        _log.info(
            "safety_cli",
            metric="safety_cli_result",
            code=code,
            duration_ms=duration_ms,
            sandbox_mode=sandbox_mode,
        )


def snapshot() -> dict[str, Any]:
    """Return a JSON-serialisable metrics snapshot."""
    with _lock:
        scan_total = _state.scan_total
        duration_sum = _state.scan_duration_ms_sum
        avg = int(duration_sum / scan_total) if scan_total else 0
        return {
            "safety_scan_total": scan_total,
            "safety_scan_cache_hit_total": _state.scan_cache_hit_total,
            "safety_scan_duration_ms_sum": duration_sum,
            "safety_scan_duration_ms_max": _state.scan_duration_ms_max,
            "safety_scan_duration_ms_avg": avg,
            "safety_check_result_total": dict(_state.check_result_total),
            "safety_finding_total": dict(_state.finding_total),
            "safety_cli_timeout_total": _state.cli_timeout_total,
            "safety_cli_missing_total": _state.cli_missing_total,
            "safety_sandbox_mode_total": dict(_state.sandbox_mode_total),
            "safety_last_scan_at": _state.last_scan_at,
        }
