"""Go SAST with complete module coverage and explicit analyser failures."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, cast

from ai_stp_platform.safety.adapters._cli import classify_cli_exit, manifest_roots, run_cli
from ai_stp_platform.safety.adapters.paths import relative_artifact_path
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import (
    ArtifactManifest,
    CheckOutcome,
    Finding,
    maximum_finding_severity,
)


def _findings(tree: Path, report: dict[str, Any], spec: CheckSpec) -> list[Finding]:
    issues = report.get("Issues")
    if issues is None:
        issues = []
    if not isinstance(issues, list):
        raise ValueError("Invalid Go SAST issues")
    findings: list[Finding] = []
    for raw in cast(list[object], issues):
        if not isinstance(raw, dict):
            raise ValueError("Invalid Go SAST issue")
        item = cast(dict[str, Any], raw)
        rule = item.get("rule_id")
        severity = item.get("severity")
        if not isinstance(rule, str) or not rule.strip() or not isinstance(severity, str):
            raise ValueError("Missing Go SAST issue identity")
        severity = severity.lower()
        if severity not in {"low", "medium", "high", "critical", "info"}:
            raise ValueError("Invalid Go SAST severity")
        findings.append(
            Finding(
                check_id=spec.check_id,
                family=spec.family,
                rule_id=rule.lower(),
                severity=severity,
                title=rule,
                path=relative_artifact_path(tree, item.get("file")),
                message=rule,
                tool_name="gosec",
            )
        )
    return findings


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    result = CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result="not_applicable",
        mandatory=spec.mandatory,
        tool_name="gosec",
    )
    if "go" not in manifest.languages:
        return result
    roots = manifest_roots(tree, "go.mod")
    if not roots:
        result.result = "not_run"
        result.detail = {"reason": "module_manifest_missing"}
        return result
    deadline = time.perf_counter() + spec.timeout_seconds
    incomplete = False
    for root in roots:
        code, out, err, ms = run_cli(
            ["gosec", "-fmt", "json", "./..."],
            cwd=root,
            timeout=max(0.0, deadline - time.perf_counter()),
        )
        result.duration_ms += ms
        if code not in {0, 1}:
            state, detail = classify_cli_exit(code, out, err)
            result.detail = detail
            result.result = state
            incomplete = True
            if code == 124:
                break
            continue
        try:
            payload: object = json.loads(out)
            if not isinstance(payload, dict):
                raise ValueError("Invalid Go SAST report")
            report = cast(dict[str, Any], payload)
            findings = _findings(tree, report, spec)
            raw_stats = report.get("Stats")
            if not isinstance(raw_stats, dict):
                raise ValueError("Invalid Go SAST coverage")
            stats = cast(dict[str, Any], raw_stats)
            files = stats.get("files")
            if type(files) is not int:
                raise ValueError("Invalid Go SAST coverage")
            errors = report.get("Golang errors")
            if errors is not None and not isinstance(errors, dict):
                raise ValueError("Invalid Go SAST errors")
            result.findings.extend(findings)
            if errors or files <= 0 or (code == 1 and not findings):
                incomplete = True
                result.result = "degraded"
                result.detail = {"reason": "analysis_incomplete", "exit_code": code}
        except (json.JSONDecodeError, ValueError):
            incomplete = True
            result.result = "degraded"
            result.detail = {"reason": "invalid_report", "exit_code": code}
    if not incomplete:
        result.result = "warning" if result.findings else "passed"
    result.severity_max = maximum_finding_severity(result.findings)
    return result
