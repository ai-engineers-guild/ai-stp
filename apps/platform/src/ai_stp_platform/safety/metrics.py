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
from math import ceil
from typing import Any

from ai_stp_platform.logging import get_logger

_log = get_logger("safety.metrics")
_lock = threading.Lock()

# Fixed buckets keep diagnostics bounded while still making latency regressions
# visible. The largest bucket matches the safety suite hard cap.
DURATION_BUCKETS_MS = (
    1,
    10,
    50,
    100,
    250,
    500,
    1_000,
    2_500,
    5_000,
    10_000,
    30_000,
    60_000,
    300_000,
    480_000,
)
OVERFLOW_BUCKET = "+Inf"


@dataclass
class _State:
    scan_total: int = 0
    scan_cache_hit_total: int = 0
    scan_duration_ms_sum: int = 0
    scan_duration_ms_max: int = 0
    scan_duration_ms_buckets: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    check_result_total: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    check_total: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    check_duration_ms_sum: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    check_duration_ms_max: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    check_duration_ms_buckets: dict[str, dict[str, int]] = field(
        default_factory=dict[str, dict[str, int]]
    )
    check_result_by_id_total: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    finding_total: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    cli_timeout_total: int = 0
    cli_missing_total: int = 0
    sandbox_mode_total: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    queue_claim_total: int = 0
    queue_claimed_total: int = 0
    queue_empty_poll_total: int = 0
    queue_batch_size_sum: int = 0
    queue_batch_size_max: int = 0
    queue_wait_ms_sum: int = 0
    queue_wait_ms_max: int = 0
    queue_wait_ms_buckets: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    queue_job_total: int = 0
    queue_job_duration_ms_sum: int = 0
    queue_job_duration_ms_max: int = 0
    queue_job_duration_ms_buckets: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    queue_job_result_total: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    queue_requeued_total: int = 0
    last_scan_at: float | None = None


_state = _State()


def reset_metrics() -> None:
    """Clear all counters (tests)."""
    global _state
    with _lock:
        _state = _State()


def _bucket(value_ms: int) -> str:
    value = max(0, int(value_ms))
    for bound in DURATION_BUCKETS_MS:
        if value <= bound:
            return str(bound)
    return OVERFLOW_BUCKET


def _record_bucket(buckets: dict[str, int], value_ms: int) -> None:
    buckets[_bucket(value_ms)] = buckets.get(_bucket(value_ms), 0) + 1


def _quantile(buckets: dict[str, int], total: int, fraction: float) -> int | None:
    """Return the upper bound of a fixed bucket containing the quantile."""
    if total == 0:
        return 0
    target = max(1, ceil(total * fraction))
    seen = 0
    for bound in DURATION_BUCKETS_MS:
        seen += buckets.get(str(bound), 0)
        if seen >= target:
            return bound
    return None


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
        _record_bucket(_state.scan_duration_ms_buckets, wall_ms)
        _state.last_scan_at = time.time()
        for outcome in outcomes:
            check_id = str(getattr(outcome, "check_id", "unknown"))
            result = str(getattr(outcome, "result", "unknown"))
            duration_ms = max(0, int(getattr(outcome, "duration_ms", 0)))
            _state.check_result_total[result] += 1
            _state.check_total[check_id] += 1
            _state.check_duration_ms_sum[check_id] += duration_ms
            _state.check_duration_ms_max[check_id] = max(
                _state.check_duration_ms_max[check_id], duration_ms
            )
            check_buckets = _state.check_duration_ms_buckets.setdefault(check_id, {})
            _record_bucket(check_buckets, duration_ms)
            _state.check_result_by_id_total[f"{check_id}:{result}"] += 1
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


