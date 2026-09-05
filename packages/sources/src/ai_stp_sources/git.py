"""GitHub ref resolution and bounded archive download (SPEC-057 REQ-5702)."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import cast
from urllib.parse import quote, urlsplit

from ai_stp_foundation.digests import digest_bytes
from ai_stp_sources.archive import MAX_GIT_ARCHIVE_BYTES, extract_component_files
from ai_stp_sources.coordinates import COMMIT_RE, canonicalize_source
from ai_stp_sources.errors import (
    FLOATING_FROZEN_SOURCE,
    UNAVAILABLE_SOURCE,
    UNSAFE_ARCHIVE,
    SourceError,
)
from ai_stp_sources.files import files_digest
from ai_stp_sources.models import GitIntent, SourceSnapshot

API_HOST = "api.github.com"
API_ROOT = f"https://{API_HOST}"
API_VERSION = "2022-11-28"
USER_AGENT = "ai-stp-sources"
TIMEOUT_SECONDS = 20.0
MAX_REDIRECTS = 2
# Commit responses can include a large changed-files section; keep the bound
# finite while allowing legitimate repositories such as gsd-core to resolve.
MAX_JSON_BYTES = 2 * 1_048_576
ALLOWED_HOSTS = frozenset({API_HOST, "github.com", "codeload.github.com"})
ARTIFACT_DIGEST_DOMAIN = "ai-stp:artifact:v1"


class GithubHttpResponse:
    def __init__(self, status_code: int, body: bytes, headers: Mapping[str, str], url: str) -> None:
        self.status_code = status_code
        self.body = body
        self.headers = headers
        self.url = url


type FetchFn = Callable[..., Awaitable[GithubHttpResponse]]


def _api_headers(*, token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": USER_AGENT,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _redirect_url(response: GithubHttpResponse) -> str | None:
    if response.status_code not in {301, 302, 307, 308}:
        return None
    location = response.headers.get("location")
    if not location:
        return None
    parsed = urlsplit(location)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_HOSTS
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise SourceError(UNSAFE_ARCHIVE, "GitHub redirect left the allowed hosts")
    return location


def _headers_for(url: str, *, token: str | None) -> dict[str, str]:
    host = urlsplit(url).hostname
    if host == API_HOST:
        return _api_headers(token=token)
    return _api_headers(token=None)


async def _get(
    url: str,
    *,
    fetch: FetchFn,
    token: str | None,
    max_bytes: int,
) -> GithubHttpResponse:
    current = url
    response: GithubHttpResponse | None = None
    for _hop in range(MAX_REDIRECTS + 1):
        response = await fetch(current, headers=_headers_for(current, token=token))
        redirected = _redirect_url(response)
        if redirected is None:
            break
        current = redirected
    if response is None:
        raise SourceError(UNAVAILABLE_SOURCE, "GitHub request failed")
    declared = response.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > max_bytes:
        raise SourceError(UNSAFE_ARCHIVE, "GitHub response exceeds the accepted size")
    if len(response.body) > max_bytes:
        raise SourceError(UNSAFE_ARCHIVE, "GitHub response exceeds the accepted size")
    return response


def _json_object(body: bytes) -> dict[str, object]:
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SourceError(UNAVAILABLE_SOURCE, "GitHub response is not JSON") from exc
    if not isinstance(parsed, dict):
        raise SourceError(UNAVAILABLE_SOURCE, "GitHub response is not an object")
    return cast(dict[str, object], parsed)


def _owner_name(source: str) -> tuple[str, str]:
    parts = [part for part in urlsplit(source).path.split("/") if part]
    return parts[0], parts[1]


def _is_rate_limited(response: GithubHttpResponse) -> bool:
    if response.status_code not in {403, 429}:
        return False
    remaining = response.headers.get("x-ratelimit-remaining")
    if remaining == "0":
        return True
    body = response.body.decode("utf-8", errors="replace").lower()
    return "rate limit" in body


def _require_github_ok(response: GithubHttpResponse, missing: str) -> None:
    if response.status_code == 200:
        return
    if _is_rate_limited(response):
        raise SourceError(UNAVAILABLE_SOURCE, "GitHub rate limit exceeded")
    raise SourceError(UNAVAILABLE_SOURCE, missing)


def _license_spdx(raw: object) -> str | None:
    if not isinstance(raw, dict):
        return None
    spdx = cast(dict[str, object], raw).get("spdx_id")
    if isinstance(spdx, str) and spdx and spdx != "NOASSERTION":
        return spdx
    return None


def reject_floating_commit(value: str) -> str:
    if COMMIT_RE.fullmatch(value) is None:
        raise SourceError(FLOATING_FROZEN_SOURCE, "frozen git provenance requires a full commit")
    return value


async def resolve_git(
    intent: GitIntent,
    *,
    fetch: FetchFn,
    token: str | None = None,
    now: datetime | None = None,
) -> SourceSnapshot:
    """Resolve a branch or tag to a full commit and download the tarball."""
    canonical = canonicalize_source(intent)
    assert isinstance(canonical, GitIntent)
    owner, name = _owner_name(canonical.repository_url)
    repo = await _get(
        f"{API_ROOT}/repos/{quote(owner, safe='')}/{quote(name, safe='')}",
        fetch=fetch,
        token=token,
        max_bytes=65_536,
    )
    _require_github_ok(repo, "GitHub repository is unavailable")
    repo_body = _json_object(repo.body)
    if repo_body.get("private") is True:
        raise SourceError(UNAVAILABLE_SOURCE, "GitHub repository is unavailable")
    repo_id = repo_body.get("id")
    if not isinstance(repo_id, int):
        raise SourceError(UNAVAILABLE_SOURCE, "GitHub repository identity is missing")
    commit_response = await _get(
        f"{API_ROOT}/repos/{quote(owner, safe='')}/{quote(name, safe='')}/commits/"
        f"{quote(canonical.tracked_ref, safe='')}",
        fetch=fetch,
        token=token,
        max_bytes=MAX_JSON_BYTES,
    )
    _require_github_ok(commit_response, "GitHub ref is unavailable")
    sha = _json_object(commit_response.body).get("sha")
    if not isinstance(sha, str):
        raise SourceError(UNAVAILABLE_SOURCE, "GitHub ref did not resolve to a commit")
    commit = reject_floating_commit(sha)
    archive = await _get(
        f"{API_ROOT}/repos/{quote(owner, safe='')}/{quote(name, safe='')}/tarball/{commit}",
        fetch=fetch,
        token=token,
        max_bytes=MAX_GIT_ARCHIVE_BYTES,
    )
    _require_github_ok(archive, "GitHub archive is unavailable")
    files = extract_component_files(
        archive.body,
        subpath=canonical.subpath,
        max_archive_bytes=MAX_GIT_ARCHIVE_BYTES,
    )
    return SourceSnapshot(
        kind="git",
        canonical_coordinate=(f"git:{canonical.repository_url}@{commit}:{canonical.subpath}"),
        exact_identity=commit,
        archive_digest=digest_bytes(ARTIFACT_DIGEST_DOMAIN, archive.body),
        component_digest=files_digest(files),
        subpath=canonical.subpath,
        repository_url=canonical.repository_url,
        github_owner=owner,
        github_name=name,
        github_repo_id=repo_id,
        observed_license=_license_spdx(repo_body.get("license")),
        files=files,
        fetched_at=now or datetime.now(UTC),
    )
