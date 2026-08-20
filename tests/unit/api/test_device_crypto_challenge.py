"""Unit tests for Ed25519 verify and itsdangerous device challenges."""

from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ai_stp_api.errors import ApiError
from ai_stp_api.slices.devices.challenge import issue_challenge, message_to_sign, verify_challenge
from ai_stp_api.slices.devices.crypto import normalize_public_key, verify_ed25519

pytestmark = pytest.mark.platform

_SECRET = "unit-test-secret-key-32-bytes-min!!"


def _keypair() -> tuple[str, Ed25519PrivateKey]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes_raw()
    pk = base64.urlsafe_b64encode(public).rstrip(b"=").decode("ascii")
    return pk, private


def test_challenge_roundtrip_and_signature_verify() -> None:
    pk, private = _keypair()
    nonce, expires_in = issue_challenge(secret_key=_SECRET, public_key=pk, ttl_seconds=120)
    assert expires_in == 120
    payload = verify_challenge(secret_key=_SECRET, nonce=nonce, public_key=pk, max_age_seconds=120)
    assert payload["pk"] == pk

    signature = (
        base64.urlsafe_b64encode(private.sign(message_to_sign(nonce))).rstrip(b"=").decode("ascii")
    )
    verify_ed25519(public_key=pk, message=message_to_sign(nonce), signature=signature)


def test_challenge_rejects_expired_nonce(monkeypatch: pytest.MonkeyPatch) -> None:
    """An expired challenge must not register a device (SPEC-002 challenge TTL).

    itsdangerous raises SignatureExpired when max_age is exceeded; we map that to
    a typed validation error so callers never see a raw signer exception.
    """
    from itsdangerous import SignatureExpired

    from ai_stp_api.errors import ErrorCategory
    from ai_stp_api.slices.devices import challenge as challenge_mod

    pk, _private = _keypair()
    nonce, _ = issue_challenge(secret_key=_SECRET, public_key=pk, ttl_seconds=60)

    class ExpiredSerializer:
        def loads(self, *_args: object, **_kwargs: object) -> object:
            raise SignatureExpired("expired", payload=None, date_signed=None)

    def fake_serializer(_secret: str) -> ExpiredSerializer:
        return ExpiredSerializer()

    monkeypatch.setattr(challenge_mod, "_serializer", fake_serializer)
    with pytest.raises(ApiError) as raised:
        verify_challenge(secret_key=_SECRET, nonce=nonce, public_key=pk, max_age_seconds=60)
    assert raised.value.category is ErrorCategory.VALIDATION
    assert "expired" in raised.value.message


def test_challenge_rejects_wrong_public_key_and_tamper() -> None:
    pk, _ = _keypair()
    other, _ = _keypair()
    nonce, _ = issue_challenge(secret_key=_SECRET, public_key=pk, ttl_seconds=60)
    with pytest.raises(ApiError) as mismatch:
        verify_challenge(secret_key=_SECRET, nonce=nonce, public_key=other, max_age_seconds=60)
    assert mismatch.value.category.value == "validation"

    with pytest.raises(ApiError):
        verify_challenge(secret_key=_SECRET, nonce=nonce + "x", public_key=pk, max_age_seconds=60)


def test_ed25519_rejects_bad_signature() -> None:
    _, private = _keypair()
    other_pk, _ = _keypair()
    message = b"nonce-bytes"
    signature = base64.urlsafe_b64encode(private.sign(message)).rstrip(b"=").decode("ascii")
    with pytest.raises(ApiError):
        verify_ed25519(public_key=other_pk, message=message, signature=signature)


def test_normalize_public_key_is_stable() -> None:
    pk, _ = _keypair()
    # Re-encode with padding and standard alphabet should normalize.
    raw = base64.urlsafe_b64decode(pk + "=" * (-len(pk) % 4))
    padded = base64.b64encode(raw).decode("ascii")
    assert normalize_public_key(padded) == pk


@pytest.mark.parametrize("public_key", ["🔐", base64.urlsafe_b64encode(b"short").decode("ascii")])
def test_public_key_rejects_invalid_encoding_and_length(public_key: str) -> None:
    with pytest.raises(ApiError):
        normalize_public_key(public_key)


def test_ed25519_rejects_signature_with_wrong_length() -> None:
    public_key, _ = _keypair()
    short_signature = base64.urlsafe_b64encode(b"short").decode("ascii")

    with pytest.raises(ApiError):
        verify_ed25519(public_key=public_key, message=b"message", signature=short_signature)


def test_challenge_rejects_non_mapping_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_stp_api.slices.devices import challenge as challenge_mod

    class InvalidSerializer:
        def loads(self, *_args: object, **_kwargs: object) -> str:
            return "invalid"

    serializer = InvalidSerializer()

    def fake_serializer(_secret: str) -> InvalidSerializer:
        return serializer

    monkeypatch.setattr(challenge_mod, "_serializer", fake_serializer)

    with pytest.raises(ApiError):
        verify_challenge(
            secret_key=_SECRET,
            nonce="nonce",
            public_key="public-key",
            max_age_seconds=60,
        )
