from datetime import UTC, datetime, timedelta
from typing import cast

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.models import RepositoryMetric
from ai_stp_platform.repository_metrics import github_api_url, refresh_github_stars


class Session:
    def __init__(self) -> None:
        self.row = None

    async def get(self, model: object, key: str):
        return self.row

    def add(self, row: object) -> None:
        self.row = row


def test_github_api_url_accepts_only_canonical_repository() -> None:
    assert (
        github_api_url("https://github.com/example/project.git")
        == "https://api.github.com/repos/example/project"
    )
    assert github_api_url("https://github.com.evil.test/example/project") is None
    assert github_api_url("http://github.com/example/project") is None
    assert github_api_url("https://github.com/example/project/extra") is None


@pytest.mark.asyncio
async def test_refresh_github_stars_caches_count_and_etag() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"stargazers_count": 42}, headers={"etag": '"metric"'}, request=request
        )

    session = Session()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        row = await refresh_github_stars(
            cast(AsyncSession, session),
            "https://github.com/example/project",
            client=client,
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )
    assert row.github_stars == 42
    assert row.etag == '"metric"'


@pytest.mark.asyncio
async def test_refresh_github_stars_keeps_fresh_cache_without_request() -> None:
    now = datetime.now(UTC)
    row = RepositoryMetric(
        repository="https://github.com/acme/tool", github_stars=7, checked_at=now
    )
    session = Session()
    session.row = row

    async def unexpected(request: httpx.Request) -> httpx.Response:
        pytest.fail(str(request))

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as client:
        result = await refresh_github_stars(
            cast(AsyncSession, session), row.repository, client=client, now=now
        )
    assert result.github_stars == 7


@pytest.mark.asyncio
async def test_refresh_github_stars_respects_failure_backoff() -> None:
    now = datetime.now(UTC)
    row = RepositoryMetric(
        repository="https://github.com/acme/tool",
        github_stars=7,
        retry_after=now + timedelta(hours=1),
    )
    session = Session()
    session.row = row

    async def unexpected(request: httpx.Request) -> httpx.Response:
        pytest.fail(str(request))

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as client:
        result = await refresh_github_stars(
            cast(AsyncSession, session), row.repository, client=client, now=now
        )
    assert result.github_stars == 7


@pytest.mark.asyncio
async def test_refresh_github_stars_hides_non_github_repository() -> None:
    session = Session()

    async def unexpected(request: httpx.Request) -> httpx.Response:
        pytest.fail(str(request))

    now = datetime.now(UTC)
    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as client:
        result = await refresh_github_stars(
            cast(AsyncSession, session), "https://example.test/tool", client=client, now=now
        )
    assert result.github_stars is None
    assert result.checked_at == now


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "payload", "expected"),
    [(304, None, 7), (200, [], None), (200, {"stargazers_count": -1}, None)],
)
async def test_refresh_github_stars_handles_conditional_and_invalid_responses(
    status: int, payload: object, expected: int | None
) -> None:
    now = datetime.now(UTC)
    row = RepositoryMetric(
        repository="https://github.com/acme/tool",
        github_stars=7,
        etag='"old"',
        checked_at=now - timedelta(days=1),
        retry_after=now - timedelta(minutes=1),
    )
    session = Session()
    session.row = row

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["if-none-match"] == '"old"'
        return httpx.Response(status, json=payload, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await refresh_github_stars(
            cast(AsyncSession, session), row.repository, client=client, now=now
        )
    assert result.github_stars == expected
    assert result.retry_after is None


@pytest.mark.asyncio
async def test_refresh_github_stars_preserves_value_and_backs_off_on_failure() -> None:
    now = datetime.now(UTC)
    row = RepositoryMetric(
        repository="https://github.com/acme/tool",
        github_stars=7,
        checked_at=now - timedelta(days=1),
    )
    session = Session()
    session.row = row

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await refresh_github_stars(
            cast(AsyncSession, session), row.repository, client=client, now=now
        )
    assert result.github_stars == 7
    assert result.failure_count == 1
    assert result.retry_after == now + timedelta(minutes=2)
