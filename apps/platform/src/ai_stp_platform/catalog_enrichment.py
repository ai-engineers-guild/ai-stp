"""Bounded catalog metadata adapters (SPEC-050).

Fetch and projection stay off until attribution, terms URL and an explicit
policy gate are all present. Observations never become trust, verification,
eligibility or install success.
"""

from __future__ import annotations

from collections import OrderedDict, defaultdict, deque
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from json import JSONDecodeError, loads
from typing import Final, Literal, cast
from urllib.parse import quote, urlsplit

import httpx
from pydantic import ValidationError

from ai_stp_contracts.federation import (
    CATALOG_ADAPTER_CACHE_MAX_ENTRIES,
    CATALOG_ADAPTER_CACHE_TTL_SECONDS,
    CATALOG_ADAPTER_CONNECT_TIMEOUT_SECONDS,
    CATALOG_ADAPTER_MAX_REQUESTS_PER_MINUTE,
    CATALOG_ADAPTER_READ_TIMEOUT_SECONDS,
    CATALOG_METADATA_ADAPTERS_ENABLED_BY_DEFAULT,
    CATALOG_METADATA_PROVIDERS,
    CATALOG_OBSERVATION_MAX_COLLECTION_ITEMS,
    CATALOG_OBSERVATION_MAX_JSON_DEPTH,
    CATALOG_OBSERVATION_MAX_REFERENCES,
    CATALOG_OBSERVATION_MAX_RESPONSE_BYTES,
    CATALOG_OBSERVATION_MAX_STRING_CODEPOINTS,
    CatalogExternalCoordinate,
    CatalogMetadataObservation,
)
from ai_stp_foundation.timestamps import format_timestamp, parse_timestamp
from ai_stp_platform.models import CatalogExternalObservation

USER_AGENT: Final[str] = "ai-stp-platform"
PROVIDER_HOSTS: Final[dict[str, str]] = {
    "skills_sh": "skills.sh",
    "nori": "nori.sh",
    "modelcontextprotocol": "modelcontextprotocol.com",
}
_IDENTIFIER_KEYS: Final[dict[str, tuple[str, ...]]] = {
    "skills_sh": ("id", "slug"),
    "nori": ("id", "slug"),
    "modelcontextprotocol": ("id", "name"),
}
_ALLOWLIST_KEYS: Final[dict[str, tuple[str, ...]]] = {
    "display_name": ("display_name", "name", "title"),
    "summary": ("summary", "description"),
    "homepage_url": ("homepage_url", "homepage", "website", "url"),
    "repository_url": ("repository_url", "repository", "repo"),
    "published_at": ("published_at", "publishedAt", "created_at"),
    "updated_at": ("updated_at", "updatedAt"),
    "popularity_count": ("popularity_count", "installs", "stars", "downloads"),
    "external_state": ("external_state", "state", "status"),
}
_STATE_MAP: Final[dict[str, str]] = {
    "present": "present",
    "active": "present",
    "archived": "archived",
    "unavailable": "unavailable",
    "missing": "unavailable",
}
_REDIRECT_STATUSES = frozenset(range(300, 400))

type FetchFn = Callable[[str], Awaitable["CatalogFetch"]]


class CatalogBoundError(ValueError):
    """Payload exceeded a closed adapter bound."""


@dataclass(frozen=True)
class CatalogAdapterPolicy:
    enabled: bool = CATALOG_METADATA_ADAPTERS_ENABLED_BY_DEFAULT
    attribution: str | None = None
    terms_url: str | None = None

    def permits(self) -> bool:
        return bool(
            self.enabled and self.attribution and self.terms_url and _public_https(self.terms_url)
        )


@dataclass(frozen=True)
class CatalogFetchRequest:
    coordinate: CatalogExternalCoordinate
    source_url: str | None = None


@dataclass(frozen=True)
class CatalogFetch:
    status_code: int
    body: bytes
    headers: Mapping[str, str]
    error: Literal["timeout", "network", "redirect"] | None = None


@dataclass(frozen=True)
class _CacheEntry:
    observation: CatalogMetadataObservation
    stored_at: datetime


