"""Catalog enrichment jobs stay off until the policy gate is open."""

from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from tests.unit.platform.catalog_enrichment_fixtures import (
    EXTERNAL_ID,
    NOW,
    all_providers,
    enabling_environ,
    happy_fetch,
)

from ai_stp_platform.queue.states import JobType
from ai_stp_worker.handlers import REGISTRY
from ai_stp_worker.handlers.catalog_enrichment import handle_catalog_enrichment

pytestmark = pytest.mark.platform


class _ForbiddenSession:
    async def execute(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("disabled enrichment must not touch storage")

    def add(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("disabled enrichment must not persist")


@pytest.mark.asyncio
async def test_handler_is_a_noop_while_the_policy_gate_is_closed() -> None:
    provider = all_providers()[0]

    async def fetch(_url: str) -> object:
        raise AssertionError("closed gate must not fetch")

    await handle_catalog_enrichment(
        cast(AsyncSession, _ForbiddenSession()),
        {
            "catalog_metadata_id": 1,
            "references": [{"provider": provider, "external_identifier": EXTERNAL_ID}],
        },
        fetch=fetch,  # type: ignore[arg-type]
        now=NOW,
        environ_map={},
    )
    assert JobType.CATALOG_ENRICHMENT.value == "catalog_enrichment"
    assert REGISTRY[JobType.CATALOG_ENRICHMENT] is handle_catalog_enrichment


@pytest.mark.asyncio
async def test_handler_fetches_only_after_attribution_and_terms_are_present() -> None:
    provider = all_providers()[0]
    seen: list[str] = []

    async def fetch(url: str) -> object:
        seen.append(url)
        return happy_fetch(provider)

    added: list[object] = []

    class _Session:
        async def execute(self, *_args: object, **_kwargs: object) -> object:
            class _Result:
                def scalars(self) -> object:
                    class _Rows:
                        def all(self) -> list[object]:
                            return []

                    return _Rows()

            return _Result()

        def add(self, row: object) -> None:
            added.append(row)

    await handle_catalog_enrichment(
        cast(AsyncSession, _Session()),
        {
            "catalog_metadata_id": 3,
            "references": [{"provider": provider, "external_identifier": EXTERNAL_ID}],
        },
        fetch=fetch,  # type: ignore[arg-type]
        now=NOW,
        environ_map=enabling_environ(provider),
    )
    assert len(seen) == 1
    assert len(added) == 1
