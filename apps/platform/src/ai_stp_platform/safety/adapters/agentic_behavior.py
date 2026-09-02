# ruff: noqa: E501
"""Deterministic checks for dangerous agent/skill behavior declarations."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding

TEXT_SUFFIXES = frozenset(
    {".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".py", ".js", ".ts", ".sh", ".ps1"}
)
MAX_TEXT_BYTES = 1 << 20

RULES: tuple[tuple[str, str], ...] = (
    (
        "subagent_output_injection",
        r"(?is)(?:subagent|child agent).{0,100}(?:output|response).{0,100}(?:treat|execute|follow).{0,40}(?:trusted|instruction|command)",
    ),
    (
        "subagent_confused_deputy",
        r"(?is)(?:ask|delegate to).{0,60}(?:parent|privileged|admin) agent.{0,100}(?:bypass|without approval|on your behalf)",
    ),
    (
        "subagent_delegation_loop",
        r"(?is)(?:spawn|create|delegate to).{0,50}(?:subagents?|child agents?).{0,100}(?:recursively|without limit|until successful|each must spawn)",
    ),
    (
        "context_window_stuffing",
        r"(?is)(?:repeat|pad|fill).{0,80}(?:context|tokens?|characters?).{0,80}(?:100000|one hundred thousand|until.{0,20}(?:full|limit))",
    ),
    (
        "agent_snooping",
        r"(?is)(?:read|scan|enumerate).{0,100}(?:other|neighboring|installed).{0,40}(?:skills?|agents?).{0,40}(?:SKILL\.md|instructions?|definitions?)",
    ),
    (
        "self_modification",
        r"(?is)(?:modify|rewrite|patch|disable).{0,80}(?:own|your).{0,30}(?:prompt|instructions?|hooks?|settings?|allowlist|configuration)",
    ),
    (
        "trigger_persistence",
        r"(?is)(?:crontab|startup|autorun|shell profile|\.bashrc|\.zshrc|git hook|scheduled task).{0,100}(?:install|append|write|persist|execute)",
    ),
    (
        "capability_laundering",
        r"(?is)(?:harmless|read-only|calculator|formatter).{0,120}(?:shell|filesystem).{0,80}(?:network|http|upload).{0,80}(?:required|permission|access)",
    ),
    (
        "tool_argument_hijacking",
        r"(?is)(?:replace|change|override|rewrite).{0,40}(?:recipient|repository|branch|filename|destination|argument).{0,80}(?:before|when).{0,50}(?:tool|call|send|invoke)",
    ),
    (
        "scope_creep",
        r"(?is)(?:on|if).{0,40}(?:error|failure).{0,100}(?:disable tls|ignore certificate|change permissions|grant admin|use --force)",
    ),
    (
        "unsafe_output_to_shell",
        r"(?is)(?:model|tool|agent|response|output).{0,80}(?:eval\s*\(|exec\s*\(|sh\s+-c|bash\s+-c|invoke-expression|template\.render).{0,60}(?:without|no).{0,30}(?:validation|sanitization|review)",
    ),
    (
        "unsafe_deserialization",
        r"(?i)(?:pickle\.loads?\s*\(|yaml\.(?:unsafe_load|load)\s*\([^\n]{0,100}Loader\s*=\s*yaml\.Loader|marshal\.load|php_unserialize|node-serialize)",
    ),
    (
        "package_lifecycle_execution",
        r"(?is)(?:postinstall|preinstall|setup\.py|password-protected (?:zip|archive)|downloaded (?:wheel|binary)).{0,100}(?:execute|run|shell|install)",
    ),
    (
        "dependency_floating",
        r"(?i)(?:(?:npx|uvx)\s+[@A-Za-z0-9_./-]+(?:\s|$)|(?:branch|version)\s*[:=]\s*[\"']?(?:main|master|latest|\*))",
    ),
    (
        "memory_poisoning",
        r"(?is)(?:write|append|store|persist).{0,80}(?:MEMORY\.md|SOUL\.md|agent memory|session state|rules file).{0,100}(?:instruction|always|future session|without telling)",
    ),
    (
        "remote_instruction_loading",
        r"(?is)(?:fetch|download|curl|request).{0,100}(?:instructions?\.md|prompt\.txt|rules\.md).{0,100}(?:execute|source|follow|treat (?:it )?as instructions?)",
    ),
    (
        "path_scope_escape",
        r"(?is)(?:\.\.[/\\]){2,}.{0,80}(?:SKILL\.md|AGENT\.md|credentials?|instructions?)",
    ),
)


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    findings: list[Finding] = []
    for rel in manifest.text_files:
        path = tree / rel
        if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
            continue
        try:
            if path.stat().st_size > MAX_TEXT_BYTES:
                findings.append(
                    _finding(spec, "context_window_stuffing", rel, "Oversized agent context file")
                )
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for rule_id, pattern in RULES:
            if re.search(pattern, text):
                findings.append(
                    _finding(spec, rule_id, rel, f"Dangerous agent behavior: {rule_id}")
                )
        if path.name == "package.json" and _has_floating_git_dependency(text):
            findings.append(
                _finding(
                    spec,
                    "dependency_floating",
                    rel,
                    "Dangerous agent behavior: dependency_floating",
                )
            )
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result="failed" if findings and spec.mandatory else "warning" if findings else "passed",
        mandatory=spec.mandatory,
        tool_name="agentic_behavior",
        severity_max="high" if findings else "info",
        findings=findings,
    )


def _has_floating_git_dependency(text: str) -> bool:
    try:
        raw_document = json.loads(text)
    except json.JSONDecodeError:
        return False
    if not isinstance(raw_document, dict):
        return False
    document = cast(dict[str, object], raw_document)
    for section in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
        dependencies = document.get(section)
        if not isinstance(dependencies, dict):
            continue
        for value in cast(dict[object, object], dependencies).values():
            if isinstance(value, str) and value.startswith(("git+http://", "git+https://")):
                return "#" not in value
    return False


def _finding(spec: CheckSpec, rule_id: str, path: str, title: str) -> Finding:
    return Finding(
        check_id=spec.check_id,
        family=spec.family,
        rule_id=rule_id,
        severity="high",
        title=title,
        path=path,
        message=redact_message(title),
        tool_name="agentic_behavior",
    )
