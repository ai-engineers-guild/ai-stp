"""Canonical JSON bytes (SPEC-015 REQ-1503/REQ-1504).

Structured contracts serialize as UTF-8 JSON per RFC 8785 after NFC
normalization of every string. Byte-order marks inside strings, non-finite
numbers and key collisions introduced by normalization are rejected before
hashing; nothing is silently repaired.

Untrusted incoming bytes enter through :func:`from_json_bytes`, which applies
the byte-level REQ-1504 rejections — BOM prefix, invalid UTF-8, duplicate
object keys before any normalization, non-finite literals — so full input
validation is ``canonize(from_json_bytes(data))``.
"""

import json
import math
import unicodedata
from typing import cast

import rfc8785

type JsonValue = bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"] | None

_BOM: str = "\ufeff"


class CanonicalizationError(ValueError):
    """A value cannot be represented as canonical JSON bytes."""


def _normalized_string(value: str) -> str:
    if _BOM in value:
        raise CanonicalizationError("byte-order mark inside a string is rejected")
    return unicodedata.normalize("NFC", value)


def _normalized(value: JsonValue) -> JsonValue:
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalizationError(f"non-finite number is rejected: {value!r}")
        return value
    if isinstance(value, str):
        return _normalized_string(value)
    if isinstance(value, list):
        return [_normalized(item) for item in value]
    # The runtime check is deliberate: static typing says dict is the only
    # remaining JsonValue, but callers can pass arbitrary runtime objects.
    if isinstance(value, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
        normalized: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):  # pyright: ignore[reportUnnecessaryIsInstance]
                raise CanonicalizationError(f"object key is not a string: {key!r}")
            normalized_key = _normalized_string(key)
            if normalized_key in normalized:
                raise CanonicalizationError(
                    f"object keys collide after NFC normalization: {normalized_key!r}"
                )
            normalized[normalized_key] = _normalized(item)
        return normalized
    raise CanonicalizationError(  # pyright: ignore[reportUnreachable]
        f"unsupported runtime type for canonical JSON: {type(value).__name__}"
    )


def canonize(value: JsonValue) -> bytes:
    """Return the canonical RFC 8785 bytes of an NFC-normalized value."""
    normalized = _normalized(value)
    try:
        return rfc8785.dumps(normalized)
    except rfc8785.CanonicalizationError as error:
        raise CanonicalizationError(str(error)) from error


def _rejecting_pairs(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    obj: dict[str, JsonValue] = {}
    for key, item in pairs:
        if key in obj:
            raise CanonicalizationError(f"duplicate object key in payload: {key!r}")
        obj[key] = item
    return obj


def _rejecting_constant(name: str) -> JsonValue:
    raise CanonicalizationError(f"non-finite JSON literal is rejected: {name}")


def from_json_bytes(data: bytes) -> JsonValue:
    """Parse untrusted JSON bytes with the byte-level REQ-1504 rejections.

    A UTF-8 BOM prefix, invalid UTF-8, duplicate object keys before any
    normalization and the non-standard ``NaN``/``Infinity`` literals fail
    closed. The result feeds :func:`canonize` for the value-level rules.
    """
    if data.startswith(b"\xef\xbb\xbf"):
        raise CanonicalizationError("byte-order mark prefix is rejected")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CanonicalizationError(f"payload is not valid UTF-8: {error.reason}") from error
    try:
        parsed = json.loads(
            text, object_pairs_hook=_rejecting_pairs, parse_constant=_rejecting_constant
        )
    except json.JSONDecodeError as error:
        raise CanonicalizationError(f"payload is not valid JSON: {error.msg}") from error
    return cast(JsonValue, parsed)
