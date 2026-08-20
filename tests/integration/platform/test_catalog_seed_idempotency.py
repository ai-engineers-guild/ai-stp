"""Integration tests for first-party seed idempotency (REQ-2110)."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.catalog_seed import load_first_party_seed, seed_corpus
from ai_stp_platform.models import CatalogMetadata

pytestmark = pytest.mark.platform


@pytest.mark.asyncio
async def test_seed_rerun_creates_no_duplicate_rows(db_session: AsyncSession) -> None:
    first = await load_first_party_seed(db_session)
    second = await load_first_party_seed(db_session)
    assert first.created_versions == len(seed_corpus())
    assert second.created_versions == 0
    assert second.reused_versions == len(seed_corpus())
    count = await db_session.scalar(select(func.count()).select_from(CatalogMetadata))
    assert count == len(seed_corpus())
    rows = (await db_session.scalars(select(CatalogMetadata))).all()
    for row in rows:
        assert row.visibility == "public"
        assert row.trust_lane == "experimental"
        assert row.component_verified is False
        assert row.author_verified is False
