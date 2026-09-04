# ruff: noqa: E501
"""Deterministic checks for dangerous agent/skill behavior declarations."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

from ai_stp_platform.safety.adapters.detector_lines import is_detector_line
from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding

TEXT_SUFFIXES = frozenset(
    {".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".py", ".js", ".ts", ".sh", ".ps1"}
)
MAX_TEXT_BYTES = 1 << 20
_NPX_UVX_INSTRUCTION_NAMES = frozenset(
    {"skill.md", "agent.md", "agents.md", "command.md", "hooks.md", "setting.md"}
)
_NPX_UVX_FLOATING = re.compile(
    r"(?i)(?:npx|uvx)\s+"
    r"(?!are\b|is\b|or\b|and\b|to\b|for\b|from\b|with\b|when\b|if\b|of\b|"
    r"in\b|on\b|at\b|a\b|an\b|the\b|as\b|by\b|be\b|package\b)"
    r"((?:@[A-Za-z0-9._-]+/)?"
    r"[A-Za-z0-9._-]+)"
    r"(?!@|==)"
    r"(?:\s|$)"
)
RULES: tuple[tuple[str, str], ...] = (
    (
        "subagent_output_injection",
        r"(?i)(?:subagent|child agent).{0,100}(?:output|response).{0,100}(?:treat|execute|follow).{0,40}(?:trusted|instruction|command)",
    ),
    (
        "subagent_confused_deputy",
        r"(?i)(?:ask|delegate to).{0,60}(?:parent|privileged|admin) agent.{0,100}(?:bypass|without approval|on your behalf)",
    ),
    (
        "subagent_delegation_loop",
        r"(?i)(?:spawn|create|delegate to).{0,50}(?:subagents?|child agents?).{0,100}(?:recursively|without limit|until successful|each must spawn)",
    ),
    (
        "context_window_stuffing",
        r"(?i)(?:repeat|pad|fill).{0,80}(?:context|tokens?|characters?).{0,80}(?:100000|one hundred thousand|until.{0,20}(?:full|limit))",
    ),
    (
        "agent_snooping",
        r"(?i)(?:read|scan|enumerate).{0,100}(?:other|neighboring|installed).{0,40}(?:skills?|agents?).{0,40}(?:SKILL\.md|instructions?|definitions?)",
    ),
    (
        "self_modification",
        r"(?i)(?:modify|rewrite|patch|disable).{0,80}(?:own|your).{0,30}(?:prompt|instructions?|hooks?|settings?|allowlist|configuration)",
    ),
    (
        "trigger_persistence",
        r"(?i)(?:crontab|startup|autorun|shell profile|\.bashrc|\.zshrc|git hooks?|scheduled task).{0,100}\b(?:install|append|write|persist|execute)\b",
    ),
    (
        "capability_laundering",
        r"(?i)(?:harmless|read-only|calculator|formatter).{0,120}(?:shell|filesystem).{0,80}(?:network|http|upload).{0,80}(?:required|permission|access)",
    ),
    (
        "tool_argument_hijacking",
        r"(?i)(?:replace|change|override|rewrite).{0,40}(?:recipient|repository|branch|filename|destination|argument).{0,80}(?:before|when).{0,50}(?:tool|call|send|invoke)",
    ),
    (
        "scope_creep",
        r"(?i)(?:on|if).{0,40}(?:error|failure).{0,100}(?:disable tls|ignore certificate|change permissions|grant admin|use --force)",
    ),
    (
        "unsafe_output_to_shell",
        r"(?i)(?:model|tool|agent|response|output).{0,80}(?:eval\s*\(|exec\s*\(|sh\s+-c|bash\s+-c|invoke-expression|template\.render).{0,60}(?:without|no).{0,30}(?:validation|sanitization|review)",
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
        r"(?i)(?:branch|version)\s*[:=]\s*[\"']?(?:main|master|latest|\*)",
    ),
    (
        "memory_poisoning",
        r"(?i)(?:write|append|store|persist).{0,80}(?:MEMORY\.md|SOUL\.md|agent memory|session state|rules file).{0,100}(?:instruction|always|future session|without telling)",
    ),
    (
        "remote_instruction_loading",
        r"(?i)(?:fetch|download|curl|request).{0,100}(?:instructions?\.md|prompt\.txt|rules\.md).{0,100}(?:execute|source|follow|treat (?:it )?as instructions?)",
    ),
    (
        "path_scope_escape",
        r"(?i)(?:\.\.[/\\]){2,}.{0,80}(?:SKILL\.md|AGENT\.md|credentials?|instructions?)",
    ),
)


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    findings: list[Finding] = []
    self_names = _self_package_names(tree, manifest)
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
        findings.extend(_scan_text(spec, rel, path.name, text, self_names))
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


def _scan_text(
    spec: CheckSpec,
    rel: str,
    name: str,
    text: str,
    self_names: frozenset[str],
) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[str] = set()
    instruction = name.lower() in _NPX_UVX_INSTRUCTION_NAMES
    for line in text.splitlines():
        if is_detector_line(line):
            continue
        for rule_id, pattern in RULES:
            if rule_id in seen:
                continue
            if re.search(pattern, line):
                seen.add(rule_id)
                findings.append(
                    _finding(spec, rule_id, rel, f"Dangerous agent behavior: {rule_id}")
                )
        if instruction and "dependency_floating" not in seen:
            match = _NPX_UVX_FLOATING.search(line)
            if match is not None and not _is_self_package(match.group(1), self_names):
                seen.add("dependency_floating")
                findings.append(
                    _finding(
                        spec,
                        "dependency_floating",
                        rel,
                        "Dangerous agent behavior: dependency_floating",
                    )
                )
    return findings


def _self_package_names(tree: Path, manifest: ArtifactManifest) -> frozenset[str]:
    names: set[str] = set()
    for rel in manifest.text_files:
        if Path(rel).name.lower() != "skill.md":
            continue
        path = tree / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        declared = _frontmatter_name(text)
        if declared:
            names.update(_package_aliases(declared))
    return frozenset(names)


def _frontmatter_name(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    for raw in text[3:end].splitlines():
        line = raw.strip()
        if not line.lower().startswith("name:"):
            continue
        value = line.split(":", 1)[1].strip().strip("'\"")
        if value:
            return value
    return None


def _package_aliases(name: str) -> set[str]:
    lowered = name.strip().lower()
    return {lowered, lowered.replace("_", "-"), lowered.replace("-", "_")}


def _is_self_package(package: str, self_names: frozenset[str]) -> bool:
    if not self_names:
        return False
    return not _package_aliases(package).isdisjoint(self_names)


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
