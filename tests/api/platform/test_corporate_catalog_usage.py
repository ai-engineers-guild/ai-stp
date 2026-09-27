"""`GET /catalog-usage` paging covers the authorized set, not the first page only."""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.session import issue_session
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, CatalogMetadata
from ai_stp_platform.organization_models import (
    CorporateCatalogAssignment,
    CorporateProject,
    CorporateTeam,
    CorporateTeamMember,
    Organization,
    OrganizationMembership,
    ProjectIdentity,
)
from ai_stp_platform.technology_models import Technology

pytestmark = pytest.mark.platform

DIGEST = "sha256:" + "6" * 64


async def _organization(
    client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    bootstrap_key: str,
) -> tuple[str, str, dict[str, str]]:
    account_id = new_id("account")
    async with sessionmaker() as db:
        db.add(Account(id=account_id, status="active", display_name="Owner"))
        await db.flush()
        session = await issue_session(db, account_id=account_id, device_id=None, ttl_seconds=3600)
        await db.commit()
    auth = {"Authorization": f"Bearer {session.raw_token}"}
    bootstrap = await client.post(
        "/v1/corporate/bootstrap",
        json={
            "organization_name": "Usage acceptance",
            "superadmin_account_id": account_id,
            "idempotency_key": bootstrap_key,
        },
        headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
    )
    assert bootstrap.status_code == 200, bootstrap.text
    return bootstrap.json()["organization_id"], account_id, auth


async def _member(
    db: AsyncSession,
    organization_id: str,
    *,
    index: int,
) -> str:
    account_id = new_id("account")
    db.add(Account(id=account_id, status="active", display_name=f"Member {index:03}"))
    db.add(
        OrganizationMembership(
            organization_id=organization_id,
            account_id=account_id,
            role="member",
            display_name=f"Member {index:03}",
            state="active",
        )
    )
    return account_id


def _employee_assignment(
    organization_id: str,
    account_id: str,
    stable_id: str,
    *,
    revision: int = 1,
) -> CorporateCatalogAssignment:
    return CorporateCatalogAssignment(
        id=new_id("operation"),
        organization_id=organization_id,
        account_id=account_id,
        object_kind="setup",
        stable_id=stable_id,
        selector="exact",
        version="1.0",
        state="current",
        revision=revision,
    )


async def _catalog_row(
    db: AsyncSession,
    organization_id: str,
    owner_account_id: str,
    stable_id: str,
) -> None:
    db.add(
        CatalogMetadata(
            owner_account_id=owner_account_id,
            organization_id=organization_id,
            object_kind="setup",
            stable_id=stable_id,
            version="1.0",
            current_revision_id="revision-1.0",
            visibility="private",
            lifecycle_state="active",
            name="Usage Setup",
            published_at=datetime.now(UTC),
            passport_document={"fixture": True},
            passport_digest=DIGEST,
            trust_lane="experimental",
        )
    )


