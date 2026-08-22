"""cargo-audit Rust SCA adapter."""

from __future__ import annotations

from pathlib import Path

from ai_stp_platform.safety.adapters._cli import manifest_roots, run_cli
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
    code, out, err, ms = run_cli(
        ["cargo", "audit", "--json"],
        cwd=roots[0],
        timeout=min(spec.timeout_seconds, 25),
    )
    if code == 127:
        # try cargo-audit binary
        code, out, err, ms = run_cli(
            ["cargo-audit", "audit"],
            cwd=roots[0],
            timeout=min(spec.timeout_seconds, 25),
        )
    if code == 127:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_run",
            mandatory=spec.mandatory,
            tool_name="cargo-audit",
            duration_ms=ms,
            detail={"reason": "tool_missing"},
        )
    findings: list[Finding] = []
    if code != 0 and (out or err):
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
