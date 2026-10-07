"""HTTPS fetch transport for official upstream resolution (SPEC-056)."""

from __future__ import annotations

import os
from collections.abc import Mapping

import httpx

from ai_stp_platform.official_upstream.errors import (
    UNAVAILABLE_UPSTREAM,
    UNSAFE_ARCHIVE,
    OfficialUpstreamError,
)
from ai_stp_sources.archive import MAX_GIT_ARCHIVE_BYTES
from ai_stp_sources.git import FetchFn, GithubHttpResponse

TIMEOUT_SECONDS = 20.0
TOKEN_ENV = "AI_STP_WORKER_GITHUB_TOKEN"
MAX_RESPONSE_BYTES = MAX_GIT_ARCHIVE_BYTES

__all__ = ["TOKEN_ENV", "FetchFn", "GithubHttpResponse", "default_fetch", "worker_github_token"]


async def default_fetch(
    url: str, *, headers: Mapping[str, str], timeout: float = TIMEOUT_SECONDS
) -> GithubHttpResponse:
    try:
        async with (
            httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client,
            client.stream("GET", url, headers=dict(headers)) as response,
        ):
            declared = response.headers.get("content-length")
            if declared is not None and declared.isdigit() and int(declared) > MAX_RESPONSE_BYTES:
                raise OfficialUpstreamError(
                    UNSAFE_ARCHIVE, "upstream response exceeds the accepted size"
                )
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                    raise OfficialUpstreamError(
                        UNSAFE_ARCHIVE, "upstream response exceeds the accepted size"
                    )
                body.extend(chunk)
            return GithubHttpResponse(
                status_code=response.status_code,
                body=bytes(body),
                headers={key.lower(): value for key, value in response.headers.items()},
                url=str(response.url),
            )
    except httpx.HTTPError as exc:
        raise OfficialUpstreamError(UNAVAILABLE_UPSTREAM, "upstream request failed") from exc


def worker_github_token() -> str | None:
    return os.environ.get(TOKEN_ENV)
