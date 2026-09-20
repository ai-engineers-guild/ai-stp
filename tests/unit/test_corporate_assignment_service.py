"""A receipt cannot bypass current catalog access."""

# pyright: reportArgumentType=false

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_stp_api.errors import ApiError
from ai_stp_api.slices.corporate import assignments, service
from ai_stp_contracts.corporate import (
    CorporateCatalogAssignmentQuery,
    CorporateCatalogAssignmentRequest,
    CorporateDistributionRequest,
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
async def test_assignment_read_keeps_metadata_when_catalog_is_not_visible(
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
            selector="exact",
            version="1.0",
            passport_digest=None,
            harness=None,
            state="current",
            revision=1,
            team_id=None,
        ),
        SimpleNamespace(
            id="team_assignment",
            object_kind="setup",
            stable_id=new_id("setup"),
            selector="exact",
            version="1.0",
            passport_digest=None,
            harness=None,
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
    assert result.total == 2
    assert result.items[0].display_name == rows[0].stable_id
    assert result.items[1].display_name == "Mobile Development"
    assert result.items[1].source_team_id == "operation_00000000000000000000000001"


def _source(**overrides: object) -> SimpleNamespace:
    base: dict[str, object] = {
        "id": new_id("operation"),
        "organization_id": new_id("organization"),
        "account_id": None,
        "team_id": None,
        "project_id": None,
        "technology_id": None,
        "object_kind": "setup",
        "stable_id": new_id("setup"),
        "selector": "exact",
        "version": "1.0",
        "harness": None,
        "state": "current",
        "revision": 1,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _distribution_request(**overrides: object) -> CorporateDistributionRequest:
    base: dict[str, object] = {
        "source_assignment_id": new_id("operation"),
        "action": "assign",
        "dry_run": False,
        "expected_revision": 1,
        "authorization_revision": 1,
        "idempotency_key": "distribution-fixture",
    }
    base.update(overrides)
    return CorporateDistributionRequest.model_validate(base)


@asynccontextmanager
async def _nested_transaction():
    yield


def _db_with_savepoints(**overrides: object) -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.begin_nested = lambda: _nested_transaction()
    for name, value in overrides.items():
        setattr(db, name, value)
    return db


@pytest.mark.asyncio
async def test_distribution_rejects_missing_or_stale_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = SimpleNamespace(account_id=new_id("account"))
    db = AsyncMock()
    db.scalar.return_value = None
    with pytest.raises(ApiError, match="source assignment is unavailable"):
        await assignments.distribute_assignment(
            db,
            ctx=ctx,
            organization_id=new_id("organization"),
            payload=_distribution_request(),
            request_id=None,
        )
    monkeypatch.setattr(
        service,
        "authorize_idempotent",
        AsyncMock(return_value=(SimpleNamespace(), None)),
    )
    db.scalar.return_value = _source(revision=2)
    with pytest.raises(ApiError, match="assignment revision is stale"):
        await assignments.distribute_assignment(
            db,
            ctx=ctx,
            organization_id=new_id("organization"),
            payload=_distribution_request(expected_revision=1),
            request_id=None,
        )
    db.scalar.return_value = _source(state="retired")
    with pytest.raises(ApiError, match="source assignment is retired"):
        await assignments.distribute_assignment(
            db,
            ctx=ctx,
            organization_id=new_id("organization"),
            payload=_distribution_request(),
            request_id=None,
        )


@pytest.mark.asyncio
async def test_distribution_dry_run_plans_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source()
    member = new_id("account")
    db = _db_with_savepoints()
    db.scalar.return_value = source
    db.scalars.side_effect = [
        SimpleNamespace(all=lambda: list[object]()),
        SimpleNamespace(all=lambda: list[object]()),
    ]
    monkeypatch.setattr(
        service,
        "authorize",
        AsyncMock(return_value=(SimpleNamespace(policy_revision=1), None)),
    )
    expanded = AsyncMock(return_value=([member], [], []))
    monkeypatch.setattr(assignments, "_expand_targets", expanded)
    monkeypatch.setattr(assignments, "_target_authorized", AsyncMock(return_value=True))
    result = await assignments.distribute_assignment(
        db,
        ctx=SimpleNamespace(account_id=new_id("account")),
        organization_id=source.organization_id,
        payload=_distribution_request(source_assignment_id=source.id, dry_run=True),
        request_id=None,
    )
    assert result.dry_run is True
    assert result.distribution_id is None
    assert result.counts.applied == 1
    assert result.targets[0].result == "applied"
    assert result.targets[0].state == "pending"
    db.add.assert_not_called()
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_distribution_marks_individual_overrides_conflicted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source()
    member = new_id("account")
    override = _source(account_id=member, id=new_id("operation"))
    db = _db_with_savepoints()
    db.scalar.return_value = source
    db.scalars.side_effect = [
        SimpleNamespace(all=lambda: [override]),
        SimpleNamespace(all=lambda: list[object]()),
    ]
    monkeypatch.setattr(
        service,
        "authorize_idempotent",
        AsyncMock(return_value=(SimpleNamespace(), None)),
    )
    monkeypatch.setattr(assignments, "_expand_targets", AsyncMock(return_value=([member], [], [])))
    monkeypatch.setattr(assignments, "_target_authorized", AsyncMock(return_value=True))
    monkeypatch.setattr(assignments, "emit_audit", AsyncMock())
    monkeypatch.setattr(service, "store_mutation_receipt", AsyncMock())
    result = await assignments.distribute_assignment(
        db,
        ctx=SimpleNamespace(account_id=new_id("account")),
        organization_id=source.organization_id,
        payload=_distribution_request(source_assignment_id=source.id),
        request_id=None,
    )
    assert result.counts.conflicted == 1
    assert result.counts.applied == 0
    assert result.targets[0].result == "conflicted"
    assert result.targets[0].overriding_assignment_id == override.id


@pytest.mark.asyncio
async def test_distribution_replay_returns_the_durable_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source()
    stored: dict[str, object] = {
        "schema_version": 1,
        "distribution_id": "distribution-fixture",
        "organization_id": source.organization_id,
        "source_assignment_id": source.id,
        "action": "assign",
        "dry_run": False,
        "source_revision": 1,
        "targets": [
            {
                "target_kind": "employee",
                "target_id": new_id("account"),
                "result": "applied",
                "state": "pending",
            }
        ],
        "exclusions": [],
        "counts": {"applied": 1, "skipped": 0, "conflicted": 0, "denied": 0, "failed": 0},
    }
    db = _db_with_savepoints()
    db.scalar.return_value = source
    monkeypatch.setattr(
        service,
        "authorize_idempotent",
        AsyncMock(
            return_value=(
                SimpleNamespace(),
                SimpleNamespace(response_body=stored),
            )
        ),
    )
    expanded = AsyncMock()
    monkeypatch.setattr(assignments, "_expand_targets", expanded)
    result = await assignments.distribute_assignment(
        db,
        ctx=SimpleNamespace(account_id=new_id("account")),
        organization_id=source.organization_id,
        payload=_distribution_request(source_assignment_id=source.id),
        request_id=None,
    )
    assert result.distribution_id == "distribution-fixture"
    assert result.counts.applied == 1
    expanded.assert_not_awaited()
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_distribution_revoke_retry_replays_instead_of_failing_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The first revoke retired the source and bumped its revision; a retry with
    # the same key must reach the receipt before the revision precondition.
    source = _source(state="retired", revision=4)
    stored = {
        "schema_version": 1,
        "distribution_id": "distribution-fixture",
        "organization_id": source.organization_id,
        "source_assignment_id": source.id,
        "action": "revoke",
        "dry_run": False,
        "source_revision": 3,
        "targets": list[object](),
        "exclusions": list[object](),
        "counts": {"applied": 0, "skipped": 0, "conflicted": 0, "denied": 0, "failed": 0},
    }
    db = _db_with_savepoints()
    db.scalar.return_value = source
    monkeypatch.setattr(
        service,
        "authorize_idempotent",
        AsyncMock(
            return_value=(
                SimpleNamespace(),
                SimpleNamespace(response_body=stored),
            )
        ),
    )
    result = await assignments.distribute_assignment(
        db,
        ctx=SimpleNamespace(account_id=new_id("account")),
        organization_id=source.organization_id,
        payload=_distribution_request(
            source_assignment_id=source.id, action="revoke", expected_revision=3
        ),
        request_id=None,
    )
    assert result.action == "revoke"
    assert result.source_revision == 3
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_distribution_revoke_marks_only_live_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(revision=3)
    live_member = new_id("account")
    idle_member = new_id("account")
    live_row = SimpleNamespace(
        target_kind="employee",
        target_id=live_member,
        operation_revision=3,
        action="assign",
        result="applied",
        state="pending",
    )
    db = _db_with_savepoints()
    db.scalar.return_value = source
    db.scalars.side_effect = [
        SimpleNamespace(all=lambda: list[object]()),
        SimpleNamespace(all=lambda: [live_row]),
    ]
    monkeypatch.setattr(
        service,
        "authorize_idempotent",
        AsyncMock(return_value=(SimpleNamespace(), None)),
    )
    monkeypatch.setattr(
        assignments,
        "_expand_targets",
        AsyncMock(return_value=([live_member, idle_member], [], [])),
    )
    monkeypatch.setattr(assignments, "_target_authorized", AsyncMock(return_value=True))
    monkeypatch.setattr(assignments, "emit_audit", AsyncMock())
    monkeypatch.setattr(service, "store_mutation_receipt", AsyncMock())
    result = await assignments.distribute_assignment(
        db,
        ctx=SimpleNamespace(account_id=new_id("account")),
        organization_id=source.organization_id,
        payload=_distribution_request(
            source_assignment_id=source.id, action="revoke", expected_revision=3
        ),
        request_id=None,
    )
    assert result.counts.applied == 1
    assert result.counts.skipped == 1
    live = next(item for item in result.targets if item.target_id == live_member)
    idle = next(item for item in result.targets if item.target_id == idle_member)
    assert live.result == "applied"
    assert live.state == "revoked"
    assert idle.result == "skipped"
    assert source.state == "retired"
    assert source.revision == 4


@pytest.mark.asyncio
async def test_distribution_repeat_assign_skips_without_persisting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A second assign at the same revision (new idempotency key) must report
    # skipped, not persist a colliding row, and not degrade to failed.
    source = _source(revision=3)
    member = new_id("account")
    live_row = SimpleNamespace(
        target_kind="employee",
        target_id=member,
        operation_revision=3,
        action="assign",
        result="applied",
        state="pending",
    )
    db = _db_with_savepoints()
    db.scalar.return_value = source
    db.scalars.side_effect = [
        SimpleNamespace(all=lambda: list[object]()),
        SimpleNamespace(all=lambda: [live_row]),
    ]
    monkeypatch.setattr(
        service,
        "authorize_idempotent",
        AsyncMock(return_value=(SimpleNamespace(), None)),
    )
    monkeypatch.setattr(assignments, "_expand_targets", AsyncMock(return_value=([member], [], [])))
    monkeypatch.setattr(assignments, "_target_authorized", AsyncMock(return_value=True))
    monkeypatch.setattr(assignments, "emit_audit", AsyncMock())
    receipt = AsyncMock()
    monkeypatch.setattr(service, "store_mutation_receipt", receipt)
    result = await assignments.distribute_assignment(
        db,
        ctx=SimpleNamespace(account_id=new_id("account")),
        organization_id=source.organization_id,
        payload=_distribution_request(source_assignment_id=source.id, expected_revision=3),
        request_id=None,
    )
    assert result.counts.skipped == 1
    assert result.counts.failed == 0
    assert result.targets[0].result == "skipped"
    assert result.targets[0].state == "pending"
    db.add.assert_not_called()
    receipt.assert_awaited_once()


@pytest.mark.asyncio
async def test_distribution_denies_unauthorized_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source()
    member = new_id("account")
    db = _db_with_savepoints()
    db.scalar.return_value = source
    db.scalars.side_effect = [
        SimpleNamespace(all=lambda: list[object]()),
        SimpleNamespace(all=lambda: list[object]()),
    ]
    monkeypatch.setattr(
        service,
        "authorize_idempotent",
        AsyncMock(return_value=(SimpleNamespace(), None)),
    )
    monkeypatch.setattr(assignments, "_expand_targets", AsyncMock(return_value=([member], [], [])))
    monkeypatch.setattr(assignments, "_target_authorized", AsyncMock(return_value=False))
    monkeypatch.setattr(assignments, "emit_audit", AsyncMock())
    monkeypatch.setattr(service, "store_mutation_receipt", AsyncMock())
    result = await assignments.distribute_assignment(
        db,
        ctx=SimpleNamespace(account_id=new_id("account")),
        organization_id=source.organization_id,
        payload=_distribution_request(source_assignment_id=source.id),
        request_id=None,
    )
    assert result.counts.denied == 1
    assert result.targets[0].result == "denied"
    assert result.targets[0].state is None
