"""Manual registry-to-project service path against migrated PostgreSQL."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.errors import ApiError
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate.service import bootstrap, create_project
from ai_stp_api.slices.technology.service import (
    change_lifecycle,
    read_landscape,
    write_category,
    write_project_technology,
    write_technology,
)
from ai_stp_contracts.corporate import CorporateBootstrapRequest, CorporateProjectCreateRequest
from ai_stp_contracts.technology import (
    CategoryWriteRequest,
    ProjectTechnologyWriteRequest,
    TechnologyLandscapeQuery,
    TechnologyLifecycleRequest,
    TechnologyWriteRequest,
)
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, AuditEvent
from ai_stp_platform.organization_models import CorporateProject


async def test_manual_usage_replay_and_revision_conflict(db_session: AsyncSession) -> None:
    account = new_id("account")
    db_session.add(Account(id=account, status="active"))
    await db_session.flush()
    ctx = AuthContext(account, "technology-test-session", None, "active", False, False)
    org = await bootstrap(
        db_session,
        payload=CorporateBootstrapRequest(
            organization_name="Registry acceptance",
            superadmin_account_id=account,
            idempotency_key="registry-bootstrap-0001",
        ),
        request_id="registry-test",
    )
    category_payload = CategoryWriteRequest.model_validate(
        {
            "metadata": {"name": "Runtime"},
            "expected_revision": 0,
            "authorization_revision": 1,
            "idempotency_key": "registry-category-0001",
        }
    )
    created_category = await write_category(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        category_id=None,
        payload=category_payload,
        request_id="registry-test",
    )
    category = created_category.category_id
    repeated_category = await write_category(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        category_id=None,
        payload=category_payload.model_copy(update={"authorization_revision": 2}),
        request_id="registry-test",
    )
    assert repeated_category == created_category
    metadata = {"name": "Bun", "category_ids": [category], "aliases": ["Bun runtime"]}
    technology_payload = TechnologyWriteRequest.model_validate(
        {
            "metadata": metadata,
            "expected_revision": 0,
            "authorization_revision": 2,
            "idempotency_key": "registry-technology-0001",
        }
    )
    first = await write_technology(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        technology_id=None,
        payload=technology_payload,
        request_id="registry-test",
    )
    tech = first.technology_id
    assert first.lifecycle == "draft"
    replay = await write_technology(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        technology_id=None,
        payload=technology_payload.model_copy(update={"authorization_revision": 3}),
        request_id="registry-test",
    )
    assert replay == first
    with pytest.raises(ApiError, match="idempotency"):
        await write_technology(
            db_session,
            ctx=ctx,
            organization_id=org.organization_id,
            technology_id=tech,
            payload=technology_payload.model_copy(update={"authorization_revision": 3}),
            request_id="registry-test",
        )
    await change_lifecycle(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        technology_id=tech,
        payload=TechnologyLifecycleRequest(
            lifecycle="active",
            expected_revision=1,
            authorization_revision=3,
            idempotency_key="registry-approval-0001",
        ),
        request_id="registry-test",
    )
    project = await create_project(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        payload=CorporateProjectCreateRequest(
            name="Manual project", authorization_revision=4, idempotency_key="registry-project-0001"
        ),
        request_id="registry-test",
    )
    usage = ProjectTechnologyWriteRequest.model_validate(
        {
            "technology_id": tech,
            "fact": {"context": "production"},
            "authorization_revision": 5,
            "expected_revision": 0,
            "idempotency_key": "registry-manual-usage-0001",
        }
    )
    result = await write_project_technology(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        project_id=project.project_id,
        payload=usage,
        request_id="registry-test",
    )
    assert result.facts[0].review == "confirmed"
    assert result.facts[0].version is None
    repeated = await write_project_technology(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        project_id=project.project_id,
        payload=usage,
        request_id="registry-test",
    )
    assert repeated.relation_id == result.relation_id
    with pytest.raises(ApiError, match="revision changed"):
        await write_project_technology(
            db_session,
            ctx=ctx,
            organization_id=org.organization_id,
            project_id=project.project_id,
            payload=usage.model_copy(
                update={
                    "authorization_revision": 6,
                    "idempotency_key": "registry-conflict-0001",
                }
            ),
            request_id="registry-test",
        )
    await db_session.flush()
    actions = list(
        (
            await db_session.scalars(
                select(AuditEvent.action).where(
                    AuditEvent.organization_id == org.organization_id,
                )
            )
        ).all()
    )
    assert actions.count("project.technology.update") == 1
    assert actions.count("project.technology.update.replay") == 1
    landscape = await read_landscape(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        filters=TechnologyLandscapeQuery(project_offset=1, project_limit=1),
        request_id="registry-landscape-test",
    )
    assert landscape.total == 1
    assert landscape.items[0].project_count == 1
    assert landscape.items[0].projects == []
    current = await read_landscape(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        filters=TechnologyLandscapeQuery(context="production"),
        request_id="registry-landscape-test",
    )
    assert current.items[0].projects[0].project_id == project.project_id
    assert current.items[0].projects[0].activity == "unknown"
    stored_project = await db_session.get(CorporateProject, project.project_id)
    assert stored_project is not None
    stored_project.activity_override = "inactive"
    await db_session.flush()
    inactive = await read_landscape(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        filters=TechnologyLandscapeQuery(),
        request_id="registry-landscape-test",
    )
    assert inactive.items[0].project_count == 0
    history = await read_landscape(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        filters=TechnologyLandscapeQuery(include_inactive=True),
        request_id="registry-landscape-test",
    )
    assert history.items[0].project_count == 1
