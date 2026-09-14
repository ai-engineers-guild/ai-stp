"""PostgreSQL integration coverage for corporate entity profiles (SPEC-083)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.support.images import image_bytes

from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_foundation.ids import new_id
from ai_stp_platform.catalog_ownership_models import (
    CorporateCatalogOwnership as CatalogOwnership,
)
from ai_stp_platform.models import Account, AvatarAsset, CatalogMetadata
from ai_stp_platform.organization_models import (
    CorporateTeam,
    Organization,
    OrganizationMembership,
)
from ai_stp_platform.technology_models import Technology

pytestmark = pytest.mark.platform


async def _account_session(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> tuple[str, str]:
    async with sessionmaker() as db:
        account = Account(id=new_id("account"), status="active")
        db.add(account)
        await db.flush()
        issued = await issue_session(db, account_id=account.id, device_id=None, ttl_seconds=3600)
        await db.commit()
        return account.id, issued.raw_token


async def _add_membership(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    organization_id: str,
    account_id: str,
    role: str = "staff",
) -> None:
    async with sessionmaker() as db:
        db.add(
            OrganizationMembership(
                organization_id=organization_id,
                account_id=account_id,
                role=role,
                display_name=f"{role} member",
                state="active",
            )
        )
        await db.commit()


async def _bootstrap(
    client: AsyncClient,
    *,
    account_id: str,
    name: str,
    key: str,
) -> str:
    response = await client.post(
        "/v1/corporate/bootstrap",
        headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
        json={
            "organization_name": name,
            "superadmin_account_id": account_id,
            "idempotency_key": key,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["organization_id"]


async def _create_team(
    client: AsyncClient,
    *,
    organization_id: str,
    token: str,
    key: str,
) -> str:
    response = await client.post(
        f"/v1/corporate/organizations/{organization_id}/teams",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Platform", "authorization_revision": 1, "idempotency_key": key},
    )
    assert response.status_code == 200, response.text
    return response.json()["team_id"]


async def _authorization_revision(
    client: AsyncClient,
    *,
    organization_id: str,
    token: str,
) -> int:
    response = await client.get(
        f"/v1/corporate/organizations/{organization_id}/context",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    return response.json()["organization"]["authorization_revision"]


async def test_profile_edit_revision_idempotency_rbac_and_tenant_isolation(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, settings = db_api_client
    owner_id, owner_token = await _account_session(sessionmaker)
    organization_id = await _bootstrap(
        client,
        account_id=owner_id,
        name="Profile isolation organization",
        key="profile-isolation-bootstrap",
    )
    team_id = await _create_team(
        client,
        organization_id=organization_id,
        token=owner_token,
        key="profile-isolation-team",
    )
    authorization_revision = await _authorization_revision(
        client, organization_id=organization_id, token=owner_token
    )
    profile_path = f"/v1/corporate/organizations/{organization_id}/entity-profiles/team/{team_id}"

    before = await client.get(profile_path, headers={"Authorization": f"Bearer {owner_token}"})
    assert before.status_code == 200, before.text
    assert before.json()["revision"] == 0

    payload = {
        "fields": {"description": "Stored in PostgreSQL"},
        "expected_revision": 0,
        "authorization_revision": authorization_revision,
        "idempotency_key": "profile-edit-0001",
    }
    written = await client.put(
        profile_path,
        headers={"Authorization": f"Bearer {owner_token}"},
        json=payload,
    )
    assert written.status_code == 200, written.text
    assert written.json()["revision"] == 1
    replay = await client.put(
        profile_path,
        headers={"Authorization": f"Bearer {owner_token}"},
        json=payload,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json() == written.json()

    second_team_id = new_id("operation")
    async with sessionmaker() as db:
        db.add(
            CorporateTeam(
                organization_id=organization_id,
                id=second_team_id,
                name="Security",
                description="",
                state="active",
                profile={},
                profile_revision=0,
            )
        )
        await db.commit()
    different_subject = await client.put(
        f"/v1/corporate/organizations/{organization_id}/entity-profiles/team/{second_team_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
        json=payload,
    )
    assert different_subject.status_code == 409, different_subject.text

    stale = await client.put(
        profile_path,
        headers={"Authorization": f"Bearer {owner_token}"},
        json={**payload, "idempotency_key": "profile-edit-stale-0001"},
    )
    assert stale.status_code == 412, stale.text

    async with sessionmaker() as db:
        row = await db.scalar(
            select(CorporateTeam).where(
                CorporateTeam.organization_id == organization_id,
                CorporateTeam.id == team_id,
            )
        )
        assert row is not None
        assert row.profile_revision == 1
        assert row.profile["description"] == "Stored in PostgreSQL"

    foreign_organization_id = new_id("organization")
    async with sessionmaker() as db:
        db.add(
            Organization(
                id=foreign_organization_id,
                kind="corporate",
                display_name="Foreign profile organization",
                state="active",
            )
        )
        db.add(
            OrganizationMembership(
                organization_id=foreign_organization_id,
                account_id=owner_id,
                role="staff",
                display_name="Foreign staff member",
                state="active",
            )
        )
        await db.commit()
    foreign = await client.get(
        f"/v1/corporate/organizations/{foreign_organization_id}/entity-profiles/team/{team_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert foreign.status_code == 403, foreign.text
    foreign_write = await client.put(
        f"/v1/corporate/organizations/{foreign_organization_id}/entity-profiles/team/{team_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            **payload,
            "authorization_revision": 1,
            "idempotency_key": "profile-cross-tenant-write-0001",
        },
    )
    assert foreign_write.status_code == 403, foreign_write.text

    staff_id, staff_token = await _account_session(sessionmaker)
    await _add_membership(
        sessionmaker,
        organization_id=organization_id,
        account_id=staff_id,
    )
    denied_payload = {
        **payload,
        "expected_revision": 1,
        "idempotency_key": "profile-edit-denied-0001",
    }
    bearer_denied = await client.put(
        profile_path,
        headers={"Authorization": f"Bearer {staff_token}"},
        json=denied_payload,
    )
    assert bearer_denied.status_code == 403, bearer_denied.text

    client.cookies.set(settings.auth.cookie_name, staff_token)
    missing_csrf = await client.put(profile_path, json=denied_payload)
    assert missing_csrf.status_code == 401, missing_csrf.text
    csrf = "profile-csrf-test-token"
    client.cookies.set(settings.auth.csrf_cookie_name, csrf)
    cookie_denied = await client.put(
        profile_path,
        headers={settings.auth.csrf_header_name: csrf},
        json=denied_payload,
    )
    assert cookie_denied.status_code == 403, cookie_denied.text

    async with sessionmaker() as db:
        owner_membership = await db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.account_id == owner_id,
            )
        )
        assert owner_membership is not None
        owner_membership.state = "suspended"
        await db.commit()
    suspended_replay = await client.put(
        profile_path,
        headers={"Authorization": f"Bearer {owner_token}"},
        json=payload,
    )
    assert suspended_replay.status_code == 403, suspended_replay.text


async def test_profile_avatar_media_upload_replay_and_delivery(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    owner_id, owner_token = await _account_session(sessionmaker)
    organization_id = await _bootstrap(
        client,
        account_id=owner_id,
        name="Profile media organization",
        key="profile-media-bootstrap",
    )
    team_id = await _create_team(
        client,
        organization_id=organization_id,
        token=owner_token,
        key="profile-media-team",
    )
    authorization_revision = await _authorization_revision(
        client, organization_id=organization_id, token=owner_token
    )
    upload_path = f"/v1/corporate/organizations/{organization_id}/profiles/team/{team_id}/media"
    profile_path = f"/v1/corporate/organizations/{organization_id}/entity-profiles/team/{team_id}"
    png = image_bytes()

    avatar = await client.post(
        upload_path,
        params={
            "purpose": "avatar",
            "expected_revision": 0,
            "authorization_revision": authorization_revision,
        },
        headers={
            "Authorization": f"Bearer {owner_token}",
            "Idempotency-Key": "profile-avatar-0001",
            "Content-Type": "image/png",
        },
        content=png,
    )
    assert avatar.status_code == 200, avatar.text
    avatar_body = avatar.json()
    assert avatar_body["kind"] == "image"

    avatar_replay = await client.post(
        upload_path,
        params={
            "purpose": "avatar",
            "expected_revision": 0,
            "authorization_revision": authorization_revision,
        },
        headers={
            "Authorization": f"Bearer {owner_token}",
            "Idempotency-Key": "profile-avatar-0001",
            "Content-Type": "image/png",
        },
        content=png,
    )
    assert avatar_replay.status_code == 200, avatar_replay.text
    assert avatar_replay.json() == avatar_body

    second_team_id = new_id("operation")
    async with sessionmaker() as db:
        db.add(
            CorporateTeam(
                organization_id=organization_id,
                id=second_team_id,
                name="Security",
                description="",
                state="active",
                profile={},
                profile_revision=0,
            )
        )
        await db.commit()
    different_subject_upload = await client.post(
        f"/v1/corporate/organizations/{organization_id}/profiles/team/{second_team_id}/media",
        params={
            "purpose": "avatar",
            "expected_revision": 0,
            "authorization_revision": authorization_revision,
        },
        headers={
            "Authorization": f"Bearer {owner_token}",
            "Idempotency-Key": "profile-avatar-0001",
            "Content-Type": "image/png",
        },
        content=png,
    )
    assert different_subject_upload.status_code == 409, different_subject_upload.text

    media = await client.post(
        upload_path,
        params={
            "purpose": "media",
            "expected_revision": 0,
            "authorization_revision": authorization_revision,
        },
        headers={
            "Authorization": f"Bearer {owner_token}",
            "Idempotency-Key": "profile-media-0001",
            "Content-Type": "image/png",
        },
        content=png,
    )
    assert media.status_code == 200, media.text
    media_body = media.json()
    media_replay = await client.post(
        upload_path,
        params={
            "purpose": "media",
            "expected_revision": 0,
            "authorization_revision": authorization_revision,
        },
        headers={
            "Authorization": f"Bearer {owner_token}",
            "Idempotency-Key": "profile-media-0001",
            "Content-Type": "image/png",
        },
        content=png,
    )
    assert media_replay.status_code == 200, media_replay.text
    assert media_replay.json() == media_body

    written = await client.put(
        profile_path,
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "fields": {
                "description": "Media-backed team",
                "avatar_asset_id": avatar_body["avatar_asset_id"],
                "media": [{"kind": "image", "url": media_body["public_url"], "alt": "Team media"}],
            },
            "expected_revision": 0,
            "authorization_revision": authorization_revision,
            "idempotency_key": "profile-media-attach-0001",
        },
    )
    assert written.status_code == 200, written.text
    assert written.json()["revision"] == 1
    assert written.json()["avatar_url"] == avatar_body["public_url"]

    read_back = await client.get(
        profile_path,
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert read_back.status_code == 200, read_back.text
    assert read_back.json()["fields"]["media"][0]["url"] == media_body["public_url"]

    for public_url in (avatar_body["public_url"], media_body["public_url"]):
        served = await client.get(public_url)
        assert served.status_code == 200, served.text
        assert served.headers["content-type"].startswith("image/")

    async with sessionmaker() as db:
        assets = await db.scalar(
            select(func.count(AvatarAsset.id)).where(AvatarAsset.account_id == owner_id)
        )
        assert assets == 2


async def test_technology_and_catalog_owners_are_independent(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    actor_id, actor_token = await _account_session(sessionmaker)
    technology_owner_id, _ = await _account_session(sessionmaker)
    catalog_owner_id, _ = await _account_session(sessionmaker)
    organization_id = await _bootstrap(
        client,
        account_id=actor_id,
        name="Independent owners organization",
        key="independent-owners-bootstrap",
    )
    await _add_membership(
        sessionmaker,
        organization_id=organization_id,
        account_id=technology_owner_id,
    )
    await _add_membership(
        sessionmaker,
        organization_id=organization_id,
        account_id=catalog_owner_id,
    )
    technology_id = new_id("technology")
    stable_id = new_id("setup")
    async with sessionmaker() as db:
        db.add(
            Technology(
                organization_id=organization_id,
                id=technology_id,
                name="Independent technology",
                profile={},
                profile_revision=0,
                lifecycle="active",
                restore_lifecycle="active",
                provenance="manual",
            )
        )
        db.add(
            CatalogMetadata(
                owner_account_id=actor_id,
                organization_id=organization_id,
                object_kind="setup",
                stable_id=stable_id,
                version="1.0",
                current_revision_id="independent-owners-revision",
                visibility="public",
                lifecycle_state="active",
                name="Independent catalog object",
                published_at=datetime.now(UTC),
                passport_document={"fixture": True},
                passport_digest="sha256:" + "0" * 64,
                trust_lane="experimental",
            )
        )
        await db.commit()
    technology_owner = await client.put(
        f"/v1/corporate/organizations/{organization_id}/technologies/{technology_id}/owner",
        headers={"Authorization": f"Bearer {actor_token}"},
        json={
            "owner_account_id": technology_owner_id,
            "expected_revision": 0,
            "authorization_revision": 1,
            "idempotency_key": "independent-technology-owner-0001",
        },
    )
    assert technology_owner.status_code == 200, technology_owner.text
    assert technology_owner.json()["owner_account_id"] == technology_owner_id

    catalog_owner = await client.put(
        f"/v1/corporate/organizations/{organization_id}/catalog-ownership",
        headers={"Authorization": f"Bearer {actor_token}"},
        json={
            "object_kind": "setup",
            "stable_id": stable_id,
            "version": "1.0",
            "owner_account_id": catalog_owner_id,
            "expected_revision": 0,
            "authorization_revision": 1,
            "idempotency_key": "independent-catalog-owner-0001",
        },
    )
    assert catalog_owner.status_code == 200, catalog_owner.text
    assert catalog_owner.json()["owner_account_id"] == catalog_owner_id

    technology_profile = await client.get(
        f"/v1/corporate/organizations/{organization_id}/entity-profiles/technology/{technology_id}",
        headers={"Authorization": f"Bearer {actor_token}"},
    )
    assert technology_profile.status_code == 200, technology_profile.text
    assert technology_profile.json()["owner_account_id"] == technology_owner_id
    catalog_profile = await client.get(
        f"/v1/corporate/organizations/{organization_id}/catalog-ownership",
        params={
            "object_kind": "setup",
            "stable_id": stable_id,
            "version": "1.0",
        },
        headers={"Authorization": f"Bearer {actor_token}"},
    )
    assert catalog_profile.status_code == 200, catalog_profile.text
    assert catalog_profile.json()["owner_account_id"] == catalog_owner_id

    async with sessionmaker() as db:
        technology = await db.get(Technology, (organization_id, technology_id))
        ownership = await db.get(
            CatalogOwnership,
            (organization_id, "setup", stable_id),
        )
        assert technology is not None and technology.owner_account_id == technology_owner_id
        assert ownership is not None and ownership.owner_account_id == catalog_owner_id
