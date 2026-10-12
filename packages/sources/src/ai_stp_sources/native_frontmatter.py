"""Bounded data-only Markdown headers shared by embedded native readers."""

from __future__ import annotations

import math
import re
from collections.abc import Iterator
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

from ai_stp_foundation.canonical import JsonValue
from ai_stp_sources.errors import INVALID_SOURCE, SourceError

_TAGS = frozenset(
    f"tag:yaml.org,2002:{kind}" for kind in ("str", "bool", "int", "float", "null", "seq", "map")
)
_IMPLICIT_SCALAR = "ai-stp:yaml:implicit-scalar"
SPACE = (
    "\t\n\v\f\r \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004"
    "\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"
)


class _LexicalLoader(yaml.BaseLoader):
    """Keep scalar spelling while distinguishing optional null from !!str."""


_LexicalLoader.add_implicit_resolver(  # pyright: ignore[reportUnknownMemberType]
    "tag:yaml.org,2002:null", re.compile(r"\A(?:|~|null|Null|NULL)\Z"), ["", "~", "n", "N"]
)
_LexicalLoader.add_implicit_resolver(  # pyright: ignore[reportUnknownMemberType]
    _IMPLICIT_SCALAR, re.compile(r"\A.*\Z", re.DOTALL), None
)


def invalid() -> SourceError:
    return SourceError(
        INVALID_SOURCE, "embedded source has invalid or ambiguous native identifiers"
    )


def header(payload: bytes, *, empty: bool = False) -> MappingNode:
    try:
        # Split only LF: other Unicode separators are content, not delimiters.
        lines = payload.decode("utf-8").split("\n")
        if not lines or lines[0].removesuffix("\r") != "---":
            raise invalid()
        end = next(
            (i for i, line in enumerate(lines[1:], 1) if line.removesuffix("\r") == "---"), None
        )
        if end is None:
            raise invalid()
        header = "\n".join(lines[1:end]) + ("\n" if end > 1 else "")
        if len(header.encode("utf-8")) > 64 * 1024:
            raise invalid()
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
                    raise invalid()
            tag = getattr(event, "tag", None)
            if (
                count > 10_000
                or depth > 8
                or aliases > 100
                or documents > 1
                or (tag and tag not in _TAGS)
            ):
                raise invalid()
        # BaseLoader retains lexical scalars instead of YAML 1.1 coercion or
        # merge expansion. Codex deserializes its string fields from those bytes.
        node = cast(
            Node | None,
            yaml.compose(header, Loader=_LexicalLoader),  # pyright: ignore[reportUnknownMemberType]
        )
    except (UnicodeError, yaml.YAMLError, RecursionError) as error:
        raise invalid() from error
    if empty and (
        node is None or (isinstance(node, ScalarNode) and node.tag == "tag:yaml.org,2002:null")
    ):
        return MappingNode("tag:yaml.org,2002:map", [])
    if not isinstance(node, MappingNode):
        raise invalid()
    _check_nodes(node, set(), [0])
    return node


def _check_nodes(node: Node, parents: set[int], count: list[int]) -> None:
    count[0] += 1
    if id(node) in parents or len(parents) > 8 or count[0] > 10_000:
        raise invalid()
    if isinstance(node, ScalarNode):
        if (
            node.tag in {_IMPLICIT_SCALAR, "tag:yaml.org,2002:bool", "tag:yaml.org,2002:null"}
            and node.value.lower() in {"true", "false", "null"}
            and node.value
            not in {"true", "True", "TRUE", "false", "False", "FALSE", "null", "Null", "NULL"}
        ):
            raise invalid()
        return
    parents.add(id(node))
    if isinstance(node, MappingNode):
        names: set[str] = set()
        for key, value in node.value:
            if not isinstance(key, ScalarNode) or key.value in names:
                raise invalid()
            names.add(key.value)
            _check_nodes(key, parents, count)
            _check_nodes(value, parents, count)
    elif isinstance(node, SequenceNode):
        for value in node.value:
            _check_nodes(value, parents, count)
    else:
        raise invalid()
    parents.remove(id(node))


def fields(node: MappingNode) -> dict[str, Node]:
    return {key.value: value for key, value in node.value}


def lexical_string(node: Node | None) -> str | None:
    if node is None:
        return None
    if not isinstance(node, ScalarNode):
        raise invalid()
    if node.tag == "tag:yaml.org,2002:null":
        return None
    return node.value


