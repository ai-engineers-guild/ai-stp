"""Real PostgreSQL integrity checks for the single tenant relationship model."""

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_foundation.ids import new_id
from ai_stp_platform.organization_models import Organization, ProjectIdentity
from ai_stp_platform.technology_models import (
    ProjectTechnologyRelation,
    Technology,
    TechnologyUsageFact,
)
from ai_stp_platform.tenant_scope import set_tenant_scope


async def test_tenant_endpoints_and_distinct_project_count(db_session: AsyncSession) -> None:
    org, other = new_id("organization"), new_id("organization")
    await set_tenant_scope(db_session, "*")
    db_session.add_all(
        [Organization(id=value, kind="corporate", display_name=value) for value in (org, other)]
    )
    await db_session.flush()
    project, provider = new_id("remote_project"), new_id("remote_project")
    db_session.add_all(
        [
            ProjectIdentity(
                id=value,
                organization_id=org,
                namespace=namespace,
                external_key=value,
                display_name=value,
            )
            for value, namespace in ((project, "remote"), (provider, "provider"))
        ]
    )
    technology = new_id("technology")
    db_session.add(Technology(id=technology, organization_id=org, name="Bun", provenance="manual"))
    await db_session.flush()
    relation = new_id("relation")
    db_session.add(
        ProjectTechnologyRelation(
            id=relation, organization_id=org, project_id=project, technology_id=technology
        )
    )
    await db_session.flush()
    db_session.add_all(
        [
            TechnologyUsageFact(
                organization_id=org, relation_id=relation, context=context, review="confirmed"
            )
            for context in ("production", "development", "testing")
        ]
    )
    await db_session.flush()
    assert (
        await db_session.scalar(
            select(func.count(func.distinct(ProjectTechnologyRelation.project_id))).join(
                TechnologyUsageFact,
                (TechnologyUsageFact.organization_id == ProjectTechnologyRelation.organization_id)
                & (TechnologyUsageFact.relation_id == ProjectTechnologyRelation.id),
            )
        )
        == 1
    )
    for tenant, endpoint in ((org, provider), (other, project)):
        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                db_session.add(
                    ProjectTechnologyRelation(
                        id=new_id("relation"),
                        organization_id=tenant,
                        project_id=endpoint,
                        technology_id=technology,
                    )
                )
                await db_session.flush()
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE project_technology_relation SET id = :new WHERE id = :old"),
                {"new": new_id("relation"), "old": relation},
            )
