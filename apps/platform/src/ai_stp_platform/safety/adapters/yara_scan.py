"""YARA custom IOC pack for binaries/archives."""

from __future__ import annotations

from pathlib import Path

from ai_stp_platform.safety.adapters._cli import run_cli
from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.policy_pack import policy_pack_root
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding

# Built-in rule content when yara CLI present; also in-proc marker scan.
_BUILTIN_YARA = """
rule ai_stp_malware_test_marker {
  strings:
    $a = "AI_STP_MALWARE_TEST_MARKER_V1" ascii
  condition:
    $a
}
"""


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    findings: list[Finding] = []
    # Always scan for platform malware marker in-proc
    for path in tree.rglob("*"):
        if not path.is_file():
            continue
        try:
            sample = path.read_bytes()[:4096]
        except OSError:
            continue
        if b"AI_STP_MALWARE_TEST_MARKER_V1" in sample:
            findings.append(
                Finding(
                    check_id=spec.check_id,
                    family=spec.family,
                    rule_id="ai_stp_malware_test_marker",
                    severity="critical",
                    title="YARA/platform malware test marker",
                    path=path.relative_to(tree).as_posix(),
                    message="AI_STP malware test marker",
                    tool_name="yara_inproc",
                )
            )

    rules_file = policy_pack_root() / "yara" / "ai_stp_basic.yar"
    if not rules_file.is_file():
        rules_file.parent.mkdir(parents=True, exist_ok=True)
        rules_file.write_text(_BUILTIN_YARA, encoding="utf-8")

    code, out, err, ms = run_cli(
        ["yara", "-r", str(rules_file), str(tree)],
        cwd=tree,
        timeout=min(spec.timeout_seconds, 25),
    )
    tool = "yara"
    if code == 127:
        tool = "yara_inproc"
        if not findings and "binary" not in manifest.flags:
            return CheckOutcome(
                check_id=spec.check_id,
                family=spec.family,
                result="not_applicable",
                mandatory=spec.mandatory,
                tool_name=tool,
            )
        if not findings:
            return CheckOutcome(
                check_id=spec.check_id,
                family=spec.family,
                result="not_run",
                mandatory=spec.mandatory,
                tool_name=tool,
                detail={"reason": "tool_missing"},
            )
    elif code not in (0,) and (out or err) and not findings:
        findings.append(
            Finding(
                check_id=spec.check_id,
                family=spec.family,
                rule_id="yara_hit",
                severity="high",
                title="YARA reported matches",
                message=redact_message((out or err)[:300]),
                tool_name="yara",
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
