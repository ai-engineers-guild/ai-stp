"""Audit payload redaction never retains tokens/sessions/nonces."""

from __future__ import annotations

from ai_stp_api.audit import redact_payload

pytestmark = __import__("pytest").mark.platform


def test_redact_payload_strips_sensitive_keys_recursively() -> None:
    payload = {
        "provider": "google",
        "session_token": "SHOULD_NOT_APPEAR",
        "nested": {
            "nonce": "challenge-value",
            "account_id": "account_x",
            "access_token": "provider-token",
        },
        "reason": "admin read",
    }
    cleaned = redact_payload(payload)
    text = repr(cleaned)
    assert "SHOULD_NOT_APPEAR" not in text
    assert "challenge-value" not in text
    assert "provider-token" not in text
    assert cleaned["provider"] == "google"
    assert cleaned["nested"]["account_id"] == "account_x"  # type: ignore[index]
    assert "session_token" not in cleaned
    assert "nonce" not in cleaned["nested"]  # type: ignore[operator]
