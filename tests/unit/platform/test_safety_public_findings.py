"""Public safety findings expose identifiers without exposing scanned content."""

from __future__ import annotations

import pytest

from ai_stp_platform.safety.percent import build_checks_summary
from ai_stp_platform.safety.types import CheckOutcome, Finding

pytestmark = pytest.mark.platform


def test_public_finding_summary_keeps_safe_identifiers_and_drops_unsafe_paths() -> None:
    outcome = CheckOutcome(
        check_id="skill_static_gate",
        family="agentic",
        result="warning",
        findings=[
            Finding(
                check_id="skill_static_gate",
                family="agentic",
                rule_id="remote_instruction_loading",
                severity="high",
                title="untrusted title with payload",
                path="SKILL.md",
                message="secret payload",
            ),
            Finding(
                check_id="skill_static_gate",
                family="agentic",
                rule_id="CAPABILITY_LAUNDERING",
                severity="medium",
                title="ignored",
                path="../outside.txt",
                message="ignored",
            ),
        ],
    )

    binding = outcome.as_binding()
    summary = binding["finding_summary"]

    assert summary == {
        "schema_version": 1,
        "count": 2,
        "severity_max": "high",
        "rule_ids": ["capability_laundering", "remote_instruction_loading"],
        "paths": ["SKILL.md"],
        "truncated": False,
    }
    assert "secret payload" not in repr(binding)
    assert "outside.txt" not in repr(binding)


def test_checks_summary_preserves_reason_and_structured_findings() -> None:
    outcome = CheckOutcome(
        check_id="skill_static_gate",
        family="agentic",
        result="warning",
        findings=[
            Finding(
                check_id="skill_static_gate",
                family="agentic",
                rule_id="capability_laundering",
                severity="medium",
                title="ignored",
                path="SKILL.md",
            )
        ],
    )

    check = build_checks_summary([outcome.as_binding()])["checks"][0]

    assert check["reason"] == "1 finding(s): capability_laundering"
    assert check["finding_summary"]["paths"] == ["SKILL.md"]
