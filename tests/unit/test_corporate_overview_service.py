"""Graph discovery authorizes before querying and consumes assignment pagination."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import assignments, overview, service
from ai_stp_contracts.corporate import CorporateCatalogAssignmentList
from ai_stp_foundation.ids import new_id
from ai_stp_platform.organization_models import CorporateTeam, Organization


@pytest.mark.asyncio
async def test_denied_organization_never_queries_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    monkeypatch.setattr(
        service,
        "authorize",
        AsyncMock(side_effect=ApiError(ErrorCategory.PERMISSION, "denied")),
    )
    ctx = AuthContext(new_id("account"), "session", None, "active", False, False)
    with pytest.raises(ApiError):
        await overview.read_overview(
            db, ctx=ctx, organization_id=new_id("organization"), request_id=None
        )
    db.scalars.assert_not_awaited()
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("include_assignments", [True, False])
async def test_hidden_projects_and_all_assignment_pages(
    monkeypatch: pytest.MonkeyPatch,
    include_assignments: bool,
) -> None:
    organization_id, project_id, hidden_id = (
        new_id("organization"),
        new_id("remote_project"),
        new_id("remote_project"),
    )
    organization = Organization(
        id=organization_id, display_name="Acme", kind="corporate", state="active", policy_revision=1
    )
    monkeypatch.setattr(service, "authorize", AsyncMock(return_value=(organization, None)))

    def permission_check(*args: Any, **kwargs: Any) -> bool:
        return kwargs["permission"] == "project.read" and kwargs["scope_id"] == project_id

    def empty_rows() -> list[Any]:
        return []

    permissions = AsyncMock(side_effect=permission_check)
    monkeypatch.setattr(overview, "has_corporate_permission", permissions)
    db = AsyncMock()
    db.scalars.side_effect = [
        SimpleNamespace(
            all=lambda: [
                SimpleNamespace(id=project_id, name="Visible"),
                SimpleNamespace(id=hidden_id, name="Secret"),
            ]
        ),
        SimpleNamespace(all=empty_rows),
        SimpleNamespace(all=empty_rows),
    ]
    assignment = {
        "assignment_id": new_id("operation"),
        "organization_id": organization_id,
        "subject_kind": "project",
        "subject_id": project_id,
        "object_kind": "setup",
        "stable_id": new_id("setup"),
        "version": "1.0",
        "state": "current",
        "revision": 1,
    }
    pages = AsyncMock(
        side_effect=[
            CorporateCatalogAssignmentList.model_validate({"items": [assignment], "total": 2}),
            CorporateCatalogAssignmentList.model_validate(
                {"items": [{**assignment, "assignment_id": new_id("operation")}], "total": 2}
            ),
        ]
    )
    monkeypatch.setattr(assignments, "list_assignments", pages)
    ctx = AuthContext(new_id("account"), "session", None, "active", False, False)
    graph = await overview.read_overview(
        db,
        ctx=ctx,
        organization_id=organization_id,
        request_id=None,
        include_assignments=include_assignments,
    )
    assert [node.name for node in graph.nodes] == ["Visible"]
    assert len(graph.nodes[0].assignments) == (2 if include_assignments else 0)
    assert graph.nodes[0].assignments_readable is include_assignments
    assert [call.kwargs["query"].offset for call in pages.await_args_list] == (
        [0, 1] if include_assignments else []
    )
    assert all(
        call.kwargs["organization_id"] == organization_id for call in permissions.await_args_list
    )


@pytest.mark.asyncio
async def test_team_leads_are_not_limited_before_authorization() -> None:
    db = AsyncMock()
    leads = [new_id("account") for _ in range(300)]
    db.scalars.return_value = SimpleNamespace(all=lambda: leads)
    team = CorporateTeam(
        id=new_id("operation"),
        organization_id=new_id("organization"),
        name="Platform",
        state="active",
        revision=1,
    )
    assert await service.team_lead_ids(db, team) == leads
    query = str(db.scalars.await_args.args[0])
    assert "LIMIT" not in query
    assert "corporate_role_binding.organization_id" in query
    assert "organization_membership.state" in query
    assert team.organization_id in db.scalars.await_args.args[0].compile().params.values()
    assert team.id in db.scalars.await_args.args[0].compile().params.values()
    team.state = "archived"
    db.scalars.reset_mock()
    assert await service.team_lead_ids(db, team) == []
    db.scalars.assert_not_awaited()


@pytest.mark.asyncio
async def test_overview_keeps_every_lead_and_authorizes_late_lead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id, team_id = new_id("organization"), new_id("operation")
    leads = [new_id("account") for _ in range(300)]
    staff_id = new_id("account")
    organization = Organization(
        id=organization_id,
        display_name="Acme",
        kind="corporate",
        state="active",
        policy_revision=1,
    )
    monkeypatch.setattr(service, "authorize", AsyncMock(return_value=(organization, None)))
    monkeypatch.setattr(service, "team_lead_ids", AsyncMock(return_value=leads))

    def permitted(*args: Any, **kwargs: Any) -> bool:
        return kwargs["permission"] == "team.read" and kwargs["scope_id"] == team_id

    monkeypatch.setattr(overview, "has_corporate_permission", AsyncMock(side_effect=permitted))
    db = AsyncMock()
    rows: list[Any] = []
    db.scalars.side_effect = [
        SimpleNamespace(all=lambda: rows),
        SimpleNamespace(all=lambda: [SimpleNamespace(id=team_id, name="Platform")]),
        SimpleNamespace(all=lambda: rows),
    ]
    pairs = [
        (SimpleNamespace(account_id=identity), SimpleNamespace(display_name=f"Person {index}"))
        for index, identity in enumerate([*leads, staff_id])
    ]
    db.execute.return_value = SimpleNamespace(all=lambda: pairs)

    def member_view(member: Any, account: Any) -> SimpleNamespace:
        return SimpleNamespace(display_name=account.display_name)

    monkeypatch.setattr(service, "member_view", member_view)
    pages = AsyncMock(return_value=CorporateCatalogAssignmentList(items=[], total=0))
    monkeypatch.setattr(assignments, "list_assignments", pages)
    ctx = AuthContext(leads[-1], "session", None, "active", False, False)
    graph = await overview.read_overview(
        db,
        ctx=ctx,
        organization_id=organization_id,
        request_id=None,
    )
    team = next(node for node in graph.nodes if node.kind == "team")
    assert team.lead_account_ids == leads
    assert len(graph.edges) == 301
    assert next(edge for edge in graph.edges if edge.child_id == staff_id).role == "staff"
    assert all(not node.assignments_readable for node in graph.nodes if node.kind == "employee")
    assert pages.await_count == 1
