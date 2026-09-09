"""Bounded GitHub requests with fixed audiences and safe upstream failures."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast
from urllib.parse import quote, urlsplit

import httpx

from ai_stp_sources.archive import MAX_GIT_ARCHIVE_BYTES
from ai_stp_sources.git import ALLOWED_HOSTS, API_ROOT, API_VERSION, GithubHttpResponse


class GitHubError(RuntimeError):
    """Only a closed reason and status cross the upstream error boundary."""

    def __init__(self, reason: str, *, status: int = 503) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status


@dataclass(frozen=True)
class GitHubReply:
    status: int
    data: object = field(repr=False)


def _api_url(path: str) -> str:
    """Build an API URL without allowing path data to alter its authority."""
    return f"{API_ROOT}{quote(path, safe='/?=&')}"


def object_data(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(
        not isinstance(key, str) for key in cast(dict[object, object], value)
    ):
        raise GitHubError("invalid_upstream_response")
    return dict(cast(dict[str, object], value))


def positive_id(value: object) -> int:
    if type(value) is not int or not 0 < value <= 9_007_199_254_740_991:
        raise GitHubError("invalid_upstream_response")
    return value


def _upstream_error(status: int, headers: Mapping[str, str]) -> GitHubError:
    if status == 429 or (status == 403 and headers.get("x-ratelimit-remaining") == "0"):
        return GitHubError("github_rate_limited", status=429)
    if status == 401:
        return GitHubError("reauthorization_required", status=401)
    if status in {403, 404}:
        return GitHubError("repository_access_denied", status=403)
    if status == 422:
        return GitHubError("github_action_refused", status=422)
    return GitHubError("github_unavailable")


class GitHubClient:
    """One injectable HTTP transport; no credentials in the object or its repr."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: dict[str, object] | None = None,
        max_bytes: int = 2 * 1_048_576,
    ) -> GithubHttpResponse:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in ALLOWED_HOSTS
            or parsed.port not in {None, 443}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise GitHubError("unsafe_github_url", status=400)
        if parsed.hostname != "api.github.com" and any(
            name.lower() == "authorization" for name in headers
        ):
            raise GitHubError("unsafe_token_audience", status=400)
        try:
            async with (
                httpx.AsyncClient(
                    timeout=httpx.Timeout(30.0, connect=5.0),
                    follow_redirects=False,
                    trust_env=False,
                    transport=self.transport,
                ) as client,
                client.stream(method, url, headers=headers, json=body) as response,
            ):
                declared = response.headers.get("content-length")
                if declared is not None and (not declared.isdigit() or int(declared) > max_bytes):
                    raise GitHubError("github_response_too_large")
                payload = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(payload) + len(chunk) > max_bytes:
                        raise GitHubError("github_response_too_large")
                    payload.extend(chunk)
                return GithubHttpResponse(
                    response.status_code,
                    bytes(payload),
                    dict(response.headers),
                    str(response.url),
                )
        except (httpx.HTTPError, OSError):
            raise GitHubError("github_unavailable") from None

    async def api(
        self,
        method: str,
        path: str,
        *,
        token: str | None,
        body: dict[str, object] | None = None,
        accepted: frozenset[int] = frozenset({200, 201, 204}),
    ) -> GitHubReply:
        if not path.startswith("/") or path.startswith("//") or "\\" in path:
            raise GitHubError("unsafe_github_url", status=400)
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "ai-stp-connector",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = await self._request(method, _api_url(path), headers=headers, body=body)
        if response.status_code not in accepted:
            raise _upstream_error(response.status_code, response.headers)
        if not response.body or response.status_code == 204:
            return GitHubReply(response.status_code, None)
        try:
            data: object = json.loads(response.body)
        except (ValueError, UnicodeDecodeError):
            raise GitHubError("invalid_upstream_response") from None
        return GitHubReply(response.status_code, data)

    async def exchange_code(
        self, *, client_id: str, client_secret: str, code: str, redirect_uri: str
    ) -> dict[str, object]:
        response = await self._request(
            "POST",
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json", "User-Agent": "ai-stp-connector"},
            body={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            max_bytes=65_536,
        )
        if response.status_code != 200:
            raise _upstream_error(response.status_code, response.headers)
        try:
            result = object_data(json.loads(response.body))
        except (ValueError, UnicodeDecodeError):
            raise GitHubError("invalid_upstream_response") from None
        if "error" in result:
            raise GitHubError("reauthorization_required", status=401)
        return result

    async def fetch(self, url: str, *, headers: Mapping[str, str]) -> GithubHttpResponse:
        """Source resolver transport; it alone owns approved archive redirects."""
        response = await self._request("GET", url, headers=headers, max_bytes=MAX_GIT_ARCHIVE_BYTES)
        if response.status_code not in {200, 301, 302, 307, 308}:
            raise _upstream_error(response.status_code, response.headers)
        return response

    async def scoped_token(
        self,
        *,
        token: str,
        client_id: str,
        client_secret: str,
        owner_id: int,
        repository_id: int,
    ) -> str:
        """Narrow a user token to one immutable repository before name-based mutations."""
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode("ascii")
        response = await self._request(
            "POST",
            f"{API_ROOT}/applications/{quote(client_id, safe='')}/token/scoped",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Basic {basic}",
                "X-GitHub-Api-Version": API_VERSION,
            },
            body={
                "access_token": token,
                "target_id": owner_id,
                "repository_ids": [repository_id],
                "permissions": {"metadata": "read", "administration": "write"},
            },
            max_bytes=65_536,
        )
        if response.status_code != 200:
            raise _upstream_error(response.status_code, response.headers)
        try:
            value = object_data(json.loads(response.body)).get("token")
        except (ValueError, UnicodeDecodeError):
            raise GitHubError("invalid_upstream_response") from None
        if (
            not isinstance(value, str)
            or not 1 <= len(value) <= 4096
            or any(char.isspace() for char in value)
        ):
            raise GitHubError("invalid_upstream_response")
        return value
