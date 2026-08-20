"""Hook schema and command argv safety."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding

ALLOWED_HOOK_TYPES = frozenset({"command", "http", "mcp_tool", "prompt", "agent"})
DANGEROUS_SHELL = re.compile(
    r"(?i)(\beval\b|`[^`]+`|\$\([^)]+\)|\|\s*(bash|sh)\b|curl\s+.*\|\s*sh|rm\s+-rf\s+/)"
)


def run_schema(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    del manifest
    findings: list[Finding] = []
    for path, data in _iter_hook_docs(tree):
        hooks = data.get("hooks")
        if hooks is None:
            continue
        if not isinstance(hooks, dict):
            findings.append(
                Finding(
                    check_id=spec.check_id,
                    family=spec.family,
                    rule_id="hook_hooks_not_object",
                    severity="high",
                    title="hooks field must be an object",
                    path=path,
                    message="invalid hooks structure",
                    tool_name="hook_schema_static",
                )
            )
            continue
        hooks_map = cast(dict[str, Any], hooks)
        for event, groups in hooks_map.items():
            if not isinstance(groups, list):
                findings.append(
                    Finding(
                        check_id=spec.check_id,
                        family=spec.family,
                        rule_id="hook_event_not_list",
                        severity="medium",
                        title=f"Hook event {event} is not a list",
                        path=path,
                        message=str(event),
                        tool_name="hook_schema_static",
                    )
                )
                continue
            for raw_group in cast(list[Any], groups):
                if not isinstance(raw_group, dict):
                    continue
                group = cast(dict[str, Any], raw_group)
                hooks_any = group.get("hooks")
                if not isinstance(hooks_any, list):
                    continue
                for raw_hook in cast(list[Any], hooks_any):
                    if not isinstance(raw_hook, dict):
                        continue
                    hook = cast(dict[str, Any], raw_hook)
                    htype = hook.get("type") or "command"
                    if htype not in ALLOWED_HOOK_TYPES:
                        findings.append(
                            Finding(
                                check_id=spec.check_id,
                                family=spec.family,
                                rule_id="hook_unknown_type",
                                severity="high",
                                title=f"Unknown hook type: {htype}",
                                path=path,
                                message=redact_message(str(htype)),
                                tool_name="hook_schema_static",
                            )
                        )
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result="failed" if findings else "passed",
        mandatory=spec.mandatory,
        tool_name="hook_schema_static",
        severity_max="high" if findings else "info",
        findings=findings,
    )


def run_command(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    del manifest
    findings: list[Finding] = []
    for path, data in _iter_hook_docs(tree):
        hooks = data.get("hooks")
        if not isinstance(hooks, dict):
            continue
        hooks_map = cast(dict[str, Any], hooks)
        for _event, groups in hooks_map.items():
            if not isinstance(groups, list):
                continue
            for raw_group in cast(list[Any], groups):
                if not isinstance(raw_group, dict):
                    continue
                group = cast(dict[str, Any], raw_group)
                hooks_any = group.get("hooks")
                if not isinstance(hooks_any, list):
                    continue
                for raw_hook in cast(list[Any], hooks_any):
                    if not isinstance(raw_hook, dict):
                        continue
                    hook = cast(dict[str, Any], raw_hook)
                    command = hook.get("command")
                    if isinstance(command, str) and DANGEROUS_SHELL.search(command):
                        findings.append(
                            Finding(
                                check_id=spec.check_id,
                                family=spec.family,
                                rule_id="hook_dangerous_shell",
                                severity="critical",
                                title="Dangerous shell pattern in hook command",
                                path=path,
                                message=redact_message(command[:120]),
                                tool_name="hook_command_argv",
                            )
                        )
                    # Prefer argv arrays; raw string with expansion is risky.
                    if (
                        isinstance(command, str)
                        and ("${" in command or "`" in command or "eval " in command.lower())
                        and not isinstance(hook.get("args"), list)
                    ):
                        findings.append(
                            Finding(
                                check_id=spec.check_id,
                                family=spec.family,
                                rule_id="hook_string_command_expansion",
                                severity="high",
                                title="Hook command uses shell expansion without argv array",
                                path=path,
                                message=redact_message(command[:120]),
                                tool_name="hook_command_argv",
                            )
                        )
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result="failed" if findings else "passed",
        mandatory=spec.mandatory,
        tool_name="hook_command_argv",
        severity_max="critical" if findings else "info",
        findings=findings,
    )


def _iter_hook_docs(tree: Path) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for path in tree.rglob("*"):
        if not path.is_file():
            continue
        if path.name not in {"settings.json", "hooks.json"} and "hooks" not in path.as_posix():
            if path.suffix not in {".json"}:
                continue
            if "hook" not in path.name.lower():
                continue
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            out.append((path.relative_to(tree).as_posix(), cast(dict[str, Any], data)))
    return out
