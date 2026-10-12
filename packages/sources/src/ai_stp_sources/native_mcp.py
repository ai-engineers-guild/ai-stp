"""Native MCP names and credential boundaries for embedded whole-file sources."""

from __future__ import annotations

import json
import re
import tomllib
import unicodedata
from collections.abc import Mapping
from decimal import Decimal
from typing import cast
from urllib.parse import parse_qsl

from pydantic import AnyUrl, ValidationError

from ai_stp_sources.native_frontmatter import invalid

_SENSITIVE = frozenset(
    [
        "apikey",
        "accesskey",
        "accesskeyid",
        "accesstoken",
        "authtoken",
        "authorization",
        "proxyauthorization",
        "clientsecret",
        "credential",
        "credentials",
        "password",
        "passwd",
        "privatekey",
        "refreshtoken",
        "secret",
        "secretkey",
        "sessiontoken",
        "token",
        "bearertoken",
        "experimentalbearertoken",
        "cookie",
        "setcookie",
    ]
)
_SUFFIXES = (
    "apikey",
    "accesskey",
    "accesskeyid",
    "token",
    "secret",
    "password",
    "passwd",
    "privatekey",
    "cookie",
)
_VARIABLE = re.compile(r"\A[a-zA-Z0-9_-]{1,256}\Z")


def _sensitive(parent: str, name: str) -> bool:
    folded = re.sub(r"[^a-zA-Z0-9]", "", name.rsplit(".", 1)[-1]).lower()
    return folded in _SENSITIVE or (
        parent
        in {
            "env",
            "environment",
            "headers",
            "http_headers",
            "extra_headers",
            "query",
            "query_params",
        }
        and folded.endswith(_SUFFIXES)
    )


def _reference(harness: str, value: str) -> bool:
    value = value.removeprefix("Bearer ")
    prefix = {"claude-code": "${", "grok-build": "${", "cursor": "${env:", "opencode": "{env:"}.get(
        harness
    )
    if prefix and value.startswith(prefix) and value.endswith("}"):
        return _VARIABLE.fullmatch(value[len(prefix) : -1]) is not None
    if harness == "opencode" and value.startswith("{file:") and value.endswith("}"):
        path = value[6:-1]
        return bool(path.strip()) and not any(
            ord(char) < 32 or 127 <= ord(char) <= 159 or char in "{}" for char in path
        )
    return False


def _url(value: str) -> None:
    try:
        parsed = AnyUrl(value)
        if not parsed.host:
            return
        if (
            parsed.username
            or parsed.password is not None
            or any(
                _sensitive("query", key)
                for part in (parsed.query, parsed.fragment)
                for key, _ in parse_qsl(part or "", keep_blank_values=True)
            )
        ):
            raise invalid()
    except ValidationError:
        # Invalid URL syntax is ordinary scalar data, just as in the native guard.
        return


def credentials(harness: str, value: object, *, parent: str = "host", held: str = "plain") -> None:
    """Check named values as data; never resolve a reference or run a command."""
    nodes = 0

    def visit(value: object, parent: str, held: str, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if depth > 128 or nodes > 20_000:
            raise invalid()
        if isinstance(value, dict):
            for name, child in cast(dict[str, object], value).items():
                field = held
                if field == "plain":
                    if harness == "codex" and not parent and name == "env_http_headers":
                        field = "environment"
                    elif _sensitive(parent, name):
                        field = "credential"
                visit(child, name, field, depth + 1)
        elif isinstance(value, list):
            for child in cast(list[object], value):
                visit(child, parent, held, depth + 1)
        elif value is not None:
            if held == "credential" and not (
                isinstance(value, str) and (not value or _reference(harness, value))
            ):
                raise invalid()
            if held == "environment" and not (
                isinstance(value, str) and _VARIABLE.fullmatch(value)
            ):
                raise invalid()
            if isinstance(value, str):
                _url(value)

    visit(value, parent, held, 0)


def _strings(value: object) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) for item in cast(list[object], value)
    )


def _mapping(value: object) -> bool:
    return isinstance(value, dict) and all(
        isinstance(item, str) for item in cast(dict[str, object], value).values()
    )


