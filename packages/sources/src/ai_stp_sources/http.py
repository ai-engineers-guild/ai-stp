"""Bounded HTTPS GETs for registry adapters (SPEC-057 REQ-5718)."""

from __future__ import annotations

import json
from typing import cast
from urllib.parse import urlsplit

from ai_stp_sources.errors import UNAVAILABLE_SOURCE, UNSAFE_ARCHIVE, SourceError
from ai_stp_sources.git import FetchFn, GithubHttpResponse

USER_AGENT = "ai-stp-sources"
MAX_REDIRECTS = 2
MAX_JSON_BYTES = 1_048_576
MAX_GRAPH_ENTRIES = 500


def registry_headers() -> dict[str, str]:
    return {"Accept": "application/json", "User-Agent": USER_AGENT}


def require_official_url(url: str, allowed_hosts: frozenset[str], *, label: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in allowed_hosts
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise SourceError(UNSAFE_ARCHIVE, f"{label} left the official registry hosts")
    return url


async def bounded_get(
    url: str,
    *,
    fetch: FetchFn,
    allowed_hosts: frozenset[str],
    max_bytes: int,
) -> GithubHttpResponse:
    current = require_official_url(url, allowed_hosts, label="request")
    response: GithubHttpResponse | None = None
    for _hop in range(MAX_REDIRECTS + 1):
        response = await fetch(current, headers=registry_headers())
        if response.status_code not in {301, 302, 307, 308}:
            break
        location = response.headers.get("location")
        if not location:
            break
        current = require_official_url(location, allowed_hosts, label="redirect")
    if response is None:
        raise SourceError(UNAVAILABLE_SOURCE, "registry request failed")
    if response.status_code in {301, 302, 307, 308}:
        raise SourceError(UNSAFE_ARCHIVE, "registry redirect exceeded the accepted hops")
    declared = response.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > max_bytes:
        raise SourceError(UNSAFE_ARCHIVE, "registry response exceeds the accepted size")
    if len(response.body) > max_bytes:
        raise SourceError(UNSAFE_ARCHIVE, "registry response exceeds the accepted size")
    return response


def json_object(body: bytes) -> dict[str, object]:
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SourceError(UNAVAILABLE_SOURCE, "registry response is not JSON") from exc
    if not isinstance(parsed, dict):
        raise SourceError(UNAVAILABLE_SOURCE, "registry response is not an object")
    return cast(dict[str, object], parsed)