class CatalogObservationCache:
    """Per-provider bounded TTL cache of last observations."""

    def __init__(
        self,
        *,
        max_entries: int = CATALOG_ADAPTER_CACHE_MAX_ENTRIES,
        ttl_seconds: int = CATALOG_ADAPTER_CACHE_TTL_SECONDS,
    ) -> None:
        self.max_entries = max_entries
        self._ttl = timedelta(seconds=ttl_seconds)
        self._entries: dict[str, OrderedDict[str, _CacheEntry]] = {
            provider: OrderedDict() for provider in CATALOG_METADATA_PROVIDERS
        }

    def get(
        self, provider: str, external_identifier: str, *, now: datetime
    ) -> CatalogMetadataObservation | None:
        bucket = self._entries[provider]
        entry = bucket.get(external_identifier)
        if entry is None:
            return None
        if now - entry.stored_at >= self._ttl:
            return None
        bucket.move_to_end(external_identifier)
        return entry.observation

    def last(self, provider: str, external_identifier: str) -> CatalogMetadataObservation | None:
        entry = self._entries[provider].get(external_identifier)
        return None if entry is None else entry.observation

    def put(
        self,
        observation: CatalogMetadataObservation,
        *,
        now: datetime,
    ) -> None:
        bucket = self._entries[observation.provider]
        bucket[observation.external_identifier] = _CacheEntry(observation, now)
        bucket.move_to_end(observation.external_identifier)
        while len(bucket) > self.max_entries:
            bucket.popitem(last=False)


class ProviderRateLimiter:
    """At most N fetches per provider in a rolling minute. Clock is injected."""

    def __init__(self, *, max_per_minute: int = CATALOG_ADAPTER_MAX_REQUESTS_PER_MINUTE) -> None:
        self._max = max_per_minute
        self._hits: dict[str, deque[datetime]] = defaultdict(deque)

    def allow(self, provider: str, *, now: datetime) -> bool:
        window = now - timedelta(minutes=1)
        hits = self._hits[provider]
        while hits and hits[0] <= window:
            hits.popleft()
        if len(hits) >= self._max:
            return False
        hits.append(now)
        return True


def policies_from_environ(environ: Mapping[str, str]) -> dict[str, CatalogAdapterPolicy]:
    """Closed env mapping. Missing or non-true enable leaves every adapter off."""
    global_on = environ.get("AI_STP_CATALOG_ENRICHMENT_ENABLED") == "true"
    policies: dict[str, CatalogAdapterPolicy] = {}
    for provider in CATALOG_METADATA_PROVIDERS:
        prefix = f"AI_STP_CATALOG_ENRICHMENT_{provider.upper()}_"
        policies[provider] = CatalogAdapterPolicy(
            enabled=global_on and environ.get(f"{prefix}ENABLED", "true") == "true",
            attribution=_optional_text(environ.get(f"{prefix}ATTRIBUTION")),
            terms_url=_optional_text(environ.get(f"{prefix}TERMS_URL")),
        )
    return policies


def official_source_url(provider: str, external_identifier: str) -> str:
    host = PROVIDER_HOSTS[provider]
    return f"https://{host}/{quote(external_identifier, safe='')}"


def source_url_is_official(provider: str, url: str) -> bool:
    parsed = urlsplit(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname == PROVIDER_HOSTS[provider]
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    )


def resolve_source_url(request: CatalogFetchRequest) -> str | None:
    if request.source_url is not None:
        if source_url_is_official(request.coordinate.provider, request.source_url):
            return request.source_url
        return None
    return official_source_url(request.coordinate.provider, request.coordinate.external_identifier)


def stale_if_expired(
    observation: CatalogMetadataObservation, *, now: datetime
) -> CatalogMetadataObservation:
    if observation.freshness == "unavailable" or observation.expires_at is None:
        return observation
    if now < parse_timestamp(observation.expires_at):
        return observation
    return observation.model_copy(update={"freshness": "stale"})


