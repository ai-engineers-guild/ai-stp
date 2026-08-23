# pyright: reportPrivateUsage=false
"""Deterministic offline safety benchmark evidence."""

from __future__ import annotations

import pytest
from scripts.safety.benchmark_offline import (  # pyright: ignore[reportPrivateUsage]
    CASES,
    _quantile,
    build_payload,
)

from ai_stp_foundation.digests import digest_bytes
from ai_stp_platform.safety.metrics import DURATION_BUCKETS_MS
from ai_stp_platform.storage.object_store import ARTIFACT_DIGEST_DOMAIN

pytestmark = pytest.mark.platform


def test_offline_corpus_build_is_byte_stable_without_network() -> None:
    payloads = [build_payload(case.files) for case in CASES]
    repeated = [build_payload(case.files) for case in CASES]

    assert payloads == repeated
    assert [digest_bytes(ARTIFACT_DIGEST_DOMAIN, payload) for payload in payloads] == [
        digest_bytes(ARTIFACT_DIGEST_DOMAIN, payload) for payload in repeated
    ]
    assert [case.name for case in CASES] == [
        "clean_instruction",
        "clean_skill",
        "clean_mcp",
    ]


def test_offline_quantiles_use_nearest_rank_deterministically() -> None:
    values = [
        DURATION_BUCKETS_MS[0],
        DURATION_BUCKETS_MS[2],
        DURATION_BUCKETS_MS[4],
        DURATION_BUCKETS_MS[6],
    ]

    assert _quantile(values, 0.50) == DURATION_BUCKETS_MS[2]
    assert _quantile(values, 0.95) == DURATION_BUCKETS_MS[6]
