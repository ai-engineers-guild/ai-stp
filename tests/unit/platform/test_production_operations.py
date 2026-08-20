"""Pure guards for optional telemetry and bounded abuse protection (#187)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ai_stp_api.correlation import CorrelationMiddleware
from ai_stp_api.errors import CATEGORY_CODE, CATEGORY_STATUS, ErrorCategory
from ai_stp_api.rate_limit import RateLimitMiddleware, SlidingWindowLimiter
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


@pytest.mark.asyncio
async def test_rate_limit_key_uses_route_template_not_concrete_path() -> None:
    app = FastAPI()
    limiter = SlidingWindowLimiter(maximum=1, window_seconds=_WINDOW_SECONDS, max_keys=16)
    app.add_middleware(RateLimitMiddleware, limiter=limiter)
    app.add_middleware(CorrelationMiddleware)

    async def read_item(item_id: str) -> dict[str, str]:
        return {"id": item_id}

    async def read_other(item_id: str) -> dict[str, str]:
        return {"id": item_id}

    app.add_api_route("/items/{item_id}", read_item, methods=["GET"])
    app.add_api_route("/other/{item_id}", read_other, methods=["GET"])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first = await client.get("/items/aaa")
        same_template = await client.get("/items/bbb")
        other_template = await client.get("/other/ccc")

    assert first.status_code == 200
    assert same_template.status_code == int(CATEGORY_STATUS[ErrorCategory.RATE_LIMITED])
    assert same_template.json()["error"]["code"] == CATEGORY_CODE[ErrorCategory.RATE_LIMITED]
    assert other_template.status_code == 200
