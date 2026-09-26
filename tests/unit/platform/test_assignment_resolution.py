"""The report and assignment API share precedence, including explicit revocation."""

from ai_stp_platform.assignment_resolution import select_assignment_winner
from ai_stp_platform.organization_models import CorporateCatalogAssignment


def test_employee_revocation_beats_inherited_assignments() -> None:
    org = CorporateCatalogAssignment(
        id="org",
        organization_id="org-1",
        object_kind="component",
        stable_id="skill-1",
        selector="exact",
        version="1.0",
        state="current",
        revision=1,
    )
    team = CorporateCatalogAssignment(
        id="team",
        organization_id="org-1",
        team_id="team-1",
        object_kind="component",
        stable_id="skill-1",
        selector="exact",
        version="2.0",
        state="current",
        revision=1,
    )
    employee = CorporateCatalogAssignment(
        id="employee",
        organization_id="org-1",
        account_id="account-1",
        object_kind="component",
        stable_id="skill-1",
        selector="exact",
        version="2.0",
        state="retired",
        revision=1,
    )
    winner, scope, considered, revoked = select_assignment_winner(
        [org, team, employee],
        account_id="account-1",
        team_ids={"team-1"},
        project_id=None,
        technology_id=None,
        harness="codex",
    )
    assert winner is None and scope is None and revoked
    assert [row.id for row, _ in considered] == ["employee", "team", "org"]
    employee.state = "current"
    winner, scope, _, revoked = select_assignment_winner(
        [org, team, employee],
        account_id="account-1",
        team_ids={"team-1"},
        project_id=None,
        technology_id=None,
        harness="codex",
    )
    assert winner is employee and scope == ("employee", "account-1") and not revoked
