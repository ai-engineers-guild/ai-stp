"""End-to-end platform safety evidence over the filesystem adversarial corpus."""

from __future__ import annotations

import pytest
from scripts.safety.run_adversarial_corpus import EXPECTED_KINDS, run_corpus

pytestmark = pytest.mark.platform


@pytest.mark.asyncio
async def test_safety_corpus_all_attacks_detected_without_clean_false_positives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_STP_SAFETY_EXTERNAL_CLI", "0")
    monkeypatch.setenv("AI_STP_SAFETY_SANDBOX", "off")

    report = await run_corpus()

    assert set(report["per_kind"]) == EXPECTED_KINDS
    assert all(10 <= values["malicious"] <= 20 for values in report["per_kind"].values())
    assert all(values["benign"] >= 2 for values in report["per_kind"].values())
    assert report["case_count"] == sum(report["cases_by_kind"].values())
    assert report["malicious_count"] == sum(
        values["malicious"] for values in report["per_kind"].values()
    )
    assert report["benign_count"] == sum(values["benign"] for values in report["per_kind"].values())
    assert report["missed"] == []
    assert report["false_positives"] == []
    assert report["ok"] is True
