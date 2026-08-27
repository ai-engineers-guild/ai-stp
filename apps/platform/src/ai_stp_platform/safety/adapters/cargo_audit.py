"""cargo-audit Rust SCA adapter."""

from __future__ import annotations

from pathlib import Path

from ai_stp_platform.safety.adapters._cli import classify_cli_exit, manifest_roots, run_cli
from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    if "rust" not in manifest.languages:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_applicable",
            mandatory=spec.mandatory,
            tool_name="cargo-audit",
        )
    # The manifest lives wherever the artefact put it; a component tree
    # keeps it under `files/`.
    roots = manifest_roots(tree, "Cargo.lock", "Cargo.toml")
    if not roots:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_applicable",
            mandatory=spec.mandatory,
            tool_name="cargo-audit",
        )
    all_results: list[tuple[str, dict[str, object], str, str, int]] = []
    for root in roots:
        code, out, err, ms = run_cli(
            ["cargo", "audit", "--json"], cwd=root, timeout=spec.timeout_seconds
        )
        if code == 127:
            code, out, err, ms = run_cli(
                ["cargo-audit", "audit"], cwd=root, timeout=spec.timeout_seconds
            )
        state, detail = classify_cli_exit(code, out, err)
        all_results.append((state, detail, out, err, ms))
        if state in {"not_run", "degraded"}:
            break
    state = "finding" if any(item[0] == "finding" for item in all_results) else all_results[-1][0]
    detail = all_results[-1][1]
    out = "\n".join(item[2] for item in all_results)
    err = "\n".join(item[3] for item in all_results)
    ms = sum(item[4] for item in all_results)
    if state not in {"finding", "passed"}:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result=state,
            mandatory=spec.mandatory,
            tool_name="cargo-audit",
            duration_ms=ms,
            detail=detail,
        )
    findings: list[Finding] = []
    if state == "finding":
        findings.append(
            Finding(
                check_id=spec.check_id,
                family=spec.family,
                rule_id="cargo_audit",
                severity="medium",
                title="cargo-audit reported issues",
                message=redact_message((out or err)[:300]),
                tool_name="cargo-audit",
            )
        )
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result="warning" if findings else "passed",
        mandatory=spec.mandatory,
        tool_name="cargo-audit",
        duration_ms=ms,
        findings=findings,
    )
