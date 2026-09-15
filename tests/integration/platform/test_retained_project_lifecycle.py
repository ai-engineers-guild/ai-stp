"""Project tombstones preserve exact identities under lifecycle concurrency checks."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.errors import ApiError
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate.service import (
    bootstrap,
    change_project_lifecycle,
    create_project,
    delete_project,
    mutation_fingerprint,
    update_project,
)
from ai_stp_api.slices.technology.service import (
    read_landscape_policy,
    write_landscape_policy,
    write_project_activity,
)
from ai_stp_contracts.corporate import (
    CorporateBootstrapRequest,
    CorporateDeleteRequest,
    CorporateProjectCreateRequest,
    CorporateProjectLifecycleRequest,
    CorporateProjectUpdateRequest,
)
from ai_stp_contracts.technology import ProjectActivityRequest, TechnologyLandscapePolicyRequest
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import (
    CorporateMutationReceipt,
    CorporateProject,
    ProjectIdentity,
)


async def test_project_deprecation_tombstone_and_restoration(db_session: AsyncSession) -> None:
    account_id = new_id("account")
    db_session.add(Account(id=account_id, status="active"))
    await db_session.flush()
    ctx = AuthContext(account_id, "project-life-session", None, "active", False, False)
    org = await bootstrap(
        db_session,
        payload=CorporateBootstrapRequest(
            organization_name="Retained project",
            superadmin_account_id=account_id,
            idempotency_key="project-life-bootstrap-0001",
        ),
        request_id="project-life",
    )
    project = await create_project(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        payload=CorporateProjectCreateRequest(
            name="Permanent identity",
            authorization_revision=1,
            idempotency_key="project-life-create-0001",
        ),
        request_id="project-life",
    )
    assert project.lifecycle == "active"
    assert (
        await create_project(
            db_session,
            ctx=ctx,
            organization_id=org.organization_id,
            payload=CorporateProjectCreateRequest(
                name="Permanent identity",
                authorization_revision=1,
                idempotency_key="project-life-create-0001",
            ),
            request_id="project-life-replay",
        )
        == project
    )
    deprecated = await change_project_lifecycle(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        project_id=project.project_id,
        payload=CorporateProjectLifecycleRequest(
            target="deprecated",
            expected_revision=1,
            authorization_revision=2,
            idempotency_key="project-life-deprecate-0001",
        ),
        request_id="project-life",
    )
    assert deprecated.lifecycle == "deprecated" and deprecated.state == "archived"
    renamed = await update_project(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        project_id=project.project_id,
        payload=CorporateProjectUpdateRequest(
            name="Renamed identity",
            state="archived",
            expected_revision=2,
            authorization_revision=3,
            idempotency_key="project-life-rename-0001",
        ),
        request_id="project-life",
    )
    assert renamed.lifecycle == "deprecated"
    archived = await change_project_lifecycle(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        project_id=project.project_id,
        payload=CorporateProjectLifecycleRequest(
            target="archived",
            expected_revision=3,
            authorization_revision=4,
            idempotency_key="project-life-archive-0001",
        ),
        request_id="project-life",
    )
    assert archived.restore_lifecycle == "deprecated"
    restored = await change_project_lifecycle(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        project_id=project.project_id,
        payload=CorporateProjectLifecycleRequest(
            target="restore",
            expected_revision=4,
            authorization_revision=5,
            idempotency_key="project-life-restore-0001",
        ),
        request_id="project-life",
    )
    assert restored.lifecycle == "deprecated"
    deletion = CorporateDeleteRequest(
        expected_revision=5, authorization_revision=6, idempotency_key="project-life-delete-0001"
    )
    deleted = await delete_project(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        project_id=project.project_id,
        payload=deletion,
        request_id="project-life",
    )
    assert deleted.resource_id == project.project_id
    assert (
        await delete_project(
            db_session,
            ctx=ctx,
            organization_id=org.organization_id,
            project_id=project.project_id,
            payload=deletion,
            request_id="project-life-replay",
        )
        == deleted
    )
    await db_session.flush()
    row = await db_session.scalar(
        select(CorporateProject).where(
            CorporateProject.id == project.project_id,
            CorporateProject.organization_id == org.organization_id,
        )
    )
    identity = await db_session.scalar(
        select(ProjectIdentity).where(
            ProjectIdentity.id == project.project_id,
            ProjectIdentity.organization_id == org.organization_id,
        )
    )
    assert row is not None and identity is not None
    assert row.lifecycle == "deleted" and row.revision == 6
    assert identity.state == "deleted" and identity.display_name == "Renamed identity"
    with pytest.raises(ApiError, match="explicit restoration"):
        await update_project(
            db_session,
            ctx=ctx,
            organization_id=org.organization_id,
            project_id=project.project_id,
            payload=CorporateProjectUpdateRequest(
                name="Implicit revival",
                state="active",
                expected_revision=6,
                authorization_revision=7,
                idempotency_key="project-life-invalid-0001",
            ),
            request_id="project-life",
        )
    final = await change_project_lifecycle(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        project_id=project.project_id,
        payload=CorporateProjectLifecycleRequest(
            target="restore",
            expected_revision=6,
            authorization_revision=7,
            idempotency_key="project-life-recover-0001",
        ),
        request_id="project-life",
    )
    assert final.project_id == project.project_id and final.lifecycle == "deprecated"
    assert final.name == "Renamed identity" and final.revision == 7
    policy = await read_landscape_policy(
        db_session, ctx=ctx, organization_id=org.organization_id, request_id="project-life"
    )
    assert policy.inactivity_months == 9 and policy.revision == 0
    policy_request = TechnologyLandscapePolicyRequest(
        inactivity_months=12,
        expected_revision=0,
        authorization_revision=8,
        idempotency_key="project-life-policy-0001",
    )
    changed_policy = await write_landscape_policy(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        payload=policy_request,
        request_id="project-life",
    )
    assert changed_policy.inactivity_months == 12 and changed_policy.revision == 1
    assert (
        await write_landscape_policy(
            db_session,
            ctx=ctx,
            organization_id=org.organization_id,
            payload=policy_request,
            request_id="project-life-replay",
        )
        == changed_policy
    )
    with pytest.raises(ApiError, match="revision changed"):
        await write_landscape_policy(
            db_session,
            ctx=ctx,
            organization_id=org.organization_id,
            payload=policy_request.model_copy(
                update={
                    "authorization_revision": 9,
                    "idempotency_key": "project-life-policy-stale-0001",
                }
            ),
            request_id="project-life",
        )
    activity_request = ProjectActivityRequest(
        repository_activity_at=None,
        activity_override="active",
        expected_revision=7,
        authorization_revision=9,
        idempotency_key="project-life-activity-0001",
    )
    activity = await write_project_activity(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        project_id=project.project_id,
        payload=activity_request,
        request_id="project-life",
    )
    assert activity.repository_activity_at is None and activity.activity_override == "active"
    assert row.lifecycle == "deprecated" and identity.state == "archived"
    assert (
        await write_project_activity(
            db_session,
            ctx=ctx,
            organization_id=org.organization_id,
            project_id=project.project_id,
            payload=activity_request,
            request_id="project-life",
        )
        == activity
    )
    other = await create_project(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        payload=CorporateProjectCreateRequest(
            name="Other exact identity",
            authorization_revision=10,
            idempotency_key="project-life-other-0001",
        ),
        request_id="project-life",
    )
    with pytest.raises(ApiError, match="idempotency key was reused"):
        await change_project_lifecycle(
            db_session,
            ctx=ctx,
            organization_id=org.organization_id,
            project_id=other.project_id,
            payload=CorporateProjectLifecycleRequest(
                target="deprecated",
                expected_revision=1,
                authorization_revision=11,
                idempotency_key="project-life-deprecate-0001",
            ),
            request_id="project-life",
        )
    legacy_payload = CorporateProjectUpdateRequest(
        name="Renamed identity",
        state="archived",
        expected_revision=2,
        authorization_revision=3,
        idempotency_key="project-life-rename-0001",
    )
    legacy_receipt = await db_session.get(
        CorporateMutationReceipt, (org.organization_id, legacy_payload.idempotency_key)
    )
    assert legacy_receipt is not None
    legacy_receipt.request_fingerprint = mutation_fingerprint(
        legacy_payload.model_dump(mode="json", exclude={"idempotency_key"})
    )
    legacy_receipt.response_body = {
        key: value
        for key, value in legacy_receipt.response_body.items()
        if key not in {"lifecycle", "restore_lifecycle"}
    }
    await db_session.flush()
    legacy_replay = await update_project(
        db_session,
        ctx=ctx,
        organization_id=org.organization_id,
        project_id=project.project_id,
        payload=legacy_payload,
        request_id="project-life-replay",
    )
    assert legacy_replay.lifecycle is None and legacy_replay.revision == 3
    assert row.lifecycle == "deprecated" and row.revision == 8
    with pytest.raises(ApiError, match="idempotency key was reused"):
        await update_project(
            db_session,
            ctx=ctx,
            organization_id=org.organization_id,
            project_id=other.project_id,
            payload=legacy_payload,
            request_id="project-life-replay",
        )
