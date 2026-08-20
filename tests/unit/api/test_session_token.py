"""Unit tests for opaque session token hashing and activity checks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ai_stp_api.session import (
    device_active_or_none,
    hash_session_token,
    mint_session_token,
    session_device_revoked,
    session_is_active,
)
from ai_stp_platform.models import AccountSession, Device

pytestmark = pytest.mark.platform


def test_mint_session_token_is_urlsafe_and_unrelated_to_hash() -> None:
    raw = mint_session_token()
    assert len(raw) >= 32
    digest = hash_session_token(raw)
    assert digest != raw
    assert len(digest) == 64
    assert digest == hash_session_token(raw)


def test_hash_session_token_never_equals_raw() -> None:
    raw = "example-token-value-not-a-real-secret"
    assert raw not in hash_session_token(raw)


def test_session_is_active_rejects_revoked_expired_and_revoked_device() -> None:
    now = datetime.now(UTC)
    live = AccountSession(
        id="a" * 64,
        account_id="account_test",
        device_id=None,
        expires_at=now + timedelta(hours=1),
        revoked_at=None,
    )
    assert session_is_active(live, now=now) is True

    revoked = AccountSession(
        id="b" * 64,
        account_id="account_test",
        device_id=None,
        expires_at=now + timedelta(hours=1),
        revoked_at=now,
    )
    assert session_is_active(revoked, now=now) is False

    expired = AccountSession(
        id="c" * 64,
        account_id="account_test",
        device_id=None,
        expires_at=now - timedelta(seconds=1),
        revoked_at=None,
    )
    assert session_is_active(expired, now=now) is False

    device = Device(
        id="device_test",
        account_id="account_test",
        public_key="pk",
        state="revoked",
    )
    bound = AccountSession(
        id="d" * 64,
        account_id="account_test",
        device_id=device.id,
        expires_at=now + timedelta(hours=1),
        revoked_at=None,
    )
    bound.device = device
    assert session_is_active(bound, now=now) is False


def test_session_is_active_accepts_naive_utc_expiry_and_active_device() -> None:
    # Breakage: naive expires_at compared without tzinfo → false inactive sessions.
    now = datetime.now(UTC)
    naive_expiry = (now + timedelta(hours=2)).replace(tzinfo=None)
    live = AccountSession(
        id="e" * 64,
        account_id="account_test",
        device_id=None,
        expires_at=naive_expiry,
        revoked_at=None,
    )
    assert session_is_active(live, now=now) is True

    device = Device(
        id="device_active",
        account_id="account_test",
        public_key="pk",
        state="active",
    )
    bound = AccountSession(
        id="f" * 64,
        account_id="account_test",
        device_id=device.id,
        expires_at=now + timedelta(hours=1),
        revoked_at=None,
    )
    bound.device = device
    assert session_is_active(bound, now=now) is True
    assert session_device_revoked(bound) is False
    assert device_active_or_none(device) is True
    assert device_active_or_none(None) is True

    device.state = "revoked"
    assert session_device_revoked(bound) is True
    assert device_active_or_none(device) is False