def parse_catalog_payload(
    provider: str,
    coordinate: CatalogExternalCoordinate,
    payload: Mapping[str, object],
    *,
    source_url: str,
    policy: CatalogAdapterPolicy,
    now: datetime,
) -> CatalogMetadataObservation:
    """Map one vendor object onto the closed allowlist. Unknown fields drop."""
    claimed = _payload_identifier(provider, payload)
    if claimed is not None and claimed != coordinate.external_identifier:
        raise CatalogBoundError("exact-coordinate mismatch")
    expires_at = now + timedelta(seconds=CATALOG_ADAPTER_CACHE_TTL_SECONDS)
    checked = format_timestamp(now)
    fields = _allowlist_fields(payload)
    return CatalogMetadataObservation.model_validate(
        {
            "provider": coordinate.provider,
            "external_identifier": coordinate.external_identifier,
            "dedup_key": coordinate.dedup_key,
            "source_url": source_url,
            "attribution": policy.attribution,
            "terms_url": policy.terms_url,
            "fetched_at": checked,
            "checked_at": checked,
            "expires_at": format_timestamp(expires_at),
            "freshness": "fresh",
            **fields,
        }
    )


def observation_from_fetch(
    request: CatalogFetchRequest,
    fetch: CatalogFetch,
    *,
    policy: CatalogAdapterPolicy,
    now: datetime,
    last: CatalogMetadataObservation | None,
) -> CatalogMetadataObservation | None:
    if not policy.permits():
        return None
    source_url = resolve_source_url(request)
    if source_url is None:
        return _unavailable(
            request,
            policy,
            now,
            last,
            source_url=official_source_url(
                request.coordinate.provider, request.coordinate.external_identifier
            ),
        )
    if fetch.error is not None or fetch.status_code in _REDIRECT_STATUSES:
        return _unavailable(request, policy, now, last, source_url=source_url)
    if fetch.status_code != 200:
        return _unavailable(request, policy, now, last, source_url=source_url)
    try:
        payload = _bounded_object(fetch.body, fetch.headers)
        return parse_catalog_payload(
            request.coordinate.provider,
            request.coordinate,
            payload,
            source_url=source_url,
            policy=policy,
            now=now,
        )
    except (CatalogBoundError, ValidationError, TypeError, ValueError):
        return _unavailable(request, policy, now, last, source_url=source_url)


async def refresh_one(
    request: CatalogFetchRequest,
    *,
    policy: CatalogAdapterPolicy,
    now: datetime,
    fetch: FetchFn | None = None,
    cache: CatalogObservationCache | None = None,
    limiter: ProviderRateLimiter | None = None,
    last: CatalogMetadataObservation | None = None,
) -> CatalogMetadataObservation | None:
    if not policy.permits():
        return None
    provider = request.coordinate.provider
    external_identifier = request.coordinate.external_identifier
    remembered = last
    if cache is not None:
        cached = cache.get(provider, external_identifier, now=now)
        if cached is not None:
            return stale_if_expired(cached, now=now)
        remembered = remembered or cache.last(provider, external_identifier)
    if limiter is not None and not limiter.allow(provider, now=now):
        result = _unavailable(
            request,
            policy,
            now,
            remembered,
            source_url=resolve_source_url(request)
            or official_source_url(provider, external_identifier),
        )
        if cache is not None:
            cache.put(result, now=now)
        return result
    source_url = resolve_source_url(request)
    if source_url is None:
        return _unavailable(
            request,
            policy,
            now,
            remembered,
            source_url=official_source_url(provider, external_identifier),
        )
    transport = fetch or _httpx_fetch
    try:
        response = await transport(source_url)
    except httpx.TimeoutException:
        response = CatalogFetch(status_code=0, body=b"", headers={}, error="timeout")
    except httpx.HTTPError:
        response = CatalogFetch(status_code=0, body=b"", headers={}, error="network")
    result = observation_from_fetch(request, response, policy=policy, now=now, last=remembered)
    if cache is not None and result is not None:
        cache.put(result, now=now)
    return result


