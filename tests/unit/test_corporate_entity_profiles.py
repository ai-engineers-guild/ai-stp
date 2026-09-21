"""Presentation boundaries, broad active team leads, and independent owners."""

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import entity_profiles, profile_uploads, service
from ai_stp_api.slices.profile import service as profile_service
from ai_stp_contracts.corporate_profiles import (
    EntityProfileFields,
    EntityProfileSubject,
    EntityProfileWriteRequest,
    TechnologyOwnerRequest,
)
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import AvatarAsset
from ai_stp_platform.organization_models import CorporateTeam
from ai_stp_platform.storage.avatar_store import AvatarObjectStore, StoredAvatar
from ai_stp_platform.technology_models import Technology


def test_profile_contracts_validate_identity_and_safe_content() -> None:
    for kind, prefix in [
        ("team", "operation"),
        ("project", "remote_project"),
        ("employee", "account"),
        ("technology", "technology"),
    ]:
        assert (
            EntityProfileSubject.model_validate(
                {
                    "subject_kind": kind,
                    "subject_id": new_id(prefix),
                }
            ).subject_kind
            == kind
        )
        with pytest.raises(ValidationError):
            EntityProfileSubject.model_validate({"subject_kind": kind, "subject_id": "arbitrary"})
    markdown = (
        "| Status | Task |\n| :--- | :--- |\n| 🚀 **In progress** | Launch a **new campaign** |"
    )
    assert EntityProfileFields(description=markdown).description == markdown
    for fields in [
        {"role": "superadmin"},
        {"links": [{"label": "Bad", "url": "http://bad"}]},
        {"media": [{"kind": "image", "url": "javascript:alert(1)", "alt": "Bad"}]},
    ]:
        with pytest.raises(ValidationError):
            EntityProfileFields.model_validate(fields)


@pytest.mark.parametrize(
    "administrator,owner,assignment,expected",
    [
        (True, False, False, True),
        (True, False, True, True),
        (False, True, False, True),
        (False, True, True, False),
        (False, False, False, False),
        (False, False, True, False),
    ],
)
async def test_edit_authority(
    monkeypatch: pytest.MonkeyPatch,
    administrator: bool,
    owner: bool,
    assignment: bool,
    expected: bool,
) -> None:
    db = AsyncMock()
    db.scalar.side_effect = ["technology" if owner else None]
    monkeypatch.setattr(
        entity_profiles, "has_corporate_permission", AsyncMock(return_value=administrator)
    )
    assert (
        await entity_profiles.can_edit_profile(
            db,
            ctx=AuthContext(new_id("account"), "session", None, "active", False, False),
            organization_id=new_id("organization"),
            subject_kind="technology",
            subject_id=new_id("technology"),
            owner_assignment=assignment,
        )
        is expected
    )


