"""ShellCheck adapter."""

from __future__ import annotations

import re
from pathlib import Path

from ai_stp_platform.safety.adapters._cli import classify_cli_exit, run_cli
from ai_stp_platform.safety.adapters.paths import relative_artifact_path
from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding

# gcc format: path:line:col: severity: message [SCxxxx]
# Greedy path so Windows `C:\...` drive colons are not the location split.
_GCC_LINE = re.compile(
    r"^(?P<path>.+):(?P<line>\d+):(?P<col>\d+):\s*(?P<severity>\w+):\s*(?P<message>.*?)"
    r"(?:\s+\[(?P<code>SC\d+)\])?\s*$"
)


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
        findings.extend(_findings_from_gcc(spec, tree, out or err))
        if not findings:
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


def _findings_from_gcc(spec: CheckSpec, tree: Path, stdout: str) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[tuple[str | None, str]] = set()
    for raw in stdout.splitlines():
        match = _GCC_LINE.match(raw.strip())
        if match is None:
            continue
        relative = relative_artifact_path(tree, match.group("path"))
        code = (match.group("code") or "shellcheck").lower()
        key = (relative, code)
        if key in seen:
            continue
        seen.add(key)
        severity = match.group("severity").lower()
        if severity == "error":
            severity = "high"
        elif severity == "warning":
            severity = "medium"
        elif severity == "note":
            severity = "low"
        elif severity not in {"info", "low", "medium", "high", "critical"}:
            severity = "medium"
        findings.append(
            Finding(
                check_id=spec.check_id,
                family=spec.family,
                rule_id=code,
                severity=severity,
                title=code,
                path=relative,
                message=redact_message(code),
                tool_name="shellcheck",
            )
        )
    return findings
