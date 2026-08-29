"""On-demand GitHub metadata stays credential-free and never invents values."""

from __future__ import annotations

import httpx
import pytest

from ai_stp_platform.github_metadata import (
    GithubFetch,
    canonical_github_source,
    fetch_github_metadata,
    metadata_from_fetch,
    redirect_path,
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
async def test_fetch_github_metadata_refuses_a_redirect_off_api_github() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"location": "https://evil.test/steal"},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_github_metadata("https://github.com/acme/tool", client=client)
    assert result == unavailable_metadata()


@pytest.mark.asyncio
async def test_a_transferred_repository_is_read_at_the_owner_it_moved_to() -> None:
    """GitHub answers 301 for a transferred repository, and that is the case.

    Every one of the nineteen setups published from the former estate cites a
    `NDDev-it-com/*` repository that was transferred to a personal account and
    then archived. Measured against the live catalogue on 2026-08-29,
    `github-metadata` answered `{"stars": null, "archived": null}` for all of
    them: the archive evidence looking straight at its own case and reporting
    nothing, because the request was made with `follow_redirects=False` and a
    transfer is a redirect.
    """
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        assert "Authorization" not in request.headers
        assert request.url.host == "api.github.com"
        if request.url.path == "/repos/old-owner/tool":
            # The shape GitHub actually sends, measured against the live API:
            # a transfer redirects to the repository's numeric identity, not to
            # its new owner and name.
            return httpx.Response(
                301,
                headers={"location": "https://api.github.com/repositories/1307421318"},
                request=request,
            )
        return httpx.Response(
            200,
            json={"stargazers_count": 3, "archived": True, "private": False},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_github_metadata("https://github.com/old-owner/tool", client=client)
    assert result.archived is True
    assert result.stars == 3
    assert seen == ["/repos/old-owner/tool", "/repositories/1307421318"]


@pytest.mark.asyncio
async def test_only_one_hop_is_followed() -> None:
    """A chain is a budget nobody set, so the second redirect is refused."""
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        nxt = len(seen)
        return httpx.Response(
            301,
            headers={"location": f"https://api.github.com/repositories/{1000 + nxt}"},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_github_metadata("https://github.com/owner/tool", client=client)
    assert result == unavailable_metadata()
    assert len(seen) == 2


def test_redirect_path_accepts_only_a_repository_on_api_github() -> None:
    def fetch(location: str, status: int = 301) -> GithubFetch:
        return GithubFetch(status_code=status, body=b"", headers={"location": location})

    assert redirect_path(fetch("https://api.github.com/repos/new/tool")) == "/repos/new/tool"
    # The form a real transfer sends.
    assert redirect_path(fetch("https://api.github.com/repositories/1307421318")) == (
        "/repositories/1307421318"
    )
    assert redirect_path(fetch("https://api.github.com/repositories/not-a-number")) is None
    # Off-host, credentialled, non-repository and non-redirect are all refused.
    assert redirect_path(fetch("https://evil.test/repos/new/tool")) is None
    assert redirect_path(fetch("https://user:pass@api.github.com/repos/new/tool")) is None
    assert redirect_path(fetch("https://api.github.com/users/new")) is None
    assert redirect_path(fetch("https://api.github.com/repos/new/tool/contents")) is None
    assert redirect_path(fetch("/repos/new/tool")) is None
    assert redirect_path(fetch("https://api.github.com/repos/new/tool", status=200)) is None
    assert redirect_path(GithubFetch(status_code=301, body=b"", headers={})) is None
