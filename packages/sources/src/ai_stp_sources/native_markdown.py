"""Native local Markdown entry rules shared with the strict Rust consumer."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import PurePosixPath

from ai_stp_foundation.canonical import JsonValue
from ai_stp_sources.native_frontmatter import SPACE as _SPACE
from ai_stp_sources.native_frontmatter import invalid, parse

_JS_SPACE = _SPACE.replace("\u0085", "") + "\ufeff"


def captured(
    files: Mapping[str, bytes], prefixes: tuple[str, ...], roots: tuple[str, ...]
) -> dict[str, tuple[str, bytes]]:
    """Normalize only declared native roots and reject alias-path collisions."""
    result: dict[str, tuple[str, bytes]] = {}
    for path, payload in files.items():
        local = next((path[len(prefix) :] for prefix in prefixes if path.startswith(prefix)), path)
        relative = next((local[len(root) :] for root in roots if local.startswith(root)), None)
        if relative is None or relative in result:
            raise invalid()
        result[relative] = (path, payload)
    return dict(sorted(result.items()))


def _reserved(name: str) -> bool:
    name = name.lower()
    return name == "anthropic-skills" or name.startswith("anthropic-skills:")


def _claude(kind: str, files: Mapping[str, bytes]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {path: [] for path in files}
    if kind == "agent":
        for path, payload in files.items():
            if not path.endswith(".md"):
                raise invalid()
            header = parse(payload)
            name, description = header.get("name"), header.get("description")
            if (
                not isinstance(name, str)
                or name.startswith("-")
                or ":" in name
                or len(name) > 256
                or not isinstance(description, str)
                or not description.strip(_SPACE)
            ):
                raise invalid()
            result[path] = [name]
        return result
    root = "skills/" if kind == "skill" else "commands/"
    for local, (path, payload) in captured(files, (".claude/", ".agents/"), (root,)).items():
        if kind == "command":
            if not local.endswith(".md"):
                continue
            name = local[:-3]
            if not name or _reserved(name) or any(char in _SPACE for char in name):
                raise invalid()
            result[path] = [name.replace("/", ":")]
            continue
        if path.endswith("/.claude-plugin/plugin.json"):
            raise invalid()
        folder, separator, leaf = local.partition("/")
        if not separator or leaf != "SKILL.md":
            continue
        if (
            folder.lower() == "synced"
            or _reserved(folder)
            or any(char in _SPACE for char in folder)
        ):
            raise invalid()
        names = {folder}
        header = parse(payload, optional=True)
        if "name" in header:
            name = header["name"]
            if (
                not isinstance(name, str)
                or not name
                or any(char in _SPACE or char in "/\\" for char in name)
                or _reserved(name)
            ):
                raise invalid()
            names.add(name)
        result[path] = sorted(names)
    return result


def _scanned(parts: list[str]) -> bool:
    return len(parts) <= 10 and all(
        not part.startswith(".") and part not in {"node_modules", "__pycache__", "dist", "build"}
        for part in parts
    )


def _cli_surface(metadata: JsonValue) -> bool:
    surfaces = metadata.get("surfaces") if isinstance(metadata, dict) else None
    if isinstance(surfaces, list):
        return not surfaces or "cli" in surfaces
    if isinstance(surfaces, str):
        values = [value.strip(_SPACE) for value in surfaces.split(",") if value.strip(_SPACE)]
        return not values or "cli" in values
    if surfaces is None:
        return True
    raise invalid()


def _cursor_agent(payload: bytes, fallback: str) -> str:
    try:
        text = payload.decode("utf-8")
    except UnicodeError as error:
        raise invalid() from error
    if text.startswith("---\r\n"):
        rest = text[5:]
    elif text.startswith("---\n"):
        rest = text[4:]
    else:
        raise invalid()
    offset = 0
    for line in rest.split("\n"):
        length = len(line) + (offset + len(line) < len(rest))
        if line.rstrip("\r") == "---":
            if offset == 0 or not rest[offset + length :].strip(_JS_SPACE):
                raise invalid()
            header = rest[:offset]
            break
        offset += length
        if len(rest[:offset].encode()) > 64 * 1024:
            raise invalid()
    else:
        raise invalid()
    name = ""
    for line in header.split("\n"):
        line = line.strip(_JS_SPACE)
        if line.startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if separator and key.strip(_JS_SPACE).lower() == "name":
            name = value.strip(_JS_SPACE)
    return name or re.sub("[_" + re.escape(_JS_SPACE) + "]+", "-", fallback)


def _cursor(kind: str, files: Mapping[str, bytes]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {path: [] for path in files}
    prefixes = (".cursor/",) if kind == "agent" else (".cursor/", ".agents/")
    root = "agents/" if kind == "agent" else "skills/"
    for local, (path, payload) in captured(files, prefixes, (root,)).items():
        parts = local.split("/")
        if not _scanned(parts[:-1]):
            continue
        if kind == "agent":
            file = PurePosixPath(local)
            if file.suffix.lower() not in {".md", ".mdc", ".markdown"}:
                continue
            name = _cursor_agent(payload, file.stem)
            if name != "claude-code-tutor":
                result[path] = [name]
            continue
        if parts[-1] != "SKILL.md":
            continue
        header = parse(payload, legacy=True)
        if not _cli_surface(header.get("metadata")):
            continue
        description = header.get("description")
        if header.get("alwaysApply") is True or not isinstance(description, str) or not description:
            raise invalid()
        result[path] = [parts[-2] if len(parts) > 1 else "skills"]
    return result


def _opencode(kind: str, files: Mapping[str, bytes]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {path: [] for path in files}
    for local, (path, payload) in captured(
        files, (".opencode/", ".agents/"), (f"{kind}s/", f"{kind}/")
    ).items():
        if kind == "skill":
            if local.rsplit("/", 1)[-1] != "SKILL.md":
                continue
            header = parse(payload, legacy=True)
            if "description" in header and not isinstance(header["description"], str):
                raise invalid()
            name = header.get("name")
        else:
            if not local.endswith(".md"):
                continue
            header = parse(payload, optional=True, legacy=True)
            name = header.get("name", local[:-3])
        if not isinstance(name, str):
            raise invalid()
        result[path] = [name]
    return result


def _grok_name(payload: bytes, fallback: str) -> str:
    try:
        text = payload.decode("utf-8")
    except UnicodeError as error:
        raise invalid() from error
    content = text.lstrip(_SPACE)
    header: dict[str, JsonValue] = {}
    if content.startswith("---"):
        length = len(text.encode()) - len(content.encode())
        for index, line in enumerate(re.findall(r"[^\n]*\n|[^\n]+$", content)):
            length += len(line.encode())
            if length > 4096:
                raise invalid()
            if index > 0 and line.strip(_SPACE) == "---":
                break
        else:
            raise invalid()
        header = parse(content.encode(), merged=False, empty=True)
    declared = header.get("name")
    if isinstance(declared, float):
        raise invalid()
    if isinstance(declared, bool):
        declared = str(declared).lower()
    elif isinstance(declared, int):
        declared = str(declared)
    for value in (declared, fallback):
        if isinstance(value, str):
            normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip(_SPACE)).strip("-").lower()
            if normalized and len(normalized) <= 64:
                return normalized
    raise invalid()


def _grok(files: Mapping[str, bytes]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {path: [] for path in files}
    for local, (path, payload) in captured(files, (".grok/", ".agents/"), ("skills/",)).items():
        parts = local.split("/")
        if parts[-1] == "SKILL.md" and 2 <= len(parts) <= 7:
            result[path] = [_grok_name(payload, parts[-2])]
    return result


def identities(harness: str, kind: str, files: Mapping[str, bytes]) -> dict[str, list[str]]:
    if harness == "claude-code":
        return _claude(kind, files)
    if harness == "cursor":
        return _cursor(kind, files)
    if harness == "opencode":
        return _opencode(kind, files)
    if harness == "grok-build":
        return _grok(files)
    raise invalid()
