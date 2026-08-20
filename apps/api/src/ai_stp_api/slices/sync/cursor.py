"""Account-bound HMAC keyset cursor for the sync outbox (ADR-0045).

Uses the existing auth secret with a dedicated cryptographic domain so a
catalog cursor cannot be replayed as a sync cursor and no extra env secret
is required. The token never logs its interior.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from typing import Any, cast

from ai_stp_contracts.http import CURSOR_PATTERN

_CURSOR_VERSION = 1
_DOMAIN = b"ai-stp:sync-cursor:v1"
_CURSOR_RE = re.compile(CURSOR_PATTERN)


class SyncCursorError(ValueError):
    """Cursor is malformed, tampered, or bound to a different account."""


@dataclass(frozen=True)
class SyncCursorPosition:
    """Exclusive keyset position in the account outbox."""

    sequence: int


def _signing_key(secret: str) -> bytes:
    """Derive a domain-separated HMAC key from the server secret."""
    return hmac.new(secret.encode("utf-8"), _DOMAIN, hashlib.sha256).digest()


def sync_page_cursor(
    *,
    last_delivered_sequence: int | None,
    incoming_cursor: str | None,
    secret: str,
    account_id: str,
) -> str | None:
    """Return the resume token for one pull page (ADR-0091, SPEC-025 REQ-2504).

    A non-empty page always points at the last delivered sequence. An empty
    page echoes the incoming cursor so a client that already consumed events
    is not sent back to sequence zero.
    """
    if last_delivered_sequence is not None:
        return encode_sync_cursor(
            secret=secret,
            account_id=account_id,
            sequence=last_delivered_sequence,
        )
    return incoming_cursor


def encode_sync_cursor(*, secret: str, account_id: str, sequence: int) -> str:
    """Build a compact HMAC-signed account-bound cursor."""
    if sequence < 0:
        raise SyncCursorError("cursor sequence is invalid")
    body: dict[str, Any] = {
        "v": _CURSOR_VERSION,
        "a": account_id,
        "s": sequence,
    }
    payload = (
        base64.urlsafe_b64encode(
            json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        .decode("ascii")
        .rstrip("=")
    )
    sig = hmac.new(_signing_key(secret), payload.encode("ascii"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")
    if len(sig_b64) != 43:
        raise SyncCursorError("cursor signature encoding failed")
    token = f"{payload}{sig_b64}"
    if len(token) > 512 or _CURSOR_RE.fullmatch(token) is None:
        raise SyncCursorError("encoded cursor exceeds wire bounds")
    return token


def decode_sync_cursor(*, secret: str, token: str, account_id: str) -> SyncCursorPosition:
    """Validate signature and account binding; return the exclusive last sequence."""
    if _CURSOR_RE.fullmatch(token) is None or len(token) <= 43:
        raise SyncCursorError("cursor shape is invalid")
    payload_b64, sig_b64 = token[:-43], token[-43:]
    expected = hmac.new(_signing_key(secret), payload_b64.encode("ascii"), hashlib.sha256).digest()
    try:
        given = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
    except Exception as exc:
        raise SyncCursorError("cursor signature is invalid") from exc
    if not hmac.compare_digest(expected, given):
        raise SyncCursorError("cursor signature is invalid")
    try:
        raw = base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4))
        parsed: object = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise SyncCursorError("cursor payload is invalid") from exc
    if not isinstance(parsed, dict):
        raise SyncCursorError("cursor payload is invalid")
    body = cast(dict[str, object], parsed)
    if body.get("v") != _CURSOR_VERSION:
        raise SyncCursorError("cursor version is unsupported")
    if body.get("a") != account_id:
        raise SyncCursorError("cursor account binding mismatch")
    sequence = body.get("s")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise SyncCursorError("cursor sequence is invalid")
    return SyncCursorPosition(sequence=sequence)
