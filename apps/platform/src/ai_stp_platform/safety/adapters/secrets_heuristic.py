"""High-confidence inline secret heuristics (fast_scan port)."""

from __future__ import annotations

import re
from pathlib import Path

from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding

SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"ghp_[A-Za-z0-9_]{36,255}"), "GitHub Personal Access Token"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{82}"), "GitHub fine-grained PAT"),
    (re.compile(r"gho_[A-Za-z0-9_]{36,255}"), "GitHub OAuth token"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS Access Key ID"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "OpenAI-style secret key"),
]

ALLOWLIST_PRAGMA = re.compile(
    r"#\s*pragma:\s*allowlist\s*secret|//\s*pragma:\s*allowlist\s*secret",
    re.I,
)


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
        if ALLOWLIST_PRAGMA.search(text):
            continue
        for pattern, label in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(
                    Finding(
                        check_id=spec.check_id,
                        family=spec.family,
                        rule_id=label.lower().replace(" ", "_"),
                        severity="critical",
                        title=f"Possible secret: {label}",
                        path=rel,
                        message=redact_message(f"{label} pattern matched"),
                        tool_name="secrets_heuristic",
                    )
                )
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result="failed" if findings else "passed",
        mandatory=spec.mandatory,
        tool_name="secrets_heuristic",
        severity_max="critical" if findings else "info",
        findings=findings,
    )
