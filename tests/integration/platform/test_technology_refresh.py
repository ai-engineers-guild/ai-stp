"""The worker folds GitLab language signals into usage facts once per head."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import ClassVar

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate.service import bootstrap, create_project
from ai_stp_api.slices.technology.service import import_seed
from ai_stp_contracts.corporate import CorporateBootstrapRequest, CorporateProjectCreateRequest
from ai_stp_contracts.technology import TechnologySeedRequest
from ai_stp_contracts.technology_seed import SEED_COORDINATES_VERSION
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, AuditEvent, Device
from ai_stp_platform.organization_models import ProjectIdentity, ProjectLink
from ai_stp_platform.queue.models import Job
from ai_stp_platform.queue.states import JobType
from ai_stp_platform.technology_models import (
    TechnologyScan,
    TechnologyUnmappedCoordinate,
    TechnologyUsageFact,
)
from ai_stp_platform.tenant_scope import set_tenant_scope
from ai_stp_worker.handlers import REGISTRY, technology_refresh
from ai_stp_worker.handlers.technology_refresh import (
    enqueue_daily_refresh,
    handle_technology_refresh,
)

pytestmark = pytest.mark.platform

BASE_URL = "https://gitlab.example.com"
HEAD = "b" * 40


class FakeGitLabClient:
    calls: ClassVar[list[tuple[str, int]]] = []

    def __init__(self, base_url: str, *, allowed_hosts: object) -> None:
        assert base_url == BASE_URL
        self.base_url = base_url

    async def head_revision(self, repository_id: int, branch: str, *, token: str) -> str:
        assert token == "gitlab-token" and branch == "main"
        self.calls.append(("revision", repository_id))
        return HEAD

    async def languages(self, repository_id: int, *, token: str) -> dict[str, float]:
        assert token == "gitlab-token"
        self.calls.append(("languages", repository_id))
        return {"Python": 80.0, "UnmappedLang": 20.0}


@pytest.fixture(autouse=True)
def _fake_gitlab(  # pyright: ignore[reportUnusedFunction]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeGitLabClient.calls = []
    monkeypatch.setattr(technology_refresh, "GitLabClient", FakeGitLabClient)


async def _linked_project(
    db_session: AsyncSession, *, account_id: str, organization_id: str, device: Device
) -> tuple[str, str]:
    project = await create_project(
        db_session,
        ctx=AuthContext(account_id, "refresh-test", None, "active", False, False),
        organization_id=organization_id,
        payload=CorporateProjectCreateRequest(
            name="Refreshed project",
            authorization_revision=2,
            idempotency_key="refresh-project-0001",
        ),
        request_id="refresh-test",
    )
    provider_id = new_id("provider_project")
    db_session.add(
        ProjectIdentity(
            id=provider_id,
            organization_id=organization_id,
            namespace="provider",
            external_key=f"gitlab:{BASE_URL}:42",
            display_name="team/service",
            provider_kind="gitlab",
            provider_installation_id=BASE_URL,
            provider_namespace_id="7",
            immutable_repository_id="42",
            current_url=f"{BASE_URL}/team/service",
            observed_name="team/service",
            observed_at=datetime.now(UTC),
            provider_default_branch="main",
            provider_observed_revision=HEAD,
            state="active",
        )
    )
    db_session.add(
        ProjectLink(
            id=new_id("project_link"),
            plan_id=new_id("link_plan"),
            plan_digest="sha256:" + "a" * 64,
            organization_id=organization_id,
            actor_account_id=account_id,
            device_id=device.id,
            local_project_id=new_id("project"),
            remote_project_id=project.project_id,
            provider_project_id=provider_id,
            state="linked",
            local_revision="local1",
            remote_revision="remote1",
            provider_revision="provider1",
            create_idempotency_key="refresh-link-0001",
        )
    )
    await db_session.flush()
    return project.project_id, provider_id


def _connections(monkeypatch: pytest.MonkeyPatch, organization_id: str) -> None:
    monkeypatch.setenv(
        "AI_STP_GITLAB_CONNECTIONS",
        json.dumps(
            {
                organization_id: {
                    "base_url": BASE_URL,
                    "token": "gitlab-token",
                    "allowed_hosts": [],
                }
            }
        ),
    )


async def test_technology_refresh_merges_languages_once_per_observed_head(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    account_id = new_id("account")
    device = Device(id=new_id("device"), account_id=account_id, public_key="refresh-key")
    db_session.add_all([Account(id=account_id, status="active"), device])
    await db_session.flush()
    ctx = AuthContext(account_id, "refresh-test", None, "active", False, False)
    org = (
        await bootstrap(
            db_session,
            payload=CorporateBootstrapRequest(
                organization_name="Refresh acceptance",
                superadmin_account_id=account_id,
                idempotency_key="refresh-bootstrap-0001",
            ),
            request_id="refresh-test",
        )
    ).organization_id
    await import_seed(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=TechnologySeedRequest(
            authorization_revision=1, idempotency_key="refresh-seed-0001"
        ),
        request_id="refresh-test",
    )
    project_id, provider_id = await _linked_project(
        db_session, account_id=account_id, organization_id=org, device=device
    )
    _connections(monkeypatch, org)
    await set_tenant_scope(db_session, "*")
    assert REGISTRY[JobType.TECHNOLOGY_REFRESH] is handle_technology_refresh

    await handle_technology_refresh(db_session, {"organization_id": org})

    scans = (
        await db_session.scalars(
            select(TechnologyScan).where(TechnologyScan.organization_id == org)
        )
    ).all()
    assert len(scans) == 1
    facts = (
        await db_session.scalars(
            select(TechnologyUsageFact).where(TechnologyUsageFact.organization_id == org)
        )
    ).all()
    # Python resolves through the seed's alias coordinates; the unknown language
    # share lands in the unmapped queue rather than an invented identity.
    assert len(facts) == 1
    assert facts[0].review == "proposed"
    queued = (
        await db_session.scalars(
            select(TechnologyUnmappedCoordinate).where(
                TechnologyUnmappedCoordinate.organization_id == org
            )
        )
    ).all()
    assert [(row.kind, row.coordinate) for row in queued] == [("alias", "unmappedlang")]
    audits = (
        await db_session.scalars(
            select(AuditEvent).where(AuditEvent.action == "technology.refresh")
        )
    ).all()
    assert len(audits) == 1 and audits[0].actor_type == "system"
    assert audits[0].payload["refreshed"] == 1

    # The head is already merged: a rerun costs one revision check and writes
    # nothing new.
    await handle_technology_refresh(db_session, {"organization_id": org})
    assert await db_session.scalar(select(func.count()).select_from(TechnologyScan)) == 1
    assert ("languages", 42) in FakeGitLabClient.calls
    assert FakeGitLabClient.calls.count(("languages", 42)) == 1
    # Scope names the provider identity so request-driven enrich and worker
    # refresh fold into the same scan lineage.
    retained = scans[0]
    assert retained.project_id == project_id
    handoff = retained.handoff["handoff"]
    assert isinstance(handoff, dict)
    assert handoff["scope"] == f"gitlab/{provider_id}"
    assert handoff["mapping_version"] == SEED_COORDINATES_VERSION


async def test_technology_refresh_enqueues_one_job_per_tenant_per_utc_day(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    account_id = new_id("account")
    db_session.add(Account(id=account_id, status="active"))
    await db_session.flush()
    org_one = (
        await bootstrap(
            db_session,
            payload=CorporateBootstrapRequest(
                organization_name="Refresh tenant one",
                superadmin_account_id=account_id,
                idempotency_key="refresh-bootstrap-one-0001",
            ),
            request_id="refresh-test",
        )
    ).organization_id
    org_two = (
        await bootstrap(
            db_session,
            payload=CorporateBootstrapRequest(
                organization_name="Refresh tenant two",
                superadmin_account_id=account_id,
                idempotency_key="refresh-bootstrap-two-0001",
            ),
            request_id="refresh-test",
        )
    ).organization_id
    monkeypatch.setenv(
        "AI_STP_GITLAB_CONNECTIONS",
        json.dumps(
            {
                org_one: {"base_url": BASE_URL, "token": "gitlab-token"},
                org_two: {"base_url": BASE_URL, "token": "gitlab-token"},
                "org_without_rows": {"base_url": BASE_URL, "token": "gitlab-token"},
            }
        ),
    )
    await set_tenant_scope(db_session, "*")
    await enqueue_daily_refresh(db_session)
    await enqueue_daily_refresh(db_session)
    jobs = (
        await db_session.scalars(
            select(Job).where(Job.job_type == JobType.TECHNOLOGY_REFRESH.value)
        )
    ).all()
    assert len(jobs) == 3
    today = datetime.now(UTC).date().isoformat()
    assert {job.idempotency_key for job in jobs} == {
        f"technology-refresh:{organization_id}:{today}"
        for organization_id in (org_one, org_two, "org_without_rows")
    }
    assert all(job.organization_id is None for job in jobs)


async def test_technology_refresh_without_configuration_is_a_no_op(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AI_STP_GITLAB_CONNECTIONS", raising=False)
    await handle_technology_refresh(db_session, {"organization_id": "org_missing"})
    assert FakeGitLabClient.calls == []
    with pytest.raises(ValueError, match="organization_id"):
        await handle_technology_refresh(db_session, {})
