"""Opengrep with scoped vendored rules; in-proc fallback when CLI missing."""

from __future__ import annotations

import re
from pathlib import Path

from ai_stp_platform.safety.adapters._cli import classify_cli_exit, run_cli
from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.policy_pack import (
    opengrep_rules_dir,
    select_opengrep_rule_files,
)
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding

FALLBACK_RULES: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"(?i)curl\s+[^\n|]*\|\s*(bash|sh)"), "pipe_to_shell", "critical"),
    (
        re.compile(r"(?i)subprocess\.(call|Popen|run)\([^)]*shell\s*=\s*True"),
        "py_shell_true",
        "high",
    ),
    (re.compile(r"(?i)child_process\.exec\("), "node_exec", "high"),
    (re.compile(r"(?i)os\.system\("), "os_system", "high"),
    (
        re.compile(r"(?i)(token|secret|password|api[_-]?key)\"?\s*:\s*\"[A-Za-z0-9_\-/.=]{12,}"),
        "mcp_plaintext",
        "high",
    ),
]


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    rule_files = select_opengrep_rule_files(manifest)
    if not has_applicable_files(manifest):
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="passed",
            mandatory=spec.mandatory,
            tool_name="opengrep",
            detail={
                "mode": "no_applicable_files",
                "rule_files": [path.name for path in rule_files],
            },
        )
    argv = ["opengrep", "--error", "--quiet"]
    if rule_files:
        for path in rule_files:
            argv.extend(["--config", str(path)])
    else:
        rules = opengrep_rules_dir()
        if rules.is_dir() and any(rules.glob("*.yml")):
            argv.extend(["--config", str(rules)])
    argv.append(str(tree))
    code, out, err, ms = run_cli(argv, cwd=tree, timeout=spec.timeout_seconds)
    if code != 127:
        if code == 124:
            return CheckOutcome(
                check_id=spec.check_id,
                family=spec.family,
                result="degraded",
                mandatory=spec.mandatory,
                tool_name="opengrep",
                duration_ms=ms,
                # The shared classifier so the limit and a spent suite deadline
                # reach the wire; the rule files are this adapter's own addition.
                detail={
                    **classify_cli_exit(code, out, err)[1],
                    "rule_files": [p.name for p in rule_files],
                },
            )
        findings: list[Finding] = []
        if code not in (0,) and (out or err):
            findings.append(
                Finding(
                    check_id=spec.check_id,
                    family=spec.family,
                    rule_id="opengrep_hit",
                    severity="high",
                    title="Opengrep reported findings",
                    message=redact_message((out or err)[:300]),
                    tool_name="opengrep",
                )
            )
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="failed" if findings else "passed",
            mandatory=spec.mandatory,
            tool_name="opengrep",
            duration_ms=ms,
            severity_max="high" if findings else "info",
            findings=findings,
            detail={
                "mode": "cli",
                "rule_files": [p.name for p in rule_files],
            },
        )

    findings = []
    paths = list(dict.fromkeys(manifest.text_files + manifest.shell_files + manifest.python_files))
    for rel in paths:
        path = tree / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern, rule, sev in FALLBACK_RULES:
            # Plaintext secret-in-JSON pattern is MCP-oriented; skip for pure skills.
            if rule == "mcp_plaintext" and not _mcp_context(manifest):
                continue
            if _non_defensive_match(pattern, text):
                findings.append(
                    Finding(
                        check_id=spec.check_id,
                        family=spec.family,
                        rule_id=rule,
                        severity=sev,
                        title=f"Owned SAST pattern: {rule}",
                        path=rel,
                        message=redact_message(rule),
                        tool_name="opengrep_fallback",
                    )
                )
    findings.extend(_scan_vendored_regex(tree, manifest, spec, rule_files))
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result="failed" if findings else "passed",
        mandatory=spec.mandatory,
        tool_name="opengrep_fallback",
        severity_max="critical" if findings else "info",
        findings=findings,
        detail={
            "mode": "fallback_owned_rules",
            "rule_files": [p.name for p in rule_files],
        },
    )


def has_applicable_files(manifest: ArtifactManifest) -> bool:
    return bool(
        manifest.python_files
        or manifest.component_type == "mcp"
        or manifest.flags & {"github_actions", "gitlab_ci", "ci"}
    )


def _mcp_context(manifest: ArtifactManifest) -> bool:
    return manifest.component_type == "mcp" or "mcp" in manifest.flags


def _scan_vendored_regex(
    tree: Path,
    manifest: ArtifactManifest,
    spec: CheckSpec,
    rule_files: list[Path],
) -> list[Finding]:
    """Parse pattern-regex from scoped vendored YAML without full semgrep."""
    findings: list[Finding] = []
    if not rule_files:
        return findings
    regexes: list[tuple[str, re.Pattern[str]]] = []
    for yml in rule_files:
        try:
            lines = yml.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        rule_id = yml.stem
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("- id:"):
                rule_id = stripped.partition(":")[2].strip()
                continue
            if not stripped.startswith("pattern-regex:"):
                continue
            pattern = stripped.partition(":")[2].strip()
            if len(pattern) >= 2 and pattern[0] == pattern[-1] and pattern[0] in "'\"":
                quote = pattern[0]
                pattern = pattern[1:-1].replace(quote * 2, quote)
            try:
                regexes.append((rule_id, re.compile(pattern)))
            except re.error:
                continue
    if not regexes:
        return findings
    for rel in manifest.text_files[:200]:
        path = tree / rel
        if not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for rid, pattern in regexes:
            if _non_defensive_match(pattern, body):
                findings.append(
                    Finding(
                        check_id=spec.check_id,
                        family=spec.family,
                        rule_id=rid[:64],
                        severity="high",
                        title=f"Vendored rule hit: {rid}",
                        path=rel,
                        message=redact_message(rid),
                        tool_name="opengrep_vendored_regex",
                    )
                )
                break
    return findings


def _non_defensive_match(pattern: re.Pattern[str], text: str) -> bool:
    defensive = re.compile(
        r"(?i)\b(?:do not|don't|never|avoid|must not|detect|block|forbid(?:den)?)\b"
    )
    return any(pattern.search(line) and not defensive.search(line) for line in text.splitlines())
