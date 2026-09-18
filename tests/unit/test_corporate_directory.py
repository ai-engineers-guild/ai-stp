"""Named facets cannot reveal unreadable technology; filtering precedes paging."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import directory, overview
from ai_stp_contracts.corporate import CorporateOrganization, CorporateOverview
from ai_stp_contracts.corporate_directory import (
    CorporateDirectoryFacets,
    CorporateDirectoryItem,
    CorporateDirectoryQuery,
    CorporateDirectoryReference,
    CorporateDirectoryView,
)
from ai_stp_foundation.ids import new_id
from ai_stp_platform.organization_models import CorporateProject, CorporateTeam
from ai_stp_platform.technology_models import Technology


def organization() -> CorporateOrganization:
    return CorporateOrganization(
        organization_id=new_id("organization"),
        display_name="Acme",
        state="active",
        authorization_revision=1,
    )


def test_filters_are_or_within_and_across_then_paginated() -> None:
    leads = [
        CorporateDirectoryReference(kind="employee", id=new_id("account"), name=name)
        for name in ("Alice", "Bob")
    ]
    technology = CorporateDirectoryReference(
        kind="technology", id=new_id("technology"), name="Python"
    )
    related = CorporateDirectoryReference(kind="team", id=new_id("operation"), name="Core")
    items = [
        CorporateDirectoryItem(
            kind="team",
            id=new_id("operation"),
            name=name,
            revision=1,
            leads=[lead],
            technologies=[technology],
            related_teams=[related],
        )
        for name, lead in zip(("A", "B"), leads, strict=True)
    ]
    items.append(
        CorporateDirectoryItem(kind="team", id=new_id("operation"), name="Archived", revision=1)
    )
    source = CorporateDirectoryView(
        organization=organization(),
        resource="teams",
        items=items,
        total=3,
        facets=CorporateDirectoryFacets(leads=leads, teams=[related], technologies=[technology]),
    )
    result = directory.select_directory(
        source,
        CorporateDirectoryQuery(
            resource="teams",
            lead_ids=[ref.id for ref in leads],
            team_ids=[related.id],
            technology_ids=[technology.id],
            offset=1,
            limit=1,
        ),
    )
    assert result.total == 2 and [item.name for item in result.items] == ["B"]
    assert result.facets == source.facets
    with pytest.raises(ValidationError):
        CorporateDirectoryQuery.model_validate({"resource": "teams", "state": "active"})
    assert (
        directory.select_directory(
            source,
            CorporateDirectoryQuery(resource="teams", query="a", technology_ids=[technology.id]),
        ).total
        == 1
    )


def test_directory_rejects_wrong_id_namespace_and_owner() -> None:
    assert "state" not in CorporateDirectoryItem.model_fields
    assert "state" not in CorporateDirectoryQuery.model_fields
    with pytest.raises(ValidationError):
        CorporateDirectoryQuery(resource="teams", team_ids=[new_id("remote_project")])
    team = CorporateDirectoryReference(kind="team", id=new_id("operation"), name="Core")
    with pytest.raises(ValidationError):
        CorporateDirectoryItem(
            kind="project",
            id=new_id("remote_project"),
            name="API",
            revision=1,
            owner_team=team,
        )
    with pytest.raises(ValidationError):
        CorporateDirectoryItem(kind="team", id=team.id, name="Core", revision=1, leads=[team])


@pytest.mark.asyncio
async def test_named_technology_relations_are_authorized_before_facets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org = organization()
    project_id, team_id, other_id, lead_id = (
        new_id("remote_project"),
        new_id("operation"),
        new_id("operation"),
        new_id("account"),
    )
    graph = CorporateOverview.model_validate(
        {
            "organization": org.model_dump(),
            "nodes": [
                {"kind": "project", "id": project_id, "name": "Platform"},
                {"kind": "team", "id": team_id, "name": "Core", "lead_account_ids": [lead_id]},
                {"kind": "team", "id": other_id, "name": "Mobile"},
                {"kind": "employee", "id": lead_id, "name": "Alice"},
            ],
            "edges": [
                {
                    "parent_id": project_id,
                    "child_id": identity,
                    "kind": "project_team",
                    "role": role,
                }
                for identity, role in ((team_id, "owner"), (other_id, "contributor"))
            ],
        }
    )
    graph_read = AsyncMock(return_value=graph)
    monkeypatch.setattr(overview, "read_overview", graph_read)
    visible_id, secret_id = new_id("technology"), new_id("technology")
    technologies = [
        Technology(id=identity, organization_id=org.organization_id, name=name)
        for identity, name in ((visible_id, "Python"), (secret_id, "Secret"))
    ]

    def permitted(*args: Any, **kwargs: Any) -> bool:
        return kwargs["scope_id"] != secret_id and not (
            kwargs["permission"] == "team.list" and kwargs["scope_id"] == other_id
        )

    monkeypatch.setattr(directory, "has_corporate_permission", AsyncMock(side_effect=permitted))
    db = AsyncMock()
    streams: list[list[Any]] = [
        technologies,
        [
            SimpleNamespace(project_id=project_id, technology_id=identity)
            for identity in (visible_id, secret_id)
        ],
        [],
        [
            CorporateTeam(
                id=identity,
                organization_id=org.organization_id,
                name=name,
                state="active",
                revision=1,
                description="Team",
            )
            for identity, name in ((team_id, "Core"), (other_id, "Mobile"))
        ],
    ]

    def scalar_rows(rows: list[Any]) -> SimpleNamespace:
        return SimpleNamespace(all=lambda: rows)

    db.scalars.side_effect = [scalar_rows(rows) for rows in streams]
    result = await directory.read_directory(
        db,
        ctx=AuthContext(lead_id, "session", None, "active", False, False),
        organization_id=org.organization_id,
        query=CorporateDirectoryQuery(resource="teams"),
        request_id=None,
    )
    assert graph_read.await_args is not None
    assert graph_read.await_args.kwargs["include_assignments"] is False
    assert result.total == 1
    assert "state" not in result.items[0].model_dump()
    assert [ref.name for ref in result.items[0].technologies] == ["Python"]
    assert [ref.name for ref in result.facets.technologies] == ["Python"]
    assert [ref.name for ref in result.items[0].related_teams] == ["Mobile"]
    assert [ref.name for ref in result.items[0].leads] == ["Alice"]
    assert all(
        org.organization_id in call.args[0].compile().params.values()
        for call in db.scalars.await_args_list
    )


@pytest.mark.asyncio
async def test_project_lead_uses_directory_field_without_changing_graph_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org = organization()
    project_id, account_id = new_id("remote_project"), new_id("account")
    graph = CorporateOverview.model_validate(
        {
            "organization": org.model_dump(),
            "nodes": [
                {"kind": "project", "id": project_id, "name": "Growth"},
                {"kind": "employee", "id": account_id, "name": "Alex Kim"},
            ],
            "edges": [],
        }
    )
    monkeypatch.setattr(overview, "read_overview", AsyncMock(return_value=graph))
    monkeypatch.setattr(directory, "has_corporate_permission", AsyncMock(return_value=True))
    db = AsyncMock()
    streams = [
        [],
        [],
        [],
        [SimpleNamespace(scope_id=project_id, account_id=account_id)],
        [
            CorporateProject(
                id=project_id,
                organization_id=org.organization_id,
                name="Growth",
                lifecycle="active",
                revision=1,
                profile={"description": "Growth experiments"},
            )
        ],
    ]
    db.scalars.side_effect = [SimpleNamespace(all=lambda rows=rows: rows) for rows in streams]
    result = await directory.read_directory(
        db,
        ctx=AuthContext(account_id, "session", None, "active", False, False),
        organization_id=org.organization_id,
        query=CorporateDirectoryQuery(resource="projects"),
        request_id=None,
    )
    assert [ref.name for ref in result.items[0].leads] == ["Alex Kim"]
    assert result.items[0].description == "Growth experiments"
    assert "state" not in result.items[0].model_dump()
    assert graph.nodes[0].lead_account_ids == []
