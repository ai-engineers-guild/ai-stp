"""Prompt-injection pattern pack for text artifacts."""

from __future__ import annotations

import base64
import re
from pathlib import Path

from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding

PI_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"(?i)ignore\s+(all\s+)?(previous|prior|above)\s+instructions"),
        "pi_ignore_previous",
        "high",
    ),
    (
        re.compile(r"(?i)disregard\s+(your|the)\s+(system|developer)\s+prompt"),
        "pi_disregard_system",
        "high",
    ),
    (
        re.compile(r"(?i)you\s+are\s+now\s+(in\s+)?(dan|jailbreak|developer\s+mode)"),
        "pi_jailbreak_role",
        "high",
    ),
    (
        re.compile(r"(?i)exfiltrat(e|ion)|send\s+(secrets|credentials|api\s*keys)\s+to"),
        "pi_exfil",
        "critical",
    ),
    (re.compile(r"(?i)do\s+not\s+tell\s+the\s+user"), "pi_hide_from_user", "medium"),
    (re.compile(r"(?i)override\s+safety"), "pi_override_safety", "high"),
]

B64_BLOB = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{40,}={0,2}(?![A-Za-z0-9+/=])")


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    findings: list[Finding] = []
    for rel in manifest.text_files:
        path = tree / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        findings.extend(_scan_text(text, rel, spec))
        # Decode short base64 side-channels and re-scan
        for match in B64_BLOB.finditer(text):
            blob = match.group(0)
            if len(blob) > 4000:
                continue
            decoded = _try_b64(blob)
            if decoded and _looks_text(decoded):
                findings.extend(_scan_text(decoded, f"{rel}#base64", spec, encoded=True))
    # High severity failures block when mandatory; pack is non-mandatory warning
    # but critical findings still surface as warning (or failed if policy tightens).
    has_high = any(f.severity in {"high", "critical"} for f in findings)
    result = "warning" if findings else "passed"
    if has_high and spec.mandatory:
        result = "failed"
    elif has_high:
        result = "warning"
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result=result if findings or result == "passed" else "passed",
        mandatory=spec.mandatory,
        tool_name="pi_content_pack",
        severity_max=max((f.severity for f in findings), default="info", key=_rank),
        findings=findings,
    )


def _scan_text(text: str, rel: str, spec: CheckSpec, *, encoded: bool = False) -> list[Finding]:
    out: list[Finding] = []
    for pattern, rule, sev in PI_PATTERNS:
        match = pattern.search(text)
        if match and not _defensive_context(text, match.start()):
            out.append(
                Finding(
                    check_id=spec.check_id,
                    family=spec.family,
                    rule_id=rule + ("_b64" if encoded else ""),
                    severity=sev,
                    title=f"Prompt-injection pattern: {rule}",
                    path=rel,
                    message=redact_message(f"matched {rule}" + (" via base64" if encoded else "")),
                    tool_name="pi_content_pack",
                )
            )
    return out


def _defensive_context(text: str, position: int) -> bool:
    line_start = text.rfind("\n", 0, position) + 1
    line_end = text.find("\n", position)
    line = text[line_start : line_end if line_end >= 0 else len(text)]
    defensive = re.compile(
        r"(?i)\b(?:do not|don't|never|avoid|must not|detect|block|example of an attack)\b"
    )
    return bool(defensive.search(line))


def _try_b64(blob: str) -> str | None:
    try:
        pad = "=" * (-len(blob) % 4)
        return base64.b64decode(blob + pad, validate=False).decode("utf-8", errors="strict")
    except Exception:
        return None


def _looks_text(s: str) -> bool:
    if not s or len(s) < 8:
        return False
    printable = sum(1 for c in s if c.isprintable() or c in "\n\r\t")
    return printable / len(s) > 0.85


def _rank(sev: str) -> int:
    return {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}.get(sev, 0)
