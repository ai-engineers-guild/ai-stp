"""The explicit demo refuses stale targets and preserves real accounts."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from tests.support.corporate_overview_seed import fixture_id, seed_demo


@pytest.mark.asyncio
async def test_demo_refuses_stale_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tests.support.corporate_overview_seed.set_tenant_scope", AsyncMock())
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(
        kind="corporate", state="active", revision=3, display_name="Twinby"
    )
    with pytest.raises(ValueError, match="precondition"):
        await seed_demo(db, "organization_00000000000000000000000001", 2)
    db.scalars.assert_not_awaited()
    db.add.assert_not_called()


def test_demo_identity_is_repeatable_and_tenant_scoped() -> None:
    from ai_stp_foundation.ids import is_valid_id

    identity = fixture_id("account", "tenant-a:Alex Kim")
    assert identity == fixture_id("account", "tenant-a:Alex Kim")
    assert identity != fixture_id("account", "tenant-b:Alex Kim")
    assert is_valid_id(identity, "account")
