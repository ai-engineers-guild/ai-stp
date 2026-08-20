"""Lightweight PDF document surface: JS/OpenAction strings + text PI re-scan."""

from __future__ import annotations

import re
from pathlib import Path

from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding

# Dangerous PDF features often visible as ASCII in streams without full parser.
_PDF_RISK = [
    (re.compile(rb"/JavaScript\b"), "pdf_javascript", "high"),
    (re.compile(rb"/JS\b"), "pdf_js", "high"),
    (re.compile(rb"/OpenAction\b"), "pdf_openaction", "high"),
    (re.compile(rb"/Launch\b"), "pdf_launch", "critical"),
    (re.compile(rb"/EmbeddedFile\b"), "pdf_embedded_file", "medium"),
    (re.compile(rb"/AA\b"), "pdf_additional_actions", "medium"),
]
_PI_TEXT = re.compile(rb"(?i)ignore\s+(all\s+)?(previous|prior)\s+instructions|exfiltrat")


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    if "pdf" not in manifest.flags:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_applicable",
            mandatory=spec.mandatory,
            tool_name="pdf_document",
        )
    findings: list[Finding] = []
    for path in tree.rglob("*.pdf"):
        if not path.is_file():
            continue
        rel = path.relative_to(tree).as_posix()
        try:
            data = path.read_bytes()[:2_000_000]
        except OSError:
            continue
        if not data.startswith(b"%PDF"):
            findings.append(
                Finding(
                    check_id=spec.check_id,
                    family=spec.family,
                    rule_id="pdf_bad_header",
                    severity="medium",
                    title="PDF missing %PDF header",
                    path=rel,
                    message="not a standard PDF header",
                    tool_name="pdf_document",
                )
            )
            continue
        for pattern, rule, sev in _PDF_RISK:
            if pattern.search(data):
                findings.append(
                    Finding(
                        check_id=spec.check_id,
                        family=spec.family,
                        rule_id=rule,
                        severity=sev,
                        title=f"PDF risk feature: {rule}",
                        path=rel,
                        message=redact_message(rule),
                        tool_name="pdf_document",
                    )
                )
        if _PI_TEXT.search(data):
            findings.append(
                Finding(
                    check_id=spec.check_id,
                    family=spec.family,
                    rule_id="pdf_text_pi",
                    severity="high",
                    title="PDF bytes contain prompt-injection-like text",
                    path=rel,
                    message="PI-like strings in PDF",
                    tool_name="pdf_document",
                )
            )
    has_high = any(f.severity in {"high", "critical"} for f in findings)
    result = "warning" if (findings and has_high) or findings else "passed"
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result=result,
        mandatory=spec.mandatory,
        tool_name="pdf_document",
        severity_max=max((f.severity for f in findings), default="info", key=_rank),
        findings=findings,
    )


def _rank(s: str) -> int:
    return {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}.get(s, 0)
