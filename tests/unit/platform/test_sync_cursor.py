"""Unit tests for account-bound sync cursor codec (REQ-2504)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest

from ai_stp_api.slices.sync.cursor import (
    SyncCursorError,
    decode_sync_cursor,
    encode_sync_cursor,
    sync_page_cursor,
)
from ai_stp_foundation.ids import new_id

pytestmark = pytest.mark.platform

_SECRET = "test-secret-key-at-least-32-bytes-long!!"
_DOMAIN = b"ai-stp:sync-cursor:v1"


def _sign_payload(secret: str, payload_b64: str) -> str:
    key = hmac.new(secret.encode("utf-8"), _DOMAIN, hashlib.sha256).digest()
    sig = hmac.new(key, payload_b64.encode("ascii"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")


def _token_for_body(secret: str, body: dict[str, object]) -> str:
    payload = (
        base64.urlsafe_b64encode(
            json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        .decode("ascii")
        .rstrip("=")
    )
    return f"{payload}{_sign_payload(secret, payload)}"


def test_round_trip_binds_account_and_sequence() -> None:
    account = new_id("account")
    token = encode_sync_cursor(secret=_SECRET, account_id=account, sequence=7)
    pos = decode_sync_cursor(secret=_SECRET, token=token, account_id=account)
    assert pos.sequence == 7


def test_foreign_account_cursor_rejected() -> None:
    account = new_id("account")
    other = new_id("account")
    token = encode_sync_cursor(secret=_SECRET, account_id=account, sequence=1)
    with pytest.raises(SyncCursorError, match="account"):
        decode_sync_cursor(secret=_SECRET, token=token, account_id=other)


def test_tampered_cursor_rejected() -> None:
    account = new_id("account")
    token = encode_sync_cursor(secret=_SECRET, account_id=account, sequence=2)
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(SyncCursorError):
        decode_sync_cursor(secret=_SECRET, token=tampered, account_id=account)


def test_wrong_secret_rejected() -> None:
    account = new_id("account")
    token = encode_sync_cursor(secret=_SECRET, account_id=account, sequence=3)
    with pytest.raises(SyncCursorError):
        decode_sync_cursor(
            secret="other-secret-key-at-least-32-bytes-xx!!",
            token=token,
            account_id=account,
        )


def test_encode_rejects_negative_sequence() -> None:
    # Breakage: negative sequences accepted and decoded as valid positions.
    with pytest.raises(SyncCursorError, match="sequence"):
        encode_sync_cursor(secret=_SECRET, account_id=new_id("account"), sequence=-1)


def test_decode_rejects_short_or_non_wire_token() -> None:
    account = new_id("account")
    with pytest.raises(SyncCursorError, match="shape"):
        decode_sync_cursor(secret=_SECRET, token="short", account_id=account)
    with pytest.raises(SyncCursorError, match="shape"):
        decode_sync_cursor(secret=_SECRET, token="*" * 50, account_id=account)


def test_decode_rejects_unsupported_version_and_non_object_payload() -> None:
    account = new_id("account")
    wrong_version = _token_for_body(_SECRET, {"v": 99, "a": account, "s": 1})
    with pytest.raises(SyncCursorError, match="version"):
        decode_sync_cursor(secret=_SECRET, token=wrong_version, account_id=account)

    # Sign a JSON array payload so signature verifies but body type fails closed.
    payload = base64.urlsafe_b64encode(b"[1,2,3]").decode("ascii").rstrip("=")
    array_token = f"{payload}{_sign_payload(_SECRET, payload)}"
    with pytest.raises(SyncCursorError, match="payload"):
        decode_sync_cursor(secret=_SECRET, token=array_token, account_id=account)


def test_decode_rejects_invalid_sequence_types() -> None:
    account = new_id("account")
    for bad_sequence in (True, -3, "1", 1.5, None):
        token = _token_for_body(_SECRET, {"v": 1, "a": account, "s": cast_sequence(bad_sequence)})
        with pytest.raises(SyncCursorError, match="sequence"):
            decode_sync_cursor(secret=_SECRET, token=token, account_id=account)


def cast_sequence(value: object) -> object:
    """Identity helper so typed test data stays explicit without magic casts."""
    return value


def test_sync_page_cursor_encodes_last_delivered_even_without_more_rows() -> None:
    account = new_id("account")
    token = sync_page_cursor(
        last_delivered_sequence=4,
        incoming_cursor=None,
        secret=_SECRET,
        account_id=account,
    )
    assert token is not None
    assert decode_sync_cursor(secret=_SECRET, token=token, account_id=account).sequence == 4


def test_sync_page_cursor_empty_page_echoes_incoming_and_does_not_rewind() -> None:
    account = new_id("account")
    incoming = encode_sync_cursor(secret=_SECRET, account_id=account, sequence=4)
    echoed = sync_page_cursor(
        last_delivered_sequence=None,
        incoming_cursor=incoming,
        secret=_SECRET,
        account_id=account,
    )
    assert echoed == incoming
    assert (
        sync_page_cursor(
            last_delivered_sequence=None,
            incoming_cursor=None,
            secret=_SECRET,
            account_id=account,
        )
        is None
    )


def test_decode_rejects_non_json_payload_bytes() -> None:
    account = new_id("account")
    payload = base64.urlsafe_b64encode(b"not-json").decode("ascii").rstrip("=")
    token = f"{payload}{_sign_payload(_SECRET, payload)}"
    with pytest.raises(SyncCursorError, match="payload"):
        decode_sync_cursor(secret=_SECRET, token=token, account_id=account)