async def test_denied_membership_never_checks_edit_grants(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    monkeypatch.setattr(
        service,
        "organization_and_membership",
        AsyncMock(side_effect=ApiError(ErrorCategory.PERMISSION, "denied")),
    )
    with pytest.raises(ApiError):
        await entity_profiles.read_profile(
            db,
            ctx=AuthContext(new_id("account"), "session", None, "active", False, False),
            organization_id=new_id("organization"),
            subject=EntityProfileSubject(subject_kind="team", subject_id=new_id("operation")),
        )
    db.scalar.assert_not_awaited()


@pytest.mark.parametrize("stale,owner", [(True, False), (False, False), (False, True)])
async def test_revision_guard_and_persistent_write(
    monkeypatch: pytest.MonkeyPatch,
    stale: bool,
    owner: bool,
) -> None:
    db = AsyncMock()
    row = (
        Technology(
            id=new_id("technology"),
            organization_id=new_id("organization"),
            name="Python",
            profile={},
            profile_revision=2,
            revision=7,
            lifecycle="active",
            provenance="manual",
        )
        if owner
        else CorporateTeam(
            id=new_id("operation"),
            organization_id=new_id("organization"),
            name="Mobile",
            profile={},
            profile_revision=2,
            revision=7,
            description="",
            state="active",
        )
    )
    subject = EntityProfileSubject(
        subject_kind="technology" if owner else "team", subject_id=row.id
    )
    monkeypatch.setattr(service, "authorize_idempotent", AsyncMock(return_value=(None, None)))
    monkeypatch.setattr(entity_profiles, "profile_target", AsyncMock(return_value=row))
    monkeypatch.setattr(entity_profiles, "can_edit_profile", AsyncMock(return_value=True))
    monkeypatch.setattr(entity_profiles, "has_corporate_permission", AsyncMock(return_value=True))
    monkeypatch.setattr(entity_profiles, "emit_audit", AsyncMock())
    receipt = AsyncMock()
    monkeypatch.setattr(service, "store_mutation_receipt", receipt)
    common: dict[str, Any] = {
        "expected_revision": 1 if stale else 2,
        "authorization_revision": 1,
        "idempotency_key": "entity-profile-test",
    }
    payload = (
        TechnologyOwnerRequest(owner_account_id=None, **common)
        if owner
        else (
            EntityProfileWriteRequest(fields=EntityProfileFields(description="# Updated"), **common)
        )
    )
    arguments: dict[str, Any] = {
        "ctx": AuthContext(new_id("account"), "session", None, "active", False, False),
        "organization_id": row.organization_id,
        "subject": subject,
        "payload": payload,
        "request_id": None,
    }
    if stale:
        with pytest.raises(ApiError):
            await entity_profiles.write_profile(db, **arguments)
        receipt.assert_not_awaited()
        assert row.profile_revision == 2
    else:
        result = await entity_profiles.write_profile(db, **arguments)
        assert result.revision == row.profile_revision == 3
        assert row.revision == 7
        if not owner:
            assert result.fields.description == "# Updated"
        receipt.assert_awaited_once()


async def test_owner_reads_without_registry_read(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    organization_id = new_id("organization")
    subject = EntityProfileSubject(subject_kind="technology", subject_id=new_id("technology"))
    row = Technology(
        id=subject.subject_id,
        organization_id=organization_id,
        name="Python",
        profile={},
        profile_revision=0,
        description="Registry description",
    )
    monkeypatch.setattr(service, "organization_and_membership", AsyncMock())
    monkeypatch.setattr(entity_profiles, "can_edit_profile", AsyncMock(return_value=True))
    target = AsyncMock(return_value=row)
    monkeypatch.setattr(entity_profiles, "profile_target", target)
    authorize = AsyncMock(side_effect=ApiError(ErrorCategory.PERMISSION, "No registry read"))
    monkeypatch.setattr(service, "authorize", authorize)
    result = await entity_profiles.read_profile(
        db,
        organization_id=organization_id,
        ctx=AuthContext(new_id("account"), "session", None, "active", False, False),
        subject=subject,
    )
    assert result.can_edit and result.fields.description == "Registry description"
    authorize.assert_not_awaited()
    assert target.await_args is not None and "lock" not in target.await_args.kwargs


@pytest.mark.parametrize("purpose", ["avatar", "media"])
async def test_foreign_assets_rejected_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
    purpose: str,
) -> None:
    db = AsyncMock()
    row = CorporateTeam(
        id=new_id("operation"),
        organization_id=new_id("organization"),
        name="Mobile",
        profile={},
        profile_revision=0,
    )
    asset_id = "avatar_" + "a" * 24
    db.get.return_value = AvatarAsset(
        id=asset_id, account_id=new_id("account"), state="ready", content_type="image/png"
    )
    monkeypatch.setattr(service, "authorize_idempotent", AsyncMock(return_value=(None, None)))
    monkeypatch.setattr(entity_profiles, "profile_target", AsyncMock(return_value=row))
    fields = (
        {"avatar_asset_id": asset_id}
        if purpose == "avatar"
        else {
            "media": [{"kind": "image", "url": f"/v1/media/avatars/{asset_id}", "alt": "Upload"}],
        }
    )
    with pytest.raises(ApiError):
        await entity_profiles.write_profile(
            db,
            ctx=AuthContext(new_id("account"), "session", None, "active", False, False),
            organization_id=row.organization_id,
            subject=EntityProfileSubject(subject_kind="team", subject_id=row.id),
            payload=EntityProfileWriteRequest(
                fields=EntityProfileFields.model_validate(fields),
                expected_revision=0,
                authorization_revision=1,
                idempotency_key="foreign-asset-key",
            ),
            request_id=None,
        )
    assert row.profile == {} and row.profile_revision == 0
    db.flush.assert_not_awaited()


async def test_lead_lookup_is_tenant_and_active_team_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = AsyncMock()
    db.scalar.return_value = None
    monkeypatch.setattr(entity_profiles, "has_corporate_permission", AsyncMock(return_value=False))
    tenant, actor = new_id("organization"), new_id("account")
    assert not await entity_profiles.can_edit_profile(
        db,
        ctx=AuthContext(actor, "session", None, "active", False, False),
        organization_id=tenant,
        subject_kind="employee",
        subject_id=new_id("account"),
    )
    statement = db.scalar.call_args.args[0].compile()
    assert tenant in statement.params.values() and actor in statement.params.values()
    assert "active" in statement.params.values() and "lead" in statement.params.values()


async def test_gallery_upload_reuses_owned_avatar_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    class Store(AvatarObjectStore):
        def __init__(self) -> None:
            pass

        namespace: str | None = None

        async def put_avatar(
            self,
            *,
            asset_id: str,
            payload: bytes,
            content_type: str,
            owner_account_id: str | None = None,
            namespace: str = "avatars",
        ) -> StoredAvatar:
            del owner_account_id
            self.namespace = namespace
            return StoredAvatar(
                asset_id=asset_id,
                object_key="accounts/account_editor/users/avatars/object",
                content_digest="sha256:stored",
                size_bytes=len(payload),
                content_type=content_type,
                public_path=f"/v1/media/avatars/{asset_id}",
            )

        async def read_bytes(
            self,
            *,
            object_key: str,
            expected_digest: str | None = None,
            expected_size: int | None = None,
        ) -> bytes:
            del object_key, expected_digest, expected_size
            return b"processed"

    db = AsyncMock()
    db.add = Mock()
    row = CorporateTeam(
        id=new_id("operation"),
        organization_id=new_id("organization"),
        name="Mobile",
        profile={},
        profile_revision=0,
    )
    monkeypatch.setattr(service, "authorize_idempotent", AsyncMock(return_value=(None, None)))
    monkeypatch.setattr(entity_profiles, "profile_target", AsyncMock(return_value=row))
    monkeypatch.setattr(service, "store_mutation_receipt", AsyncMock())
    monkeypatch.setattr(profile_uploads, "emit_audit", AsyncMock())
    store = Store()
    payload = b"\x89PNG\r\n\x1a\n" + b"x" * 40
    response = await profile_uploads.upload(
        db,
        store,
        ctx=AuthContext(new_id("account"), "session", None, "active", False, False),
        organization_id=row.organization_id,
        subject=EntityProfileSubject(subject_kind="team", subject_id=row.id),
        purpose="media",
        payload=payload,
        content_type="image/png",
        expected_revision=0,
        authorization_revision=1,
        idempotency_key="gallery-upload-test",
        request_id=None,
    )
    assert response.public_url.startswith("/v1/media/avatars/")
    assert store.namespace == "users/avatars"

    asset = AvatarAsset(
        id=response.media_id,
        account_id=new_id("account"),
        state="ready",
        content_type="image/png",
        size_bytes=len(payload),
        object_key="accounts/other/users/avatars/object",
        content_digest="sha256:stored",
    )
    db.get.return_value = asset
    delivered = await profile_service.read_avatar_bytes(db, store, asset_id=response.media_id)
    assert delivered == (b"processed", "image/png")
