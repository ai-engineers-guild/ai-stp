"""pip-audit Python SCA adapter."""

from __future__ import annotations

from pathlib import Path

from ai_stp_platform.safety.adapters._cli import run_cli
from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    if "python" not in manifest.languages and "manifests" not in manifest.flags:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_applicable",
            mandatory=spec.mandatory,
            tool_name="pip-audit",
        )
    has_req = any(
        (tree / name).is_file() for name in ("requirements.txt", "pyproject.toml", "Pipfile.lock")
    )
    if not has_req and "python" not in manifest.languages:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_applicable",
            mandatory=spec.mandatory,
            tool_name="pip-audit",
        )
    code, out, err, ms = run_cli(
        ["pip-audit", "-r", "requirements.txt"]
        if (tree / "requirements.txt").is_file()
        else ["pip-audit"],
        cwd=tree,
        timeout=min(spec.timeout_seconds, 25),
    )
    if code == 127:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_run",
            mandatory=spec.mandatory,
            tool_name="pip-audit",
            duration_ms=ms,
            detail={"reason": "tool_missing"},
        )
    findings: list[Finding] = []
    if code != 0 and (out or err):
        findings.append(
            Finding(
                check_id=spec.check_id,
                family=spec.family,
                rule_id="pip_audit",
                severity="medium",
                title="pip-audit reported issues",
                message=redact_message((out or err)[:300]),
                tool_name="pip-audit",
            )
        )
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result="warning" if findings else "passed",
        mandatory=spec.mandatory,
        tool_name="pip-audit",
        duration_ms=ms,
        findings=findings,
    )
