"""Closed JobType registry (SPEC-018 REQ-1802)."""

from __future__ import annotations

import pytest

from ai_stp_platform.queue.states import JobType
from ai_stp_worker.handlers import REGISTRY, resolve

pytestmark = pytest.mark.platform


def test_registry_accepts_declared_types() -> None:
    expected = set(JobType)
    assert set(REGISTRY) == expected
    for job_type in expected:
        assert resolve(str(job_type)) is not None


def test_registry_rejects_unknown_and_sign_type() -> None:
    assert resolve("sign") is None
    assert resolve("not-a-job") is None
    with pytest.raises(ValueError):
        JobType("sign")
