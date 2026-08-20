"""Opaque keyset cursor unit tests (SPEC-021 REQ-2105, ADR-0042)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai_stp_api.slices.catalog.service import relation_filter_signature
from ai_stp_platform.catalog_cursor import (
    CursorError,
    CursorKey,
    decode_cursor,
    encode_cursor,
    filter_signature,
)

pytestmark = pytest.mark.platform

_SECRET = "unit-test-cursor-secret-at-least-32b"


def test_cursor_round_trip_and_filter_binding() -> None:
    fsig = filter_signature(
        object_kind="component",
        q="pytest",
        tags=["python"],
        harness_id="claude-code",
        component_type="skill",
        include_experimental=True,
    )
    key = CursorKey(published_at=datetime(2026, 8, 5, tzinfo=UTC), stable_id="component_abc")
    token = encode_cursor(secret=_SECRET, filter_sig=fsig, key=key)
    decoded = decode_cursor(secret=_SECRET, token=token, filter_sig=fsig)
    assert decoded.stable_id == key.stable_id
    assert decoded.published_at == key.published_at


def test_tampered_cursor_is_rejected() -> None:
    fsig = filter_signature(
        object_kind="component",
        q=None,
        tags=[],
        harness_id=None,
        component_type=None,
        include_experimental=False,
    )
    token = encode_cursor(
        secret=_SECRET,
        filter_sig=fsig,
        key=CursorKey(published_at=datetime(2026, 1, 1, tzinfo=UTC), stable_id="component_x"),
    )
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(CursorError):
        decode_cursor(secret=_SECRET, token=tampered, filter_sig=fsig)


def test_foreign_filter_cursor_is_rejected() -> None:
    fsig_a = filter_signature(
        object_kind="component",
        q="a",
        tags=[],
        harness_id=None,
        component_type=None,
        include_experimental=False,
    )
    fsig_b = filter_signature(
        object_kind="component",
        q="b",
        tags=[],
        harness_id=None,
        component_type=None,
        include_experimental=False,
    )
    token = encode_cursor(
        secret=_SECRET,
        filter_sig=fsig_a,
        key=CursorKey(published_at=datetime(2026, 1, 1, tzinfo=UTC), stable_id="component_x"),
    )
    with pytest.raises(CursorError, match="filter"):
        decode_cursor(secret=_SECRET, token=token, filter_sig=fsig_b)


def test_invalid_cursor_shape_is_rejected() -> None:
    fsig = filter_signature(
        object_kind="component",
        q=None,
        tags=[],
        harness_id=None,
        component_type=None,
        include_experimental=False,
    )
    with pytest.raises(CursorError, match="shape"):
        decode_cursor(secret=_SECRET, token="not-a-cursor", filter_sig=fsig)
    with pytest.raises(CursorError, match="shape"):
        decode_cursor(secret=_SECRET, token="a" * 40, filter_sig=fsig)


def test_wrong_secret_is_rejected() -> None:
    fsig = filter_signature(
        object_kind="component",
        q=None,
        tags=[],
        harness_id=None,
        component_type=None,
        include_experimental=False,
    )
    token = encode_cursor(
        secret=_SECRET,
        filter_sig=fsig,
        key=CursorKey(published_at=datetime(2026, 1, 1, tzinfo=UTC), stable_id="component_x"),
    )
    with pytest.raises(CursorError, match="signature"):
        decode_cursor(secret="other-secret-at-least-32-bytes!!!!!", token=token, filter_sig=fsig)


def test_unsupported_version_is_rejected() -> None:
    fsig = filter_signature(
        object_kind="component",
        q=None,
        tags=[],
        harness_id=None,
        component_type=None,
        include_experimental=False,
    )
    key = CursorKey(published_at=datetime(2026, 1, 1, tzinfo=UTC), stable_id="component_x")
    # Force a foreign version into the signed body by patching encode path.
    import base64
    import hashlib
    import hmac
    import json

    from ai_stp_foundation.timestamps import format_timestamp

    body = {
        "v": 99,
        "f": fsig,
        "t": format_timestamp(key.published_at),
        "i": key.stable_id,
    }
    payload = (
        base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":"), sort_keys=True).encode())
        .decode("ascii")
        .rstrip("=")
    )
    sig = hmac.new(_SECRET.encode(), payload.encode("ascii"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")
    token = f"{payload}{sig_b64}"
    with pytest.raises(CursorError, match="version"):
        decode_cursor(secret=_SECRET, token=token, filter_sig=fsig)


def test_non_object_payload_is_rejected() -> None:
    import base64
    import hashlib
    import hmac
    import json

    fsig = filter_signature(
        object_kind="component",
        q=None,
        tags=[],
        harness_id=None,
        component_type=None,
        include_experimental=False,
    )
    payload = (
        base64.urlsafe_b64encode(json.dumps([1, 2, 3], separators=(",", ":")).encode())
        .decode("ascii")
        .rstrip("=")
    )
    sig = hmac.new(_SECRET.encode(), payload.encode("ascii"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")
    token = f"{payload}{sig_b64}"
    with pytest.raises(CursorError, match="payload"):
        decode_cursor(secret=_SECRET, token=token, filter_sig=fsig)


def test_missing_key_fields_are_rejected() -> None:
    import base64
    import hashlib
    import hmac
    import json

    fsig = filter_signature(
        object_kind="component",
        q=None,
        tags=[],
        harness_id=None,
        component_type=None,
        include_experimental=False,
    )
    body = {"v": 1, "f": fsig, "t": 123, "i": None}
    payload = (
        base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":"), sort_keys=True).encode())
        .decode("ascii")
        .rstrip("=")
    )
    sig = hmac.new(_SECRET.encode(), payload.encode("ascii"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")
    token = f"{payload}{sig_b64}"
    with pytest.raises(CursorError, match="key"):
        decode_cursor(secret=_SECRET, token=token, filter_sig=fsig)


def _search_signature(
    *,
    service_domain: str | None = None,
    country_code: str | None = None,
    service_domains: list[str] | None = None,
    country_codes: list[str] | None = None,
    updated_from: str | None = None,
    updated_to: str | None = None,
) -> str:
    packed_service, packed_country = relation_filter_signature(
        service_domain=service_domain,
        country_code=country_code,
        service_domains=service_domains or [],
        country_codes=country_codes or [],
    )
    return filter_signature(
        object_kind="component",
        q=None,
        tags=[],
        harness_id=None,
        component_type=None,
        include_experimental=True,
        service_domain=packed_service,
        country_code=packed_country,
        updated_from=updated_from,
        updated_to=updated_to,
    )


def test_filter_signature_binds_relation_lists_dates_and_legacy_singletons() -> None:
    empty = _search_signature()
    singleton_service = _search_signature(service_domain="Example.COM")
    list_service = _search_signature(service_domains=["example.com"])
    multi_service = _search_signature(service_domains=["example.com", "kaspi.kz"])
    singleton_country = _search_signature(country_code="us")
    list_country = _search_signature(country_codes=["US"])
    other_country = _search_signature(country_codes=["KZ"])
    unspecified_country = _search_signature(country_codes=["unspecified"])
    dated = _search_signature(updated_from="2026-01-01", updated_to="2026-01-31")
    from_only = _search_signature(updated_from="2026-01-01")

    assert singleton_service == list_service
    assert singleton_country == list_country
    assert multi_service != singleton_service
    assert other_country != list_country
    assert unspecified_country != list_country
    assert dated != empty
    assert dated != from_only
    assert empty == _search_signature(service_domains=[], country_codes=[])


def test_cursor_from_one_relation_or_date_filter_is_rejected_by_another() -> None:
    key = CursorKey(published_at=datetime(2026, 1, 1, tzinfo=UTC), stable_id="component_x")
    service_a = _search_signature(service_domains=["example.com"])
    service_b = _search_signature(service_domains=["kaspi.kz"])
    country_a = _search_signature(country_codes=["US"])
    country_b = _search_signature(country_codes=["unspecified"])
    dates_a = _search_signature(updated_from="2026-01-01", updated_to="2026-01-31")
    dates_b = _search_signature(updated_from="2026-02-01", updated_to="2026-02-28")

    for current, foreign in (
        (service_a, service_b),
        (country_a, country_b),
        (dates_a, dates_b),
    ):
        token = encode_cursor(secret=_SECRET, filter_sig=current, key=key)
        with pytest.raises(CursorError, match="filter"):
            decode_cursor(secret=_SECRET, token=token, filter_sig=foreign)