async def refresh_many(
    requests: Sequence[CatalogFetchRequest],
    *,
    policies: Mapping[str, CatalogAdapterPolicy],
    now: datetime,
    fetch: FetchFn | None = None,
    cache: CatalogObservationCache | None = None,
    limiter: ProviderRateLimiter | None = None,
    last_valid: Mapping[str, CatalogMetadataObservation] | None = None,
) -> list[CatalogMetadataObservation]:
    remembered = last_valid or {}
    seen: set[str] = set()
    results: list[CatalogMetadataObservation] = []
    for request in requests:
        if len(results) >= CATALOG_OBSERVATION_MAX_REFERENCES:
            break
        key = request.coordinate.dedup_key
        if key in seen:
            continue
        seen.add(key)
        observation = await refresh_one(
            request,
            policy=policies.get(request.coordinate.provider, CatalogAdapterPolicy()),
            now=now,
            fetch=fetch,
            cache=cache,
            limiter=limiter,
            last=remembered.get(key),
        )
        if observation is not None:
            results.append(observation)
    return results


def observation_from_row(row: CatalogExternalObservation) -> CatalogMetadataObservation:
    return CatalogMetadataObservation.model_validate(
        {
            "provider": row.provider,
            "external_identifier": row.external_identifier,
            "dedup_key": row.dedup_key,
            "source_url": row.source_url,
            "attribution": row.attribution,
            "terms_url": row.terms_url,
            "fetched_at": None if row.fetched_at is None else format_timestamp(row.fetched_at),
            "checked_at": format_timestamp(row.checked_at),
            "expires_at": None if row.expires_at is None else format_timestamp(row.expires_at),
            "freshness": row.freshness,
            "display_name": row.display_name,
            "summary": row.summary,
            "homepage_url": row.homepage_url,
            "repository_url": row.repository_url,
            "published_at": None
            if row.published_at is None
            else format_timestamp(row.published_at),
            "updated_at": None if row.updated_at is None else format_timestamp(row.updated_at),
            "popularity_count": row.popularity_count,
            "external_state": row.external_state,
        }
    )


def apply_observation(
    row: CatalogExternalObservation | None,
    observation: CatalogMetadataObservation,
    catalog_metadata_id: int,
) -> CatalogExternalObservation:
    """Copy a closed observation onto a persistence row without extra fields."""
    target = row or CatalogExternalObservation(catalog_metadata_id=catalog_metadata_id)
    target.catalog_metadata_id = catalog_metadata_id
    target.provider = observation.provider
    target.external_identifier = observation.external_identifier
    target.dedup_key = observation.dedup_key
    target.source_url = observation.source_url
    target.attribution = observation.attribution
    target.terms_url = observation.terms_url
    target.fetched_at = _as_datetime(observation.fetched_at)
    target.checked_at = parse_timestamp(observation.checked_at)
    target.expires_at = _as_datetime(observation.expires_at)
    target.freshness = observation.freshness
    target.display_name = observation.display_name
    target.summary = observation.summary
    target.homepage_url = observation.homepage_url
    target.repository_url = observation.repository_url
    target.published_at = _as_datetime(observation.published_at)
    target.updated_at = _as_datetime(observation.updated_at)
    target.popularity_count = observation.popularity_count
    target.external_state = observation.external_state
    return target


def _unavailable(
    request: CatalogFetchRequest,
    policy: CatalogAdapterPolicy,
    now: datetime,
    last: CatalogMetadataObservation | None,
    *,
    source_url: str,
) -> CatalogMetadataObservation:
    checked = format_timestamp(now)
    if last is not None and last.fetched_at is not None:
        return last.model_copy(
            update={
                "checked_at": checked,
                "freshness": "unavailable",
                "external_state": "unavailable",
                "attribution": policy.attribution or last.attribution,
                "terms_url": policy.terms_url or last.terms_url,
            }
        )
    return CatalogMetadataObservation.model_validate(
        {
            "provider": request.coordinate.provider,
            "external_identifier": request.coordinate.external_identifier,
            "dedup_key": request.coordinate.dedup_key,
            "source_url": source_url,
            "attribution": policy.attribution,
            "terms_url": policy.terms_url,
            "fetched_at": None,
            "checked_at": checked,
            "expires_at": None,
            "freshness": "unavailable",
            "external_state": "unavailable",
        }
    )


