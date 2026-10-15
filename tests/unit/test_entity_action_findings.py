"""Finding menu rights match review mutation prerequisites."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.session import AuthContext
from ai_stp_api.slices.entity_actions import service
from ai_stp_api.slices.technology import detection
from ai_stp_contracts.entity_actions import EntityActionSubject


@pytest.mark.parametrize("review_allowed", [False, True])
async def test_dependency_creation_requires_review_authority(
    monkeypatch: pytest.MonkeyPatch, review_allowed: bool
) -> None:
    finding = SimpleNamespace(
        kind="package",
        coordinate="pkg:test",
        context="production",
        technology_id=None,
        candidate_technology_id=None,
        tier="dependency",
    )
    monkeypatch.setattr(
        detection,
        "read_scan_detail",
        AsyncMock(
            return_value=SimpleNamespace(
                project_id="project_1",
                findings=[finding],
            )
        ),
    )

    def allowed(*args: object, **kwargs: object) -> bool:
        return kwargs["permission"] == "technology.create" or review_allowed

    permission = AsyncMock(side_effect=allowed)
    monkeypatch.setattr(service, "subject_permission_allowed", permission)
    menu = await service.read_menu(
        Mock(spec=AsyncSession),
        ctx=AuthContext(
            account_id="account_1",
            session_id="session_1",
            device_id=None,
            account_status="active",
            is_admin=False,
            via_cookie=False,
        ),
        subject=EntityActionSubject(
            kind="finding",
            id="scan_1",
            organization_id="org_1",
            finding_kind="package",
            coordinate="pkg:test",
            usage_context="production",
        ),
    )
    assert [action.id for action in menu.actions] == (
        ["evidence", "make_technology"] if review_allowed else ["evidence"]
    )