def record_queue_claim(
    *,
    batch_size: int,
    claimed_count: int,
    queue_wait_ms_sum: int = 0,
    queue_wait_ms_max: int = 0,
) -> None:
    """Record one queue poll and the wait of jobs returned by it."""
    with _lock:
        _state.queue_claim_total += 1
        _state.queue_claimed_total += max(0, int(claimed_count))
        if claimed_count == 0:
            _state.queue_empty_poll_total += 1
        _state.queue_batch_size_sum += max(0, int(batch_size))
        _state.queue_batch_size_max = max(_state.queue_batch_size_max, int(batch_size))
        _state.queue_wait_ms_sum += max(0, int(queue_wait_ms_sum))
        _state.queue_wait_ms_max = max(_state.queue_wait_ms_max, int(queue_wait_ms_max))
        if claimed_count:
            _record_bucket(_state.queue_wait_ms_buckets, queue_wait_ms_max)

    _log.info(
        "safety_queue_claim",
        metric="safety_queue_claim_total",
        batch_size=batch_size,
        claimed_count=claimed_count,
    )


def record_queue_job(*, job_type: str, duration_ms: int, result: str) -> None:
    """Record one handler execution without retaining job identifiers or payloads."""
    del job_type  # The aggregate is intentionally low-cardinality for now.
    with _lock:
        duration = max(0, int(duration_ms))
        _state.queue_job_total += 1
        _state.queue_job_duration_ms_sum += duration
        _state.queue_job_duration_ms_max = max(_state.queue_job_duration_ms_max, duration)
        _record_bucket(_state.queue_job_duration_ms_buckets, duration)
        _state.queue_job_result_total[str(result)] += 1


def record_queue_requeue(*, count: int) -> None:
    """Record jobs returned to the queue during worker drain."""
    with _lock:
        _state.queue_requeued_total += max(0, int(count))


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
            "safety_scan_duration_ms_buckets": dict(_state.scan_duration_ms_buckets),
            "safety_scan_duration_ms_p50": _quantile(
                _state.scan_duration_ms_buckets, scan_total, 0.50
            ),
            "safety_scan_duration_ms_p95": _quantile(
                _state.scan_duration_ms_buckets, scan_total, 0.95
            ),
            "safety_scan_duration_ms_p99": _quantile(
                _state.scan_duration_ms_buckets, scan_total, 0.99
            ),
            "safety_check_result_total": dict(_state.check_result_total),
            "safety_check_total": dict(_state.check_total),
            "safety_check_duration_ms_sum": dict(_state.check_duration_ms_sum),
            "safety_check_duration_ms_max": dict(_state.check_duration_ms_max),
            "safety_check_duration_ms_avg": {
                check_id: int(_state.check_duration_ms_sum[check_id] / count)
                for check_id, count in _state.check_total.items()
            },
            "safety_check_duration_ms_buckets": {
                check_id: dict(buckets)
                for check_id, buckets in _state.check_duration_ms_buckets.items()
            },
            "safety_check_result_by_id_total": dict(_state.check_result_by_id_total),
            "safety_finding_total": dict(_state.finding_total),
            "safety_cli_timeout_total": _state.cli_timeout_total,
            "safety_cli_missing_total": _state.cli_missing_total,
            "safety_sandbox_mode_total": dict(_state.sandbox_mode_total),
            "safety_queue_claim_total": _state.queue_claim_total,
            "safety_queue_claimed_total": _state.queue_claimed_total,
            "safety_queue_empty_poll_total": _state.queue_empty_poll_total,
            "safety_queue_batch_size_sum": _state.queue_batch_size_sum,
            "safety_queue_batch_size_max": _state.queue_batch_size_max,
            "safety_queue_wait_ms_sum": _state.queue_wait_ms_sum,
            "safety_queue_wait_ms_max": _state.queue_wait_ms_max,
            "safety_queue_wait_ms_buckets": dict(_state.queue_wait_ms_buckets),
            "safety_queue_job_total": _state.queue_job_total,
            "safety_queue_job_duration_ms_sum": _state.queue_job_duration_ms_sum,
            "safety_queue_job_duration_ms_max": _state.queue_job_duration_ms_max,
            "safety_queue_job_duration_ms_buckets": dict(_state.queue_job_duration_ms_buckets),
            "safety_queue_job_result_total": dict(_state.queue_job_result_total),
            "safety_queue_requeued_total": _state.queue_requeued_total,
            "safety_last_scan_at": _state.last_scan_at,
        }
