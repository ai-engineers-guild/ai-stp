"""External service registry and country roof integration (#269)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.errors import CATEGORY_CODE, ErrorCategory
from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_api.slices.owner import service as owner_service
from ai_stp_contracts.catalog import CATALOG_UNSPECIFIED_FILTER
from ai_stp_contracts.owner import OwnerExternalProductCreateRequest
from ai_stp_foundation.ids import new_id
from ai_stp_platform.catalog_seed import FIXTURE_COMPONENT_ID, load_first_party_seed
from ai_stp_platform.models import Account, CatalogMetadata

pytestmark = pytest.mark.platform


def _experimental_ids(payload: Mapping[str, Any]) -> list[str]:
    experimental = payload.get("experimental")
    if not isinstance(experimental, list):
        return []
    ids: list[str] = []
    for raw in cast(list[Any], experimental):
        if not isinstance(raw, dict):
            continue
        stable_id = cast(dict[str, Any], raw).get("stable_id")
        if isinstance(stable_id, str):
            ids.append(stable_id)
    return ids


async def _owner(sessionmaker: async_sessionmaker[AsyncSession]) -> tuple[str, str]:
    async with sessionmaker() as db:
        account = Account(id=new_id("account"))
        db.add(account)
        await db.flush()
        token = await issue_session(db, account_id=account.id, device_id=None, ttl_seconds=3600)
        await db.commit()
        return account.id, token.raw_token


async def _seed_service(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    name: str,
    primary_url: str,
    country_codes: list[str],
) -> None:
    async with sessionmaker() as db:
        await owner_service.create_external_product(
            db,
            body=OwnerExternalProductCreateRequest(
                name=name,
                primary_url=primary_url,
                country_codes=country_codes,
            ),
        )


@pytest.mark.asyncio
async def test_owner_creates_and_attaches_service_visible_under_country(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    async with sessionmaker() as db:
        await load_first_party_seed(db)
        metadata = await db.scalar(
            select(CatalogMetadata).where(
                CatalogMetadata.object_kind == "component",
                CatalogMetadata.stable_id == FIXTURE_COMPONENT_ID,
            )
        )
        assert metadata is not None
        issued = await issue_session(
            db, account_id=metadata.owner_account_id, device_id=None, ttl_seconds=3600
        )
        await db.commit()
    stable_id = FIXTURE_COMPONENT_ID
    token = issued.raw_token
    headers = {"Authorization": f"Bearer {token}"}
    await _seed_service(
        sessionmaker,
        name="Kaspi",
        primary_url="https://KASPI.KZ/shop/?utm=x",
        country_codes=["KZ"],
    )
    removed = await client.post("/v1/owner/external-products", headers=headers, json={})
    assert removed.status_code == 404
    attached = await client.put(
        f"/v1/owner/objects/component/{stable_id}/external-products",
        headers=headers,
        json={"schema_version": 1, "canonical_domains": ["kaspi.kz"]},
    )
    assert attached.status_code == 200
    country = await client.get("/v1/catalog/countries/KZ")
    assert country.status_code == 200
    assert country.json()["services"][0]["canonical_domain"] == "kaspi.kz"
    assert country.json()["objects"][0]["stable_id"] == stable_id
    service = await client.get("/v1/catalog/services/kaspi.kz")
    assert service.status_code == 200
    assert service.json()["objects"][0]["stable_id"] == stable_id
    detail = await client.get(f"/v1/catalog/components/{stable_id}")
    assert detail.status_code == 200
    assert detail.json()["country_codes"] == ["KZ"]
    assert detail.json()["services"][0]["canonical_domain"] == "kaspi.kz"
    filtered = await client.get(
        "/v1/catalog/components",
        params={
            "country_code": "KZ",
            "service_domain": "kaspi.kz",
            "page": 1,
            "include_experimental": "true",
        },
    )
    assert filtered.status_code == 200
    assert stable_id in _experimental_ids(filtered.json())
    current = await client.get(
        f"/v1/owner/objects/component/{stable_id}/external-products", headers=headers
    )
    assert current.status_code == 200
    assert current.json()["items"][0]["canonical_domain"] == "kaspi.kz"


@pytest.mark.asyncio
async def test_catalog_search_accepts_multi_and_unspecified_relation_filters(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    async with sessionmaker() as db:
        await load_first_party_seed(db)
        metadata = await db.scalar(
            select(CatalogMetadata).where(
                CatalogMetadata.object_kind == "component",
                CatalogMetadata.stable_id == FIXTURE_COMPONENT_ID,
            )
        )
        assert metadata is not None
        issued = await issue_session(
            db, account_id=metadata.owner_account_id, device_id=None, ttl_seconds=3600
        )
        await db.commit()
    stable_id = FIXTURE_COMPONENT_ID
    headers = {"Authorization": f"Bearer {issued.raw_token}"}
    await _seed_service(
        sessionmaker, name="Example Pay", primary_url="https://example.com", country_codes=["US"]
    )
    await _seed_service(
        sessionmaker, name="Worldwide", primary_url="https://worldwide.example", country_codes=[]
    )
    attached = await client.put(
        f"/v1/owner/objects/component/{stable_id}/external-products",
        headers=headers,
        json={
            "schema_version": 1,
            "canonical_domains": ["example.com", "worldwide.example"],
        },
    )
    assert attached.status_code == 200

    multi = await client.get(
        "/v1/catalog/components",
        params=[
            ("country_codes", "US"),
            ("country_codes", "KZ"),
            ("service_domains", "example.com"),
            ("include_experimental", "true"),
            ("page", "1"),
        ],
    )
    assert multi.status_code == 200
    assert stable_id in _experimental_ids(multi.json())

    singleton_and_list = await client.get(
        "/v1/catalog/components",
        params={
            "country_code": "US",
            "country_codes": "KZ",
            "service_domain": "example.com",
            "include_experimental": "true",
            "page": 1,
        },
    )
    assert singleton_and_list.status_code == 200
    assert stable_id in _experimental_ids(singleton_and_list.json())

    unspecified_country = await client.get(
        "/v1/catalog/components",
        params={
            "country_codes": CATALOG_UNSPECIFIED_FILTER,
            "include_experimental": "true",
            "page": 1,
        },
    )
    assert unspecified_country.status_code == 200
    assert stable_id in _experimental_ids(unspecified_country.json())

    unspecified_service = await client.get(
        "/v1/catalog/components",
        params={
            "service_domains": CATALOG_UNSPECIFIED_FILTER,
            "include_experimental": "true",
            "page": 1,
        },
    )
    assert unspecified_service.status_code == 200
    assert stable_id not in _experimental_ids(unspecified_service.json())

    and_mismatch = await client.get(
        "/v1/catalog/components",
        params={
            "service_domains": CATALOG_UNSPECIFIED_FILTER,
            "country_codes": "US",
            "include_experimental": "true",
            "page": 1,
        },
    )
    assert and_mismatch.status_code == 200
    assert stable_id not in _experimental_ids(and_mismatch.json())

    paged = await client.get(
        "/v1/catalog/components",
        params={
            "include_experimental": "true",
            "page_size": 1,
        },
    )
    assert paged.status_code == 200
    cursor = paged.json()["page"]["next_cursor"]
    assert cursor is not None
    same_signature = await client.get(
        "/v1/catalog/components",
        params={
            "include_experimental": "true",
            "cursor": cursor,
            "page_size": 1,
        },
    )
    assert same_signature.status_code == 200
    mismatched_signature = await client.get(
        "/v1/catalog/components",
        params={
            "country_codes": "US",
            "include_experimental": "true",
            "cursor": cursor,
            "page_size": 1,
        },
    )
    assert mismatched_signature.status_code == 400
    assert mismatched_signature.json()["error"]["code"] == CATEGORY_CODE[ErrorCategory.VALIDATION]


@pytest.mark.asyncio
async def test_service_creation_rejects_deep_link(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    _owner_id, token = await _owner(sessionmaker)
    response = await client.post(
        "/v1/requests",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "schema_version": 1,
            "topic": "service_request",
            "service": {
                "name": "Deep",
                "primary_url": "https://kaspi.kz/shop/item",
                "description_ru": "Описание",
                "description_en": "Description",
                "source_url": "https://kaspi.kz/about",
                "country_codes": ["KZ"],
            },
            "idempotency_key": "deep-service-request",
        },
    )
    assert response.status_code == 400
