"""Queued catalog metadata refresh (SPEC-050). Disabled until the policy gate."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from os import environ
from typing import cast

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.federation import CatalogExternalCoordinate
from ai_stp_platform.catalog_enrichment import (
    CatalogFetchRequest,
    FetchFn,
    apply_observation,
    observation_from_row,
    policies_from_environ,
    refresh_many,
)
from ai_stp_platform.models import CatalogExternalObservation


async def handle_catalog_enrichment(
    session: AsyncSession,
    payload: Mapping[str, object],
    *,
    fetch: FetchFn | None = None,
    now: datetime | None = None,
    persist: bool = True,
    environ_map: Mapping[str, str] | None = None,
) -> None:
    """Refresh exact stored coordinates. No-op while the production gate is closed."""
    policies = policies_from_environ(environ_map if environ_map is not None else environ)
    if not any(policy.permits() for policy in policies.values()):
        return
    requests = _requests_from_payload(payload)
    if not requests:
        return
    catalog_metadata_id = payload.get("catalog_metadata_id")
    rows: dict[str, CatalogExternalObservation] = {}
    last_valid = {}
    if persist and isinstance(catalog_metadata_id, int):
        rows = await _load_last(session, catalog_metadata_id)
        last_valid = {key: observation_from_row(row) for key, row in rows.items()}
    observations = await refresh_many(
        requests,
        policies=policies,
        now=now or datetime.now(UTC),
        fetch=fetch,
        last_valid=last_valid,
    )
    if persist and isinstance(catalog_metadata_id, int):
        for observation in observations:
            session.add(
                apply_observation(rows.get(observation.dedup_key), observation, catalog_metadata_id)
            )


def _requests_from_payload(payload: Mapping[str, object]) -> list[CatalogFetchRequest]:
    raw = payload.get("references")
    if not isinstance(raw, list):
        return []
    requests: list[CatalogFetchRequest] = []
    for item in cast(list[object], raw):
        if not isinstance(item, dict):
            continue
        reference = cast(dict[str, object], item)
        provider = reference.get("provider")
        identifier = reference.get("external_identifier")
        if not isinstance(provider, str) or not isinstance(identifier, str):
            continue
        try:
            coordinate = CatalogExternalCoordinate.model_validate(
                {"provider": provider, "external_identifier": identifier}
            )
        except ValidationError:
            continue
        source_url = reference.get("source_url")
        requests.append(
            CatalogFetchRequest(
                coordinate=coordinate,
                source_url=source_url if isinstance(source_url, str) else None,
            )
        )
    return requests


async def _load_last(
    session: AsyncSession, catalog_metadata_id: int
) -> dict[str, CatalogExternalObservation]:
    rows = await session.execute(
        select(CatalogExternalObservation).where(
            CatalogExternalObservation.catalog_metadata_id == catalog_metadata_id
        )
    )
    found = rows.scalars().all()
    return {row.dedup_key: row for row in found}
