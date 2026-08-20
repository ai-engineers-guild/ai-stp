"""ESLint security plugin adapter for JS/TS trees."""

from __future__ import annotations

from pathlib import Path

from ai_stp_platform.safety.adapters._cli import run_cli
from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    if "js" not in manifest.languages:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_applicable",
            mandatory=spec.mandatory,
            tool_name="eslint",
        )
    # Prefer npx eslint if local config exists; otherwise owned opengrep covers JS.
    code, out, err, ms = run_cli(
        ["eslint", ".", "--max-warnings", "0"],
        cwd=tree,
        timeout=min(spec.timeout_seconds, 25),
    )
    if code == 127:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_run",
            mandatory=spec.mandatory,
            tool_name="eslint",
            duration_ms=ms,
            detail={"reason": "tool_missing", "fallback": "sast_opengrep"},
        )
    findings: list[Finding] = []
    if code != 0 and (out or err):
        findings.append(
            Finding(
                check_id=spec.check_id,
                family=spec.family,
                rule_id="eslint",
                severity="medium",
                title="ESLint reported issues",
                message=redact_message((out or err)[:300]),
                tool_name="eslint",
            )
        )
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result="warning" if findings else "passed",
        mandatory=spec.mandatory,
        tool_name="eslint",
        duration_ms=ms,
        findings=findings,
    )
