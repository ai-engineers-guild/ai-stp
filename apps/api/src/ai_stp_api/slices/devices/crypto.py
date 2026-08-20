"""Ed25519 public-key verification for device registration."""

from __future__ import annotations

import base64
import binascii

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ai_stp_api.errors import ApiError, ErrorCategory


def _b64decode(value: str) -> bytes:
    """Decode standard or urlsafe base64, with optional padding."""
    cleaned = value.strip().replace("-", "+").replace("_", "/")
    pad = "=" * (-len(cleaned) % 4)
    try:
        return base64.b64decode(cleaned + pad, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ApiError(ErrorCategory.VALIDATION, "invalid public key encoding") from exc


def parse_public_key(public_key: str) -> bytes:
    """Parse a 32-byte Ed25519 public key from base64 text."""
    raw = _b64decode(public_key)
    if len(raw) != 32:
        raise ApiError(ErrorCategory.VALIDATION, "public key must be 32 bytes")
    return raw


def normalize_public_key(public_key: str) -> str:
    """Return a canonical urlsafe base64 form without padding."""
    raw = parse_public_key(public_key)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def verify_ed25519(*, public_key: str, message: bytes, signature: str) -> None:
    """Verify an Ed25519 signature; raise on any failure without leaking key material."""
    pk_bytes = parse_public_key(public_key)
    sig_bytes = _b64decode(signature)
    if len(sig_bytes) != 64:
        raise ApiError(ErrorCategory.VALIDATION, "invalid device signature")
    try:
        Ed25519PublicKey.from_public_bytes(pk_bytes).verify(sig_bytes, message)
    except (InvalidSignature, ValueError) as exc:
        raise ApiError(ErrorCategory.VALIDATION, "invalid device signature") from exc
