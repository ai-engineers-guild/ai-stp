"""Named native syntax transforms for recast and component materialize.

Path remapping is not a native conversion. This module rewrites MCP server
objects, agent documents, hook manifests, and plugin packs into the target
harness form, or refuses. It does not invent a second rewrite engine: setup
recast and component materialize call the same functions.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Final, cast

import tomlkit

from ai_stp_cli.local.components import Rule
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.harnesses import HarnessId

_HEADING = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_PLUGIN_MANIFESTS: Final[dict[str, str]] = {
    "claude-code": ".claude-plugin/plugin.json",
    "cursor": ".cursor-plugin/plugin.json",
}
_MODULE_PLUGIN_HARNESSES: Final[frozenset[str]] = frozenset({"opencode", "pi"})


@dataclass(frozen=True)
class NativeTransform:
    """One lossless-enough native rewrite of already remapped files."""

    files: dict[str, bytes]
    modes: dict[str, int]
    source_paths: dict[str, str]
    losses: tuple[str, ...]


def transform(
    *,
    component_type: str,
    source_harness: HarnessId,
    target: Rule,
    files: Mapping[str, bytes],
    modes: Mapping[str, int],
    source_paths: Mapping[str, str],
) -> NativeTransform | None:
    """Rewrite remapped members into the target harness syntax, or refuse."""
    if component_type == "mcp":
        return None
    if component_type == "agent":
        return _agents(target, files, modes, source_paths)
    if component_type == "hook":
        return _hooks(target, files, modes, source_paths)
    if component_type == "plugin":
        return _plugins(source_harness, target, files, modes, source_paths)
    return NativeTransform(dict(files), dict(modes), dict(source_paths), ())


def encode_mcp_servers(
    servers: Mapping[str, JsonValue], target: Rule
) -> tuple[bytes, tuple[str, ...]] | None:
    """Serialize a logical MCP server map in the target host form."""
    if target.shape != "file":
        return None
    rewritten: dict[str, JsonValue] = {}
    losses: list[str] = []
    for name, raw in servers.items():
        if not isinstance(raw, dict):
            return None
        converted = _mcp_server_for_target(cast(dict[str, JsonValue], raw), target)
        if converted is None:
            return None
        body, extra = converted
        rewritten[name] = body
        losses.extend(extra)
    suffix = PurePosixPath(target.relative).suffix.casefold()
    payload: dict[str, JsonValue] = rewritten
    if not target.declared_key:
        wrapper = "mcp_servers" if suffix == ".toml" else "mcpServers"
        payload = {wrapper: rewritten}
    elif target.declared_key == "mcp" and suffix in {".json", ".jsonc"}:
        payload = rewritten
    try:
        if suffix == ".toml":
            encoded = tomlkit.dumps(payload).encode("utf-8")
        elif suffix in {".json", ".jsonc"}:
            encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
        else:
            return None
    except (TypeError, ValueError):
        return None
    return encoded, tuple(dict.fromkeys(losses))


def logical_mcp_servers(document: JsonValue) -> dict[str, JsonValue] | None:
    """Unwrap one MCP host document to a name→server map."""
    if not isinstance(document, dict):
        return None
    for key in ("mcpServers", "mcp_servers", "mcp"):
        held = document.get(key)
        if isinstance(held, dict):
            nested = held.get("servers")
            if (
                isinstance(nested, dict)
                and nested
                and all(isinstance(value, dict) for value in nested.values())
            ):
                return cast(dict[str, JsonValue], nested)
            if held and all(isinstance(value, dict) for value in held.values()):
                return cast(dict[str, JsonValue], held)
    if document and all(isinstance(value, dict) for value in document.values()):
        return cast(dict[str, JsonValue], document)
    return None


def _mcp_server_for_target(
    raw: dict[str, JsonValue], target: Rule
) -> tuple[dict[str, JsonValue], tuple[str, ...]] | None:
    command, args, env, url, dropped = _canonical_mcp(raw)
    losses = list(dropped)
    wants_opencode = target.declared_key == "mcp"
    if wants_opencode:
        if command is None:
            return None
        body: dict[str, JsonValue] = {
            "type": "local",
            "command": [command, *args],
        }
        if env:
            body["environment"] = cast(JsonValue, env)
        if url is not None:
            losses.append("remote MCP url is omitted on an OpenCode local server")
        return body, tuple(dict.fromkeys(losses))
    if command is None:
        return None
    body = {"command": command, "args": list(args)}
    if env:
        body["env"] = cast(JsonValue, env)
    if url is not None:
        losses.append("remote MCP url is omitted on a stdio MCP host")
    return body, tuple(dict.fromkeys(losses))


def _canonical_mcp(
    raw: dict[str, JsonValue],
) -> tuple[str | None, list[str], dict[str, str], str | None, tuple[str, ...]]:
    losses: list[str] = []
    url = raw.get("url") if isinstance(raw.get("url"), str) else None
    env_raw = raw.get("environment") if "environment" in raw else raw.get("env")
    env: dict[str, str] = {}
    if isinstance(env_raw, dict):
        env = {str(key): str(value) for key, value in env_raw.items()}
    command_raw = raw.get("command")
    args_raw = raw.get("args")
    args: list[str] = [str(item) for item in args_raw] if isinstance(args_raw, list) else []
    command: str | None
    if isinstance(command_raw, list) and command_raw:
        command = str(command_raw[0])
        rest = [str(item) for item in command_raw[1:]]
        if args and rest and args != rest:
            losses.append("MCP command array and args disagreed; the array won")
        args = rest or args
    elif isinstance(command_raw, str) and command_raw:
        command = command_raw
    else:
        command = None
    kind = raw.get("type")
    if isinstance(kind, str) and kind not in {"local", "stdio"} and command is None:
        losses.append(f"MCP type {kind} has no local command")
    return command, args, env, url if isinstance(url, str) else None, tuple(losses)


def _agents(
    target: Rule,
    files: Mapping[str, bytes],
    modes: Mapping[str, int],
    source_paths: Mapping[str, str],
) -> NativeTransform | None:
    if target.shape != "directory":
        return None
    rewritten: dict[str, bytes] = {}
    new_modes: dict[str, int] = {}
    new_sources: dict[str, str] = {}
    losses: list[str] = []
    for path, payload in files.items():
        suffix = PurePosixPath(path).suffix.casefold()
        if target.harness_id == "codex":
            if suffix == ".toml":
                dest, body = path, payload
            elif suffix in {".md", ".mdc"}:
                dest = str(PurePosixPath(path).with_suffix(".toml"))
                body = _markdown_to_codex_agent(path, payload)
                losses.append(f"{PurePosixPath(path).name} was rewritten as Codex TOML")
            else:
                return None
        else:
            if suffix in {".md", ".mdc"}:
                dest, body = path, payload
            elif suffix == ".toml":
                dest = str(PurePosixPath(path).with_suffix(".md"))
                body = _codex_agent_to_markdown(payload)
                losses.append(f"{PurePosixPath(path).name} was rewritten as Markdown")
            else:
                return None
        if dest in rewritten:
            return None
        rewritten[dest] = body
        new_modes[dest] = modes.get(path, 0o644)
        new_sources[dest] = source_paths.get(path, path)
    if not rewritten:
        return None
    return NativeTransform(rewritten, new_modes, new_sources, tuple(dict.fromkeys(losses)))


def _markdown_to_codex_agent(path: str, payload: bytes) -> bytes:
    text = payload.decode("utf-8", errors="replace")
    heading = _HEADING.search(text)
    name = heading.group(1).strip() if heading else PurePosixPath(path).stem
    description = _HEADING.sub("", text, count=1).strip() or name
    escaped = description.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'name = "{name}"\ndescription = "{escaped}"\n'.encode()


def _codex_agent_to_markdown(payload: bytes) -> bytes:
    parsed = tomlkit.parse(payload.decode("utf-8")).unwrap()
    name = str(parsed.get("name") or "agent")
    description = str(parsed.get("description") or "")
    body = f"# {name}\n"
    if description:
        body += f"\n{description}\n"
    return body.encode("utf-8")


def _hooks(
    target: Rule,
    files: Mapping[str, bytes],
    modes: Mapping[str, int],
    source_paths: Mapping[str, str],
) -> NativeTransform | None:
    if len(files) != 1:
        return None
    path, payload = next(iter(files.items()))
    document = _json_object(payload)
    if document is None:
        return None
    if target.shape == "file":
        dest = target.relative
    elif target.shape == "directory":
        dest = f"{target.relative.rstrip('/')}/hooks.json"
    else:
        return None
    losses: tuple[str, ...] = ()
    if dest != path:
        losses = (f"hook document moved from {path} to {dest}",)
    mode = modes.get(path, 0o644)
    origin = source_paths.get(path, path)
    encoded = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return NativeTransform({dest: encoded}, {dest: mode}, {dest: origin}, losses)


def _plugins(
    source_harness: HarnessId,
    target: Rule,
    files: Mapping[str, bytes],
    modes: Mapping[str, int],
    source_paths: Mapping[str, str],
) -> NativeTransform | None:
    if target.harness_id in _MODULE_PLUGIN_HARNESSES:
        if not any(path.endswith((".js", ".ts")) for path in files):
            return None
        return NativeTransform(dict(files), dict(modes), dict(source_paths), ())
    wanted = _PLUGIN_MANIFESTS.get(target.harness_id, "plugin.json")
    rewritten: dict[str, bytes] = {}
    new_modes: dict[str, int] = {}
    new_sources: dict[str, str] = {}
    losses: list[str] = []
    for path, payload in files.items():
        dest = _retarget_plugin_manifest(path, wanted)
        if dest != path:
            losses.append(f"plugin manifest moved to {wanted}")
        if dest in rewritten:
            return None
        rewritten[dest] = payload
        new_modes[dest] = modes.get(path, 0o644)
        new_sources[dest] = source_paths.get(path, path)
    if not rewritten:
        return None
    return NativeTransform(rewritten, new_modes, new_sources, tuple(dict.fromkeys(losses)))


def _retarget_plugin_manifest(path: str, wanted: str) -> str:
    posix = PurePosixPath(path)
    if posix.name != "plugin.json":
        return path
    parts = list(posix.parts[:-1])
    if parts and parts[-1] in {".claude-plugin", ".cursor-plugin"}:
        parts.pop()
    return str(PurePosixPath(*parts, *PurePosixPath(wanted).parts)) if parts else wanted


def _json_object(payload: bytes) -> dict[str, JsonValue] | None:
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return cast(dict[str, JsonValue], parsed) if isinstance(parsed, dict) else None
