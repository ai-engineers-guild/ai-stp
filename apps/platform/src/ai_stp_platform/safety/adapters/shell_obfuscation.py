"""Shell obfuscation / base64-to-shell side channels."""

from __future__ import annotations

import base64
import re
from pathlib import Path

from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding

PATTERNS = [
    (re.compile(r"(?i)base64\s+-d\s*\|\s*(bash|sh)"), "b64_pipe_shell", "critical"),
    (re.compile(r"(?i)eval\s+\$\("), "eval_subshell", "high"),
    (re.compile(r"(?i)\$'\\x[0-9a-f]{2}"), "hex_escape_obfuscation", "medium"),
    (re.compile(r"(?i)\$\{[a-z_]+:0:1\}"), "char_concat_obfuscation", "medium"),
]


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    findings: list[Finding] = []
    for rel in manifest.shell_files or []:
        path = tree / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern, rule, sev in PATTERNS:
            if pattern.search(text):
                findings.append(
                    Finding(
                        check_id=spec.check_id,
                        family=spec.family,
                        rule_id=rule,
                        severity=sev,
                        title=f"Shell obfuscation: {rule}",
                        path=rel,
                        message=redact_message(rule),
                        tool_name="shell_obfuscation",
                    )
                )
        for m in re.finditer(r"[A-Za-z0-9+/]{32,}={0,2}", text):
            blob = m.group(0)
            try:
                pad = "=" * (-len(blob) % 4)
                decoded = base64.b64decode(blob + pad).decode("utf-8", errors="strict")
            except Exception:
                continue
            if re.search(r"(?i)(curl|wget|bash|sh\s+-c|/dev/tcp)", decoded):
                findings.append(
                    Finding(
                        check_id=spec.check_id,
                        family=spec.family,
                        rule_id="b64_decoded_shell",
                        severity="critical",
                        title="Base64 payload decodes to shell/network command",
                        path=rel,
                        message=redact_message(decoded[:120]),
                        tool_name="shell_obfuscation",
                    )
                )
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result="failed"
        if any(f.severity == "critical" for f in findings)
        else ("warning" if findings else "passed"),
        mandatory=spec.mandatory,
        tool_name="shell_obfuscation",
        severity_max=max((f.severity for f in findings), default="info", key=lambda s: s),
        findings=findings,
    )
