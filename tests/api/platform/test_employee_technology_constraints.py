"""Database tenant constraints protect retained competence identity."""

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import Organization, OrganizationMembership
from ai_stp_platform.technology_models import EmployeeTechnology, Technology

pytestmark = pytest.mark.platform


async def test_competence_database_tenant_and_unique_constraints(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    _, sessionmaker, _ = db_api_client
    organization_id = new_id("organization")
    other_id = new_id("organization")
    account_id = new_id("account")
    technology_id = new_id("technology")
    async with sessionmaker() as db:
        db.add(Account(id=account_id, status="active"))
        db.add_all(
            [
                Organization(id=organization_id, kind="corporate", display_name="Competences"),
                Organization(id=other_id, kind="corporate", display_name="Other"),
            ]
        )
        await db.flush()
        db.add(
            OrganizationMembership(
                organization_id=organization_id, account_id=account_id, role="staff"
            )
        )
        db.add(
            Technology(
                organization_id=organization_id, id=technology_id, name="Swift", provenance="manual"
            )
        )
        await db.flush()
        db.add(
            EmployeeTechnology(
                organization_id=organization_id,
                id=new_id("relation"),
                account_id=account_id,
                technology_id=technology_id,
            )
        )
        await db.flush()
        for tenant in [organization_id, other_id]:
            with pytest.raises(IntegrityError):
                async with db.begin_nested():
                    db.add(
                        EmployeeTechnology(
                            organization_id=tenant,
                            id=new_id("relation"),
                            account_id=account_id,
                            technology_id=technology_id,
                        )
                    )
                    await db.flush()
