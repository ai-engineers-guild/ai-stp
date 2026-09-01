"""HTTPS fetch transport for official upstream resolution (SPEC-056)."""

from __future__ import annotations

import os
from collections.abc import Mapping

import httpx

from ai_stp_platform.official_upstream.errors import UNAVAILABLE_UPSTREAM, OfficialUpstreamError
from ai_stp_sources.git import FetchFn, GithubHttpResponse

TIMEOUT_SECONDS = 20.0
TOKEN_ENV = "AI_STP_WORKER_GITHUB_TOKEN"

__all__ = ["TOKEN_ENV", "FetchFn", "GithubHttpResponse", "default_fetch", "worker_github_token"]


async def default_fetch(
    url: str, *, headers: Mapping[str, str], timeout: float = TIMEOUT_SECONDS
) -> GithubHttpResponse:
    async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
        try:
            response = await client.get(url, headers=dict(headers))
        except httpx.HTTPError as exc:
            raise OfficialUpstreamError(UNAVAILABLE_UPSTREAM, "upstream request failed") from exc
        return GithubHttpResponse(
            status_code=response.status_code,
            body=bytes(response.content),
            headers={key.lower(): value for key, value in response.headers.items()},
            url=str(response.url),
        )


def worker_github_token() -> str | None:
    return os.environ.get(TOKEN_ENV)
