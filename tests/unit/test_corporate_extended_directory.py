"""Extended directories retain authorized facets while filtering before paging."""

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


def ref(kind: Any, prefix: str, name: str) -> CorporateDirectoryReference:
    return CorporateDirectoryReference(kind=kind, id=new_id(prefix), name=name)


def test_extended_identity_and_filters() -> None:
    category = ref("category", "category", "Language")
    project = ref("project", "remote_project", "Platform")
    team = ref("team", "operation", "Core")
    owner = ref("employee", "account", "Alice")
    items = [
        CorporateDirectoryItem(
            kind="technology",
            id=new_id("technology"),
            name=name,
            revision=1,
            categories=[category],
            projects=[project],
            teams=[team],
            owner=owner,
        )
        for name in ("A", "B")
    ]
    source = CorporateDirectoryView(
        organization=CorporateOrganization(
            organization_id=new_id("organization"),
            display_name="Acme",
            state="active",
            authorization_revision=1,
        ),
        resource="technologies",
        items=items,
        total=2,
        facets=CorporateDirectoryFacets(
            leads=[], teams=[team], technologies=[], projects=[project], categories=[category]
        ),
    )
    result = directory.select_directory(
        source,
        CorporateDirectoryQuery(
            resource="technologies",
            category_ids=[new_id("category"), category.id],
            project_ids=[project.id],
            team_ids=[team.id],
            offset=1,
            limit=1,
        ),
    )
    assert result.total == 2 and result.items == [items[1]]
    assert result.facets == source.facets
    assert (
        directory.select_directory(
            source,
            CorporateDirectoryQuery(
                resource="technologies", project_ids=[new_id("remote_project")]
            ),
        ).total
        == 0
    )
    with pytest.raises(ValidationError):
        CorporateDirectoryReference(kind="category", id=new_id("technology"), name="Wrong")
    with pytest.raises(ValidationError):
        CorporateDirectoryQuery(resource="technologies", category_ids=[new_id("account")])
    with pytest.raises(ValidationError):
        CorporateDirectoryItem(
            kind="technology", id=items[0].id, name="Wrong", revision=1, owner=team
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", ["members", "technologies"])
async def test_extended_projection_authorizes_names_before_facets(
    monkeypatch: pytest.MonkeyPatch, resource: Any
) -> None:
    org = CorporateOrganization(
        organization_id=new_id("organization"),
        display_name="Acme",
        state="active",
        authorization_revision=1,
    )
    team, project, employee = (
        ref("team", "operation", "Core"),
        ref("project", "remote_project", "Platform"),
        ref("employee", "account", "Alice"),
    )
    visible, hidden = new_id("technology"), new_id("technology")
    category, secret_category = new_id("category"), new_id("category")
    graph = CorporateOverview.model_validate(
        {
            "organization": org.model_dump(),
            "nodes": [
                team.model_dump() | {"lead_account_ids": [employee.id]},
                project.model_dump(),
                employee.model_dump(),
            ],
            "edges": [
                {
                    "kind": "project_team",
                    "parent_id": project.id,
                    "child_id": team.id,
                    "role": "owner",
                },
                {
                    "kind": "team_employee",
                    "parent_id": team.id,
                    "child_id": employee.id,
                    "role": "lead",
                },
            ],
        }
    )
    monkeypatch.setattr(overview, "read_overview", AsyncMock(return_value=graph))

    def permitted(*args: Any, **kwargs: Any) -> bool:
        return kwargs["scope_id"] != hidden

    monkeypatch.setattr(
        directory,
        "has_corporate_permission",
        AsyncMock(side_effect=permitted),
    )
    technologies = [
        SimpleNamespace(
            id=identity,
            name=name,
            lifecycle="active",
            revision=1,
            description="",
            owner_account_id=employee.id,
        )
        for identity, name in [(visible, "Python"), (hidden, "Secret")]
    ]
    streams: list[list[Any]] = [
        technologies,
        [
            SimpleNamespace(project_id=project.id, technology_id=identity)
            for identity in (visible, hidden)
        ],
        [],
    ]
    if resource == "members":
        streams += [
            [
                SimpleNamespace(account_id=employee.id, technology_id=identity)
                for identity in (visible, hidden)
            ],
            [SimpleNamespace(account_id=employee.id, state="active", revision=1, role="staff")],
        ]
    else:
        streams += [
            [SimpleNamespace(id=category, name="Language")],
            [
                SimpleNamespace(technology_id=visible, category_id=identity)
                for identity in (category, secret_category)
            ],
        ]
    db = AsyncMock()

    def scalar_rows(rows: list[Any]) -> SimpleNamespace:
        return SimpleNamespace(all=lambda: rows)

    db.scalars.side_effect = [scalar_rows(rows) for rows in streams]
    result = await directory.read_directory(
        db,
        ctx=AuthContext(employee.id, "session", None, "active", False, False),
        organization_id=org.organization_id,
        query=CorporateDirectoryQuery(resource=resource),
        request_id=None,
    )
    assert result.total == 1
    assert "state" not in result.items[0].model_dump()
    assert [item.id for item in result.items[0].teams] == [team.id]
    assert [item.id for item in result.items[0].projects] == [project.id]
    assert "Secret" not in result.model_dump_json()
    if resource == "members":
        assert result.items[0].is_lead
        assert [item.id for item in result.facets.technologies] == [visible]
        assert (
            directory.select_directory(
                result, CorporateDirectoryQuery(resource="members", is_lead=False)
            ).total
            == 0
        )
    else:
        assert result.items[0].owner == employee
        assert [item.id for item in result.facets.categories] == [category]
    assert all(
        org.organization_id in call.args[0].compile().params.values()
        for call in db.scalars.await_args_list
    )
