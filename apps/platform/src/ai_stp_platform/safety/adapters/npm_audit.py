"""npm audit SCA adapter for JS package trees."""

from __future__ import annotations

from pathlib import Path

from ai_stp_platform.safety.adapters._cli import manifest_roots, run_cli
from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    # Wherever the manifest actually is. In a component tree it is under
    # `files/`, never at the root the old test looked at.
    roots = manifest_roots(tree, "package.json")
    if "js" not in manifest.languages and not roots:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_applicable",
            mandatory=spec.mandatory,
            tool_name="npm",
        )
    if not roots:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_applicable",
            mandatory=spec.mandatory,
            tool_name="npm",
        )
    code, out, err, ms = run_cli(
        ["npm", "audit", "--audit-level=moderate", "--json"],
        cwd=roots[0],
        timeout=min(spec.timeout_seconds, 30),
    )
    if code == 127:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_run",
            mandatory=spec.mandatory,
            tool_name="npm",
            duration_ms=ms,
            detail={"reason": "tool_missing"},
        )
    findings: list[Finding] = []
    # npm audit exits non-zero when vulns found
    if code != 0 and (out or err):
        findings.append(
            Finding(
                check_id=spec.check_id,
                family=spec.family,
                rule_id="npm_audit",
                severity="medium",
                title="npm audit reported issues",
                message=redact_message((out or err)[:300]),
                tool_name="npm",
            )
        )
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result="warning" if findings else "passed",
        mandatory=spec.mandatory,
        tool_name="npm",
        duration_ms=ms,
        findings=findings,
    )
