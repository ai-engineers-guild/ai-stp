"""Hidden content in markdown/HTML (comments, zero-width, dangerous schemes)."""

from __future__ import annotations

import re
from pathlib import Path

from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding

HTML_COMMENT = re.compile(r"<!--([\s\S]*?)-->")
ZW_CHARS = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u202a-\u202e]")
DANGEROUS_SCHEME = re.compile(r"(?i)\]\(\s*(javascript:|data:text/html)")
MD_IMG_EXFIL = re.compile(
    r"(?i)!\[[^\]]*\]\(\s*https?://[^)]+\?(?:[^)]*(?:token|secret|key|data)=)"
)


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    findings: list[Finding] = []
    for rel in manifest.text_files:
        if not rel.lower().endswith((".md", ".html", ".htm", ".txt", ".yml", ".yaml")):
            continue
        path = tree / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in HTML_COMMENT.finditer(text):
            body = m.group(1).strip()
            if len(body) < 8:
                continue
            sev = "high" if re.search(r"(?i)ignore|exfil|secret|instruction", body) else "medium"
            findings.append(
                Finding(
                    check_id=spec.check_id,
                    family=spec.family,
                    rule_id="html_comment_hidden",
                    severity=sev,
                    title="HTML comment may hide instructions",
                    path=rel,
                    message=redact_message(body[:160]),
                    tool_name="content_hidden",
                )
            )
        if ZW_CHARS.search(text):
            findings.append(
                Finding(
                    check_id=spec.check_id,
                    family=spec.family,
                    rule_id="zero_width_chars",
                    severity="medium",
                    title="Zero-width / bidi override characters present",
                    path=rel,
                    message="unicode stealth characters detected",
                    tool_name="content_hidden",
                )
            )
        if DANGEROUS_SCHEME.search(text):
            findings.append(
                Finding(
                    check_id=spec.check_id,
                    family=spec.family,
                    rule_id="dangerous_md_scheme",
                    severity="critical",
                    title="Dangerous URL scheme in markdown link",
                    path=rel,
                    message="javascript: or data:text/html link",
                    tool_name="content_hidden",
                )
            )
        if MD_IMG_EXFIL.search(text):
            findings.append(
                Finding(
                    check_id=spec.check_id,
                    family=spec.family,
                    rule_id="md_image_exfil",
                    severity="high",
                    title="Markdown image URL looks like exfil channel",
                    path=rel,
                    message="image URL query may exfiltrate secrets",
                    tool_name="content_hidden",
                )
            )
    has_crit = any(f.severity in {"critical", "high"} for f in findings)
    if findings and has_crit:
        result = "warning" if not spec.mandatory else "failed"
    elif findings:
        result = "warning"
    else:
        result = "passed"
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result=result,
        mandatory=spec.mandatory,
        tool_name="content_hidden",
        severity_max=max(
            (f.severity for f in findings),
            default="info",
            key=lambda s: {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}.get(s, 0),
        ),
        findings=findings,
    )