async def test_catalog_usage_pages_cover_the_authorized_set(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    """101 authorized rows read across bounded offset/limit pages (#333)."""
    client, sessionmaker, _ = db_api_client
    organization_id, owner_id, auth = await _organization(
        client, sessionmaker, bootstrap_key="usage-paging-bootstrap"
    )
    setup_id = new_id("setup")
    async with sessionmaker() as db:
        await _catalog_row(db, organization_id, owner_id, setup_id)
        subjects = [await _member(db, organization_id, index=index) for index in range(101)]
        await db.flush()
        db.add_all(
            [_employee_assignment(organization_id, subject, setup_id) for subject in subjects]
        )
        await db.commit()

    path = f"/v1/corporate/organizations/{organization_id}/catalog-usage"
    params = {"object_kind": "setup", "stable_id": setup_id}
    first = await client.get(path, params={**params, "limit": 100}, headers=auth)
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["total"] == 101
    assert len(first_body["items"]) == 100

    second = await client.get(path, params={**params, "limit": 100, "offset": 100}, headers=auth)
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["total"] == 101
    assert len(second_body["items"]) == 1

    empty = await client.get(path, params={**params, "limit": 100, "offset": 101}, headers=auth)
    assert empty.status_code == 200, empty.text
    assert empty.json()["total"] == 101
    assert empty.json()["items"] == []

    combined = first_body["items"] + second_body["items"]
    assert len(combined) == 101
    assert len({item["assignment_id"] for item in combined}) == 101
    names = [item["subject_name"] for item in combined]
    assert names == sorted(names, key=str.casefold)
    assert all(item["subject_kind"] == "employee" for item in combined)

    smaller = await client.get(path, params={**params, "limit": 40}, headers=auth)
    assert len(smaller.json()["items"]) == 40


async def test_catalog_usage_covers_all_subject_kinds_and_effective_members(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    """Employee, team, project and technology rows plus effective team members (#333)."""
    client, sessionmaker, _ = db_api_client
    organization_id, owner_id, auth = await _organization(
        client, sessionmaker, bootstrap_key="usage-kinds-bootstrap"
    )
    setup_id = new_id("setup")
    team_id = new_id("operation")
    project_id = new_id("remote_project")
    technology_id = new_id("technology")
    async with sessionmaker() as db:
        await _catalog_row(db, organization_id, owner_id, setup_id)
        employee_id = await _member(db, organization_id, index=1)
        team_member_id = await _member(db, organization_id, index=2)
        await db.flush()
        db.add(
            CorporateTeam(
                organization_id=organization_id,
                id=team_id,
                name="Platform",
                description="",
                state="active",
                profile={},
                profile_revision=0,
            )
        )
        db.add(
            CorporateTeamMember(
                organization_id=organization_id,
                team_id=team_id,
                account_id=team_member_id,
            )
        )
        db.add(
            ProjectIdentity(
                id=project_id,
                organization_id=organization_id,
                namespace="remote",
                external_key=f"corporate:{project_id}",
                display_name="Usage project",
            )
        )
        await db.flush()
        db.add(
            CorporateProject(
                id=project_id,
                organization_id=organization_id,
                name="Usage project",
            )
        )
        db.add(
            Technology(
                organization_id=organization_id,
                id=technology_id,
                name="Swift",
                provenance="manual",
                lifecycle="active",
            )
        )
        await db.flush()
        db.add_all(
            [
                _employee_assignment(organization_id, employee_id, setup_id),
                CorporateCatalogAssignment(
                    id=new_id("operation"),
                    organization_id=organization_id,
                    team_id=team_id,
                    object_kind="setup",
                    stable_id=setup_id,
                    selector="exact",
                    version="1.0",
                    state="current",
                    revision=1,
                ),
                CorporateCatalogAssignment(
                    id=new_id("operation"),
                    organization_id=organization_id,
                    project_id=project_id,
                    object_kind="setup",
                    stable_id=setup_id,
                    selector="exact",
                    version="1.0",
                    state="current",
                    revision=1,
                ),
                CorporateCatalogAssignment(
                    id=new_id("operation"),
                    organization_id=organization_id,
                    technology_id=technology_id,
                    object_kind="setup",
                    stable_id=setup_id,
                    selector="exact",
                    version="1.0",
                    state="current",
                    revision=1,
                ),
            ]
        )
        await db.commit()

    path = f"/v1/corporate/organizations/{organization_id}/catalog-usage"
    response = await client.get(
        path,
        params={"object_kind": "setup", "stable_id": setup_id, "version": "1.0"},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    kinds = {item["subject_kind"] for item in body["items"]}
    assert kinds == {"employee", "team", "project", "technology"}
    assert body["total"] == len(body["items"])
    effective = [item for item in body["items"] if item["source"] == "effective"]
    assert len(effective) == 1
    assert effective[0]["subject_kind"] == "employee"
    assert effective[0]["subject_id"] == team_member_id
    assert effective[0]["source_team_id"] == team_id
    direct_subjects = {item["subject_id"] for item in body["items"] if item["source"] == "direct"}
    assert {employee_id, team_id, project_id, technology_id} <= direct_subjects


async def test_catalog_usage_stays_inside_the_tenant(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    """Same-object rows in another tenant never leak into the page (#333)."""
    client, sessionmaker, _ = db_api_client
    organization_id, owner_id, auth = await _organization(
        client, sessionmaker, bootstrap_key="usage-tenant-bootstrap-a"
    )
    other_id = new_id("organization")
    other_owner = new_id("account")
    setup_id = new_id("setup")
    async with sessionmaker() as db:
        db.add(Account(id=other_owner, status="active", display_name="Other Owner"))
        db.add(
            Organization(
                id=other_id,
                kind="corporate",
                display_name="Other tenant",
            )
        )
        await _catalog_row(db, organization_id, owner_id, setup_id)
        subject = await _member(db, organization_id, index=1)
        outsider = await _member(db, other_id, index=2)
        await db.flush()
        db.add_all(
            [
                _employee_assignment(organization_id, subject, setup_id),
                _employee_assignment(other_id, outsider, setup_id),
            ]
        )
        await db.commit()

    response = await client.get(
        f"/v1/corporate/organizations/{organization_id}/catalog-usage",
        params={"object_kind": "setup", "stable_id": setup_id},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert [item["subject_id"] for item in body["items"]] == [subject]
    assert all(item["organization_id"] == organization_id for item in body["items"])
