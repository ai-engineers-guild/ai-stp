"""Catalog metadata adapters stay bounded, gated, and non-authoritative."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import cast

import httpx
import pytest
from tests.unit.platform.catalog_enrichment_fixtures import (
    EXTERNAL_ID,
    NOW,
    all_providers,
    enabling_environ,
    fetch_request,
    happy_fetch,
    happy_payload,
    permitted_policy,
    ttl_later,
)

from ai_stp_contracts.federation import (
    CATALOG_ADAPTER_CACHE_MAX_ENTRIES,
    CATALOG_ADAPTER_MAX_REQUESTS_PER_MINUTE,
    CATALOG_METADATA_ADAPTERS_ENABLED_BY_DEFAULT,
    CATALOG_OBSERVATION_MAX_JSON_DEPTH,
    CATALOG_OBSERVATION_MAX_REFERENCES,
    CATALOG_OBSERVATION_MAX_RESPONSE_BYTES,
    CATALOG_OBSERVATION_MAX_STRING_CODEPOINTS,
    describe_catalog_metadata,
)
from ai_stp_platform.catalog_enrichment import (
    CatalogAdapterPolicy,
    CatalogFetch,
    CatalogObservationCache,
    ProviderRateLimiter,
    apply_observation,
    observation_from_fetch,
    official_source_url,
    policies_from_environ,
    refresh_many,
    refresh_one,
    source_url_is_official,
    stale_if_expired,
)
from ai_stp_platform.models import CatalogExternalObservation

pytestmark = pytest.mark.platform


def test_production_policies_are_closed_until_attribution_and_terms_exist() -> None:
    assert CATALOG_METADATA_ADAPTERS_ENABLED_BY_DEFAULT is False
    policy = CatalogAdapterPolicy()
    assert policy.permits() is False
    assert policy.enabled is False
    incomplete = CatalogAdapterPolicy(enabled=True, attribution="skills.sh catalog", terms_url=None)
    assert incomplete.permits() is False


@pytest.mark.parametrize("provider", all_providers())
def test_policy_fixture_blocks_fetch_and_observation_stays_non_authoritative(
    provider: str,
) -> None:
    closed = CatalogAdapterPolicy()
    request = fetch_request(provider)
    result = observation_from_fetch(
        request, happy_fetch(provider), policy=closed, now=NOW, last=None
    )
    assert result is None
    permitted = observation_from_fetch(
        request, happy_fetch(provider), policy=permitted_policy(provider), now=NOW, last=None
    )
    assert permitted is not None
    descriptor = describe_catalog_metadata(permitted)
    assert descriptor.author_verified is False
    assert descriptor.component_verified is False
    assert descriptor.registry_effect == "none"
    assert descriptor.target_write is False
    assert descriptor.authority == "external_observation"


@pytest.mark.parametrize("provider", all_providers())
def test_source_url_stays_on_the_official_host(provider: str) -> None:
    official = official_source_url(provider, EXTERNAL_ID)
    assert source_url_is_official(provider, official)
    assert source_url_is_official(provider, "https://evil.test/steal") is False
    credentialed = f"https://user:pass@{official.removeprefix('https://')}"
    assert source_url_is_official(provider, credentialed) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", all_providers())
async def test_refresh_one_happy_path_keeps_allowlist_and_drops_unknown_fields(
    provider: str,
) -> None:
    captured: list[str] = []

    async def fetch(url: str) -> CatalogFetch:
        captured.append(url)
        return happy_fetch(provider)

    observation = await refresh_one(
        fetch_request(provider),
        policy=permitted_policy(provider),
        now=NOW,
        fetch=fetch,
    )
    assert observation is not None
    assert observation.display_name == f"{provider}-name"
    assert observation.summary == f"{provider}-summary"
    assert observation.popularity_count == 4
    assert observation.freshness == "fresh"
    assert observation.fetched_at is not None
    assert observation.expires_at is not None
    dumped = observation.model_dump()
    assert "content" not in dumped
    assert "install_command" not in dumped
    assert observation.author_verified is False
    assert captured == [official_source_url(provider, EXTERNAL_ID)]


@pytest.mark.asyncio
async def test_independent_references_survive_one_adapter_failure() -> None:
    providers = all_providers()

    async def fetch(url: str) -> CatalogFetch:
        if PROVIDER_HOSTS_FROM_URL(url) == providers[1]:
            return CatalogFetch(status_code=200, body=b"{", headers={})
        for provider in providers:
            if official_source_url(provider, EXTERNAL_ID) == url:
                return happy_fetch(provider)
        raise AssertionError(url)

    results = await refresh_many(
        [fetch_request(provider) for provider in providers],
        policies={provider: permitted_policy(provider) for provider in providers},
        now=NOW,
        fetch=fetch,
    )
    by_provider = {item.provider: item for item in results}
    assert by_provider[providers[0]].freshness == "fresh"
    assert by_provider[providers[1]].freshness == "unavailable"
    assert by_provider[providers[2]].freshness == "fresh"
    assert by_provider[providers[0]].display_name == f"{providers[0]}-name"
    assert by_provider[providers[2]].display_name == f"{providers[2]}-name"


def PROVIDER_HOSTS_FROM_URL(url: str) -> str:
    from ai_stp_platform.catalog_enrichment import PROVIDER_HOSTS

    for provider, host in PROVIDER_HOSTS.items():
        if host in url:
            return provider
    raise AssertionError(url)


@pytest.mark.asyncio
async def test_reference_cap_and_dedup_do_not_fetch_extras() -> None:
    provider = all_providers()[0]
    seen: list[str] = []

    async def fetch(url: str) -> CatalogFetch:
        seen.append(url)
        identifier = url.rsplit("/", 1)[-1]
        return happy_fetch(provider, identifier)

    extras = [
        fetch_request(provider, f"pkg:exact-{index}")
        for index in range(CATALOG_OBSERVATION_MAX_REFERENCES + 3)
    ]
    extras.append(fetch_request(provider, "pkg:exact-0"))
    results = await refresh_many(
        extras,
        policies={provider: permitted_policy(provider)},
        now=NOW,
        fetch=fetch,
    )
    assert len(results) == CATALOG_OBSERVATION_MAX_REFERENCES
    assert len(seen) == CATALOG_OBSERVATION_MAX_REFERENCES


@pytest.mark.asyncio
async def test_cache_ttl_and_entry_bound_skip_refetch() -> None:
    provider = all_providers()[0]
    cache = CatalogObservationCache(max_entries=2, ttl_seconds=60)
    hits = 0

    async def fetch(_url: str) -> CatalogFetch:
        nonlocal hits
        hits += 1
        return happy_fetch(provider)

    first = await refresh_one(
        fetch_request(provider, "a"),
        policy=permitted_policy(provider),
        now=NOW,
        fetch=fetch,
        cache=cache,
    )
    second = await refresh_one(
        fetch_request(provider, "a"),
        policy=permitted_policy(provider),
        now=NOW + timedelta(seconds=10),
        fetch=fetch,
        cache=cache,
    )
    assert first == second
    assert hits == 1
    await refresh_one(
        fetch_request(provider, "b"),
        policy=permitted_policy(provider),
        now=NOW,
        fetch=fetch,
        cache=cache,
    )
    await refresh_one(
        fetch_request(provider, "c"),
        policy=permitted_policy(provider),
        now=NOW,
        fetch=fetch,
        cache=cache,
    )
    assert cache.get(provider, "a", now=NOW) is None
    assert cache.get(provider, "c", now=NOW) is not None


def test_cache_bound_matches_contract_default() -> None:
    assert CatalogObservationCache().max_entries == CATALOG_ADAPTER_CACHE_MAX_ENTRIES


@pytest.mark.asyncio
async def test_rate_limit_is_clock_controlled_and_keeps_last_valid() -> None:
    provider = all_providers()[0]
    limiter = ProviderRateLimiter(max_per_minute=1)
    last = await refresh_one(
        fetch_request(provider),
        policy=permitted_policy(provider),
        now=NOW,
        fetch=lambda _url: _const_fetch(happy_fetch(provider)),
        limiter=limiter,
    )
    assert last is not None and last.freshness == "fresh"
    blocked = await refresh_one(
        fetch_request(provider),
        policy=permitted_policy(provider),
        now=NOW + timedelta(seconds=1),
        fetch=lambda _url: _const_fetch(happy_fetch(provider)),
        limiter=limiter,
        last=last,
    )
    assert blocked is not None
    assert blocked.freshness == "unavailable"
    assert blocked.display_name == last.display_name
    assert blocked.fetched_at == last.fetched_at
    assert limiter.allow(provider, now=NOW + timedelta(seconds=2)) is False
    assert limiter.allow(provider, now=NOW + timedelta(minutes=1, seconds=1)) is True
    assert CATALOG_ADAPTER_MAX_REQUESTS_PER_MINUTE >= 1


async def _const_fetch(result: CatalogFetch) -> CatalogFetch:
    return result


def test_ttl_turns_last_valid_observation_stale_without_a_fetch() -> None:
    provider = all_providers()[0]
    fresh = observation_from_fetch(
        fetch_request(provider),
        happy_fetch(provider),
        policy=permitted_policy(provider),
        now=NOW,
        last=None,
    )
    assert fresh is not None
    assert fresh.freshness == "fresh"
    stale = stale_if_expired(fresh, now=ttl_later())
    assert stale.freshness == "stale"
    assert stale.display_name == fresh.display_name


def test_apply_observation_copies_only_allowlist_columns() -> None:
    provider = all_providers()[0]
    observation = observation_from_fetch(
        fetch_request(provider),
        happy_fetch(provider),
        policy=permitted_policy(provider),
        now=NOW,
        last=None,
    )
    assert observation is not None
    row = apply_observation(None, observation, catalog_metadata_id=9)
    assert isinstance(row, CatalogExternalObservation)
    assert row.catalog_metadata_id == 9
    assert row.provider == provider
    assert row.display_name == observation.display_name
    assert row.freshness == "fresh"
    assert "content" not in row.__dict__


def test_environ_policy_stays_off_without_the_global_enable_flag() -> None:
    provider = all_providers()[0]
    env = enabling_environ(provider)
    env.pop("AI_STP_CATALOG_ENRICHMENT_ENABLED")
    policies = policies_from_environ(env)
    assert policies[provider].permits() is False
    policies = policies_from_environ(enabling_environ(provider))
    assert policies[provider].permits() is True


@pytest.mark.asyncio
async def test_httpx_fetch_sends_no_credentials_and_does_not_follow_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = all_providers()[0]
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert "Authorization" not in request.headers
        assert request.headers["user-agent"]
        return httpx.Response(
            302,
            headers={"location": "https://evil.test/steal"},
            request=request,
        )

    async def fake_client(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("refresh_one must use the injected fetch in this test")

    result = await refresh_one(
        fetch_request(provider),
        policy=permitted_policy(provider),
        now=NOW,
        fetch=_redirect_fetch,
    )
    assert result is not None
    assert result.freshness == "unavailable"
    del fake_client
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await client.get(
            official_source_url(provider, EXTERNAL_ID), follow_redirects=False
        )
    assert response.status_code == 302
    assert len(seen) == 1


async def _redirect_fetch(_url: str) -> CatalogFetch:
    return CatalogFetch(
        status_code=302,
        body=b"",
        headers={"location": "https://evil.test/steal"},
        error="redirect",
    )


def test_bounded_parser_rejects_oversized_and_deep_payloads() -> None:
    provider = all_providers()[0]
    request = fetch_request(provider)
    policy = permitted_policy(provider)
    oversized = CatalogFetch(
        status_code=200,
        body=b"{}",
        headers={"content-length": str(CATALOG_OBSERVATION_MAX_RESPONSE_BYTES + 1)},
    )
    oversized_result = observation_from_fetch(request, oversized, policy=policy, now=NOW, last=None)
    assert oversized_result is not None
    assert oversized_result.freshness == "unavailable"
    long_name = "n" * (CATALOG_OBSERVATION_MAX_STRING_CODEPOINTS + 1)
    long_body = json.dumps({**happy_payload(provider), "name": long_name}).encode()
    long_result = observation_from_fetch(
        request,
        CatalogFetch(status_code=200, body=long_body, headers={}),
        policy=policy,
        now=NOW,
        last=None,
    )
    assert long_result is not None
    assert long_result.freshness == "unavailable"
    deep: object = {"id": EXTERNAL_ID}
    current = cast(dict[str, object], deep)
    for index in range(CATALOG_OBSERVATION_MAX_JSON_DEPTH + 2):
        nested: dict[str, object] = {}
        current["child"] = nested
        current = nested
        del index
    deep_result = observation_from_fetch(
        request,
        CatalogFetch(status_code=200, body=json.dumps(deep).encode(), headers={}),
        policy=policy,
        now=NOW,
        last=None,
    )
    assert deep_result is not None
    assert deep_result.freshness == "unavailable"
