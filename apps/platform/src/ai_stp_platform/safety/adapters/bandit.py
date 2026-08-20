"""Bandit Python SAST adapter."""

from __future__ import annotations

from pathlib import Path

from ai_stp_platform.safety.adapters._cli import run_cli
from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    if "python" not in manifest.languages:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_applicable",
            mandatory=spec.mandatory,
            tool_name="bandit",
        )
    code, out, err, ms = run_cli(
        ["bandit", "-q", "-r", str(tree), "-f", "txt"],
        cwd=tree,
        timeout=spec.timeout_seconds,
    )
    if code == 127:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_run",
            mandatory=spec.mandatory,
            tool_name="bandit",
            duration_ms=ms,
            detail={"reason": "tool_missing"},
        )
    findings: list[Finding] = []
    if code != 0:
        findings.append(
            Finding(
                check_id=spec.check_id,
                family=spec.family,
                rule_id="bandit",
                severity="medium",
                title="Bandit reported issues",
                message=redact_message((out or err)[:300]),
                tool_name="bandit",
            )
        )
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result="warning" if findings else "passed",
        mandatory=spec.mandatory,
        tool_name="bandit",
        duration_ms=ms,
        findings=findings,
    )
