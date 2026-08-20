"""Deterministic catalog-adapter fixtures. No live network and no vendor registry."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from ai_stp_contracts.federation import (
    CATALOG_ADAPTER_CACHE_TTL_SECONDS,
    CATALOG_METADATA_PROVIDERS,
    CatalogExternalCoordinate,
)
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.catalog_enrichment import (
    PROVIDER_HOSTS,
    CatalogAdapterPolicy,
    CatalogFetch,
    CatalogFetchRequest,
    official_source_url,
)

NOW = datetime(2026, 8, 17, 12, 0, 0, tzinfo=UTC)
EXTERNAL_ID = "pkg:exact-1"


def permitted_policy(provider: str) -> CatalogAdapterPolicy:
    host = PROVIDER_HOSTS[provider]
    return CatalogAdapterPolicy(
        enabled=True,
        attribution=f"{provider} catalog observation",
        terms_url=f"https://{host}/terms",
    )


def coordinate(provider: str, external_identifier: str = EXTERNAL_ID) -> CatalogExternalCoordinate:
    return CatalogExternalCoordinate.model_validate(
        {"provider": provider, "external_identifier": external_identifier}
    )


def fetch_request(provider: str, external_identifier: str = EXTERNAL_ID) -> CatalogFetchRequest:
    return CatalogFetchRequest(
        coordinate=coordinate(provider, external_identifier),
        source_url=official_source_url(provider, external_identifier),
    )


def happy_payload(provider: str, external_identifier: str = EXTERNAL_ID) -> dict[str, object]:
    id_key = "slug" if provider == "nori" else "id"
    return {
        id_key: external_identifier,
        "name": f"{provider}-name",
        "description": f"{provider}-summary",
        "homepage": f"https://{PROVIDER_HOSTS[provider]}/home",
        "repository": "https://github.com/example/tool",
        "published_at": format_timestamp(NOW - timedelta(days=2)),
        "updated_at": format_timestamp(NOW - timedelta(hours=3)),
        "installs": 4,
        "state": "active",
        "content": "must-not-execute()",
        "author_verified": True,
        "install_command": "curl | sh",
    }


def happy_fetch(provider: str, external_identifier: str = EXTERNAL_ID) -> CatalogFetch:
    return CatalogFetch(
        status_code=200,
        body=json.dumps(happy_payload(provider, external_identifier)).encode(),
        headers={"content-type": "application/json"},
    )


def enabling_environ(provider: str) -> dict[str, str]:
    policy = permitted_policy(provider)
    prefix = f"AI_STP_CATALOG_ENRICHMENT_{provider.upper()}_"
    assert policy.attribution is not None
    assert policy.terms_url is not None
    return {
        "AI_STP_CATALOG_ENRICHMENT_ENABLED": "true",
        f"{prefix}ATTRIBUTION": policy.attribution,
        f"{prefix}TERMS_URL": policy.terms_url,
    }


def all_providers() -> tuple[str, ...]:
    return CATALOG_METADATA_PROVIDERS


def ttl_later() -> datetime:
    return NOW + timedelta(seconds=CATALOG_ADAPTER_CACHE_TTL_SECONDS + 1)
