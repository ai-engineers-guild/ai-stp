"""ShellCheck adapter."""

from __future__ import annotations

from pathlib import Path

from ai_stp_platform.safety.adapters._cli import classify_cli_exit, run_cli
from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    if not manifest.shell_files:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_applicable",
            mandatory=spec.mandatory,
            tool_name="shellcheck",
        )
    targets = [str(tree / rel) for rel in manifest.shell_files if (tree / rel).is_file()]
    if not targets:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_applicable",
            mandatory=spec.mandatory,
            tool_name="shellcheck",
        )
    code, out, err, ms = run_cli(
        ["shellcheck", "-f", "gcc", *targets[:50]],
        cwd=tree,
        timeout=spec.timeout_seconds,
    )
    state, detail = classify_cli_exit(code, out, err)
    if state not in {"finding", "passed"}:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result=state,
            mandatory=spec.mandatory,
            tool_name="shellcheck",
            duration_ms=ms,
            detail=detail,
        )
    findings: list[Finding] = []
    if state == "finding":
        findings.append(
            Finding(
                check_id=spec.check_id,
                family=spec.family,
                rule_id="shellcheck",
                severity="medium",
                title="ShellCheck reported issues",
                message=redact_message((out or err)[:300]),
                tool_name="shellcheck",
            )
        )
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result="warning" if findings else "passed",
        mandatory=spec.mandatory,
        tool_name="shellcheck",
        duration_ms=ms,
        findings=findings,
    )
