"""On-demand GitHub metadata stays credential-free and never invents values."""

from __future__ import annotations

import httpx
import pytest

from ai_stp_platform.github_metadata import (
    GithubFetch,
    canonical_github_source,
    fetch_github_metadata,
    metadata_from_fetch,
    repository_from_passport,
    unavailable_metadata,
)


def test_canonical_github_source_accepts_only_public_github() -> None:
    assert (
        canonical_github_source("https://github.com/acme/tool.git")
        == "https://github.com/acme/tool"
    )
    assert canonical_github_source("https://github.com.evil.test/acme/tool") is None
    assert canonical_github_source("http://github.com/acme/tool") is None
    assert canonical_github_source("https://user:pass@github.com/acme/tool") is None


def test_repository_from_passport_reads_only_the_source_field() -> None:
    assert repository_from_passport({"source": {"repository": "https://github.com/acme/tool"}}) == (
        "https://github.com/acme/tool"
    )
    assert repository_from_passport({"source": None}) is None
    assert repository_from_passport(None) is None


def test_metadata_from_fetch_keeps_active_and_archived_apart() -> None:
    active = metadata_from_fetch(
        GithubFetch(
            status_code=200,
            body=b'{"stargazers_count": 3, "archived": false, "private": false}',
            headers={"content-type": "application/json"},
        )
    )
    assert active.stars == 3
    assert active.archived is False
    archived = metadata_from_fetch(
        GithubFetch(
            status_code=200,
            body=b'{"stargazers_count": 1, "archived": true, "private": false}',
            headers={},
        )
    )
    assert archived.archived is True


@pytest.mark.parametrize(
    "status_code",
    [403, 404, 429, 500],
)
def test_metadata_from_fetch_treats_error_statuses_as_unavailable(status_code: int) -> None:
    result = metadata_from_fetch(GithubFetch(status_code=status_code, body=b"{}", headers={}))
    assert result == unavailable_metadata()


def test_metadata_from_fetch_rejects_private_malformed_and_oversized() -> None:
    assert (
        metadata_from_fetch(
            GithubFetch(
                status_code=200,
                body=b'{"stargazers_count": 1, "archived": true, "private": true}',
                headers={},
            )
        )
        == unavailable_metadata()
    )
    assert (
        metadata_from_fetch(GithubFetch(status_code=200, body=b"not-json", headers={}))
        == unavailable_metadata()
    )
    assert (
        metadata_from_fetch(
            GithubFetch(status_code=200, body=b"{}", headers={"content-length": "999999"})
        )
        == unavailable_metadata()
    )


@pytest.mark.asyncio
async def test_fetch_github_metadata_sends_no_credentials_and_follows_no_redirects() -> None:
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert "Authorization" not in request.headers
        assert request.url.host == "api.github.com"
        return httpx.Response(
            200,
            json={"stargazers_count": 8, "archived": False, "private": False},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_github_metadata("https://github.com/acme/tool", client=client)
    assert result.stars == 8
    assert result.archived is False
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_fetch_github_metadata_does_not_follow_redirects() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"location": "https://evil.test/steal"},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_github_metadata("https://github.com/acme/tool", client=client)
    assert result == unavailable_metadata()
