"""Best-effort GitHub repository metrics, isolated from catalog trust."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from urllib.parse import urlsplit

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.models import RepositoryMetric

MAX_FAILURE_BACKOFF = timedelta(hours=24)
METRIC_TTL = timedelta(hours=12)


def github_api_url(repository: str) -> str | None:
    parsed = urlsplit(repository)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.scheme != "https" or parsed.hostname != "github.com" or len(parts) != 2:
        return None
    owner, name = parts
    return f"https://api.github.com/repos/{owner}/{name.removesuffix('.git')}"


async def refresh_github_stars(
    session: AsyncSession,
    repository: str,
    *,
    client: httpx.AsyncClient,
    now: datetime | None = None,
) -> RepositoryMetric:
    moment = now or datetime.now(UTC)
    row = await session.get(RepositoryMetric, repository) or RepositoryMetric(repository=repository)
    if row.checked_at is not None and moment - row.checked_at < METRIC_TTL:
        return row
    if row.retry_after is not None and moment < row.retry_after:
        return row
    api_url = github_api_url(repository)
    if api_url is None:
        row.github_stars = None
        row.checked_at = moment
        session.add(row)
        return row
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if row.etag:
        headers["If-None-Match"] = row.etag
    response = await client.get(api_url, headers=headers)
    row.checked_at = moment
    if response.status_code == 304:
        row.failure_count = 0
        row.retry_after = None
    elif response.status_code == 200:
        payload = cast(object, response.json())
        stars = (
            cast(dict[str, object], payload).get("stargazers_count")
            if isinstance(payload, dict)
            else None
        )
        row.github_stars = stars if isinstance(stars, int) and stars >= 0 else None
        row.etag = response.headers.get("etag")
        row.failure_count = 0
        row.retry_after = None
    else:
        row.failure_count = (row.failure_count or 0) + 1
        delay = min(timedelta(minutes=2 ** min(row.failure_count, 10)), MAX_FAILURE_BACKOFF)
        row.retry_after = moment + delay
    session.add(row)
    return row
