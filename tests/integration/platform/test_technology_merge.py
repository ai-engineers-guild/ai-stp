"""Deliberate merges keep canonical pair IDs, evidence and exact plan preconditions."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.errors import ApiError
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate.service import bootstrap, create_project, create_team
from ai_stp_api.slices.technology.merge import merge_technology, read_merge_plan
from ai_stp_api.slices.technology.service import (
    change_lifecycle,
    import_seed,
    list_technologies,
    read_landscape,
    write_project_technology,
    write_technology_team,
)
from ai_stp_contracts.corporate import (
    CorporateBootstrapRequest,
    CorporateProjectCreateRequest,
    CorporateTeamCreateRequest,
)
from ai_stp_contracts.technology import (
    ProjectTechnologyWriteRequest,
    TechnologyLandscapeQuery,
    TechnologyLifecycleRequest,
    TechnologyMergeRequest,
    TechnologySeedRequest,
    TechnologyTeamWriteRequest,
)
from ai_stp_contracts.technology_seed import SEED_TECHNOLOGIES
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account
from ai_stp_platform.technology_models import (
    ProjectTechnologyRelation,
    Technology,
    TechnologyTeamResponsibility,
    TechnologyUsageFact,
)


async def test_merge_conflict_preflight_then_retains_pairs_and_history(
    db_session: AsyncSession,
) -> None:
    account_id = new_id("account")
    db_session.add(Account(id=account_id, status="active"))
    await db_session.flush()
    ctx = AuthContext(account_id, "merge-test-session", None, "active", False, False)
    org = (
        await bootstrap(
            db_session,
            payload=CorporateBootstrapRequest(
                organization_name="Merge acceptance",
                superadmin_account_id=account_id,
                idempotency_key="merge-bootstrap-0001",
            ),
            request_id="merge-test",
        )
    ).organization_id
    await import_seed(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=TechnologySeedRequest(
            authorization_revision=1, idempotency_key="merge-initial-seed-0001"
        ),
        request_id="merge-test",
    )
    source, target = SEED_TECHNOLOGIES[0][0], SEED_TECHNOLOGIES[1][0]
    for technology_id, authorization in ((source, 2), (target, 3)):
        await change_lifecycle(
            db_session,
            ctx=ctx,
            organization_id=org,
            technology_id=technology_id,
            payload=TechnologyLifecycleRequest(
                lifecycle="active",
                expected_revision=1,
                authorization_revision=authorization,
                idempotency_key=f"merge-approve-{authorization}-0001",
            ),
            request_id="merge-test",
        )
    project = await create_project(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=CorporateProjectCreateRequest(
            name="Shared canonical project",
            authorization_revision=4,
            idempotency_key="merge-project-0001",
        ),
        request_id="merge-test",
    )
    source_fact = {
        "context": "production",
        "version": "1.2.3",
        "version_kind": "observed_version",
        "evidence": [
            {
                "source": "observed",
                "path": "package.json",
                "observed_at": "2026-09-12T00:00:00.000Z",
                "source_revision": "commit-a",
            }
        ],
    }
    original_source = await write_project_technology(
        db_session,
        ctx=ctx,
        organization_id=org,
        project_id=project.project_id,
        payload=ProjectTechnologyWriteRequest.model_validate(
            {
                "technology_id": source,
                "fact": source_fact,
                "expected_revision": 0,
                "authorization_revision": 5,
                "idempotency_key": "merge-source-use-0001",
            }
        ),
        request_id="merge-test",
    )
    conflicting_target = await write_project_technology(
        db_session,
        ctx=ctx,
        organization_id=org,
        project_id=project.project_id,
        payload=ProjectTechnologyWriteRequest.model_validate(
            {
                "technology_id": target,
                "fact": {
                    "context": "production",
                    "version": "^1.0",
                    "version_kind": "declared_range",
                },
                "expected_revision": 0,
                "authorization_revision": 6,
                "idempotency_key": "merge-target-use-0001",
            }
        ),
        request_id="merge-test",
    )
    with pytest.raises(ApiError, match="conflicting usage facts"):
        await read_merge_plan(
            db_session,
            ctx=ctx,
            organization_id=org,
            source_id=source,
            target_id=target,
            request_id="merge-test",
        )
    source_row = await db_session.get(Technology, (org, source))
    assert source_row is not None and source_row.redirect_id is None
    target_fact = {
        **source_fact,
        "evidence": [
            {
                "source": "observed",
                "path": "bun.lock",
                "observed_at": "2026-09-12T00:00:00.000Z",
                "source_revision": "commit-a",
            }
        ],
    }
    corrected_target = await write_project_technology(
        db_session,
        ctx=ctx,
        organization_id=org,
        project_id=project.project_id,
        payload=ProjectTechnologyWriteRequest.model_validate(
            {
                "technology_id": target,
                "fact": target_fact,
                "expected_revision": 1,
                "authorization_revision": 7,
                "idempotency_key": "merge-target-correct-0001",
            }
        ),
        request_id="merge-test",
    )
    assert corrected_target.relation_id == conflicting_target.relation_id
    other_project = await create_project(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=CorporateProjectCreateRequest(
            name="Source-only project",
            authorization_revision=8,
            idempotency_key="merge-other-project-0001",
        ),
        request_id="merge-test",
    )
    other_source = await write_project_technology(
        db_session,
        ctx=ctx,
        organization_id=org,
        project_id=other_project.project_id,
        payload=ProjectTechnologyWriteRequest.model_validate(
            {
                "technology_id": source,
                "fact": {"context": "testing"},
                "expected_revision": 0,
                "authorization_revision": 9,
                "idempotency_key": "merge-other-source-0001",
            }
        ),
        request_id="merge-test",
    )
    team = await create_team(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=CorporateTeamCreateRequest(
            name="Responsible team",
            authorization_revision=10,
            idempotency_key="merge-team-create-0001",
        ),
        request_id="merge-test",
    )
    source_responsibility = await write_technology_team(
        db_session,
        ctx=ctx,
        organization_id=org,
        technology_id=source,
        payload=TechnologyTeamWriteRequest(
            team_id=team.team_id,
            expected_revision=0,
            authorization_revision=11,
            idempotency_key="merge-team-source-0001",
        ),
        request_id="merge-test",
    )
    plan = await read_merge_plan(
        db_session,
        ctx=ctx,
        organization_id=org,
        source_id=source,
        target_id=target,
        request_id="merge-test",
    )
    assert plan.affected_project_count == 2 and plan.affected_team_count == 1
    mutation = TechnologyMergeRequest(
        target_id=target,
        expected_revision=2,
        target_expected_revision=2,
        plan_digest=plan.digest,
        authorization_revision=12,
        idempotency_key="merge-technology-apply-0001",
    )
    with pytest.raises(ApiError, match="plan changed"):
        await merge_technology(
            db_session,
            ctx=ctx,
            organization_id=org,
            source_id=source,
            payload=mutation.model_copy(update={"plan_digest": "sha256:" + "0" * 64}),
            request_id="merge-test",
        )
    result = await merge_technology(
        db_session,
        ctx=ctx,
        organization_id=org,
        source_id=source,
        payload=mutation,
        request_id="merge-test",
    )
    assert result.source.technology_id == source and result.source.redirect_id == target
    assert result.target.name == "npm CLI" and result.target.lifecycle == "active"
    assert result.project_effects[0].target_relation_id == corrected_target.relation_id
    assert result.project_effects[0].source_relation_id == original_source.relation_id
    assert result.project_effects[0].target_action == "update"
    created_effect = next(
        effect for effect in result.project_effects if effect.project_id == other_project.project_id
    )
    assert created_effect.source_relation_id == other_source.relation_id
    assert created_effect.target_action == "create"
    assert created_effect.target_relation_id != other_source.relation_id
    assert result.team_effects[0].source_relation_id == source_responsibility.relation_id
    source_team = await db_session.get(
        TechnologyTeamResponsibility, (org, source_responsibility.relation_id)
    )
    assert (
        source_team is not None
        and source_team.state == "retired"
        and source_team.technology_id == source
    )
    assert (
        await merge_technology(
            db_session,
            ctx=ctx,
            organization_id=org,
            source_id=source,
            payload=mutation,
            request_id="merge-test-replay",
        )
        == result
    )
    await db_session.flush()
    source_pair = await db_session.get(
        ProjectTechnologyRelation, (org, original_source.relation_id)
    )
    target_pair = await db_session.get(
        ProjectTechnologyRelation, (org, corrected_target.relation_id)
    )
    assert (
        source_pair is not None
        and source_pair.state == "retired"
        and source_pair.technology_id == source
    )
    assert (
        target_pair is not None
        and target_pair.state == "current"
        and target_pair.technology_id == target
    )
    original_fact = await db_session.get(
        TechnologyUsageFact, (org, original_source.relation_id, "production")
    )
    merged_fact = await db_session.get(
        TechnologyUsageFact, (org, corrected_target.relation_id, "production")
    )
    assert (
        original_fact is not None
        and original_fact.review == "confirmed"
        and len(original_fact.evidence) == 1
    )
    assert (
        merged_fact is not None
        and merged_fact.review == "confirmed"
        and len(merged_fact.evidence) == 2
    )
    registry = await list_technologies(
        db_session,
        ctx=ctx,
        organization_id=org,
        include_archived=False,
        offset=0,
        limit=128,
        search="Bun",
        request_id="merge-test",
    )
    assert registry.total == 1 and registry.items[0].technology_id == target
    landscape = await read_landscape(
        db_session,
        ctx=ctx,
        organization_id=org,
        filters=TechnologyLandscapeQuery(technology_id=target),
        request_id="merge-test",
    )
    assert landscape.items[0].project_count == 2
    assert (
        len(
            (
                await db_session.scalars(
                    select(ProjectTechnologyRelation).where(
                        ProjectTechnologyRelation.organization_id == org
                    )
                )
            ).all()
        )
        == 4
    )
