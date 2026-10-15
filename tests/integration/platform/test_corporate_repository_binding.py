"""The web source flow has no device binding and never queues scanning."""

import uuid
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.integration.platform.test_repository_scan import (
    _bootstrap_org,  # pyright: ignore[reportPrivateUsage]
)

from ai_stp_api.errors import ApiError
from ai_stp_api.settings import Settings
from ai_stp_api.slices.corporate import repositories, service
from ai_stp_contracts.corporate import (
    CorporateProjectCreateRequest,
    CorporateRepositoryBindRequest,
    CorporateRepositoryPlanRequest,
)
from ai_stp_platform.organization_models import CorporateRepositoryBinding, Organization
from ai_stp_platform.queue.models import Job


async def test_explicit_web_binding_and_replay_without_scan(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, org, _ = await _bootstrap_org(db_session)
    project = await service.create_project(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=CorporateProjectCreateRequest(
            name="Repository UI", authorization_revision=1, idempotency_key=uuid.uuid4().hex
        ),
        request_id=None,
    )
    organization = await db_session.get(Organization, org)
    assert organization is not None
    revision = organization.policy_revision
    metadata = {
        "provider": "github",
        "repository_url": "https://github.com/example/repo",
        "repository_id": "42",
        "namespace_id": "7",
        "name": "example/repo",
        "default_branch": "main",
        "observed_revision": "a" * 40,
    }
    monkeypatch.setattr(repositories, "resolve_repository", AsyncMock(return_value=metadata))
    plan = await repositories.plan_repository(
        org,
        project.project_id,
        CorporateRepositoryPlanRequest(
            repository_url=metadata["repository_url"],
            expected_revision=1,
            authorization_revision=revision,
            idempotency_key=uuid.uuid4().hex,
        ),
        ctx,
        db_session,
        cast(Settings, None),
    )
    assert (
        await db_session.scalar(select(func.count()).select_from(CorporateRepositoryBinding)) == 0
    )
    payload = CorporateRepositoryBindRequest(
        plan_key=plan.plan_key,
        plan_digest=plan.plan_digest,
        authorization_revision=revision,
        idempotency_key=uuid.uuid4().hex,
    )
    linked = await repositories.bind_repository(
        org, project.project_id, payload, ctx, db_session, cast(Settings, None)
    )
    assert linked.repositories[0].repository_url == metadata["repository_url"]
    replay = await repositories.bind_repository(
        org, project.project_id, payload, ctx, db_session, cast(Settings, None)
    )
    assert replay == linked
    assert (
        await db_session.scalar(select(func.count()).select_from(CorporateRepositoryBinding)) == 1
    )
    assert await db_session.scalar(select(func.count()).select_from(Job)) == 0


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/a/b",
        "https://user:pass@github.com/a/b",
        "https://github.com/a/b/tree/main",
        "https://github.com:invalid/a/b",
        "https://github.com/a/../b",
        "https://github.com/a/b?token=secret",
    ],
)
def test_repository_url_rejects_unsafe_coordinates(url: str) -> None:
    with pytest.raises(ApiError):
        repositories.repository_coordinates(url)


@pytest.mark.parametrize("provider", ["github", "gitlab"])
async def test_repository_edit_matches_live_owner_team_lead_menu(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    from ai_stp_api.session import AuthContext
    from ai_stp_api.slices.entity_actions.service import read_menu
    from ai_stp_contracts.corporate import CorporateMemberCreateRequest, CorporateTeamCreateRequest
    from ai_stp_contracts.entity_actions import EntityActionSubject
    from ai_stp_platform.organization_models import CorporateRoleBinding, CorporateTeamMember

    owner, org, _ = await _bootstrap_org(db_session)

    async def revision() -> int:
        organization = await db_session.get(Organization, org)
        assert organization is not None
        return organization.policy_revision

    lead = await service.create_member(
        db_session,
        ctx=owner,
        organization_id=org,
        payload=CorporateMemberCreateRequest(
            display_name="Owner team lead",
            email="owner-lead@example.test",
            role="staff",
            authorization_revision=await revision(),
            idempotency_key=uuid.uuid4().hex,
        ),
        request_id=None,
    )
    team = await service.create_team(
        db_session,
        ctx=owner,
        organization_id=org,
        payload=CorporateTeamCreateRequest(
            name="Owner team",
            employee_ids=[lead.account_id],
            lead_account_id=lead.account_id,
            authorization_revision=await revision(),
            idempotency_key=uuid.uuid4().hex,
        ),
        request_id=None,
    )
    project = await service.create_project(
        db_session,
        ctx=owner,
        organization_id=org,
        payload=CorporateProjectCreateRequest(
            name="Owned project",
            owner_team_id=team.team_id,
            authorization_revision=await revision(),
            idempotency_key=uuid.uuid4().hex,
        ),
        request_id=None,
    )
    ctx = AuthContext(lead.account_id, "owner-lead", None, "active", False, False)
    subject = EntityActionSubject(kind="project", id=project.project_id, organization_id=org)
    menu = await read_menu(db_session, ctx=ctx, subject=subject)
    assert "edit" in [action.id for action in menu.actions]
    metadata = {
        "provider": provider,
        "repository_url": f"https://{provider}.com/example/repo",
        "repository_id": "42",
        "namespace_id": "7",
        "name": "example/repo",
        "default_branch": "main",
        "observed_revision": "a" * 40,
    }
    remote = AsyncMock(return_value=metadata)
    monkeypatch.setattr(repositories, "resolve_repository", remote)
    payload = CorporateRepositoryPlanRequest(
        repository_url=metadata["repository_url"],
        expected_revision=project.revision,
        authorization_revision=await revision(),
        idempotency_key=uuid.uuid4().hex,
    )
    plan = await repositories.plan_repository(
        org, project.project_id, payload, ctx, db_session, cast(Settings, None)
    )
    linked = await repositories.bind_repository(
        org,
        project.project_id,
        CorporateRepositoryBindRequest(
            plan_key=plan.plan_key,
            plan_digest=plan.plan_digest,
            authorization_revision=await revision(),
            idempotency_key=uuid.uuid4().hex,
        ),
        ctx,
        db_session,
        cast(Settings, None),
    )
    assert linked.repositories[0].provider == provider
    membership = await db_session.scalar(
        select(CorporateTeamMember).where(
            CorporateTeamMember.team_id == team.team_id,
            CorporateTeamMember.account_id == lead.account_id,
        )
    )
    assert membership is not None
    membership.role = "staff"
    binding = await db_session.scalar(
        select(CorporateRoleBinding).where(
            CorporateRoleBinding.account_id == lead.account_id,
            CorporateRoleBinding.scope_kind == "team",
            CorporateRoleBinding.scope_id == team.team_id,
            CorporateRoleBinding.role == "lead",
        )
    )
    assert binding is not None
    binding.role = "staff"
    await db_session.flush()
    menu = await read_menu(db_session, ctx=ctx, subject=subject)
    assert "edit" not in [action.id for action in menu.actions]
    calls = remote.call_count
    with pytest.raises(ApiError):
        await repositories.plan_repository(
            org, project.project_id, payload, ctx, db_session, cast(Settings, None)
        )
    assert remote.call_count == calls
