"""MCP config static scan (ported from ai-repo-safety scan_mcp_config)."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding

RISKY_NAMES = {".mcp.json", "claude_desktop_config.json"}
RISKY_COMMAND_PATTERNS = [
    re.compile(r"curl\s+.*\|\s*(bash|sh)", re.I),
    re.compile(r"wget\s+.*\|\s*(bash|sh)", re.I),
    re.compile(r"powershell.*(iex|invoke-expression)", re.I),
]
SECRET_LIKE = re.compile(
    r"(?i)(token|secret|password|api[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9_\-/.=]{12,}"
)
DOCKER_LATEST = re.compile(r"(?i)\bdocker://[^\s\"']+:latest\b")
WRITE_SCOPE = re.compile(r"(?i)\b(write|delete|admin|full|all|\*)\b")
EXPIRY_KEYS = {"expires", "expires_at", "expiresAt", "expiry", "rotation", "rotates_at", "ttl"}


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    del manifest
    findings: list[Finding] = []
    candidates = list(tree.rglob("*"))
    for path in candidates:
        if not path.is_file():
            continue
        name = path.name
        rel = path.relative_to(tree).as_posix()
        if name not in RISKY_NAMES and not (name.endswith(".json") and "mcp" in rel.lower()):
            continue
        findings.extend(_scan_file(path, rel, spec))
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result="failed" if findings else "passed",
        mandatory=spec.mandatory,
        tool_name="mcp_config_static",
        severity_max="high" if findings else "info",
        findings=findings,
    )


def _scan_file(path: Path, rel: str, spec: CheckSpec) -> list[Finding]:
    out: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    if SECRET_LIKE.search(text):
        out.append(_f(spec, "mcp_secret_like", "Secret-like plaintext in MCP config", rel, "high"))
    for pat in RISKY_COMMAND_PATTERNS:
        if pat.search(text):
            out.append(
                _f(
                    spec,
                    "mcp_risky_command",
                    f"Risky command pattern: {pat.pattern}",
                    rel,
                    "critical",
                )
            )
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return out
    for raw_obj in _walk(payload):
        if not isinstance(raw_obj, dict):
            continue
        obj = cast(dict[str, Any], raw_obj)
        command = _extract_command(obj)
        if command and _unpinned_npx(command):
            out.append(_f(spec, "mcp_unpinned_npx", "Unpinned npx package invocation", rel, "high"))
        if command and _unpinned_uvx(command):
            out.append(_f(spec, "mcp_unpinned_uvx", "Unpinned uvx package invocation", rel, "high"))
        if command and DOCKER_LATEST.search(command):
            out.append(
                _f(spec, "mcp_docker_latest", "Docker image uses mutable latest tag", rel, "medium")
            )
        for key in ("scope", "scopes", "permissions"):
            if key not in obj:
                continue
            for scope in _flatten_scopes(obj[key]):
                if WRITE_SCOPE.search(scope):
                    out.append(
                        _f(
                            spec,
                            "mcp_write_scope",
                            f"Over-privileged scope: {scope}",
                            rel,
                            "medium",
                        )
                    )
        token_like = any(
            isinstance(obj.get(k), str) and len(str(obj.get(k))) >= 12
            for k in ("token", "secret", "password", "apiKey", "api_key")
        )
        if token_like and not any(k in obj for k in EXPIRY_KEYS):
            out.append(
                _f(
                    spec,
                    "mcp_token_no_expiry",
                    "Token-like credential without expiry metadata",
                    rel,
                    "high",
                )
            )
    return out


def _f(spec: CheckSpec, rule: str, title: str, path: str, sev: str) -> Finding:
    return Finding(
        check_id=spec.check_id,
        family=spec.family,
        rule_id=rule,
        severity=sev,
        title=title,
        path=path,
        message=redact_message(title),
        tool_name="mcp_config_static",
    )


def _walk(node: Any) -> Iterator[Any]:
    if isinstance(node, dict):
        yield node
        for value in cast(dict[Any, Any], node).values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in cast(list[Any], node):
            yield from _walk(value)


def _flatten_scopes(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, list):
        return [i for i in cast(list[Any], node) if isinstance(i, str)]
    return []


def _extract_command(obj: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("command", "cmd"):
        value = obj.get(key)
        if isinstance(value, str):
            parts.append(value)
            break
        if isinstance(value, list):
            items = cast(list[Any], value)
            if all(isinstance(i, str) for i in items):
                parts.extend(cast(list[str], items))
                break
    args = obj.get("args")
    if isinstance(args, list):
        arg_items = cast(list[Any], args)
        if all(isinstance(i, str) for i in arg_items):
            parts.extend(cast(list[str], arg_items))
    return " ".join(parts)


def _unpinned_npx(command: str) -> bool:
    parts = command.strip().split()
    if len(parts) < 2 or parts[0].lower() != "npx":
        return False
    package = parts[1]
    return "@" not in package[1:]


def _unpinned_uvx(command: str) -> bool:
    parts = command.strip().split()
    if len(parts) < 2 or parts[0].lower() != "uvx":
        return False
    return "==" not in parts[1]
