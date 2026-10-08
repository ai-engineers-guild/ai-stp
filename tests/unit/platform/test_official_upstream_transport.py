"""The Official worker bounds downloads before buffering an upstream response."""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import partial

import httpx
import pytest

from ai_stp_platform.official_upstream import github
from ai_stp_platform.official_upstream.errors import (
    UNAVAILABLE_UPSTREAM,
    UNSAFE_ARCHIVE,
    OfficialUpstreamError,
)

pytestmark = pytest.mark.platform


class TrackingStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes], *, fail: bool = False) -> None:
        self.chunks = chunks
        self.fail = fail
        self.reads = 0
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            self.reads += 1
            yield chunk
        if self.fail:
            raise httpx.ReadError("upstream disconnected")

    async def aclose(self) -> None:
        self.closed = True


def install_transport(
    monkeypatch: pytest.MonkeyPatch,
    stream: TrackingStream,
    *,
    headers: dict[str, str] | None = None,
    status: int = 200,
) -> None:
    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers, stream=stream)

    monkeypatch.setattr(github, "MAX_RESPONSE_BYTES", 8)
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        partial(httpx.AsyncClient, transport=httpx.MockTransport(respond)),
    )


@pytest.mark.parametrize("headers", [{}, {"content-length": "1"}])
async def test_oversize_stream_stops_without_consuming_the_tail(
    monkeypatch: pytest.MonkeyPatch, headers: dict[str, str]
) -> None:
    stream = TrackingStream([b"12345678", b"9", b"unread tail"])
    install_transport(monkeypatch, stream, headers=headers)
    with pytest.raises(OfficialUpstreamError) as caught:
        await github.default_fetch("https://api.github.com/test", headers={})
    assert caught.value.code == UNSAFE_ARCHIVE
    assert stream.reads == 2
    assert stream.closed


async def test_declared_oversize_is_refused_before_reading(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = TrackingStream([b"unread"])
    install_transport(monkeypatch, stream, headers={"content-length": "9"})
    with pytest.raises(OfficialUpstreamError) as caught:
        await github.default_fetch("https://api.github.com/test", headers={})
    assert caught.value.code == UNSAFE_ARCHIVE
    assert stream.reads == 0
    assert stream.closed


async def test_exact_limit_preserves_response_and_closes_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = TrackingStream([b"1234", b"5678"])
    install_transport(monkeypatch, stream, headers={"X-RateLimit-Remaining": "0"}, status=429)
    response = await github.default_fetch("https://api.github.com/test", headers={})
    assert response.body == b"12345678"
    assert response.status_code == 429
    assert response.headers["x-ratelimit-remaining"] == "0"
    assert stream.closed


async def test_interrupted_stream_keeps_transient_failure_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = TrackingStream([b"short"], fail=True)
    install_transport(monkeypatch, stream)
    with pytest.raises(OfficialUpstreamError) as caught:
        await github.default_fetch("https://api.github.com/test", headers={})
    assert caught.value.code == UNAVAILABLE_UPSTREAM
    assert stream.closed