def _bounded_object(body: bytes, headers: Mapping[str, str]) -> dict[str, object]:
    declared = headers.get("content-length") or headers.get("Content-Length")
    if declared is not None and (
        not declared.isdigit() or int(declared) > CATALOG_OBSERVATION_MAX_RESPONSE_BYTES
    ):
        raise CatalogBoundError("oversized content-length")
    if len(body) > CATALOG_OBSERVATION_MAX_RESPONSE_BYTES:
        raise CatalogBoundError("oversized body")
    try:
        parsed = cast(object, loads(body))
    except (JSONDecodeError, UnicodeDecodeError) as error:
        raise CatalogBoundError("malformed json") from error
    if not isinstance(parsed, dict):
        raise CatalogBoundError("root must be an object")
    _walk_bounds(cast(object, parsed), depth=0)
    return cast(dict[str, object], parsed)


def _walk_bounds(node: object, *, depth: int) -> None:
    if depth > CATALOG_OBSERVATION_MAX_JSON_DEPTH:
        raise CatalogBoundError("json depth")
    if isinstance(node, str) and len(node) > CATALOG_OBSERVATION_MAX_STRING_CODEPOINTS:
        raise CatalogBoundError("string length")
    if isinstance(node, list):
        items = cast(list[object], node)
        if len(items) > CATALOG_OBSERVATION_MAX_COLLECTION_ITEMS:
            raise CatalogBoundError("collection size")
        for item in items:
            _walk_bounds(item, depth=depth + 1)
        return
    if isinstance(node, dict):
        values = cast(dict[object, object], node)
        if len(values) > CATALOG_OBSERVATION_MAX_COLLECTION_ITEMS:
            raise CatalogBoundError("collection size")
        for value in values.values():
            _walk_bounds(value, depth=depth + 1)


def _payload_identifier(provider: str, payload: Mapping[str, object]) -> str | None:
    for key in _IDENTIFIER_KEYS[provider]:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _allowlist_fields(payload: Mapping[str, object]) -> dict[str, object]:
    fields: dict[str, object] = {"external_state": "present"}
    for field, keys in _ALLOWLIST_KEYS.items():
        value = _first_present(payload, keys)
        if value is None:
            continue
        if field in {"homepage_url", "repository_url"}:
            if isinstance(value, str) and _public_https(value):
                fields[field] = value
            continue
        if field in {"published_at", "updated_at"}:
            if isinstance(value, str):
                try:
                    fields[field] = format_timestamp(parse_timestamp(value))
                except ValueError:
                    continue
            continue
        if field == "popularity_count":
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                fields[field] = value
            continue
        if field == "external_state":
            if isinstance(value, str) and value in _STATE_MAP:
                fields[field] = _STATE_MAP[value]
            continue
        if isinstance(value, str) and value:
            fields[field] = value
    return fields


def _first_present(payload: Mapping[str, object], keys: Sequence[str]) -> object | None:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _public_https(url: str) -> bool:
    parsed = urlsplit(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    )


def _optional_text(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return value


def _as_datetime(value: str | None) -> datetime | None:
    return None if value is None else parse_timestamp(value)


async def _httpx_fetch(url: str) -> CatalogFetch:
    parsed = urlsplit(url)
    if parsed.username is not None or parsed.password is not None:
        return CatalogFetch(status_code=0, body=b"", headers={}, error="network")
    timeout = httpx.Timeout(
        connect=CATALOG_ADAPTER_CONNECT_TIMEOUT_SECONDS,
        read=CATALOG_ADAPTER_READ_TIMEOUT_SECONDS,
        write=CATALOG_ADAPTER_READ_TIMEOUT_SECONDS,
        pool=CATALOG_ADAPTER_CONNECT_TIMEOUT_SECONDS,
    )
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        response = await client.get(url)
    if response.status_code in _REDIRECT_STATUSES:
        return CatalogFetch(
            status_code=response.status_code,
            body=response.content,
            headers={key.lower(): value for key, value in response.headers.items()},
            error="redirect",
        )
    return CatalogFetch(
        status_code=response.status_code,
        body=response.content,
        headers={key.lower(): value for key, value in response.headers.items()},
    )
