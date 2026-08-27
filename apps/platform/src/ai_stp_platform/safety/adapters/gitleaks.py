"""Gitleaks secrets adapter — not_run when binary missing."""

from __future__ import annotations

from pathlib import Path

from ai_stp_platform.safety.adapters._cli import classify_cli_exit, run_cli
from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    del manifest
    # Prefer filesystem scan; older builds use `detect --source`.
    code, out, err, ms = run_cli(
        [
            "gitleaks",
            "detect",
            "--source",
            str(tree),
            "--no-git",
            "--redact",
            "-f",
            "json",
            "--exit-code",
            "1",
        ],
        cwd=tree,
        timeout=min(spec.timeout_seconds, 20),
    )
    if code == 127:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_run",
            mandatory=spec.mandatory,
            tool_name="gitleaks",
            duration_ms=ms,
            detail={"reason": "tool_missing"},
        )
    if code == 124:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="degraded",
            mandatory=spec.mandatory,
            tool_name="gitleaks",
            duration_ms=ms,
            # The shared classifier, so this says which limit was hit and
            # whether the tool ran at all rather than only "timeout".
            detail=classify_cli_exit(code, out, err)[1],
        )
    findings: list[Finding] = []
    # Exit 1 means leaks found for gitleaks with --exit-code 1
    if code == 1:
        findings.append(
            Finding(
                check_id=spec.check_id,
                family=spec.family,
                rule_id="gitleaks_finding",
                severity="critical",
                title="Gitleaks reported secrets",
                message=redact_message((out or err or "secrets found")[:300]),
                tool_name="gitleaks",
            )
        )
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="failed",
            mandatory=spec.mandatory,
            tool_name="gitleaks",
            duration_ms=ms,
            severity_max="critical",
            findings=findings,
        )
    if code != 0:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="degraded",
            mandatory=spec.mandatory,
            tool_name="gitleaks",
            duration_ms=ms,
            detail={"exit": code, "stderr": redact_message(err)},
        )
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result="passed",
        mandatory=spec.mandatory,
        tool_name="gitleaks",
        duration_ms=ms,
    )
