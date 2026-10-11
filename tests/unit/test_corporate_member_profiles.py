"""Corporate names are tenant-local and profile requests cannot change authority."""

import pytest
from pydantic import ValidationError

from ai_stp_api.slices.corporate.service import member_view
from ai_stp_contracts.corporate import CorporateMemberCreateRequest, CorporateMemberProfileRequest
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import OrganizationMembership


def test_tenant_member_names_do_not_mutate_shared_account() -> None:
    account = Account(id=new_id("account"), display_name="Public name", status="active")
    first = OrganizationMembership(
        organization_id=new_id("organization"),
        account_id=account.id,
        display_name="Mobile lead",
        role="staff",
        state="active",
        revision=2,
    )
    second = OrganizationMembership(
        organization_id=new_id("organization"),
        account_id=account.id,
        display_name="Other organization name",
        role="staff",
        state="active",
        revision=1,
    )
    assert member_view(first, account).display_name == "Mobile lead"
    assert member_view(second, account).display_name == "Other organization name"
    assert account.display_name == "Public name"
    second.display_name = None
    assert member_view(second, account).display_name == "Public name"


def test_profile_boundary_rejects_blank_names_and_authority_fields() -> None:
    payload = {
        "display_name": "Alice",
        "expected_revision": 1,
        "authorization_revision": 1,
        "idempotency_key": "profile-test-key",
    }
    assert CorporateMemberProfileRequest.model_validate(payload).display_name == "Alice"
    for invalid in [
        {**payload, "display_name": "  "},
        {**payload, "role": "superadmin"},
        {**payload, "state": "suspended"},
        {**payload, "expected_revision": 0},
    ]:
        with pytest.raises(ValidationError):
            CorporateMemberProfileRequest.model_validate(invalid)


def test_member_creation_allows_unassigned_members_and_keeps_catalog_assignment_exact() -> None:
    assignment: dict[str, str] = {
        "object_kind": "component",
        "stable_id": new_id("component"),
        "version": "1.0",
    }
    payload: dict[str, object] = {
        "display_name": "Alice",
        "email": "alice@example.com",
        "role": "staff",
        "team_ids": [new_id("operation")],
        "project_ids": [new_id("remote_project")],
        "catalog_assignments": [assignment],
        "authorization_revision": 1,
        "idempotency_key": "member-create-fixture",
    }
    request = CorporateMemberCreateRequest.model_validate(payload)
    assert request.catalog_assignments[0].version == "1.0"
    unassigned = CorporateMemberCreateRequest.model_validate({**payload, "team_ids": []})
    assert unassigned.team_ids == []
    changes_list: tuple[dict[str, object], ...] = (
        {"catalog_assignments": [{**assignment, "version": "latest"}]},
        {"catalog_assignments": [{**assignment, "object_kind": "setup"}]},
    )
    for changes in changes_list:
        with pytest.raises(ValidationError):
            CorporateMemberCreateRequest.model_validate({**payload, **changes})


@pytest.mark.asyncio
async def test_member_detail_includes_directory_profile_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from typing import cast
    from unittest.mock import AsyncMock, Mock

    from sqlalchemy.ext.asyncio import AsyncSession

    from ai_stp_api.session import AuthContext
    from ai_stp_api.slices.corporate import service, subject_access

    account = Account(id=new_id("account"), display_name="Alice", status="active")
    organization_id = new_id("organization")
    member = OrganizationMembership(
        organization_id=organization_id,
        account_id=account.id,
        role="staff",
        state="active",
        revision=1,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        job_title_id=new_id("job_title"),
    )
    db = cast(
        AsyncSession,
        SimpleNamespace(
            execute=AsyncMock(return_value=Mock(one_or_none=Mock(return_value=(member, account)))),
            scalar=AsyncMock(
                side_effect=["alice@example.com", datetime(2026, 2, 1, tzinfo=UTC), "Engineer"]
            ),
        ),
    )
    authorize = AsyncMock()
    monkeypatch.setattr(service, "authorize", authorize)
    monkeypatch.setattr(service, "emit_audit", AsyncMock())
    monkeypatch.setattr(subject_access, "subject_available_actions", AsyncMock(return_value=[]))
    ctx = AuthContext(account.id, "session", None, "active", False, False)
    result = await service.read_member(
        db, ctx=ctx, organization_id=organization_id, account_id=account.id, request_id=None
    )
    assert result.contact_email == "alice@example.com"
    assert result.job_title_name == "Engineer"
    assert result.joined_at is not None and result.joined_at.startswith("2026-01-01")
    assert result.last_activity_at is not None
    assert result.last_activity_at.startswith("2026-02-01")
    assert authorize.await_args is not None
    assert authorize.await_args.kwargs["scope_id"] == account.id


@pytest.mark.asyncio
async def test_catalog_grant_target_requires_the_same_organization() -> None:
    from types import SimpleNamespace
    from typing import cast
    from unittest.mock import AsyncMock

    from sqlalchemy.ext.asyncio import AsyncSession

    from ai_stp_api.slices.corporate import service

    scope_target_exists = service._scope_target_exists  # pyright: ignore[reportPrivateUsage]
    organization_id = new_id("organization")
    stable_id = new_id("component")
    scalar = AsyncMock(return_value=None)
    db = cast(AsyncSession, SimpleNamespace(scalar=scalar))
    assert not await scope_target_exists(
        db, organization_id=organization_id, scope_kind="catalog_object", scope_id=stable_id
    )
    scalar_await = scalar.await_args
    assert scalar_await is not None
    query = scalar_await.args[0].compile().params
    assert organization_id in query.values()
    assert stable_id in query.values()
    scalar.return_value = stable_id
    assert await scope_target_exists(
        db, organization_id=organization_id, scope_kind="catalog_object", scope_id=stable_id
    )


def test_named_catalog_object_scope_is_accepted_for_direct_grants() -> None:
    from ai_stp_contracts.corporate import CorporatePermissionGrantRequest

    request = CorporatePermissionGrantRequest(
        account_id=new_id("account"),
        permission="catalog_object.read",
        scope_kind="catalog_object",
        scope_id=new_id("setup"),
        authorization_revision=1,
        idempotency_key="catalog-grant-test",
    )
    assert request.scope_kind == "catalog_object"
