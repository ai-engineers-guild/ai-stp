"""Gitleaks secrets adapter — not_run when binary missing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from ai_stp_platform.safety.adapters._cli import classify_cli_exit, run_cli
from ai_stp_platform.safety.adapters.paths import is_test_path, relative_artifact_path
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
            "--no-banner",
            "--redact",
            "--report-format",
            "json",
            # Current gitleaks writes the report only when --report-path is set.
            "--report-path",
            "-",
            "--exit-code",
            "1",
        ],
        cwd=tree,
        timeout=spec.timeout_seconds,
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
    # Exit 1 means leaks found for gitleaks with --exit-code 1
    if code == 1:
        findings = _findings_from_report(spec, tree, out)
        if not findings:
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
        blocking = [finding for finding in findings if not is_test_path(finding.path)]
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="failed" if blocking else "warning",
            mandatory=spec.mandatory,
            tool_name="gitleaks",
            duration_ms=ms,
            severity_max="critical" if blocking else "medium",
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


def _findings_from_report(spec: CheckSpec, tree: Path, stdout: str) -> list[Finding]:
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    findings: list[Finding] = []
    for item in cast(list[object], parsed):
        if not isinstance(item, dict):
            continue
        row = cast(dict[str, object], item)
        rule = row.get("RuleID")
        title = row.get("Description")
        relative = relative_artifact_path(tree, row.get("File"))
        rule_id = rule[:64] if isinstance(rule, str) and rule else "gitleaks_finding"
        heading = (
            str(title)[:240] if isinstance(title, str) and title else "Gitleaks reported secrets"
        )
        findings.append(
            Finding(
                check_id=spec.check_id,
                family=spec.family,
                rule_id=rule_id,
                severity="critical",
                title=heading,
                path=relative,
                message=redact_message(rule_id),
                tool_name="gitleaks",
            )
        )
    return findings
