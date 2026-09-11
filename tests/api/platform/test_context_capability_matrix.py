"""API evidence for the SPEC-076 authorization matrix."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.session import issue_session
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, Device
from ai_stp_platform.organization_models import Organization, OrganizationMembership

pytestmark = pytest.mark.platform
pytest_plugins = ("tests.api.platform.test_context_project_ledger",)


@pytest.mark.parametrize(
    ("role", "admin_capability"),
    [("owner", False), ("admin", False), ("member", False)],
)
async def test_owner_admin_member_projection_matrix(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
    role: str,
    admin_capability: bool,
) -> None:
    client, sessionmaker, token, organization_id, _link_id, _remote_project_id = project_harness
    async with sessionmaker() as db:
        personal = await db.get(Organization, organization_id)
        membership = await db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id
            )
        )
        assert personal is not None and membership is not None
        organization = Organization(
            id=new_id("organization"),
            kind="corporate",
            owner_account_id=None,
            display_name="Corporate",
        )
        db.add(organization)
        db.add(
            OrganizationMembership(
                organization_id=organization.id,
                account_id=membership.account_id,
                role=role,
                state="active",
            )
        )
        await db.commit()
        organization_id = organization.id

    response = await client.get(
        f"/v1/organizations/{organization_id}/capabilities",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    capabilities = response.json()["capabilities"]
    assert ("organization.manage" in capabilities) is admin_capability
    assert "project.read" in capabilities
    assert "project.list" in capabilities
    unavailable = response.json()["unavailable"]
    for capability in ("team.manage", "assignment.assign", "saml.manage", "audit.read"):
        assert capability not in capabilities
        assert capability in unavailable


async def test_outsider_suspended_and_foreign_contexts_fail_closed(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
) -> None:
    client, sessionmaker, token, organization_id, link_id, _remote_project_id = project_harness
    async with sessionmaker() as db:
        personal_membership = await db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id
            )
        )
        assert personal_membership is not None
        suspended_organization = Organization(
            id=new_id("organization"),
            kind="corporate",
            owner_account_id=None,
            display_name="Suspended",
        )
        suspended_membership = OrganizationMembership(
            organization_id=suspended_organization.id,
            account_id=personal_membership.account_id,
            role="member",
            state="suspended",
        )
        foreign = Organization(
            id=new_id("organization"),
            kind="corporate",
            owner_account_id=None,
            display_name="Foreign",
        )
        db.add_all([suspended_organization, suspended_membership, foreign])
        await db.commit()
        outsider = Account(id=new_id("account"))
        device = Device(
            id=new_id("device"),
            account_id=outsider.id,
            public_key="b3V0c2lkZXItcHJvamVjdC1sZWRnZS1rZXk=",
            state="active",
        )
        db.add(outsider)
        await db.flush()
        db.add(device)
        await db.flush()
        issued = await issue_session(
            db, account_id=outsider.id, device_id=device.id, ttl_seconds=3600
        )
        await db.commit()
        organization_id = suspended_organization.id
        foreign_id = foreign.id
        outsider_token = issued.raw_token

    suspended = await client.get(
        f"/v1/organizations/{organization_id}/capabilities",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert suspended.status_code == 403
    foreign_response = await client.get(
        f"/v1/organizations/{foreign_id}/capabilities",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert foreign_response.status_code == 403
    outsider_response = await client.get(
        f"/v1/organizations/{organization_id}/capabilities",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    assert outsider_response.status_code == 403

    forged = await client.get(
        f"/v1/projects/links/{link_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-AI-STP-Organization-Id": organization_id,
            "X-AI-STP-Capabilities": "project.update,organization.manage",
        },
    )
    assert forged.status_code in {403, 404}
