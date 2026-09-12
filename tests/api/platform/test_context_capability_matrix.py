"""API evidence for the SPEC-076 authorization matrix."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.session import issue_session
from ai_stp_foundation.ids import new_id
from ai_stp_platform.corporate_authorization import PrincipalType, has_corporate_permission
from ai_stp_platform.models import Account, Device
from ai_stp_platform.organization_models import (
    CorporateProject,
    CorporateRole,
    CorporateRoleBinding,
    CorporateRolePermission,
    CorporateServicePrincipal,
    Organization,
    OrganizationMembership,
)

pytestmark = pytest.mark.platform
pytest_plugins = ("tests.api.platform.test_context_project_ledger",)


@pytest.mark.parametrize("principal_type", ["user", "service_principal"])
@pytest.mark.parametrize("grant_first", [False, True])
async def test_multiple_inherited_bindings_and_projection_fail_closed(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
    principal_type: PrincipalType,
    grant_first: bool,
) -> None:
    client, sessionmaker, token, personal_id, _link_id, _project_id = project_harness
    async with sessionmaker() as db:
        membership = await db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == personal_id
            )
        )
        assert membership is not None
        account_id = membership.account_id
        organization = Organization(
            id=new_id("organization"), kind="corporate", display_name="Scoped policy"
        )
        db.add(organization)
        await db.flush()
        organization_id = organization.id
        member = OrganizationMembership(
            organization_id=organization_id, account_id=account_id, role="viewer"
        )
        principal = CorporateServicePrincipal(
            id=new_id("service_principal"), organization_id=organization_id, name="Probe"
        )
        db.add_all([member, principal])
        project = CorporateProject(
            id=new_id("remote_project"), organization_id=organization_id, name="Bound"
        )
        other_project = CorporateProject(
            id=new_id("remote_project"), organization_id=organization_id, name="Unbound"
        )
        db.add_all([project, other_project])
        db.add_all(
            [
                CorporateRole(organization_id=organization_id, name="viewer"),
                CorporateRole(organization_id=organization_id, name="editor"),
                CorporateRole(
                    organization_id=organization_id, name="inherited", parent_role="editor"
                ),
            ]
        )
        await db.flush()
        db.add(
            CorporateRolePermission(
                organization_id=organization_id, role="viewer", permission="organization.read"
            )
        )
        db.add_all(
            [
                CorporateRolePermission(
                    organization_id=organization_id, role="editor", permission=permission
                )
                for permission in ("organization.manage", "project.update")
            ]
        )
        principal_id = account_id if principal_type == "user" else principal.id
        roles = ["inherited", "viewer"] if grant_first else ["viewer", "inherited"]
        bindings = [
            CorporateRoleBinding(
                id=new_id("operation"),
                organization_id=organization_id,
                principal_type=principal_type,
                account_id=account_id if principal_type == "user" else None,
                service_principal_id=principal.id
                if principal_type == "service_principal"
                else None,
                role=role,
                scope_kind="organization",
                scope_id=organization_id,
            )
            for role in roles
        ]
        db.add_all(bindings)
        await db.commit()

        async def allowed(
            *,
            permission: str = "organization.manage",
            scope_kind: str = "organization",
            scope_id: str | None = None,
            organization_id: str = organization_id,
            authorization_revision: int | None = None,
        ) -> bool:
            return await has_corporate_permission(
                db,
                organization_id=organization_id,
                principal_type=principal_type,
                principal_id=principal_id,
                permission=permission,
                scope_kind=scope_kind,
                scope_id=scope_id,
                authorization_revision=authorization_revision,
            )

        assert await allowed()
        assert not await allowed(authorization_revision=organization.policy_revision + 1)
        assert not await allowed(organization_id=personal_id)
        if principal_type == "user":
            response = await client.get(
                f"/v1/organizations/{organization_id}/capabilities",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200, response.text
            assert "organization.manage" in response.json()["capabilities"]
            context = await client.get(
                f"/v1/corporate/organizations/{organization_id}/context",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert context.status_code == 200, context.text
            assert "organization.manage" in context.json()["capabilities"]
        grant = next(binding for binding in bindings if binding.role == "inherited")
        grant.scope_kind = "project"
        grant.scope_id = project.id
        await db.commit()
        assert not await allowed()
        assert await allowed(permission="project.update", scope_kind="project", scope_id=project.id)
        assert not await allowed(
            permission="project.update", scope_kind="project", scope_id=other_project.id
        )
        if principal_type == "user":
            response = await client.get(
                f"/v1/organizations/{organization_id}/capabilities",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200, response.text
            assert "organization.manage" not in response.json()["capabilities"]
            assert response.json()["unavailable"]["organization.manage"] == "forbidden"
            context = await client.get(
                f"/v1/corporate/organizations/{organization_id}/context",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert context.status_code == 200, context.text
            assert "organization.manage" not in context.json()["capabilities"]
        grant.state = "revoked"
        await db.commit()
        assert not await allowed(
            permission="project.update", scope_kind="project", scope_id=project.id
        )
        grant.state = "active"
        if principal_type == "user":
            member.state = "suspended"
        else:
            principal.state = "suspended"
        await db.commit()
        assert not await allowed(
            permission="project.update", scope_kind="project", scope_id=project.id
        )


@pytest.mark.parametrize(
    ("role", "read_capability"),
    [
        ("owner", True),
        ("admin", True),
        ("member", True),
        ("lead", False),
        ("staff", False),
        ("custom", False),
    ],
)
async def test_owner_admin_member_projection_matrix(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
    role: str,
    read_capability: bool,
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
    assert "organization.manage" not in capabilities
    assert ("project.read" in capabilities) is read_capability
    assert ("project.list" in capabilities) is read_capability
    assert ("project.update" in capabilities) is read_capability
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
