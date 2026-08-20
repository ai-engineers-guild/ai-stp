"""Shared SPEC-050 conformance suite for every catalog metadata adapter."""

from __future__ import annotations

import json
from urllib.parse import unquote

import httpx
import pytest
from tests.unit.platform.catalog_enrichment_fixtures import (
    EXTERNAL_ID,
    NOW,
    all_providers,
    coordinate,
    fetch_request,
    happy_fetch,
    happy_payload,
    permitted_policy,
)

from ai_stp_contracts.federation import (
    CATALOG_OBSERVATION_MAX_COLLECTION_ITEMS,
    CATALOG_OBSERVATION_MAX_RESPONSE_BYTES,
)
from ai_stp_platform.catalog_enrichment import (
    CatalogFetch,
    observation_from_fetch,
    official_source_url,
    refresh_one,
)

pytestmark = pytest.mark.platform


@pytest.mark.parametrize("provider", all_providers())
def test_happy_payload_projects_closed_observation(provider: str) -> None:
    observation = observation_from_fetch(
        fetch_request(provider),
        happy_fetch(provider),
        policy=permitted_policy(provider),
        now=NOW,
        last=None,
    )
    assert observation is not None
    assert observation.provider == provider
    assert observation.external_identifier == EXTERNAL_ID
    assert observation.dedup_key == coordinate(provider).dedup_key
    assert observation.source_url == official_source_url(provider, EXTERNAL_ID)
    assert observation.freshness == "fresh"
    assert observation.fetched_at == observation.checked_at
    assert observation.expires_at is not None


@pytest.mark.parametrize("provider", all_providers())
def test_malformed_and_non_object_payloads_are_unavailable(provider: str) -> None:
    request = fetch_request(provider)
    policy = permitted_policy(provider)
    for body in (b"{", b"[]", b"null", b""):
        result = observation_from_fetch(
            request,
            CatalogFetch(status_code=200, body=body, headers={}),
            policy=policy,
            now=NOW,
            last=None,
        )
        assert result is not None
        assert result.freshness == "unavailable"
        assert result.fetched_at is None


@pytest.mark.parametrize("provider", all_providers())
def test_oversized_body_and_collection_are_unavailable(provider: str) -> None:
    request = fetch_request(provider)
    policy = permitted_policy(provider)
    too_big = CatalogFetch(
        status_code=200,
        body=b"{" + b"x" * (CATALOG_OBSERVATION_MAX_RESPONSE_BYTES + 1) + b"}",
        headers={},
    )
    too_big_result = observation_from_fetch(request, too_big, policy=policy, now=NOW, last=None)
    assert too_big_result is not None
    assert too_big_result.freshness == "unavailable"
    wide = {"id": EXTERNAL_ID} | {
        f"k{index}": index for index in range(CATALOG_OBSERVATION_MAX_COLLECTION_ITEMS)
    }
    wide_result = observation_from_fetch(
        request,
        CatalogFetch(status_code=200, body=json.dumps(wide).encode(), headers={}),
        policy=policy,
        now=NOW,
        last=None,
    )
    assert wide_result is not None
    assert wide_result.freshness == "unavailable"


@pytest.mark.parametrize("provider", all_providers())
def test_unknown_fields_are_dropped_and_never_executed(provider: str) -> None:
    payload = happy_payload(provider) | {
        "artifact": "bytes",
        "eval": "__import__('os').system('id')",
        "trust_lane": "authoritative",
        "component_verified": True,
    }
    observation = observation_from_fetch(
        fetch_request(provider),
        CatalogFetch(status_code=200, body=json.dumps(payload).encode(), headers={}),
        policy=permitted_policy(provider),
        now=NOW,
        last=None,
    )
    assert observation is not None
    assert observation.freshness == "fresh"
    assert observation.component_verified is False
    assert observation.author_verified is False
    assert "eval" not in observation.model_dump()
    assert "artifact" not in observation.model_dump()


@pytest.mark.parametrize("provider", all_providers())
def test_exact_coordinate_mismatch_does_not_bind_another_identity(provider: str) -> None:
    payload = happy_payload(provider, "pkg:other")
    last = observation_from_fetch(
        fetch_request(provider),
        happy_fetch(provider),
        policy=permitted_policy(provider),
        now=NOW,
        last=None,
    )
    result = observation_from_fetch(
        fetch_request(provider),
        CatalogFetch(status_code=200, body=json.dumps(payload).encode(), headers={}),
        policy=permitted_policy(provider),
        now=NOW,
        last=last,
    )
    assert result is not None
    assert result.freshness == "unavailable"
    assert result.external_identifier == EXTERNAL_ID
    assert result.display_name == last.display_name if last is not None else None


@pytest.mark.parametrize("provider", all_providers())
@pytest.mark.asyncio
async def test_timeout_is_unavailable_and_keeps_last_valid(provider: str) -> None:
    last = observation_from_fetch(
        fetch_request(provider),
        happy_fetch(provider),
        policy=permitted_policy(provider),
        now=NOW,
        last=None,
    )
    assert last is not None

    async def boom(_url: str) -> CatalogFetch:
        raise httpx.TimeoutException("connect")

    result = await refresh_one(
        fetch_request(provider),
        policy=permitted_policy(provider),
        now=NOW,
        fetch=boom,
        last=last,
    )
    assert result is not None
    assert result.freshness == "unavailable"
    assert result.display_name == last.display_name
    assert result.fetched_at == last.fetched_at


@pytest.mark.parametrize("provider", all_providers())
def test_unofficial_source_url_cannot_redirect_the_coordinate(provider: str) -> None:
    request = fetch_request(provider)
    request = type(request)(
        coordinate=request.coordinate,
        source_url="https://evil.test/" + EXTERNAL_ID,
    )
    result = observation_from_fetch(
        request,
        happy_fetch(provider),
        policy=permitted_policy(provider),
        now=NOW,
        last=None,
    )
    assert result is not None
    assert result.freshness == "unavailable"
    assert unquote(result.source_url).endswith(EXTERNAL_ID)
    assert "evil.test" not in result.source_url
