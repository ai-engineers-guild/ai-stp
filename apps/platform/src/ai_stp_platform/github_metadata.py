"""On-demand public GitHub stars and archive state (SPEC-049)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, cast
from urllib.parse import quote, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_stp_contracts.catalog import GitHubMetadata

API_HOST = "api.github.com"
API_ROOT = f"https://{API_HOST}"
API_VERSION = "2022-11-28"
TIMEOUT_SECONDS = 5.0
MAX_RESPONSE_BYTES = 65_536
USER_AGENT = "ai-stp-platform"


class _RepositoryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    stargazers_count: Annotated[int, Field(ge=0)]
    archived: bool
    private: bool


@dataclass(frozen=True)
class GithubFetch:
    """Transport result used by tests without exposing raw GitHub payloads."""

    status_code: int
    body: bytes
    headers: dict[str, str]


def canonical_github_source(repository: str) -> str | None:
    """Return the closed public GitHub source URL, or None when unsupported."""
    parsed = urlsplit(repository)
    parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or len(parts) != 2
        or not all(parts)
    ):
        return None
    name = parts[1].removesuffix(".git")
    if not name:
        return None
    return f"https://github.com/{parts[0]}/{name}"


def _request_path(source: str) -> str | None:
    parsed = urlsplit(source)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2:
        return None
    return f"/repos/{quote(parts[0], safe='')}/{quote(parts[1], safe='')}"


def unavailable_metadata() -> GitHubMetadata:
    return GitHubMetadata(stars=None, archived=None)


def repository_from_passport(document: object) -> str | None:
    """Read the exact passport source URL without accepting a browser-supplied host."""
    if not isinstance(document, dict):
        return None
    payload = cast(dict[str, object], document)
    source = payload.get("source")
    if not isinstance(source, dict):
        return None
    source_map = cast(dict[str, object], source)
    repository = source_map.get("repository")
    return repository if isinstance(repository, str) else None


def redirect_path(fetch: GithubFetch) -> str | None:
    """The repository path a transfer redirect points at, if it is safe to follow.

    GitHub answers `301` for a repository whose owner changed, and this request
    is deliberately made with `follow_redirects=False`, so a transferred
    repository read as "metadata unavailable" rather than as what it is.

    That blinded the archive evidence to the one history it exists for. Measured
    2026-08-29 against the live catalogue: nineteen published setups cite
    `NDDev-it-com/*`, every one of those repositories was transferred to a
    personal account and archived, and `github-metadata` answered
    `{"stars": null, "archived": null}` for all of them — the feature looking
    straight at its own case and reporting nothing.

    Following it stays inside the original guarantee rather than relaxing it.
    The `Location` must be an absolute URL on `api.github.com` whose path is
    still `/repos/<owner>/<name>`; anything else is refused, so no request ever
    leaves that host and none of them carries a credential. One hop only: a
    second redirect is refused rather than chased, because a chain is a budget
    nobody set.
    """
    if fetch.status_code not in (301, 302, 307, 308):
        return None
    location = fetch.headers.get("location")
    if not location:
        return None
    parsed = urlsplit(location)
    if (
        parsed.scheme != "https"
        or parsed.hostname != API_HOST
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 3 or parts[0] != "repos":
        return None
    return f"/repos/{quote(parts[1], safe='')}/{quote(parts[2], safe='')}"


def metadata_from_fetch(fetch: GithubFetch) -> GitHubMetadata:
    """Project a bounded GitHub response into nullable stars/archived."""
    if fetch.status_code != 200:
        return unavailable_metadata()
    declared = fetch.headers.get("content-length")
    too_large = declared is not None and (
        not declared.isdigit() or int(declared) > MAX_RESPONSE_BYTES
    )
    if too_large or len(fetch.body) > MAX_RESPONSE_BYTES:
        return unavailable_metadata()
    try:
        raw = cast(dict[str, object], json.loads(fetch.body))
        parsed = _RepositoryResponse.model_validate(
            {
                "stargazers_count": raw.get("stargazers_count"),
                "archived": raw.get("archived"),
                "private": raw.get("private"),
            }
        )
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError, TypeError, ValueError):
        return unavailable_metadata()
    if parsed.private:
        return unavailable_metadata()
    return GitHubMetadata(stars=parsed.stargazers_count, archived=parsed.archived)


async def fetch_github_metadata(
    repository: str,
    *,
    client: httpx.AsyncClient,
) -> GitHubMetadata:
    """One credential-free, no-redirect request to api.github.com."""
    source = canonical_github_source(repository)
    path = _request_path(source) if source else None
    if source is None or path is None:
        return unavailable_metadata()
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": USER_AGENT,
    }
    for _hop in range(2):
        try:
            response = await client.get(
                f"{API_ROOT}{path}",
                headers=headers,
                timeout=TIMEOUT_SECONDS,
                follow_redirects=False,
            )
        except httpx.HTTPError:
            return unavailable_metadata()
        fetch = GithubFetch(
            status_code=response.status_code,
            body=response.content,
            headers={key.lower(): value for key, value in response.headers.items()},
        )
        moved = redirect_path(fetch)
        if moved is None or moved == path:
            return metadata_from_fetch(fetch)
        path = moved
    return unavailable_metadata()
