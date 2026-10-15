"""Detail menus preserve server authority and order while omitting redundant navigation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import service as corporate_service
from ai_stp_api.slices.entity_actions import service
from ai_stp_api.slices.owner import service as owner_service
from ai_stp_contracts.entity_actions import EntityAction, EntityActionMenu, EntityActionSubject
from ai_stp_platform.organization_models import OrganizationMembership


@pytest.mark.parametrize(
    "kind",
    ["component", "setup", "team", "project", "member", "technology", "category", "scan", "area"],
)
@pytest.mark.parametrize("detail", [False, True])
async def test_detail_context_preserves_permissions_and_order(
    monkeypatch: pytest.MonkeyPatch, kind: str, detail: bool
) -> None:
    subject = EntityActionSubject.model_validate(
        {"kind": kind, "id": "entity_example", "view": "detail" if detail else None}
    )
    actions = [
        EntityAction(id="open", group="navigation"),
        EntityAction(id="copy_id", group="sharing"),
        EntityAction(id="edit", group="management"),
        EntityAction(id="delete", group="danger"),
        EntityAction(id="report", group="support"),
    ]
    projection = EntityActionMenu(subject=subject, actions=actions)
    monkeypatch.setattr(service, "_read_menu", AsyncMock(return_value=projection))
    result = await service.read_menu(Mock(spec=AsyncSession), ctx=None, subject=subject)
    assert [action.id for action in result.actions] == (
        ["copy_id", "edit", "delete", "report"]
        if detail
        else ["open", "copy_id", "edit", "delete", "report"]
    )
    assert result.subject == subject
    assert projection.actions == actions


async def test_catalog_menu_projects_edit_before_presentation_for_authorized_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Mock(spec=AsyncSession)
    db.scalar = AsyncMock(
        return_value=SimpleNamespace(
            version="1.0", name="A component", visibility="private", owner_account_id="account_1"
        )
    )
    monkeypatch.setattr(
        owner_service,
        "read_owner_object_capabilities",
        AsyncMock(
            return_value=SimpleNamespace(
                capabilities=["edit", "edit_presentation", "manage_access"]
            )
        ),
    )
    menu = await service.read_menu(
        db,
        ctx=AuthContext("account_1", "session_1", None, "active", False, False),
        subject=EntityActionSubject(kind="component", id="component_1"),
    )
    actions = [action.id for action in menu.actions]
    assert actions.index("edit") < actions.index("edit_presentation")
    assert "manage_access" in actions


async def test_member_grant_action_needs_target_read_and_binding_create_but_not_member_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Mock(spec=AsyncSession)
    db.scalar = AsyncMock(
        return_value=OrganizationMembership(
            organization_id="organization_1", account_id="employee_1"
        )
    )
    monkeypatch.setattr(
        corporate_service,
        "organization_and_membership",
        AsyncMock(return_value=(SimpleNamespace(id="organization_1", policy_revision=3), None)),
    )
    monkeypatch.setattr(
        corporate_service, "organization_admin_state", AsyncMock(return_value=(set(), None))
    )

    async def permission(_db: object, **kwargs: object) -> bool:
        return kwargs["permission"] in {"member.read", "binding.create"}

    monkeypatch.setattr(service, "subject_permission_allowed", permission)
    menu = await service.read_menu(
        db,
        ctx=AuthContext("admin_1", "session_1", None, "active", False, False),
        subject=EntityActionSubject(
            kind="member", id="employee_1", organization_id="organization_1"
        ),
    )
    assert "manage_access" in [action.id for action in menu.actions]
