"""ClamAV malware adapter (strict profile)."""

from __future__ import annotations

from pathlib import Path

from ai_stp_platform.safety.adapters._cli import classify_cli_exit, run_cli
from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding

# Platform malware test marker (not full EICAR — full EICAR triggers host AV locks).
MALWARE_TEST_MARK = "AI_STP_MALWARE_TEST_MARKER_V1"


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    # In-proc EICAR / test malware marker always
    findings: list[Finding] = []
    for path in tree.rglob("*"):
        if not path.is_file():
            continue
        try:
            sample = path.read_bytes()[:512]
        except OSError:
            continue
        if MALWARE_TEST_MARK.encode("ascii") in sample:
            findings.append(
                Finding(
                    check_id=spec.check_id,
                    family=spec.family,
                    rule_id="malware_test_marker",
                    severity="critical",
                    title="Malware test marker present",
                    path=path.relative_to(tree).as_posix(),
                    message="AI_STP malware test marker detected",
                    tool_name="malware_local",
                )
            )

    code, out, err, ms = run_cli(
        ["clamscan", "-r", "--no-summary", str(tree)],
        cwd=tree,
        timeout=spec.timeout_seconds,
    )
    tool = "clamscan"
    state, detail = classify_cli_exit(code, out, err)
    if state == "not_run":
        if findings:
            return CheckOutcome(
                check_id=spec.check_id,
                family=spec.family,
                result="failed",
                mandatory=spec.mandatory,
                tool_name="malware_local",
                severity_max="critical",
                findings=findings,
                detail={"clamav": "missing", "in_proc": True},
            )
        # No binary and no binary flag risk → not_run only if profile expected it
        if "binary" not in manifest.flags:
            return CheckOutcome(
                check_id=spec.check_id,
                family=spec.family,
                result="not_applicable",
                mandatory=spec.mandatory,
                tool_name="clamscan",
            )
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_run",
            mandatory=spec.mandatory,
            tool_name="clamscan",
            detail=detail,
        )
    if state == "degraded":
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result=state,
            mandatory=spec.mandatory,
            tool_name=tool,
            duration_ms=ms,
            detail=detail,
        )
    if state == "finding":
        findings.append(
            Finding(
                check_id=spec.check_id,
                family=spec.family,
                rule_id="clamav_infected",
                severity="critical",
                title="ClamAV reported infected files",
                message=redact_message((out or err)[:300]),
                tool_name=tool,
            )
        )
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result="failed" if findings else "passed",
        mandatory=spec.mandatory,
        tool_name=tool,
        duration_ms=ms,
        severity_max="critical" if findings else "info",
        findings=findings,
    )