_LEGACY = re.compile(
    r"\A(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|"
    r"[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}(?:[Tt]|[ \t]+)[0-9]{1,2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]*)?(?:[ \t]*(?:Z|[-+][0-9]{1,2}(?::[0-9]{2})?))?|"
    r"[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+|"
    r"[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.(?:[0-9_]*[0-9])?)\Z"
)
_INTEGER = re.compile(r"\A[-+]?(?:[0-9][0-9_]*|0[xX][0-9a-fA-F_]+|0[oO][0-7_]+|0[bB][01_]+)\Z")
_FLOAT = re.compile(
    r"\A[-+]?(?:(?:[0-9][0-9_]*)?\.[0-9_]+(?:[eE][-+]?[0-9]+)?|"
    r"[0-9][0-9_]*\.(?:[eE][-+]?[0-9]+)?|[0-9][0-9_]*[eE][-+]?[0-9]+|"
    r"\.(?:inf|Inf|INF|nan|NaN|NAN))\Z"
)


def _scalar(node: ScalarNode, *, legacy: bool) -> JsonValue:
    text = node.value
    tag = node.tag.removeprefix("tag:yaml.org,2002:")
    if tag == "str":
        return text
    if tag == "null":
        return None
    implicit = tag == _IMPLICIT_SCALAR
    if legacy and implicit and _LEGACY.fullmatch(text):
        raise invalid()
    if tag == "bool" or (implicit and text in {"true", "True", "TRUE", "false", "False", "FALSE"}):
        if text not in {"true", "True", "TRUE", "false", "False", "FALSE"}:
            raise invalid()
        return text.lower() == "true"
    try:
        if tag == "int" or (implicit and _INTEGER.fullmatch(text)):
            digits = text.lstrip("-+").replace("_", "")
            base = 0 if digits[:2].lower() in {"0x", "0o", "0b"} else 10
            if (
                legacy
                and len(digits) > 1
                and digits.startswith("0")
                and set(digits) <= set("01234567")
            ):
                base = 8
            number = int(text.replace("_", ""), base)
            if not -(2**63) <= number < 2**64:
                raise invalid()
            return number
        if tag == "float" or (implicit and _FLOAT.fullmatch(text)):
            number = float(text.replace("_", ""))
            if not math.isfinite(number):
                raise invalid()
            return number
    except ValueError as error:
        raise invalid() from error
    if not implicit:
        raise invalid()
    return text


def _value(node: Node, *, merged: bool, legacy: bool) -> JsonValue:
    if isinstance(node, ScalarNode):
        return _scalar(node, legacy=legacy)
    if isinstance(node, SequenceNode):
        return [_value(value, merged=merged, legacy=legacy) for value in node.value]
    if isinstance(node, MappingNode):
        return {
            key: _value(value, merged=merged, legacy=legacy)
            for key, value in _merged_fields(node, merged=merged).items()
        }
    raise invalid()


def _merged_fields(node: MappingNode, *, merged: bool) -> dict[str, Node]:
    result = fields(node)
    if not merged or "<<" not in result:
        return result
    merge = result.pop("<<")
    values = merge.value if isinstance(merge, SequenceNode) else [merge]
    inherited: dict[str, Node] = {}
    for value in reversed(values):
        if not isinstance(value, MappingNode):
            raise invalid()
        inherited.update(_merged_fields(value, merged=True))
    return inherited | result


def parse(
    payload: bytes,
    *,
    optional: bool = False,
    merged: bool = True,
    legacy: bool = False,
    empty: bool = False,
    lexical_fields: tuple[str, ...] = (),
) -> dict[str, JsonValue]:
    """Read a native dialect without YAML 1.1 booleans or executable tags."""
    if optional:
        try:
            text = payload.decode("utf-8")
        except UnicodeError as error:
            raise invalid() from error
        if text.split("\n", 1)[0].removesuffix("\r") != "---":
            if text.lstrip(SPACE + "\ufeff").startswith("---"):
                raise invalid()
            return {}
    node = header(payload, empty=empty)
    # Validate all values, including ignored metadata, before selecting lexical
    # fields. Typed native String deserialization preserves scalar spelling.
    _value(node, merged=False, legacy=legacy)
    result = cast(dict[str, JsonValue], _value(node, merged=merged, legacy=legacy))
    for key, value in _merged_fields(node, merged=merged).items():
        if key in lexical_fields:
            result[key] = lexical_string(value)
    return result
