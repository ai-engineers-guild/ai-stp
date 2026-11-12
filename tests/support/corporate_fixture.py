"""Seed an owned corporate account and project through the actual API/database."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import (
    CorporateProject,
    CorporateProjectMember,
    ProjectIdentity,
)


async def seed_corporate(app: Any, origin: str) -> tuple[str, str, str]:
    account, project = new_id("account"), new_id("remote_project")
    async with app.state.sessionmaker() as db:
        db.add(Account(id=account))
        await db.commit()
    async with AsyncClient(base_url=origin, timeout=15, trust_env=False) as client:
        response = await client.post(
            "/v1/corporate/bootstrap",
            json={
                "organization_name": "Installed fixture company",
                "superadmin_account_id": account,
                "idempotency_key": "installed-desktop-corporate-bootstrap",
            },
            headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
        )
        assert response.status_code == 200
        organization = response.json()["organization_id"]
        assert isinstance(organization, str)
    async with app.state.sessionmaker() as db:
        db.add(
            ProjectIdentity(
                id=project,
                organization_id=organization,
                namespace="remote",
                external_key="installed-desktop:shared-project",
                display_name="Installed shared project",
            )
        )
        await db.flush()
        db.add(
            CorporateProject(
                id=project, organization_id=organization, name="Installed shared project"
            )
        )
        await db.flush()
        db.add(
            CorporateProjectMember(
                organization_id=organization, project_id=project, account_id=account, role="owner"
            )
        )
        await db.commit()
    return account, organization, project
