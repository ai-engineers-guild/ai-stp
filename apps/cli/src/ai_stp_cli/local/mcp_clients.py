"""Structural reading of MCP client servers declared inside a setting file.

A dedicated client file such as Claude Code's `.mcp.json` proves itself by
existing, so discovery reports it without opening it. Three harnesses keep
their client servers somewhere else: inside a file that is also a setting --
`config.toml` for `codex` and `grok-build`, `opencode.json` for `opencode`.
There, existence proves nothing. The file is present on every machine that ran
the harness once, and `"mcp": {}` is a common way to declare no server at all.
Declaring a layout at that path alone would report a client configuration for
every such machine.

This module answers the narrower question the inventory needs: does this exact
file declare MCP servers, and under which names. Only the names are read. The
values beside them -- command, arguments, URL, headers, environment -- are
never returned, so a token written into a server entry cannot reach a passport,
a log or a fixture.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Final, cast

#: A client configuration is written by hand. Anything larger is not one, and
#: is refused rather than parsed, so an unbounded file cannot be pulled into
#: memory by naming it after a setting.
MAX_CLIENT_BYTES: Final[int] = 1024 * 1024


def _string_end(text: str, start: int) -> int:
    """The index just past the JSON string opening at `start`."""
    index = start + 1
    length = len(text)
    while index < length:
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == '"':
            return index + 1
        index += 1
    return length


def _without_comments(text: str) -> str:
    """JSONC reduced to JSON: comments removed, trailing commas dropped.

    Written out rather than taken as a dependency. The whole need is to read
    key names out of one hand-written file, and a parser short enough to read
    in full is a smaller risk in the discovery path than another package.

    Strings are stepped over rather than scanned, so a `//` inside a URL and a
    comma inside a description survive untouched.
    """
    kept: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        if text[index] == '"':
            end = _string_end(text, index)
            kept.append(text[index:end])
            index = end
            continue
        if text.startswith("//", index):
            line_end = text.find("\n", index)
            if line_end < 0:
                break
            index = line_end
            continue
        if text.startswith("/*", index):
            closed = text.find("*/", index + 2)
            index = length if closed < 0 else closed + 2
            continue
        kept.append(text[index])
        index += 1
    return _without_trailing_commas("".join(kept))


def _without_trailing_commas(text: str) -> str:
    kept: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        if text[index] == '"':
            end = _string_end(text, index)
            kept.append(text[index:end])
            index = end
            continue
        if text[index] == ",":
            look = index + 1
            while look < length and text[look] in " \t\r\n":
                look += 1
            if look < length and text[look] in "}]":
                index += 1
                continue
        kept.append(text[index])
        index += 1
    return "".join(kept)


def _document(path: Path) -> dict[str, object] | None:
    """The file parsed by the format its name declares, or `None`.

    A file that cannot be read, is too large, is not UTF-8, is malformed, or
    does not hold a mapping at the top level yields `None`. A malformed file is
    not evidence of anything, and guessing at its intent is exactly the
    heuristic this adapter exists to avoid.
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if len(raw) > MAX_CLIENT_BYTES:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    try:
        if path.suffix == ".toml":
            parsed: object = tomllib.loads(text)
        elif path.suffix == ".jsonc":
            parsed = json.loads(_without_comments(text))
        else:
            parsed = json.loads(text)
    except (tomllib.TOMLDecodeError, ValueError):
        return None
    return cast("dict[str, object]", parsed) if isinstance(parsed, dict) else None


def declared_servers(path: Path, key: str) -> tuple[str, ...]:
    """Names of the MCP servers this file declares under `key`, sorted.

    Empty when the file is unreadable, malformed, carries no such key, or
    declares an empty mapping. Callers read empty as "this file is not a client
    configuration", which is the point: `"mcp": {}` says the harness was told
    to run no server, not that a client configuration is present.
    """
    document = _document(path)
    if document is None:
        return ()
    servers = document.get(key)
    if not isinstance(servers, dict):
        return ()
    named = cast("dict[object, object]", servers)
    return tuple(sorted(name for name in named if isinstance(name, str) and name))
