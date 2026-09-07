"""Provider HTTP boundary: successful images, bounded redirects and streamed failures."""

from collections.abc import AsyncIterator

import httpx
import pytest
from tests.support.images import image_bytes

from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.slices.profile.avatar import AVATAR_REDIRECT_LIMIT, fetch_provider_avatar
from ai_stp_contracts.public_profile import AVATAR_MAX_BYTES

pytestmark = pytest.mark.platform


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "url"),
    [
        ("github", "https://avatars.githubusercontent.com/u/1"),
        ("google", "https://lh3.googleusercontent.com/avatar"),
    ],
)
async def test_provider_image_fetch_accepts_only_bounded_images(provider: str, url: str) -> None:
    payload = image_bytes()

    def reply(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers
        return httpx.Response(200, content=payload, headers={"content-type": "image/png"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
        assert await fetch_provider_avatar(client, url, provider) == (payload, "image/png")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target",
    [
        "https://127.0.0.1/private",
        "http://avatars.githubusercontent.com/u/2",
        "https://evil.test/u/1",
    ],
)
async def test_provider_redirect_is_validated_before_the_next_request(target: str) -> None:
    calls: list[str] = []

    def reply(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": target})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(reply), follow_redirects=True
    ) as client:
        with pytest.raises(ApiError) as caught:
            await fetch_provider_avatar(
                client, "https://avatars.githubusercontent.com/u/1", "github"
            )
    assert caught.value.category == ErrorCategory.VALIDATION
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_provider_redirect_loop_is_bounded() -> None:
    calls = 0

    def reply(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(302, headers={"location": "/again"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
        with pytest.raises(ApiError) as caught:
            await fetch_provider_avatar(
                client, "https://avatars.githubusercontent.com/u/1", "github"
            )
    assert caught.value.category == ErrorCategory.DEPENDENCY
    assert calls == AVATAR_REDIRECT_LIMIT + 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "mime", "category"),
    [
        (404, "image/png", ErrorCategory.DEPENDENCY),
        (200, "text/html", ErrorCategory.VALIDATION),
        (200, "", ErrorCategory.VALIDATION),
    ],
)
async def test_provider_bad_response_is_typed(
    status: int, mime: str, category: ErrorCategory
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                status, content=b"no image", headers={"content-type": mime}
            )
        )
    ) as client:
        with pytest.raises(ApiError) as caught:
            await fetch_provider_avatar(
                client, "https://avatars.githubusercontent.com/u/1", "github"
            )
    assert caught.value.category == category


class OversizedStream(httpx.AsyncByteStream):
    def __init__(self) -> None:
        self.closed = False
        self.chunks = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for _ in range(3):
            self.chunks += 1
            yield b"x" * AVATAR_MAX_BYTES

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_provider_oversize_stream_stops_and_closes() -> None:
    stream = OversizedStream()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, stream=stream, headers={"content-type": "image/png"}
            )
        )
    ) as client:
        with pytest.raises(ApiError) as caught:
            await fetch_provider_avatar(
                client, "https://avatars.githubusercontent.com/u/1", "github"
            )
    assert caught.value.category == ErrorCategory.VALIDATION
    assert stream.closed
    assert stream.chunks == 2


@pytest.mark.asyncio
async def test_provider_timeout_is_a_dependency_failure() -> None:
    def reply(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
        with pytest.raises(ApiError) as caught:
            await fetch_provider_avatar(
                client, "https://avatars.githubusercontent.com/u/1", "github"
            )
    assert caught.value.category == ErrorCategory.DEPENDENCY
