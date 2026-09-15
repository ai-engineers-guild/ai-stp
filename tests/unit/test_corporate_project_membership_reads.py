"""Reverse project reads intersect explicit membership with authorized discovery."""

# pyright: reportArgumentType=false

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ai_stp_api.slices.corporate import service
from ai_stp_contracts.corporate import CorporateProjectList, CorporateProjectView
from ai_stp_foundation.ids import new_id


@pytest.mark.asyncio
async def test_employee_projects_do_not_invent_team_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = new_id("organization")
    account_id = new_id("account")
    project_id = new_id("remote_project")
    other_id = new_id("remote_project")
    read = AsyncMock()
    monkeypatch.setattr(service, "read_member", read)
    projects = CorporateProjectList(
        items=[
            CorporateProjectView(
                project_id=identity,
                organization_id=organization_id,
                name=name,
                state="active",
                revision=1,
            )
            for identity, name in ((project_id, "Mobile"), (other_id, "Other"))
        ]
    )
    monkeypatch.setattr(service, "list_projects", AsyncMock(return_value=projects))
    db = AsyncMock()
    db.scalars.return_value = SimpleNamespace(all=lambda: [project_id, "unreadable-project"])
    result = await service.list_member_projects(
        db,
        ctx=SimpleNamespace(account_id=account_id),
        organization_id=organization_id,
        account_id=account_id,
        request_id=None,
    )  # type: ignore[arg-type]
    assert [project.name for project in result.items] == ["Mobile"]
    read.assert_awaited_once()
