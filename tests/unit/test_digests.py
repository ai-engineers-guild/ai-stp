"""Domain-separated digests: separation, closed domains, canonical form."""

import pytest

from ai_stp_foundation import DIGEST_DOMAINS, DigestError, digest_bytes, digest_canonical, is_digest


def test_same_payload_differs_across_every_domain_pair() -> None:
    payload = b"identical bytes"
    digests = {digest_bytes(domain, payload) for domain in DIGEST_DOMAINS}
    assert len(digests) == len(DIGEST_DOMAINS)


def test_unknown_domain_fails_closed() -> None:
    with pytest.raises(DigestError):
        digest_bytes("ai-stp:manifest:v1", b"")


def test_digest_form_is_canonical() -> None:
    value = digest_canonical("ai-stp:passport:v1", {"a": 1})
    assert is_digest(value)
    assert not is_digest(value.upper())
    assert not is_digest("sha256:short")


def test_canonical_digest_ignores_key_order() -> None:
    left = digest_canonical("ai-stp:passport:v1", {"a": 1, "b": 2})
    right = digest_canonical("ai-stp:passport:v1", {"b": 2, "a": 1})
    assert left == right
