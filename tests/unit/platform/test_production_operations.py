"""Pure guards for optional telemetry and bounded abuse protection (#187)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ai_stp_api.correlation import CorrelationMiddleware
from ai_stp_api.errors import CATEGORY_CODE, CATEGORY_STATUS, ErrorCategory
from ai_stp_api.rate_limit import (
    HttpRateGate,
    RateLimitMiddleware,
    SlidingWindowLimiter,
    build_http_rate_gate,
)
from ai_stp_api.settings import ServiceSettings

pytestmark = pytest.mark.platform

_WINDOW_SECONDS = 60
_LIMIT = 2
_ORIGIN = "test-origin"


def test_otel_headers_accept_runtime_pairs_without_normalizing_values() -> None:
    settings = ServiceSettings(
        otel_exporter_headers="Authorization=Basic runtime-value,stream-name=default"
    )

    assert settings.otel_headers() == {
        "Authorization": "Basic runtime-value",
        "stream-name": "default",
    }


def test_otel_headers_reject_malformed_entry_without_echoing_value() -> None:
    settings = ServiceSettings(otel_exporter_headers="Authorization")

    with pytest.raises(ValueError, match="name=value") as error:
        settings.otel_headers()

    assert "Authorization" not in str(error.value)


def test_sliding_window_limiter_prunes_expired_requests() -> None:
    limiter = SlidingWindowLimiter(
        maximum=_LIMIT,
        window_seconds=_WINDOW_SECONDS,
        max_keys=_LIMIT,
    )

    assert limiter.allow(_ORIGIN, now=0)
    assert limiter.allow(_ORIGIN, now=1)
    assert not limiter.allow(_ORIGIN, now=2)
    assert limiter.allow(_ORIGIN, now=_WINDOW_SECONDS)


def test_sliding_window_limiter_zero_limit_keeps_profile_disabled() -> None:
    limiter = SlidingWindowLimiter(maximum=0, window_seconds=_WINDOW_SECONDS, max_keys=_LIMIT)

    assert limiter.allow(_ORIGIN, now=0)
    assert limiter.allow(_ORIGIN, now=1)


def test_sliding_window_limiter_admits_unrelated_key_past_max_keys() -> None:
    limiter = SlidingWindowLimiter(maximum=_LIMIT, window_seconds=_WINDOW_SECONDS, max_keys=2)

    assert limiter.allow("first", now=0)
    assert limiter.allow("second", now=0)
    assert limiter.slot_count(now=0) == 2
    assert limiter.allow("third", now=1)
    assert limiter.holds("third", now=1)
    assert limiter.slot_count(now=1) == 2
    assert not limiter.holds("first", now=1)


def test_sliding_window_limiter_releases_idle_key_after_window() -> None:
    limiter = SlidingWindowLimiter(maximum=_LIMIT, window_seconds=_WINDOW_SECONDS, max_keys=2)

    assert limiter.allow("idle", now=0)
    assert limiter.allow("active", now=20)
    assert limiter.holds("idle", now=20)
    assert not limiter.holds("idle", now=_WINDOW_SECONDS)
    assert limiter.holds("active", now=_WINDOW_SECONDS)
    assert limiter.slot_count(now=_WINDOW_SECONDS) == 1
    assert limiter.allow("new", now=_WINDOW_SECONDS)
    assert limiter.holds("active", now=_WINDOW_SECONDS)
    assert limiter.holds("new", now=_WINDOW_SECONDS)
    assert limiter.slot_count(now=_WINDOW_SECONDS) == 2


def _gate_from_service(service: ServiceSettings) -> HttpRateGate:
    return build_http_rate_gate(
        overall_requests=service.rate_limit_overall_requests,
        overall_window_seconds=service.rate_limit_overall_window_seconds,
        ip_requests=service.rate_limit_ip_requests,
        ip_window_seconds=service.rate_limit_ip_window_seconds,
        max_keys=service.rate_limit_max_keys,
    )


def test_sliding_window_limiter_would_allow_does_not_record() -> None:
    limiter = SlidingWindowLimiter(maximum=1, window_seconds=_WINDOW_SECONDS, max_keys=2)

    assert limiter.would_allow(_ORIGIN, now=0)
    assert limiter.would_allow(_ORIGIN, now=0)
    assert limiter.allow(_ORIGIN, now=0)
    assert not limiter.would_allow(_ORIGIN, now=1)
    assert not limiter.allow(_ORIGIN, now=1)


def test_http_rate_gate_overall_window_rejects_the_101st_request() -> None:
    """A per-route or per-IP minute cap would still admit the 101st distinct peer."""
    service = ServiceSettings()
    gate = _gate_from_service(service)
    limit = service.rate_limit_overall_requests

    for index in range(limit):
        assert gate.allow(f"peer-{index}", now=0)
    assert not gate.allow("overflow", now=0)


def test_http_rate_gate_peer_window_rejects_the_1001st_from_one_origin() -> None:
    """Spacing stays under the overall minute cap so the hour window is what binds."""
    service = ServiceSettings()
    gate = _gate_from_service(service)
    limit = service.rate_limit_ip_requests
    step = service.rate_limit_ip_window_seconds / limit

    for index in range(limit):
        assert gate.allow("one", now=index * step)
    denied_at = (limit - 1) * step + 1
    assert not gate.allow("one", now=denied_at)
    assert gate.allow("other", now=denied_at)


def test_http_rate_gate_many_peers_still_trip_the_overall_budget() -> None:
    service = ServiceSettings()
    gate = _gate_from_service(service)
    limit = service.rate_limit_overall_requests

    for index in range(limit):
        assert gate.allow(f"origin-{index}", now=0)
    assert not gate.allow("origin-new", now=0)


def test_http_rate_gate_rejection_does_not_debit_the_other_window() -> None:
    ip_first = build_http_rate_gate(
        overall_requests=10,
        overall_window_seconds=_WINDOW_SECONDS,
        ip_requests=2,
        ip_window_seconds=3600,
        max_keys=16,
    )
    assert ip_first.allow("A", now=0)
    assert ip_first.allow("A", now=1)
    assert not ip_first.allow("A", now=2)
    for index in range(8):
        assert ip_first.allow(f"B{index}", now=3 + index)
    assert not ip_first.allow("extra", now=20)

    overall_first = build_http_rate_gate(
        overall_requests=2,
        overall_window_seconds=_WINDOW_SECONDS,
        ip_requests=10,
        ip_window_seconds=3600,
        max_keys=16,
    )
    assert overall_first.allow("A", now=0)
    assert overall_first.allow("B", now=1)
    assert not overall_first.allow("C", now=2)
    # Overall still holds B until t=61; space C past that and past each
    # overall window so the hourly budget is what the loop is counting.
    start = _WINDOW_SECONDS + 2
    spaced = _WINDOW_SECONDS + 1
    for index in range(10):
        assert overall_first.allow("C", now=start + index * spaced)
    assert not overall_first.allow("C", now=start + 10 * spaced)


def test_http_rate_gate_explicit_zero_disables_that_dimension() -> None:
    overall_off = build_http_rate_gate(
        overall_requests=0,
        overall_window_seconds=_WINDOW_SECONDS,
        ip_requests=2,
        ip_window_seconds=3600,
        max_keys=8,
    )
    assert overall_off.allow("A", now=0)
    assert overall_off.allow("A", now=1)
    assert not overall_off.allow("A", now=2)
    assert overall_off.allow("B", now=2)

    peer_off = build_http_rate_gate(
        overall_requests=2,
        overall_window_seconds=_WINDOW_SECONDS,
        ip_requests=0,
        ip_window_seconds=3600,
        max_keys=8,
    )
    spaced = _WINDOW_SECONDS + 1
    for index in range(20):
        assert peer_off.allow("A", now=index * spaced)


@pytest.mark.asyncio
async def test_rate_limit_middleware_shares_the_overall_window_across_routes() -> None:
    app = FastAPI()
    gate = build_http_rate_gate(
        overall_requests=1,
        overall_window_seconds=_WINDOW_SECONDS,
        ip_requests=100,
        ip_window_seconds=3600,
        max_keys=16,
    )
    app.add_middleware(RateLimitMiddleware, gate=gate)
    app.add_middleware(CorrelationMiddleware)

    async def read_item(item_id: str) -> dict[str, str]:
        return {"id": item_id}

    async def read_other(item_id: str) -> dict[str, str]:
        return {"id": item_id}

    app.add_api_route("/items/{item_id}", read_item, methods=["GET"])
    app.add_api_route("/other/{item_id}", read_other, methods=["GET"])
    limited_status = int(CATEGORY_STATUS[ErrorCategory.RATE_LIMITED])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first = await client.get("/items/aaa")
        other_template = await client.get("/other/ccc")

    assert first.status_code == 200
    assert other_template.status_code == limited_status
    assert other_template.json()["error"]["code"] == CATEGORY_CODE[ErrorCategory.RATE_LIMITED]
    assert other_template.headers["Retry-After"] == str(_WINDOW_SECONDS)


@pytest.mark.asyncio
async def test_rate_limit_middleware_isolates_transport_peers() -> None:
    app = FastAPI()
    ip_window = 3600
    gate = build_http_rate_gate(
        overall_requests=100,
        overall_window_seconds=_WINDOW_SECONDS,
        ip_requests=1,
        ip_window_seconds=ip_window,
        max_keys=16,
    )
    app.add_middleware(RateLimitMiddleware, gate=gate)
    app.add_middleware(CorrelationMiddleware)

    async def ping() -> dict[str, str]:
        return {"ok": "yes"}

    app.add_api_route("/ping", ping, methods=["GET"])
    limited_status = int(CATEGORY_STATUS[ErrorCategory.RATE_LIMITED])

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("10.0.0.1", 1)),
        base_url="http://test",
    ) as first_peer:
        admitted = await first_peer.get("/ping")
        limited = await first_peer.get("/ping")

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("10.0.0.2", 1)),
        base_url="http://test",
    ) as second_peer:
        other = await second_peer.get("/ping")

    assert admitted.status_code == 200
    assert limited.status_code == limited_status
    assert limited.json()["error"]["code"] == CATEGORY_CODE[ErrorCategory.RATE_LIMITED]
    assert limited.headers["Retry-After"] == str(ip_window)
    assert other.status_code == 200


@pytest.mark.asyncio
async def test_rate_limit_middleware_ignores_forwarded_headers() -> None:
    app = FastAPI()
    gate = build_http_rate_gate(
        overall_requests=100,
        overall_window_seconds=_WINDOW_SECONDS,
        ip_requests=1,
        ip_window_seconds=3600,
        max_keys=16,
    )
    app.add_middleware(RateLimitMiddleware, gate=gate)
    app.add_middleware(CorrelationMiddleware)

    async def ping() -> dict[str, str]:
        return {"ok": "yes"}

    app.add_api_route("/ping", ping, methods=["GET"])
    limited_status = int(CATEGORY_STATUS[ErrorCategory.RATE_LIMITED])

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("10.0.0.1", 1)),
        base_url="http://test",
    ) as client:
        first = await client.get("/ping", headers={"X-Forwarded-For": "8.8.8.8"})
        second = await client.get("/ping", headers={"X-Forwarded-For": "9.9.9.9"})

    assert first.status_code == 200
    assert second.status_code == limited_status
    assert second.json()["error"]["code"] == CATEGORY_CODE[ErrorCategory.RATE_LIMITED]
