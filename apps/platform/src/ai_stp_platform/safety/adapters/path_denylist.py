"""Forbidden path patterns (ported from ai-repo-safety forbid_sensitive_files)."""

from __future__ import annotations

import fnmatch
from pathlib import Path

from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding

# Secrets and keys only. MCP config basenames (.mcp.json, claude_desktop_config.json)
# are owned by mcp_config_static — denylisting them here blocks legitimate mcp
# packages that ship those names even when the config itself is clean.
DENY = [
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa",
    "id_ed25519",
    "credentials.json",
    "credentials.*.json",
    "service-account*.json",
    "token.json",
    "tokens.json",
    "secrets.json",
    "*.ovpn",
]
ALLOW = {
    ".env.example",
    "env.example",
    "example.env",
    "credentials.example.json",
    "example.credentials.json",
    "service-account.example.json",
}


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    del manifest
    findings: list[Finding] = []
    for path in tree.rglob("*"):
        if not path.is_file():
            continue
        name = path.name
        if name in ALLOW:
            continue
        rel = path.relative_to(tree).as_posix()
        if any(fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel, pat) for pat in DENY):
            findings.append(
                Finding(
                    check_id=spec.check_id,
                    family=spec.family,
                    rule_id="path_denylist",
                    severity="critical",
                    title="Forbidden sensitive path in artifact",
                    path=rel,
                    message=redact_message(f"path matched denylist: {name}"),
                    tool_name="path_denylist",
                )
            )
    result = "failed" if findings else "passed"
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result=result,
        mandatory=spec.mandatory,
        tool_name="path_denylist",
        severity_max="critical" if findings else "info",
        findings=findings,
    )
