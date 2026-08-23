"""Bandit Python SAST adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ai_stp_platform.safety.adapters._cli import classify_cli_exit, run_cli
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
        ["bandit", "-q", "-r", str(tree), "-f", "json"],
        cwd=tree,
        timeout=spec.timeout_seconds,
    )
    state, detail = classify_cli_exit(code, out, err)
    if state != "finding" and state != "passed":
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result=state,
            mandatory=spec.mandatory,
            tool_name="bandit",
            duration_ms=ms,
            detail=detail,
        )
    findings: list[Finding] = []
    if state == "finding":
        try:
            report = cast(dict[str, Any], json.loads(out))
            results = cast(list[Any], report.get("results", []))
        except (json.JSONDecodeError, TypeError, ValueError):
            return CheckOutcome(
                check_id=spec.check_id,
                family=spec.family,
                result="degraded",
                mandatory=spec.mandatory,
                tool_name="bandit",
                duration_ms=ms,
                detail={"reason": "invalid_report"},
            )
        for raw in results:
            if not isinstance(raw, dict):
                continue
            item = cast(dict[str, Any], raw)
            rule_id = str(item.get("test_id") or "bandit").lower()
            severity = str(item.get("issue_severity") or "medium").lower()
            findings.append(
                Finding(
                    check_id=spec.check_id,
                    family=spec.family,
                    rule_id=rule_id,
                    severity=severity,
                    title=rule_id,
                    path=_relative_path(tree, item.get("filename")),
                    message=redact_message(rule_id),
                    tool_name="bandit",
                )
            )
        if not findings:
            return CheckOutcome(
                check_id=spec.check_id,
                family=spec.family,
                result="degraded",
                mandatory=spec.mandatory,
                tool_name="bandit",
                duration_ms=ms,
                detail={"reason": "empty_finding_report"},
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


def _relative_path(tree: Path, value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return Path(value).resolve().relative_to(tree.resolve()).as_posix()
    except (OSError, ValueError):
        return None
