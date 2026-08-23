"""pip-audit Python SCA adapter."""

from __future__ import annotations

from pathlib import Path

from ai_stp_platform.safety.adapters._cli import classify_cli_exit, manifest_roots, run_cli
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
    # Wherever the artefact put them; a component tree keeps them under
    # `files/`, so the old root-only test found nothing and answered
    # `not_applicable` for every tree that had a manifest.
    roots = manifest_roots(tree, "requirements.txt", "pyproject.toml", "Pipfile.lock")
    if not roots and "python" not in manifest.languages:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_applicable",
            mandatory=spec.mandatory,
            tool_name="pip-audit",
        )
    outcomes: list[tuple[str, dict[str, object], str, str, int]] = []
    for where in roots or (tree,):
        code, out, err, ms = run_cli(
            ["pip-audit", "-r", "requirements.txt"]
            if (where / "requirements.txt").is_file()
            else ["pip-audit"],
            cwd=where,
            timeout=min(spec.timeout_seconds, 25),
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
            tool_name="pip-audit",
            duration_ms=ms,
            detail=detail,
        )
    findings: list[Finding] = []
    if state == "finding":
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
