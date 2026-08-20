"""Dedupe findings by family ownership and severity."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from ai_stp_platform.safety.types import CheckOutcome, Finding

_SEV_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def fingerprint_finding(finding: Finding) -> str:
    raw = f"{finding.family}|{finding.rule_id}|{finding.path or ''}|{finding.title}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def dedupe_findings(findings: Iterable[Finding]) -> list[Finding]:
    """Keep highest severity per (family, rule_id, path, title)."""
    best: dict[str, Finding] = {}
    for finding in findings:
        fp = finding.fingerprint or fingerprint_finding(finding)
        finding.fingerprint = fp
        prev = best.get(fp)
        if prev is None or _SEV_RANK.get(finding.severity, 0) > _SEV_RANK.get(prev.severity, 0):
            best[fp] = finding
    return list(best.values())


def apply_findings_to_outcome(outcome: CheckOutcome) -> CheckOutcome:
    """Normalize findings and derive severity_max / result upgrades."""
    outcome.findings = dedupe_findings(outcome.findings)
    if outcome.findings:
        outcome.severity_max = max(
            outcome.findings,
            key=lambda f: _SEV_RANK.get(f.severity, 0),
        ).severity
    return outcome


def redact_message(text: str, *, limit: int = 200) -> str:
    """Strip likely secret material and truncate."""
    import re

    cleaned = re.sub(
        r"(?i)(ghp_|github_pat_|sk-|AKIA|xox[baprs]-)[A-Za-z0-9_\-]{8,}",
        "[REDACTED]",
        text,
    )
    cleaned = re.sub(
        r"(?i)(token|secret|password|api[_-]?key)\s*[:=]\s*\S+", r"\1=[REDACTED]", cleaned
    )
    if len(cleaned) > limit:
        return cleaned[: limit - 3] + "..."
    return cleaned
