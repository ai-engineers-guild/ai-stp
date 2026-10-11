"""Byte-derived local skill identities, matching the pinned native Codex reader.

Only newly frozen Codex skills use this boundary. Other harness loaders and
immutable retained definitions are not inferred from a component's display name.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator, Mapping
from typing import cast

import yaml
from yaml.events import (
    AliasEvent,
    CollectionEndEvent,
    CollectionStartEvent,
    DocumentStartEvent,
    Event,
)
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from ai_stp_sources.errors import INVALID_SOURCE, SourceError

_SPACE = re.compile(
    r"[\u0009-\u000d\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+"
)
_TAGS = frozenset(
    f"tag:yaml.org,2002:{kind}" for kind in ("str", "bool", "int", "float", "null", "seq", "map")
)
_PLUGIN_DIRECTORIES = (".codex-plugin", ".claude-plugin", ".cursor-plugin")
_IMPLICIT_SCALAR = "ai-stp:yaml:implicit-scalar"


class _LexicalLoader(yaml.BaseLoader):
    """Keep scalar spelling while distinguishing optional null from !!str."""


_LexicalLoader.add_implicit_resolver(  # pyright: ignore[reportUnknownMemberType]
    "tag:yaml.org,2002:null", re.compile(r"\A(?:|~|null|Null|NULL)\Z"), ["", "~", "n", "N"]
)
_LexicalLoader.add_implicit_resolver(  # pyright: ignore[reportUnknownMemberType]
    _IMPLICIT_SCALAR, re.compile(r"\A.*\Z", re.DOTALL), None
)


def _invalid() -> SourceError:
    return SourceError(
        INVALID_SOURCE, "embedded Codex skill has invalid or ambiguous native identifiers"
    )


def _header(payload: bytes) -> MappingNode:
    try:
        # Split only LF: other Unicode separators are content, not delimiters.
        lines = payload.decode("utf-8").split("\n")
        if not lines or lines[0].removesuffix("\r") != "---":
            raise _invalid()
        end = next(
            (i for i, line in enumerate(lines[1:], 1) if line.removesuffix("\r") == "---"), None
        )
        if end is None:
            raise _invalid()
        header = "\n".join(lines[1:end]) + ("\n" if end > 1 else "")
        if len(header.encode("utf-8")) > 64 * 1024:
            raise _invalid()
        depth = aliases = documents = 0
        events = cast(
            Iterator[Event],
            yaml.parse(header, Loader=yaml.BaseLoader),  # pyright: ignore[reportUnknownMemberType]
        )
        for count, event in enumerate(events, 1):
            depth += isinstance(event, CollectionStartEvent)
            depth -= isinstance(event, CollectionEndEvent)
            aliases += isinstance(event, AliasEvent)
            if isinstance(event, DocumentStartEvent):
                documents += 1
                if event.version is not None or event.tags:
                    raise _invalid()
            tag = getattr(event, "tag", None)
            if (
                count > 10_000
                or depth > 8
                or aliases > 100
                or documents > 1
                or (tag and tag not in _TAGS)
            ):
                raise _invalid()
        # BaseLoader retains lexical scalars instead of YAML 1.1 coercion or
        # merge expansion. Codex deserializes its string fields from those bytes.
        node = cast(
            Node | None,
            yaml.compose(header, Loader=_LexicalLoader),  # pyright: ignore[reportUnknownMemberType]
        )
    except (UnicodeError, yaml.YAMLError, RecursionError) as error:
        raise _invalid() from error
    if not isinstance(node, MappingNode):
        raise _invalid()
    _check_nodes(node, set(), [0])
    return node


def _check_nodes(node: Node, parents: set[int], count: list[int]) -> None:
    count[0] += 1
    if id(node) in parents or len(parents) > 8 or count[0] > 10_000:
        raise _invalid()
    if isinstance(node, ScalarNode):
        if (
            node.tag in {_IMPLICIT_SCALAR, "tag:yaml.org,2002:bool", "tag:yaml.org,2002:null"}
            and node.value.lower() in {"true", "false", "null"}
            and node.value
            not in {"true", "True", "TRUE", "false", "False", "FALSE", "null", "Null", "NULL"}
        ):
            raise _invalid()
        return
    parents.add(id(node))
    if isinstance(node, MappingNode):
        names: set[str] = set()
        for key, value in node.value:
            if not isinstance(key, ScalarNode) or key.value in names:
                raise _invalid()
            names.add(key.value)
            _check_nodes(key, parents, count)
            _check_nodes(value, parents, count)
    elif isinstance(node, SequenceNode):
        for value in node.value:
            _check_nodes(value, parents, count)
    else:
        raise _invalid()
    parents.remove(id(node))


def _fields(node: MappingNode) -> dict[str, Node]:
    return {key.value: value for key, value in node.value}


def _string(node: Node | None) -> str | None:
    if node is None:
        return None
    if not isinstance(node, ScalarNode):
        raise _invalid()
    if node.tag == "tag:yaml.org,2002:null":
        return None
    return node.value


def skill_identities(files: Mapping[str, bytes]) -> dict[str, list[str]]:
    """Return IDs on visible SKILL.md members, rejecting collisions and plugins."""
    captured: dict[str, tuple[str, bytes]] = {}
    for path, payload in files.items():
        local = (
            path.removeprefix(".codex/")
            if path.startswith(".codex/")
            else path.removeprefix(".agents/")
        )
        if not local.startswith("skills/") or local in captured:
            raise _invalid()
        captured[local] = (path, payload)
    result: dict[str, list[str]] = {path: [] for path in files}
    names: set[str] = set()
    for local, (path, payload) in captured.items():
        parts = local.removeprefix("skills/").split("/")
        if parts[-1] != "SKILL.md" or len(parts) > 7 or any(part.startswith(".") for part in parts):
            continue
        ancestor = local.rsplit("/", 1)[0]
        while True:
            prefix = ancestor + "/" if ancestor else ""
            if any(
                prefix + directory + "/plugin.json" in captured for directory in _PLUGIN_DIRECTORIES
            ):
                raise _invalid()
            if not ancestor:
                break
            ancestor = ancestor.rsplit("/", 1)[0] if "/" in ancestor else ""
        fields = _fields(_header(payload))
        metadata = fields.get("metadata")
        if metadata is not None:
            if not isinstance(metadata, MappingNode):
                raise _invalid()
            _string(_fields(metadata).get("short-description"))
        description = _string(fields.get("description"))
        if description is None or not _SPACE.sub(" ", description).strip(" "):
            raise _invalid()
        declared = _string(fields.get("name"))
        name = _SPACE.sub(" ", declared or "").strip(" ") or _SPACE.sub(
            " ", parts[-2] if len(parts) > 1 else "skills"
        ).strip(" ")
        if (
            not name
            or len(name) > 64
            or unicodedata.normalize("NFC", name) != name
            or any(unicodedata.category(char) == "Cc" for char in name)
            or name in names
        ):
            raise _invalid()
        names.add(name)
        result[path] = [name]
    if not names:
        raise _invalid()
    return result
