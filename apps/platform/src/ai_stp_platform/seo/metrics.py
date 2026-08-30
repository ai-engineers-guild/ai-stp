"""Aggregated SEO metrics. No prompt, body, subject ID or job payload."""

from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from ai_stp_platform.safety.metrics import DURATION_BUCKETS_MS, OVERFLOW_BUCKET

_lock = threading.Lock()


def _bucket(duration_ms: int) -> str:
    for edge in DURATION_BUCKETS_MS:
        if duration_ms <= edge:
            return str(edge)
    return OVERFLOW_BUCKET


@dataclass
class _SeoState:
    build_total: int = 0
    build_duration_ms_sum: int = 0
    build_duration_ms_max: int = 0
    build_outcome_total: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    enrich_total: int = 0
    enrich_duration_ms_sum: int = 0
    enrich_duration_ms_max: int = 0
    enrich_outcome_total: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    active_base_total: int = 0
    active_enriched_total: int = 0
    rejected_reason_total: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    stale_total: int = 0
    index_reason_total: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    sitemap_generation: int = 0
    sitemap_cache_age_seconds: int = 0
    model_request_total: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    model_token_total: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    model_cost_micros_total: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    build_duration_ms_buckets: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    enrich_duration_ms_buckets: dict[str, int] = field(default_factory=lambda: defaultdict(int))


_state = _SeoState()


def reset_seo_metrics() -> None:
    global _state
    with _lock:
        _state = _SeoState()


def record_seo_build(*, outcome: str, duration_ms: int, index_reasons: Sequence[str]) -> None:
    with _lock:
        _state.build_total += 1
        _state.build_duration_ms_sum += duration_ms
        _state.build_duration_ms_max = max(_state.build_duration_ms_max, duration_ms)
        _state.build_outcome_total[outcome] += 1
        _state.build_duration_ms_buckets[_bucket(duration_ms)] += 1
        for reason in index_reasons:
            _state.index_reason_total[reason] += 1
        if outcome == "base_active":
            _state.active_base_total += 1


def record_seo_enrich(
    *,
    outcome: str,
    duration_ms: int,
    model_alias: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost_micros: int = 0,
) -> None:
    with _lock:
        _state.enrich_total += 1
        _state.enrich_duration_ms_sum += duration_ms
        _state.enrich_duration_ms_max = max(_state.enrich_duration_ms_max, duration_ms)
        _state.enrich_outcome_total[outcome] += 1
        _state.enrich_duration_ms_buckets[_bucket(duration_ms)] += 1
        if outcome == "active":
            _state.active_enriched_total += 1
        elif outcome == "stale":
            _state.stale_total += 1
        else:
            _state.rejected_reason_total[outcome] += 1
        if model_alias:
            _state.model_request_total[model_alias] += 1
            _state.model_token_total[model_alias] += prompt_tokens + completion_tokens
            _state.model_cost_micros_total[model_alias] += cost_micros


def record_sitemap_generation(*, generation: int, cache_age_seconds: int) -> None:
    with _lock:
        _state.sitemap_generation = generation
        _state.sitemap_cache_age_seconds = cache_age_seconds


def seo_metrics_snapshot() -> dict[str, Any]:
    with _lock:
        return {
            "seo_build_total": _state.build_total,
            "seo_build_duration_ms_sum": _state.build_duration_ms_sum,
            "seo_build_duration_ms_max": _state.build_duration_ms_max,
            "seo_build_outcome_total": dict(_state.build_outcome_total),
            "seo_build_duration_ms_buckets": dict(_state.build_duration_ms_buckets),
            "seo_enrich_total": _state.enrich_total,
            "seo_enrich_duration_ms_sum": _state.enrich_duration_ms_sum,
            "seo_enrich_duration_ms_max": _state.enrich_duration_ms_max,
            "seo_enrich_outcome_total": dict(_state.enrich_outcome_total),
            "seo_enrich_duration_ms_buckets": dict(_state.enrich_duration_ms_buckets),
            "seo_active_base_total": _state.active_base_total,
            "seo_active_enriched_total": _state.active_enriched_total,
            "seo_rejected_reason_total": dict(_state.rejected_reason_total),
            "seo_stale_total": _state.stale_total,
            "seo_index_reason_total": dict(_state.index_reason_total),
            "seo_sitemap_generation": _state.sitemap_generation,
            "seo_sitemap_cache_age_seconds": _state.sitemap_cache_age_seconds,
            "seo_model_request_total": dict(_state.model_request_total),
            "seo_model_token_total": dict(_state.model_token_total),
            "seo_model_cost_micros_total": dict(_state.model_cost_micros_total),
        }
