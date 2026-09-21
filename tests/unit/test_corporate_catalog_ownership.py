"""Operational owner coordinates, mutation receipts, and access revalidation."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import ValidationError

from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import catalog_ownership as ownership
from ai_stp_api.slices.corporate import entity_profiles, service
from ai_stp_contracts.corporate_catalog_ownership import (
    CorporateCatalogOwnershipQuery,
    CorporateCatalogOwnershipRequest,
)
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account


@pytest.fixture(autouse=True)
def stub_object_capabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "ai_stp_api.slices.corporate.subject_access.catalog_object_capabilities",
        AsyncMock(return_value=[]),
    )


def payload(**changes: object) -> CorporateCatalogOwnershipRequest:
    return CorporateCatalogOwnershipRequest.model_validate(
        {
            "object_kind": "setup",
            "stable_id": new_id("setup"),
            "version": "1.0",
            "owner_account_id": new_id("account"),
            "expected_revision": 0,
            "authorization_revision": 1,
            "idempotency_key": "operational-owner-test",
            **changes,
        }
    )


def test_kind_and_retained_clear() -> None:
    with pytest.raises(ValidationError, match="identity"):
        payload(stable_id=new_id("component"))
    with pytest.raises(ValidationError, match="retained revision"):
        payload(owner_account_id=None)
    assert payload(owner_account_id=None, expected_revision=1).owner_account_id is None
    assert (
        payload(object_kind="component", stable_id=new_id("component")).object_kind == "component"
    )


def test_migration_chain() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision("0075_corporate_catalog_ownership")
    assert revision is not None
    assert revision.down_revision == "0074_corporate_entity_profiles"
    assert len(script.get_heads()) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("denied", ["actor", "employee", "catalog"])
async def test_replay_revalidates_access(monkeypatch: pytest.MonkeyPatch, denied: str) -> None:
    request = payload()
    db = AsyncMock()
    db.scalar.return_value = SimpleNamespace(state="active")
    monkeypatch.setattr(
        service,
        "authorize_idempotent",
        AsyncMock(
            return_value=(None, SimpleNamespace(response_body={})),
            side_effect=ApiError(ErrorCategory.PERMISSION, "actor denied")
            if denied == "actor"
            else None,
        ),
    )
    monkeypatch.setattr(
        service, "read_member", AsyncMock(return_value=SimpleNamespace(display_name="Employee"))
    )
    monkeypatch.setattr(
        ownership,
        "get_visible_metadata",
        AsyncMock(
            side_effect=[SimpleNamespace(published_at=True, lifecycle_state="active"), None]
            if denied == "catalog"
            else None,
            return_value=SimpleNamespace(published_at=True, lifecycle_state="active"),
        ),
    )
    if denied == "employee":
        db.scalar.return_value = None
    ctx = AuthContext(new_id("account"), "session", None, "active", False, False)
    with pytest.raises(ApiError):
        await ownership.write_ownership(
            db,
            ctx=ctx,
            organization_id=new_id("organization"),
            payload=request,
            request_id=None,
        )
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_reassign_clear_and_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    db.add = Mock()
    db.get.return_value = None
    db.scalar.return_value = SimpleNamespace(state="active")
    monkeypatch.setattr(
        service, "member_view", Mock(return_value=SimpleNamespace(display_name="Employee"))
    )
    original_get = db.get

    def get(model: type[Any], _key: Any) -> Any:
        return (
            SimpleNamespace(display_name="Employee")
            if model is Account
            else original_get.return_value
        )

    original_get.side_effect = get
    authorize = AsyncMock(return_value=(None, None))
    receipt = AsyncMock()
    audit = AsyncMock()
    monkeypatch.setattr(service, "authorize_idempotent", authorize)
    monkeypatch.setattr(
        service, "read_member", AsyncMock(return_value=SimpleNamespace(display_name="Employee"))
    )
    monkeypatch.setattr(service, "store_mutation_receipt", receipt)
    monkeypatch.setattr(ownership, "emit_audit", audit)
    monkeypatch.setattr(
        ownership,
        "get_visible_metadata",
        AsyncMock(return_value=SimpleNamespace(published_at=True, lifecycle_state="active")),
    )
    organization_id = new_id("organization")
    ctx = AuthContext(new_id("account"), "session", None, "active", False, False)
    request = payload()
    created = await ownership.write_ownership(
        db, ctx=ctx, organization_id=organization_id, payload=request, request_id=None
    )
    row = db.add.call_args.args[0]
    db.get.return_value = row
    assert created.revision == 1 and created.owner_account_id == request.owner_account_id
    assert authorize.call_args.kwargs["permission"] == "entity_profile.owner"
    assert authorize.call_args.kwargs["scope_kind"] == "catalog_object"
    assert created.owner_display_name == "Employee" and created.can_edit
    with pytest.raises(ApiError, match="revision is stale"):
        await ownership.write_ownership(
            db, ctx=ctx, organization_id=organization_id, payload=request, request_id=None
        )
    replacement = request.model_copy(
        update={"owner_account_id": new_id("account"), "expected_revision": 1, "version": "2.0"}
    )
    changed = await ownership.write_ownership(
        db, ctx=ctx, organization_id=organization_id, payload=replacement, request_id=None
    )
    assert changed.revision == 2 and row.stable_id == request.stable_id
    cleared = await ownership.write_ownership(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=replacement.model_copy(update={"owner_account_id": None, "expected_revision": 2}),
        request_id=None,
    )
    assert cleared.revision == 3 and cleared.owner_account_id is None
    assert receipt.await_count == audit.await_count == 3
    assert db.add.call_count == 1


@pytest.mark.asyncio
async def test_absent_read_is_revision_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "authorize", AsyncMock())
    monkeypatch.setattr(entity_profiles, "can_edit_profile", AsyncMock(return_value=False))
    monkeypatch.setattr(
        ownership,
        "get_visible_metadata",
        AsyncMock(return_value=SimpleNamespace(published_at=True, lifecycle_state="active")),
    )
    db = AsyncMock()
    db.get.return_value = None
    ctx = AuthContext(new_id("account"), "session", None, "active", False, False)
    result = await ownership.read_ownership(
        db,
        ctx=ctx,
        organization_id=new_id("organization"),
        subject=CorporateCatalogOwnershipQuery(
            object_kind="setup", stable_id=new_id("setup"), version="1.0"
        ),
        request_id=None,
    )
    assert result.revision == 0 and result.owner_account_id is None
    assert result.owner_display_name is None and not result.can_edit


@pytest.mark.asyncio
async def test_scoped_receipt_without_scope_id_is_only_allowed_for_profile_operations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization = SimpleNamespace(id=new_id("organization"), policy_revision=1)
    membership = SimpleNamespace(revision=1)
    db = AsyncMock()
    db.scalar.return_value = organization
    monkeypatch.setattr(
        service,
        "authorize",
        AsyncMock(return_value=(organization, membership)),
    )
    monkeypatch.setattr(service, "emit_audit", AsyncMock())

    non_upload_receipt = SimpleNamespace(
        operation="team.update",
        request_fingerprint="sha256:receipt",
        response_body={},
    )
    db.get.return_value = non_upload_receipt
    with pytest.raises(ApiError, match="idempotency key was reused"):
        await service.authorize_idempotent(
            db,
            ctx=AuthContext(new_id("account"), "session", None, "active", False, False),
            organization_id=organization.id,
            permission="team.update",
            scope_kind="team",
            scope_id=new_id("operation"),
            authorization_revision=1,
            idempotency_key="scoped-receipt-test",
            operation="team.update",
            fingerprint="sha256:receipt",
        )

    upload_receipt = SimpleNamespace(
        operation="entity.profile.upload",
        request_fingerprint="sha256:upload",
        response_body={},
    )
    db.get.return_value = upload_receipt
    result = await service.authorize_idempotent(
        db,
        ctx=AuthContext(new_id("account"), "session", None, "active", False, False),
        organization_id=organization.id,
        permission="entity_profile.update",
        scope_kind="team",
        scope_id=new_id("operation"),
        authorization_revision=1,
        idempotency_key="scoped-upload-receipt-test",
        operation="entity.profile.upload",
        fingerprint="sha256:upload",
    )
    assert result == (organization, upload_receipt)

    profile_receipt = SimpleNamespace(
        operation="entity.profile.update",
        request_fingerprint="sha256:profile",
        response_body={},
    )
    db.get.return_value = profile_receipt
    result = await service.authorize_idempotent(
        db,
        ctx=AuthContext(new_id("account"), "session", None, "active", False, False),
        organization_id=organization.id,
        permission="entity_profile.update",
        scope_kind="team",
        scope_id=new_id("operation"),
        authorization_revision=1,
        idempotency_key="scoped-profile-receipt-test",
        operation="entity.profile.update",
        fingerprint="sha256:profile",
    )
    assert result == (organization, profile_receipt)
