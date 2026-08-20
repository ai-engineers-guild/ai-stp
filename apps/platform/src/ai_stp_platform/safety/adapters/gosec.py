"""gosec Go SAST adapter."""

from __future__ import annotations

from pathlib import Path

from ai_stp_platform.safety.adapters._cli import run_cli
from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    if "go" not in manifest.languages:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_applicable",
            mandatory=spec.mandatory,
            tool_name="gosec",
        )
    code, out, err, ms = run_cli(
        ["gosec", "-fmt", "json", "./..."],
        cwd=tree,
        timeout=min(spec.timeout_seconds, 25),
    )
    if code == 127:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_run",
            mandatory=spec.mandatory,
            tool_name="gosec",
            duration_ms=ms,
            detail={"reason": "tool_missing"},
        )
    findings: list[Finding] = []
    if code != 0 and (out or err):
        findings.append(
            Finding(
                check_id=spec.check_id,
                family=spec.family,
                rule_id="gosec",
                severity="medium",
                title="gosec reported issues",
                message=redact_message((out or err)[:300]),
                tool_name="gosec",
            )
        )
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result="warning" if findings else "passed",
        mandatory=spec.mandatory,
        tool_name="gosec",
        duration_ms=ms,
        findings=findings,
    )
