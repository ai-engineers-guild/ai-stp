"""Detail menus preserve server authority and order while omitting redundant navigation."""

from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.slices.entity_actions import service
from ai_stp_contracts.entity_actions import EntityAction, EntityActionMenu, EntityActionSubject


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
