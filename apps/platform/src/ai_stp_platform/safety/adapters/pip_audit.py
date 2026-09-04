"""pip-audit Python SCA adapter."""

from __future__ import annotations

from pathlib import Path

from ai_stp_platform.safety.adapters._cli import classify_cli_exit, manifest_roots, run_cli
from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding

# Bare `pip-audit` against pyproject.toml waits on an index. Only invoke when a
# lock or pinned requirements file exists, and never ask pip to resolve.
_REQUIREMENTS_NAME = "requirements.txt"
_LOCK_NAMES = ("pylock.toml",)


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    del manifest
    requirement_roots = manifest_roots(tree, _REQUIREMENTS_NAME)
    lock_roots = manifest_roots(tree, *_LOCK_NAMES)
    jobs: list[tuple[Path, list[str]]] = []
    for where in requirement_roots:
        jobs.append((where, ["pip-audit", "-r", _REQUIREMENTS_NAME, "--disable-pip"]))
    for where in lock_roots:
        jobs.append((where, ["pip-audit", "--locked", "--disable-pip"]))
    if not jobs:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_applicable",
            mandatory=spec.mandatory,
            tool_name="pip-audit",
            detail={"reason": "no_lockfile"},
        )
    outcomes: list[tuple[str, dict[str, object], str, str, int]] = []
    for where, argv in jobs:
        code, out, err, ms = run_cli(argv, cwd=where, timeout=spec.timeout_seconds)
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
