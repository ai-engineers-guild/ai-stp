"""Manual registry-to-project service path against migrated PostgreSQL."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.errors import ApiError
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate.service import bootstrap, change_project_lifecycle, create_project
from ai_stp_api.slices.technology.service import (
    change_category_lifecycle,
    change_lifecycle,
    import_seed,
    list_technologies,
    read_landscape,
    write_category,
    write_project_activity,
    write_project_technology,
    write_technology,
)
from ai_stp_contracts.context import context_authorization_revision
from ai_stp_contracts.corporate import (
    CorporateBootstrapRequest,
    CorporateProjectCreateRequest,
    CorporateProjectLifecycleRequest,
)
from ai_stp_contracts.technology import (
    CategoryLifecycleRequest,
    CategoryWriteRequest,
    ProjectActivityRequest,
    ProjectTechnologyWriteRequest,
    TechnologyCategoryMetadata,
    TechnologyLandscapeQuery,
    TechnologyLifecycleRequest,
    TechnologySeedRequest,
    TechnologyUsageFact,
    TechnologyWriteRequest,
)
from ai_stp_contracts.technology_seed import SEED_CATEGORIES, SEED_TECHNOLOGIES
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, AuditEvent
from ai_stp_platform.organization_models import (
    CorporateProject,
    CorporateRole,
    CorporateRoleBinding,
    CorporateRolePermission,
    Organization,
    OrganizationMembership,
)
from ai_stp_platform.technology_models import Technology, TechnologyCategory


async def test_seed_replay_preserves_owner_edits(db_session: AsyncSession) -> None:
    account = new_id("account")
    db_session.add(Account(id=account, status="active"))
    await db_session.flush()
    ctx = AuthContext(account, "seed-test-session", None, "active", False, False)
    org = await bootstrap(
        db_session,
        payload=CorporateBootstrapRequest(
            organization_name="Seed acceptance",
            superadmin_account_id=account,
            idempotency_key="seed-bootstrap-0001",
        ),
        request_id="seed-test",
    )
    payload = TechnologySeedRequest(authorization_revision=1, idempotency_key="seed-import-0001")
    first = await import_seed(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        payload=payload,
        request_id="seed-test",
    )
    assert len(first.created_category_ids) == 23
    assert len(first.created_technology_ids) == 7
    assert (
        await import_seed(
            db_session,
            ctx=ctx,
            organization_id=org.organization_id,
            payload=payload,
            request_id="seed-replay",
        )
        == first
    )
    technology_id, metadata = SEED_TECHNOLOGIES[0]
    edited = await write_technology(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        technology_id=technology_id,
        payload=TechnologyWriteRequest(
            authorization_revision=2,
            expected_revision=1,
            idempotency_key="seed-owner-edit-0001",
            metadata=metadata.model_copy(update={"description": "Owner description"}),
        ),
        request_id="seed-edit",
    )
    repeated = await import_seed(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        payload=payload.model_copy(
            update={"authorization_revision": 3, "idempotency_key": "seed-import-0002"}
        ),
        request_id="seed-test",
    )
    assert repeated.created_category_ids == repeated.created_technology_ids == []
    assert len(repeated.retained_category_ids) == 23
    assert len(repeated.retained_technology_ids) == 7
    row = await db_session.get(Technology, (org.organization_id, technology_id))
    assert row is not None and row.description == "Owner description"
    assert row.revision == edited.revision and row.lifecycle == "draft"
    assert len(
        list(
            (
                await db_session.scalars(
                    select(TechnologyCategory).where(
                        TechnologyCategory.organization_id == org.organization_id
                    )
                )
            ).all()
        )
    ) == len(SEED_CATEGORIES)

    category_id = metadata.category_ids[0]
    archived_category = await change_category_lifecycle(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        category_id=category_id,
        payload=CategoryLifecycleRequest(
            expected_revision=1,
            target="archived",
            authorization_revision=3,
            idempotency_key="seed-owner-category-remove-0001",
        ),
        request_id="seed-category-remove",
    )
    assert archived_category.state == "archived" and archived_category.revision == 2
    await import_seed(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        payload=payload.model_copy(
            update={
                "authorization_revision": 4,
                "idempotency_key": "seed-import-after-remove-0001",
            }
        ),
        request_id="seed-after-remove",
    )
    category_row = await db_session.get(TechnologyCategory, (org.organization_id, category_id))
    assert category_row is not None and category_row.state == "archived"
    with pytest.raises(ApiError, match="active categories"):
        await write_technology(
            db_session,
            ctx=ctx,
            organization_id=org.organization_id,
            technology_id=None,
            payload=TechnologyWriteRequest(
                expected_revision=0,
                authorization_revision=4,
                idempotency_key="seed-new-archived-category-0001",
                metadata=metadata.model_copy(
                    update={"name": "New archived classification", "aliases": []}
                ),
            ),
            request_id="seed-new-archived-category",
        )
    retained_edit = await write_technology(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        technology_id=technology_id,
        payload=TechnologyWriteRequest(
            expected_revision=edited.revision,
            authorization_revision=4,
            idempotency_key="seed-retain-archived-category-0001",
            metadata=metadata.model_copy(update={"description": "Retained owner classification"}),
        ),
        request_id="seed-retain-archived-category",
    )
    assert (
        retained_edit.technology_id == technology_id and category_id in retained_edit.category_ids
    )
    restored_category = await change_category_lifecycle(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        category_id=category_id,
        payload=CategoryLifecycleRequest(
            expected_revision=2,
            target="active",
            authorization_revision=5,
            idempotency_key="seed-owner-category-restore-0001",
        ),
        request_id="seed-category-restore",
    )
    assert restored_category.category_id == category_id and restored_category.revision == 3
    assert restored_category.state == "active"

    other_id = new_id("organization")
    db_session.add(Organization(id=other_id, kind="corporate", display_name="Seed isolated tenant"))
    await db_session.flush()
    db_session.add_all(
        [
            OrganizationMembership(
                organization_id=other_id, account_id=account, role="seed-maintainer"
            ),
            CorporateRole(organization_id=other_id, name="seed-maintainer"),
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            CorporateRolePermission(
                organization_id=other_id, role="seed-maintainer", permission=permission
            )
            for permission in ("technology.create", "category.create")
        ]
    )
    db_session.add(
        CorporateRoleBinding(
            id=new_id("operation"),
            organization_id=other_id,
            account_id=account,
            role="seed-maintainer",
            scope_kind="organization",
            scope_id=other_id,
        )
    )
    await db_session.flush()
    collision = await write_category(
        db_session,
        ctx=ctx,
        organization_id=other_id,
        category_id=None,
        payload=CategoryWriteRequest(
            authorization_revision=1,
            idempotency_key="seed-collision-category-0001",
            expected_revision=0,
            metadata=TechnologyCategoryMetadata(name="Identity and security infrastructure"),
        ),
        request_id="seed-collision",
    )
    with pytest.raises(ApiError, match="seed category name already exists"):
        await import_seed(
            db_session,
            ctx=ctx,
            organization_id=other_id,
            payload=TechnologySeedRequest(
                authorization_revision=2, idempotency_key="seed-collision-import-0001"
            ),
            request_id="seed-collision",
        )
    isolated_categories = list(
        (
            await db_session.scalars(
                select(TechnologyCategory).where(TechnologyCategory.organization_id == other_id)
            )
        ).all()
    )
    assert [entry.id for entry in isolated_categories] == [collision.category_id]
    assert (
        await db_session.scalar(select(Technology.id).where(Technology.organization_id == other_id))
        is None
    )
    retained = await db_session.get(Technology, (org.organization_id, technology_id))
    assert retained is not None and retained.description == "Retained owner classification"
    seed_audits = list(
        (
            await db_session.scalars(
                select(AuditEvent).where(
                    AuditEvent.organization_id == org.organization_id,
                    AuditEvent.action == "technology.seed.import",
                )
            )
        ).all()
    )
    assert len(seed_audits) == 3
    assert all(entry.reason == "initial_registry_import" for entry in seed_audits)
    assert all(entry.payload["source"] == "seed_manifest" for entry in seed_audits)
    archived = await change_lifecycle(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        technology_id=technology_id,
        payload=TechnologyLifecycleRequest(
            lifecycle="archived",
            expected_revision=retained_edit.revision,
            authorization_revision=6,
            idempotency_key="seed-archive-draft-0001",
        ),
        request_id="seed-archive",
    )
    assert archived.restore_lifecycle == "draft"
    restored = await change_lifecycle(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        technology_id=technology_id,
        payload=TechnologyLifecycleRequest(
            lifecycle="draft",
            expected_revision=archived.revision,
            authorization_revision=7,
            idempotency_key="seed-restore-draft-0001",
        ),
        request_id="seed-restore",
    )
    assert restored.lifecycle == "draft" and restored.technology_id == technology_id
    for query, expected_id in (
        ("  REACT.js  ", SEED_TECHNOLOGIES[5][0]),
        ("Postgres", SEED_TECHNOLOGIES[6][0]),
    ):
        candidates = await list_technologies(
            db_session,
            ctx=ctx,
            organization_id=org.organization_id,
            include_archived=False,
            offset=0,
            limit=128,
            search=query,
            request_id="seed-search",
        )
        assert candidates.total == 1 and candidates.items[0].technology_id == expected_id
        landscape = await read_landscape(
            db_session,
            ctx=ctx,
            organization_id=org.organization_id,
            filters=TechnologyLandscapeQuery(query=query),
            request_id="seed-search",
        )
        assert landscape.total == 1 and landscape.items[0].technology.technology_id == expected_id
    literal = await list_technologies(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        include_archived=False,
        offset=0,
        limit=128,
        search="%",
        request_id="seed-search",
    )
    assert literal.total == 0
    category_grant = await db_session.get(
        CorporateRolePermission, (other_id, "seed-maintainer", "category.create")
    )
    assert category_grant is not None
    await db_session.delete(category_grant)
    await db_session.flush()
    with pytest.raises(ApiError, match="capability is forbidden"):
        await import_seed(
            db_session,
            ctx=ctx,
            organization_id=other_id,
            payload=TechnologySeedRequest(
                authorization_revision=2, idempotency_key="seed-denied-import-0001"
            ),
            request_id="seed-denied",
        )


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
    development = await write_project_technology(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        project_id=project.project_id,
        payload=ProjectTechnologyWriteRequest.model_validate(
            {
                "technology_id": tech,
                "fact": {"context": "development"},
                "authorization_revision": context_authorization_revision(
                    "corporate",
                    org.organization_id,
                    6,
                    1,
                ),
                "expected_revision": 1,
                "idempotency_key": "registry-development-usage-0001",
            }
        ),
        request_id="registry-test",
    )
    assert development.relation_id == result.relation_id
    assert len(development.facts) == 2
    for revision in (
        context_authorization_revision("corporate", org.organization_id, 6, 1),
        context_authorization_revision("corporate", org.organization_id, 7, 2),
        context_authorization_revision("corporate", new_id("organization"), 7, 1),
    ):
        with pytest.raises(ApiError, match="capability revision is stale"):
            await write_project_technology(
                db_session,
                ctx=ctx,
                organization_id=org.organization_id,
                project_id=project.project_id,
                payload=ProjectTechnologyWriteRequest.model_validate(
                    {
                        "technology_id": tech,
                        "fact": {"context": "testing"},
                        "authorization_revision": revision,
                        "expected_revision": 2,
                        "idempotency_key": "registry-opaque-conflict-0001",
                    }
                ),
                request_id="registry-test",
            )
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
    for presentation in ("grouped", "radar", "relationships"):
        projected = await read_landscape(
            db_session,
            ctx=ctx,
            organization_id=org.organization_id,
            filters=TechnologyLandscapeQuery.model_validate(
                {"view": presentation, "context": "production"}
            ),
            request_id="registry-shared-projection-test",
        )
        assert projected.items == current.items and projected.total == current.total
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
    stored_org = await db_session.get(Organization, org.organization_id)
    assert stored_org is not None
    source_status = await write_project_activity(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        project_id=project.project_id,
        payload=ProjectActivityRequest(
            expected_revision=stored_project.revision,
            authorization_revision=stored_org.policy_revision,
            idempotency_key="registry-source-unavailable-0001",
            repository_activity_at=None,
            activity_override="inactive",
            source_availability="unavailable",
        ),
        request_id="registry-source-unavailable",
    )
    assert source_status.source_availability == "unavailable"
    assert stored_project.lifecycle == "active"
    unavailable_source = await read_landscape(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        filters=TechnologyLandscapeQuery(source_availability="unavailable", include_inactive=True),
        request_id="registry-unavailable-source-landscape",
    )
    assert unavailable_source.items[0].project_count == 1
    assert unavailable_source.items[0].projects[0].source_availability == "unavailable"
    assert unavailable_source.items[0].projects[0].usage.facts == development.facts
    available_source = await read_landscape(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        filters=TechnologyLandscapeQuery(source_availability="available", include_inactive=True),
        request_id="registry-available-source-landscape",
    )
    assert available_source.items[0].project_count == 0
    older_writer = await write_project_activity(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        project_id=project.project_id,
        payload=ProjectActivityRequest(
            expected_revision=source_status.revision,
            authorization_revision=stored_org.policy_revision,
            idempotency_key="registry-source-older-writer-0001",
            repository_activity_at=None,
            activity_override=None,
        ),
        request_id="registry-source-older-writer",
    )
    assert older_writer.source_availability == "unavailable"
    await change_project_lifecycle(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        project_id=project.project_id,
        payload=CorporateProjectLifecycleRequest(
            expected_revision=stored_project.revision,
            authorization_revision=stored_org.policy_revision,
            idempotency_key="registry-archive-project-0001",
            target="archived",
        ),
        request_id="registry-archive-project",
    )
    retired = await write_project_technology(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        project_id=project.project_id,
        payload=ProjectTechnologyWriteRequest(
            technology_id=tech,
            state="retired",
            fact=TechnologyUsageFact(context="production"),
            expected_revision=development.revision,
            authorization_revision=stored_org.policy_revision,
            idempotency_key="registry-retire-archived-0001",
        ),
        request_id="registry-retire-archived",
    )
    assert retired.relation_id == result.relation_id
    assert retired.state == "retired" and retired.facts == development.facts
