"""A receipt cannot bypass current catalog access."""

# pyright: reportArgumentType=false

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ai_stp_api.errors import ApiError
from ai_stp_api.slices.corporate import assignments, service
from ai_stp_contracts.corporate import (
    CorporateCatalogAssignmentQuery,
    CorporateCatalogAssignmentRequest,
)
from ai_stp_foundation.ids import new_id


@pytest.mark.asyncio
async def test_assignment_replay_rechecks_catalog_access(monkeypatch: pytest.MonkeyPatch) -> None:
    authorize = AsyncMock(return_value=(None, SimpleNamespace(response_body={})))
    visible = AsyncMock(return_value=None)
    monkeypatch.setattr(service, "authorize_idempotent", authorize)
    monkeypatch.setattr(assignments, "get_visible_metadata", visible)
    payload = CorporateCatalogAssignmentRequest(
        subject_kind="employee",
        subject_id=new_id("account"),
        object_kind="setup",
        stable_id=new_id("setup"),
        version="1.0",
        expected_revision=0,
        authorization_revision=1,
        idempotency_key="assignment-fixture",
    )
    db = AsyncMock()
    ctx = SimpleNamespace(account_id=new_id("account"))
    with pytest.raises(ApiError, match="catalog version is unavailable"):
        await assignments.write_assignment(
            db, ctx=ctx, organization_id=new_id("organization"), payload=payload, request_id=None
        )  # type: ignore[arg-type]
    visible.assert_awaited_once()
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_assignment_read_filters_catalog_and_marks_team_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "read_member", AsyncMock())
    visible = AsyncMock(
        side_effect=[
            None,
            SimpleNamespace(name="Mobile Development", published_at=True, lifecycle_state="active"),
        ]
    )
    monkeypatch.setattr(assignments, "get_visible_metadata", visible)
    rows = [
        SimpleNamespace(
            id="hidden_assignment",
            object_kind="setup",
            stable_id=new_id("setup"),
            version="1.0",
            state="current",
            revision=1,
            team_id=None,
        ),
        SimpleNamespace(
            id="team_assignment",
            object_kind="setup",
            stable_id=new_id("setup"),
            version="1.0",
            state="current",
            revision=2,
            team_id="operation_00000000000000000000000001",
        ),
    ]
    db = AsyncMock()
    db.scalars.return_value = SimpleNamespace(all=lambda: rows)
    query = CorporateCatalogAssignmentQuery(subject_kind="employee", subject_id=new_id("account"))
    result = await assignments.list_assignments(
        db,
        ctx=SimpleNamespace(account_id=new_id("account")),
        organization_id=new_id("organization"),
        query=query,
        request_id=None,
    )  # type: ignore[arg-type]
    assert result.total == 1
    assert result.items[0].display_name == "Mobile Development"
    assert result.items[0].source_team_id == "operation_00000000000000000000000001"
