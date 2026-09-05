"""HMAC-signed opaque keyset cursors for the public catalog (ADR-0042)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from ai_stp_contracts.catalog import merged_or_values, normalize_search_text, unique_sorted
from ai_stp_contracts.http import CURSOR_PATTERN
from ai_stp_foundation.timestamps import format_timestamp

_CURSOR_VERSION = 2
_CURSOR_RE = __import__("re").compile(CURSOR_PATTERN)


class CursorError(ValueError):
    """Cursor is malformed, tampered, or bound to a different filter."""


@dataclass(frozen=True)
class CursorKey:
    """Exclusive keyset position: selected sort keys then stable_id."""

    published_at: datetime
    stable_id: str
    likes_count: int = 0
    relevance: int = 0


def filter_signature(
    *,
    object_kind: str,
    q: str | None,
    tags: list[str],
    harness_id: str | None,
    component_type: str | None,
    include_experimental: bool,
    include_deprecated: bool = False,
    harness_ids: list[str] | None = None,
    component_types: list[str] | None = None,
    authors: list[str] | None = None,
    verified_only: bool = False,
    sort: str = "relevance",
    sort_direction: str = "desc",
    support_tier: str | None = None,
    support_state: str | None = None,
    service_domain: str | None = None,
    country_code: str | None = None,
    updated_from: str | None = None,
    updated_to: str | None = None,
) -> str:
    """Hash the active filter so a cursor cannot migrate across queries."""
    payload = {
        "kind": object_kind,
        "q": normalize_search_text(q),
        "tags": unique_sorted(tags),
        # In the signature because it changes the result set: a cursor issued
        # while superseded versions were hidden must not be replayed against a
        # listing that offers them, or the walk skips and duplicates.
        "include_deprecated": include_deprecated,
        "harness_ids": merged_or_values(harness_id, harness_ids),
        "component_types": merged_or_values(component_type, component_types),
        "authors": unique_sorted(authors or []),
        "verified_only": verified_only,
        "support_tier": support_tier,
        "support_state": support_state,
        "service_domain": service_domain,
        "country_code": country_code,
        "include_experimental": include_experimental,
        "sort": sort,
        "sort_direction": sort_direction,
    }
    # Omit empty bounds so existing cursors stay valid when no date filter is set.
    if updated_from:
        payload["updated_from"] = updated_from
    if updated_to:
        payload["updated_to"] = updated_to
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def encode_cursor(*, secret: str, filter_sig: str, key: CursorKey) -> str:
    """Build a compact HMAC-signed cursor matching CURSOR_PATTERN."""
    body: dict[str, Any] = {
        "v": _CURSOR_VERSION,
        "f": filter_sig,
        "t": format_timestamp(key.published_at),
        "i": key.stable_id,
        "l": int(key.likes_count),
        "r": int(key.relevance),
    }
    # Wire pattern forbids `.`; pack as payload||sig with a fixed-length
    # trailing HMAC (urlsafe base64 of 32 bytes is always 43 chars unpadded).
    payload = (
        base64.urlsafe_b64encode(
            json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        .decode("ascii")
        .rstrip("=")
    )
    sig = hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")
    if len(sig_b64) != 43:
        raise CursorError("cursor signature encoding failed")
    token = f"{payload}{sig_b64}"
    if len(token) > 512 or _CURSOR_RE.fullmatch(token) is None:
        raise CursorError("encoded cursor exceeds wire bounds")
    return token


def decode_cursor(*, secret: str, token: str, filter_sig: str) -> CursorKey:
    """Validate signature and filter binding; return the exclusive last key."""
    if _CURSOR_RE.fullmatch(token) is None or len(token) <= 43:
        raise CursorError("cursor shape is invalid")
    payload_b64, sig_b64 = token[:-43], token[-43:]
    expected = hmac.new(
        secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
    ).digest()
    try:
        given = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
    except Exception as exc:
        raise CursorError("cursor signature is invalid") from exc
    if not hmac.compare_digest(expected, given):
        raise CursorError("cursor signature is invalid")
    try:
        raw = base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4))
        parsed: object = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise CursorError("cursor payload is invalid") from exc
    if not isinstance(parsed, dict):
        raise CursorError("cursor payload is invalid")
    body = cast(dict[str, object], parsed)
    if body.get("f") != filter_sig:
        raise CursorError("cursor filter signature mismatch")
    published_raw = body.get("t")
    stable_id = body.get("i")
    if not isinstance(published_raw, str) or not isinstance(stable_id, str):
        raise CursorError("cursor key is invalid")
    if body.get("v") != _CURSOR_VERSION:
        raise CursorError("cursor version is unsupported")
    likes_raw = body.get("l", 0)
    relevance_raw = body.get("r", 0)
    if not isinstance(likes_raw, int) or not isinstance(relevance_raw, int):
        raise CursorError("cursor key is invalid")
    from ai_stp_foundation.timestamps import parse_timestamp

    return CursorKey(
        published_at=parse_timestamp(published_raw),
        stable_id=stable_id,
        likes_count=likes_raw,
        relevance=relevance_raw,
    )
