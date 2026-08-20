"""Stateless device registration challenge (itsdangerous, ADR-0041)."""

from __future__ import annotations

import secrets
from typing import cast

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ai_stp_api.errors import ApiError, ErrorCategory

_SALT = "ai-stp-device-challenge-v1"


def _serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key, salt=_SALT)


def issue_challenge(
    *,
    secret_key: str,
    public_key: str,
    ttl_seconds: int,
) -> tuple[str, int]:
    """Return ``(signed_nonce, expires_in)`` bound to the candidate public key."""
    payload: dict[str, str] = {
        "pk": public_key,
        "n": secrets.token_urlsafe(16),
    }
    token = _serializer(secret_key).dumps(payload)
    return str(token), ttl_seconds


def verify_challenge(
    *,
    secret_key: str,
    nonce: str,
    public_key: str,
    max_age_seconds: int,
) -> dict[str, object]:
    """Validate signer freshness and public-key binding.

    Raises typed validation errors on expiry, tamper or key mismatch. Never
    returns or logs the raw secret.
    """
    try:
        # itsdangerous.loads is typed as Any; narrow at this boundary.
        raw: object = _serializer(secret_key).loads(nonce, max_age=max_age_seconds)
    except SignatureExpired as exc:
        raise ApiError(ErrorCategory.VALIDATION, "challenge expired") from exc
    except BadSignature as exc:
        raise ApiError(ErrorCategory.VALIDATION, "challenge invalid") from exc

    if not isinstance(raw, dict):
        raise ApiError(ErrorCategory.VALIDATION, "challenge invalid")
    payload = cast(dict[str, object], raw)
    if payload.get("pk") != public_key:
        raise ApiError(ErrorCategory.VALIDATION, "challenge public key mismatch")
    return payload


def message_to_sign(nonce: str) -> bytes:
    """Canonical bytes the device private key must sign."""
    return nonce.encode("utf-8")