def _claude(server: Mapping[str, object]) -> None:
    transport = server.get("type", "stdio")
    if transport == "stdio":
        command = server.get("command")
        valid = isinstance(command, str) and bool(command.strip())
        valid = valid and ("args" not in server or _strings(server["args"]))
        valid = valid and ("env" not in server or _mapping(server["env"]))
    elif transport in ("http", "streamable-http", "sse", "ws"):
        url = server.get("url")
        valid = isinstance(url, str) and bool(url.strip())
        valid = valid and ("headers" not in server or _mapping(server["headers"]))
        valid = valid and (
            "headersHelper" not in server or isinstance(server["headersHelper"], str)
        )
        if transport != "ws" and "oauth" in server:
            oauth = server["oauth"]
            if not isinstance(oauth, dict):
                raise invalid()
            fields = cast(dict[str, object], oauth)
            valid = valid and all(
                key not in fields or isinstance(fields[key], str) for key in ("clientId", "scopes")
            )
            if "callbackPort" in fields:
                port = fields["callbackPort"]
                valid = (
                    valid
                    and not isinstance(port, bool)
                    and isinstance(port, (int, float, Decimal))
                    and 1 <= port <= 65535
                    and port % 1 == 0
                )
            if "authServerMetadataUrl" in fields:
                metadata = fields["authServerMetadataUrl"]
                try:
                    valid = (
                        valid
                        and isinstance(metadata, str)
                        and metadata.strip().startswith("https://")
                        and bool(AnyUrl(metadata).host)
                    )
                except ValidationError:
                    valid = False
    else:
        valid = False
    if not valid:
        raise invalid()


def server_names(harness: str, entries: Mapping[str, object]) -> list[str]:
    if len(entries) > 500:
        raise invalid()
    for name, server in entries.items():
        if (
            not name.strip()
            or len(name) > 200
            or unicodedata.normalize("NFC", name) != name
            or any(unicodedata.category(char) == "Cc" for char in name)
            or not isinstance(server, dict)
        ):
            raise invalid()
        credentials(harness, cast(dict[str, object], server), parent="")
        if harness == "claude-code":
            _claude(cast(dict[str, object], server))
    return sorted(entries)


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise invalid()
    return result


def _constant(_value: str) -> object:
    raise invalid()


def _jsonc(source: str) -> str:
    """Strip comments and trailing commas in one bounded, forward-only scan."""
    kept: list[str] = []
    decoder = json.JSONDecoder()
    index = 0
    previous = ""
    trailing: int | None = None
    while index < len(source):
        char = source[index]
        if char == '"':
            _value, end = decoder.raw_decode(source, index)
            kept.append(source[index:end])
            index, previous, trailing = end, '"', None
            continue
        if source.startswith("//", index):
            index += 2
            while index < len(source) and source[index] not in "\r\n":
                index += 1
            kept.append(" ")
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            if end < 0:
                raise invalid()
            index = end + 2
            kept.append(" ")
            continue
        if char not in " \t\r\n":
            if char in "}]" and previous == "," and trailing is not None:
                kept[trailing] = ""
            trailing = len(kept) if char == "," and previous not in "[{,:" else None
            previous = char
        kept.append(char)
        index += 1
    return "".join(kept)


def _bounded(document: dict[str, object]) -> dict[str, object]:
    pending: list[tuple[object, int]] = [(document, 0)]
    nodes = 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if depth > 128 or nodes > 20_000:
            raise invalid()
        if isinstance(value, dict):
            # JSON can spell lone surrogates that cannot be native UTF-8.
            try:
                for name in cast(dict[str, object], value):
                    name.encode("utf-8")
            except UnicodeError as error:
                raise invalid() from error
            pending.extend((child, depth + 1) for child in cast(dict[str, object], value).values())
        elif isinstance(value, list):
            pending.extend((child, depth + 1) for child in cast(list[object], value))
        elif isinstance(value, str):
            try:
                value.encode("utf-8")
            except UnicodeError as error:
                raise invalid() from error
    return document


def _document(path: str, payload: bytes) -> dict[str, object]:
    if len(payload) > 4 * 1024 * 1024:
        raise invalid()
    try:
        source = payload.decode("utf-8")
        suffix = path.rsplit(".", 1)[-1]
        if suffix == "toml":
            return _bounded(cast(dict[str, object], tomllib.loads(source)))
        if suffix not in {"json", "jsonc"}:
            raise invalid()
        if suffix == "jsonc":
            source = _jsonc(source)
        document: object = json.loads(
            source, object_pairs_hook=_object, parse_constant=_constant, parse_float=Decimal
        )
    except (UnicodeError, ValueError, RecursionError) as error:
        raise invalid() from error
    if not isinstance(document, dict):
        raise invalid()
    return _bounded(cast(dict[str, object], document))


def identities(harness: str, files: Mapping[str, bytes]) -> dict[str, list[str]]:
    key = {
        "claude-code": "mcpServers",
        "cursor": "mcpServers",
        "antigravity": "mcpServers",
        "codex": "mcp_servers",
        "grok-build": "mcp_servers",
        "opencode": "mcp",
    }.get(harness)
    if key is None:
        raise invalid()
    result: dict[str, list[str]] = {}
    for path, payload in files.items():
        document = _document(path, payload)
        if harness == "claude-code" and (path != ".mcp.json" or set(document) != {key}):
            raise invalid()
        entries = document.get(key)
        if not isinstance(entries, dict):
            raise invalid()
        credentials(harness, {name: value for name, value in document.items() if name != key})
        result[path] = server_names(harness, cast(dict[str, object], entries))
    return result
