"""npm audit SCA adapter for JS package trees."""

from __future__ import annotations

from pathlib import Path

from ai_stp_platform.safety.adapters._cli import classify_cli_exit, manifest_roots, run_cli
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
    outcomes: list[tuple[str, dict[str, object], str, str, int]] = []
    for root in roots:
        code, out, err, ms = run_cli(
            ["npm", "audit", "--audit-level=moderate", "--json"],
            cwd=root,
            timeout=min(spec.timeout_seconds, 30),
        )
        state, detail = classify_cli_exit(code, out, err)
        outcomes.append((state, detail, out, err, ms))
        if state in {"not_run", "degraded"}:
            break
    state = "finding" if any(item[0] == "finding" for item in outcomes) else outcomes[-1][0]
    detail = outcomes[-1][1]
    out = "\n".join(item[2] for item in outcomes)
    err = "\n".join(item[3] for item in outcomes)
    ms = sum(item[4] for item in outcomes)
    if state not in {"finding", "passed"}:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result=state,
            mandatory=spec.mandatory,
            tool_name="npm",
            duration_ms=ms,
            detail=detail,
        )
    findings: list[Finding] = []
    # npm audit exits non-zero when vulns found
    if state == "finding":
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
