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
