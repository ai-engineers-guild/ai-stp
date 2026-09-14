"""Normalized hierarchy cannot manufacture identities or dangling tenant links."""

from typing import Any

import pytest
from pydantic import ValidationError

from ai_stp_contracts.corporate import CorporateOverview, CorporateOverviewNode
from ai_stp_foundation.ids import new_id


def test_overview_keeps_shared_team_as_one_node() -> None:
    projects = [new_id("remote_project"), new_id("remote_project")]
    team, employee = new_id("operation"), new_id("account")
    payload: dict[str, Any] = {
        "organization": {
            "organization_id": new_id("organization"),
            "display_name": "Acme",
            "state": "active",
            "authorization_revision": 1,
        },
        "nodes": [
            *[{"kind": "project", "id": identity, "name": "Mobile"} for identity in projects],
            {"kind": "team", "id": team, "name": "Platform", "lead_account_ids": [employee]},
            {"kind": "employee", "id": employee, "name": "Alice"},
        ],
        "edges": [
            *[
                {"parent_id": identity, "child_id": team, "kind": "project_team", "role": "owner"}
                for identity in projects
            ],
            {"parent_id": team, "child_id": employee, "kind": "team_employee", "role": "lead"},
        ],
    }
    graph = CorporateOverview.model_validate(payload)
    assert len(graph.nodes) == 4
    assert len(graph.edges) == 3
    for mutation in (
        {"nodes": [*payload["nodes"], payload["nodes"][0]]},
        {"edges": [*payload["edges"], payload["edges"][0]]},
        {"nodes": payload["nodes"][:-1]},
        {
            "edges": [
                {"parent_id": employee, "child_id": team, "kind": "team_employee", "role": "staff"}
            ]
        },
        {
            "edges": [
                {"parent_id": projects[0], "child_id": team, "kind": "project_team", "role": "lead"}
            ]
        },
    ):
        with pytest.raises(ValidationError):
            CorporateOverview.model_validate({**payload, **mutation})


def test_overview_uses_existing_typed_id_namespaces() -> None:
    assert CorporateOverviewNode(kind="team", id=new_id("operation"), name="Team").kind == "team"
    with pytest.raises(ValidationError):
        CorporateOverviewNode(kind="team", id=new_id("project"), name="Wrong kind")
    with pytest.raises(ValidationError):
        CorporateOverviewNode(
            kind="employee",
            id=new_id("account"),
            name="Alice",
            lead_account_ids=[new_id("account")],
        )
