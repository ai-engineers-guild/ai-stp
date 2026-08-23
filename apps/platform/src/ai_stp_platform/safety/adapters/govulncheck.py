"""govulncheck Go SCA adapter."""

from __future__ import annotations

from pathlib import Path

from ai_stp_platform.safety.adapters._cli import classify_cli_exit, run_cli
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
            tool_name="govulncheck",
        )
    code, out, err, ms = run_cli(
        ["govulncheck", "./..."],
        cwd=tree,
        timeout=min(spec.timeout_seconds, 25),
    )
    state, detail = classify_cli_exit(code, out, err)
    if state != "finding" and state != "passed":
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result=state,
            mandatory=spec.mandatory,
            tool_name="govulncheck",
            duration_ms=ms,
            detail=detail,
        )
    findings: list[Finding] = []
    if state == "finding":
        findings.append(
            Finding(
                check_id=spec.check_id,
                family=spec.family,
                rule_id="govulncheck",
                severity="medium",
                title="govulncheck reported issues",
                message=redact_message((out or err)[:300]),
                tool_name="govulncheck",
            )
        )
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result="warning" if findings else "passed",
        mandatory=spec.mandatory,
        tool_name="govulncheck",
        duration_ms=ms,
        findings=findings,
    )
