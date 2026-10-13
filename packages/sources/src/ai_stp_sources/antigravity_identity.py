"""Antigravity's immediate skill directories and typed Markdown agents."""

from __future__ import annotations

from collections.abc import Mapping

from ai_stp_foundation.canonical import JsonValue
from ai_stp_sources.native_frontmatter import invalid, parse
from ai_stp_sources.native_markdown import captured
from ai_stp_sources.native_mcp import server_names


def _agent(payload: bytes) -> str:
    header = parse(payload, lexical_fields=("name", "description"))
    name, description = header.get("name"), header.get("description")
    if not isinstance(name, str) or not name or not isinstance(description, str) or not description:
        raise invalid()
    for field in ("tools", "skills", "plugins"):
        if field in header:
            value = header[field]
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise invalid()
    for field in ("mainAgent", "subagent"):
        if field in header and not isinstance(header[field], bool):
            raise invalid()
    for field in ("model", "commandExecutionPolicy"):
        if field in header and not isinstance(header[field], str):
            raise invalid()
    if "mcpServers" in header:
        servers = header["mcpServers"]
        if not isinstance(servers, list):
            raise invalid()
        named: dict[str, JsonValue] = {}
        for server in servers:
            if not isinstance(server, dict):
                raise invalid()
            server_name = server.get("name")
            if not isinstance(server_name, str) or not server_name or server_name in named:
                raise invalid()
            named[server_name] = server
        # The nested map owns server names and uses the same credential guard.
        server_names("antigravity", named)
    return name


def identities(kind: str, files: Mapping[str, bytes]) -> dict[str, list[str]]:
    roots = (
        ("config/skills/", ".agents/skills/")
        if kind == "skill"
        else ("config/agents/", "antigravity-cli/agents/", ".agents/agents/")
    )
    result: dict[str, list[str]] = {path: [] for path in files}
    for local, (path, payload) in captured(files, (".gemini/",), roots).items():
        if kind == "agent":
            direct, nested = "/" not in local, local.count("/") == 1
            if (direct and local.endswith(".json")) or (nested and local.endswith("/agent.json")):
                raise invalid()
            if (direct and local.endswith(".md")) or (nested and local.endswith("/agent.md")):
                result[path] = [_agent(payload)]
            continue
        parts = local.split("/")
        if len(parts) != 2 or not parts[1].endswith(".md") or parts[1][:-3].lower() != "skill":
            continue
        header = parse(payload, empty=True, lexical_fields=("name", "description"))
        for field in ("disable-model-invocation", "disable-slash-command"):
            value = header.get(field)
            if value is not None and not isinstance(value, bool):
                raise invalid()
        name = header.get("name")
        result[path] = [name if isinstance(name, str) and name else parts[1][:-3]]
    return result
