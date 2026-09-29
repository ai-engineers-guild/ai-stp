"""The report and assignment API share precedence, including explicit revocation."""

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform import assignment_resolution
from ai_stp_platform.assignment_resolution import (
    eligible_assignment_versions,
    select_assignment_winner,
)
from ai_stp_platform.catalog_read import PublicVersionRow
from ai_stp_platform.models import CatalogMetadata
from ai_stp_platform.organization_models import CorporateCatalogAssignment


def _version_row(version: str, *, lifecycle: str = "active", digest: str = "d") -> PublicVersionRow:
    return PublicVersionRow(
        metadata=CatalogMetadata(),
        passport={},
        passport_digest=f"sha256:{digest * 64}",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        trust_lane="authoritative",
        author_verified=False,
        component_verified=False,
        lifecycle=lifecycle,
        stable_id="stable-1",
        version=version,
        object_kind="component",
    )


@pytest.mark.asyncio
async def test_eligible_versions_skip_malformed_and_ineligible_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Stored catalog rows can hold a malformed version or a lifecycle that is
    # not assignable; one corrupt row must not fail the whole resolution.
    rows = [
        _version_row("1.2"),
        _version_row("not-a-version"),
        _version_row("1.9"),
        _version_row("9.9", lifecycle="retired"),
    ]
    monkeypatch.setattr(
        assignment_resolution,
        "get_visible_object_versions",
        AsyncMock(return_value=rows),
    )
    session = cast(AsyncSession, AsyncMock())
    eligible = await eligible_assignment_versions(
        session,
        object_kind="component",
        stable_id="stable-1",
        account_id=None,
    )
    assert [version for version, _ in eligible] == ["1.2", "1.9"]


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
