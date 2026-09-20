"""A receipt cannot bypass current catalog access."""

# pyright: reportArgumentType=false

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.slices.corporate import assignments, service
from ai_stp_contracts.corporate import (
    CorporateAssignmentPlanRequest,
    CorporateCatalogAssignmentQuery,
    CorporateCatalogAssignmentRequest,
    CorporateDistributionRequest,
    CorporatePlanMaterializedItem,
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
        "passport_digest": None,
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


def _plan_request(**overrides: object) -> CorporateAssignmentPlanRequest:
    base: dict[str, object] = {
        "account_id": new_id("account"),
        "harness": "claude-code",
    }
    base.update(overrides)
    return CorporateAssignmentPlanRequest.model_validate(base)


def _scalars(items: list[object]) -> SimpleNamespace:
    return SimpleNamespace(all=lambda: items)


async def _run_plan(
    monkeypatch: pytest.MonkeyPatch,
    *,
    rows: list[object],
    teams: list[object] | None = None,
    eligible: dict[str, list[tuple[str, str]]] | None = None,
    payload: CorporateAssignmentPlanRequest,
):
    monkeypatch.setattr(service, "read_member", AsyncMock())
    db = AsyncMock()
    db.scalars.side_effect = [_scalars(list(teams or [])), _scalars(list(rows))]
    versions = dict(eligible or {})

    def _by_line(
        _db: object, *, object_kind: str, stable_id: str, account_id: str
    ) -> list[tuple[str, str]]:
        return list(versions.get(stable_id, []))

    monkeypatch.setattr(assignments, "_eligible_versions", AsyncMock(side_effect=_by_line))
    monkeypatch.setattr(assignments, "get_visible_metadata", AsyncMock(return_value=None))
    organization_id = new_id("organization")
    result = await assignments.plan_assignments(
        db,
        ctx=SimpleNamespace(account_id=new_id("account")),
        organization_id=organization_id,
        payload=payload,
        request_id=None,
    )
    return result, organization_id


@pytest.mark.asyncio
async def test_plan_classifies_outdated_install_and_remove(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_id = new_id("setup")
    component_id = new_id("component")
    rows = [
        _source(
            stable_id=setup_id,
            version="2.0",
            passport_digest="sha256:" + "1" * 64,
        ),
        _source(stable_id=component_id, object_kind="component", version="1.0"),
    ]
    materialized = [
        CorporatePlanMaterializedItem(object_kind="setup", stable_id=setup_id, version="1.0"),
        CorporatePlanMaterializedItem(
            object_kind="component", stable_id=new_id("component"), version="3.0"
        ),
    ]
    result, _ = await _run_plan(
        monkeypatch,
        rows=rows,
        eligible={
            setup_id: [("1.0", "sha256:" + "0" * 64), ("2.0", "sha256:" + "1" * 64)],
            component_id: [("1.0", "sha256:" + "0" * 64)],
        },
        payload=_plan_request(materialized=materialized),
    )
    assert result.total == 3
    keys = {(item.object_kind, item.stable_id): item for item in result.items}
    assigned = keys[("setup", setup_id)]
    assert assigned.outcome == "outdated"
    assert assigned.action == "update"
    assert assigned.version == "2.0"
    assert assigned.passport_digest == "sha256:" + "1" * 64
    assert assigned.installed_version == "1.0"
    assert assigned.source_scope == "organization"
    missing = keys[("component", component_id)]
    assert missing.outcome == "missing"
    assert missing.action == "install"
    foreign = keys[("component", materialized[1].stable_id)]
    assert foreign.state == "unassigned"
    assert foreign.outcome == "unassigned"
    assert foreign.action == "remove"
    assert foreign.installed_version == "3.0"


@pytest.mark.asyncio
async def test_plan_reports_installed_revoked_and_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = new_id("account")
    installed_id = new_id("setup")
    revoked_id = new_id("setup")
    unsupported_id = new_id("setup")
    rows = [
        _source(
            stable_id=installed_id,
            version="1.0",
            passport_digest="sha256:" + "2" * 64,
        ),
        _source(
            stable_id=revoked_id,
            account_id=account,
            state="retired",
            version="1.0",
            passport_digest="sha256:" + "3" * 64,
        ),
        _source(stable_id=unsupported_id, selector="latest", version=None),
    ]
    materialized = [
        CorporatePlanMaterializedItem(
            object_kind="setup",
            stable_id=installed_id,
            version="1.0",
            passport_digest="sha256:" + "2" * 64,
        ),
        CorporatePlanMaterializedItem(object_kind="setup", stable_id=revoked_id, version="1.0"),
    ]
    result, _ = await _run_plan(
        monkeypatch,
        rows=rows,
        eligible={installed_id: [("1.0", "sha256:" + "2" * 64)]},
        payload=_plan_request(account_id=account, materialized=materialized),
    )
    keys = {(item.object_kind, item.stable_id): item for item in result.items}
    current = keys[("setup", installed_id)]
    assert current.outcome == "installed"
    assert current.action == "none"
    revoked = keys[("setup", revoked_id)]
    assert revoked.state == "revoked"
    assert revoked.outcome == "revoked"
    assert revoked.action == "remove"
    unsupported = keys[("setup", unsupported_id)]
    assert unsupported.state == "assigned"
    assert unsupported.outcome == "unsupported"
    assert unsupported.action == "none"
    assert unsupported.version is None
    assert unsupported.diagnostic is not None


@pytest.mark.asyncio
async def test_plan_is_deterministic_and_sorted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        _source(stable_id=new_id("setup"), version="2.0"),
        _source(stable_id=new_id("component"), object_kind="component", version="1.0"),
    ]
    payload = _plan_request()
    digest = "sha256:" + "4" * 64
    eligible = {row.stable_id: [("1.0", digest), ("2.0", digest)] for row in rows}
    first, organization_id = await _run_plan(
        monkeypatch, rows=rows, eligible=eligible, payload=payload
    )
    second, _ = await _run_plan(monkeypatch, rows=rows, eligible=eligible, payload=payload)
    assert [item.model_dump(mode="json") for item in first.items] == [
        item.model_dump(mode="json") for item in second.items
    ]
    ordering = [(item.object_kind, item.stable_id) for item in first.items]
    assert ordering == sorted(ordering)
    assert first.organization_id == organization_id


@pytest.mark.asyncio
async def test_plan_requires_member_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service,
        "read_member",
        AsyncMock(side_effect=ApiError(ErrorCategory.PERMISSION, "denied")),
    )
    db = AsyncMock()
    with pytest.raises(ApiError, match="denied"):
        await assignments.plan_assignments(
            db,
            ctx=SimpleNamespace(account_id=new_id("account")),
            organization_id=new_id("organization"),
            payload=_plan_request(),
            request_id=None,
        )
    db.scalars.assert_not_called()
