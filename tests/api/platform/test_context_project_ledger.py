# pyright: reportPrivateUsage=false
"""Executable acceptance evidence for the organization-scoped project DAG."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.app import create_app
from ai_stp_api.session import AuthContext, issue_session
from ai_stp_api.settings import Settings
from ai_stp_api.slices.context import service as context_service
from ai_stp_api.slices.context.service import _plan_digest, _sync_plan_preimage
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, AuditEvent, Device
from ai_stp_platform.organization_models import (
    CorporateProject,
    Organization,
    OrganizationMembership,
    ProjectIdentity,
    ProjectLink,
    ProjectLinkPlan,
    ProjectLinkProposal,
    ProjectRevision,
    ProjectRevisionHead,
    ProjectRevisionReceipt,
    ProjectSyncPlan,
)

pytestmark = pytest.mark.platform


@pytest_asyncio.fixture
async def project_harness(
    migrated_database_url: str,
    settings_factory: Any,
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str]]:
    settings: Settings = settings_factory(database_url=migrated_database_url)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with app.state.sessionmaker() as db:
            account = Account(id=new_id("account"))
            device = Device(
                id=new_id("device"),
                account_id=account.id,
                public_key="dGVzdC1wcm9qZWN0LWxlZGdlci1rZXk=",
                state="active",
            )
            organization = Organization(
                id=new_id("organization"),
                kind="personal",
                owner_account_id=account.id,
                display_name="Personal",
            )
            remote = ProjectIdentity(
                id=new_id("remote_project"),
                organization_id=organization.id,
                namespace="remote",
                external_key="remote-1",
                display_name="Remote one",
            )
            link = ProjectLink(
                id=new_id("project_link"),
                plan_id=new_id("link_plan"),
                plan_digest="sha256:" + "a" * 64,
                organization_id=organization.id,
                actor_account_id=account.id,
                device_id=device.id,
                local_project_id=new_id("project"),
                remote_project_id=remote.id,
                state="linked",
                local_revision="initial",
                remote_revision="initial",
                create_idempotency_key="link-create-00000001",
            )
            db.add_all(
                [
                    account,
                    device,
                    organization,
                    OrganizationMembership(
                        organization_id=organization.id,
                        account_id=account.id,
                        role="owner",
                        state="active",
                    ),
                    remote,
                ]
            )
            # ProjectLink has scalar foreign keys without ORM relationships;
            # flush its prerequisites explicitly for PostgreSQL ordering.
            await db.flush()
            db.add(link)
            await db.flush()
            issued = await issue_session(
                db, account_id=account.id, device_id=device.id, ttl_seconds=3600
            )
            await db.commit()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield (
                client,
                app.state.sessionmaker,
                issued.raw_token,
                organization.id,
                link.id,
                remote.id,
            )


def revision_payload(
    *,
    remote_project_id: str,
    parents: list[str],
    expected: str | None,
    event_id: str,
    idempotency_key: str,
    authorization_revision: str,
    tombstone: bool = False,
) -> dict[str, object]:
    projection: dict[str, object] = {
        "schema_version": 1,
        "kind": "project",
        "remote_project_id": remote_project_id,
        "index_digest": "sha256:" + "b" * 64,
        "index_state": "ready",
        "tombstone": tombstone,
    }
    document = {
        "schema_version": 1,
        "remote_project_id": remote_project_id,
        "parent_revision_ids": parents,
        "operation": "tombstone" if tombstone else "upsert",
        "projection": projection,
    }
    return {
        "schema_version": 1,
        "event_id": event_id,
        "revision_id": digest_canonical("ai-stp:revision:v1", cast(JsonValue, document)),
        "parent_revision_ids": parents,
        "operation": document["operation"],
        "content_digest": digest_canonical("ai-stp:revision:v1", cast(JsonValue, projection)),
        "projection": projection,
        "expected_head_revision_id": expected,
        "authorization_revision": authorization_revision,
        "idempotency_key": idempotency_key,
    }


async def test_context_mutation_waits_for_revocation_and_refuses_without_plan_or_audit(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, sessionmaker, token, organization, link_id, remote = project_harness
    local_project = new_id("project")
    async with sessionmaker() as db:
        link = await db.get(ProjectLink, link_id)
        assert link is not None
        device = await db.get(Device, link.device_id)
        assert device is not None
        # Authentication's optional last-seen update must not take the lock
        # before the mutation guard whose revocation barrier this test observes.
        device.last_seen_at = datetime.now(UTC)
        await db.commit()
    entered: asyncio.Future[int] = asyncio.get_running_loop().create_future()
    original = context_service.require_active_device

    async def observe_guard(
        db: AsyncSession, *, ctx: AuthContext, for_update: bool = False
    ) -> Device:
        pid = await db.scalar(text("SELECT pg_backend_pid()"))
        assert isinstance(pid, int)
        if not entered.done():
            entered.set_result(pid)
        return await original(db, ctx=ctx, for_update=for_update)

    monkeypatch.setattr(context_service, "require_active_device", observe_guard)
    request: asyncio.Task[Response] | None = None
    try:
        async with sessionmaker() as revoker:
            link = await revoker.get(ProjectLink, link_id)
            assert link is not None
            device = await revoker.scalar(
                select(Device).where(Device.id == link.device_id).with_for_update()
            )
            assert device is not None
            device.state = "revoked"
            await revoker.flush()
            audits = await revoker.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.action == "project.link_planned",
                )
            )
            request = asyncio.create_task(
                client.post(
                    f"/v1/organizations/{organization}/project-link-plans",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "local_project_id": local_project,
                        "remote_project_id": remote,
                        "local_revision": "local-1",
                        "remote_revision": "initial",
                        "authorization_revision": f"personal:{organization}:1:1",
                        "idempotency_key": "revocation-barrier-plan",
                    },
                )
            )
            pid = await asyncio.wait_for(asyncio.shield(entered), timeout=5)
            deadline = asyncio.get_running_loop().time() + 5
            while not await revoker.scalar(
                text("SELECT EXISTS (SELECT 1 FROM pg_locks WHERE pid = :pid AND NOT granted)"),
                {"pid": pid},
            ):
                assert not request.done(), "mutation crossed an uncommitted device revocation"
                assert asyncio.get_running_loop().time() < deadline
                await asyncio.sleep(0.01)
            await revoker.commit()
        refused = await asyncio.wait_for(asyncio.shield(request), timeout=5)
        assert refused.status_code == 403, refused.text
        async with sessionmaker() as db:
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(ProjectLinkPlan)
                    .where(
                        ProjectLinkPlan.local_project_id == local_project,
                    )
                )
                == 0
            )
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(
                        AuditEvent.action == "project.link_planned",
                    )
                )
                == audits
            )
    finally:
        if request is not None and not request.done():
            request.cancel()
            await asyncio.gather(request, return_exceptions=True)


async def test_link_plan_outcome_reads_lost_confirmation_without_mutation(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
) -> None:
    client, sessionmaker, token, organization, old_link_id, remote = project_harness
    headers = {"Authorization": f"Bearer {token}", "X-AI-STP-Organization-Id": organization}
    revision = f"personal:{organization}:1:1"
    created = await client.post(
        f"/v1/organizations/{organization}/project-link-plans",
        headers=headers,
        json={
            "local_project_id": new_id("project"),
            "remote_project_id": remote,
            "local_revision": "local-1",
            "remote_revision": "initial",
            "authorization_revision": revision,
            "idempotency_key": "outcome-plan-0001",
        },
    )
    assert created.status_code == 201, created.text
    plan = created.json()
    route = f"/v1/organizations/{organization}/project-link-plans/{plan['plan_id']}/outcome"
    request_route = f"/v1/organizations/{organization}/project-link-plan-requests/outcome-plan-0001"

    async def counts() -> list[int | None]:
        async with sessionmaker() as db:
            return [
                await db.scalar(select(func.count()).select_from(model))
                for model in (ProjectLinkPlan, ProjectLink, AuditEvent)
            ]

    before = await counts()
    ready = await client.get(route, headers=headers)
    assert ready.status_code == 200, ready.text
    assert ready.headers["cache-control"] == "private, no-store"
    assert ready.json()["plan"] == plan
    assert ready.json()["state"] == "ready" and ready.json()["link"] is None
    assert ready.json()["observation_only"] is True
    assert ready.json()["authorization_revision"] == revision
    by_request = await client.get(request_route, headers=headers)
    assert by_request.status_code == 200, by_request.text
    assert by_request.headers["cache-control"] == "private, no-store"
    assert by_request.json()["plan"] == plan
    assert by_request.json()["state"] == "ready" and by_request.json()["link"] is None
    assert await counts() == before
    absent = await client.get(
        request_route.replace("outcome-plan-0001", "absent-plan-0001"),
        headers=headers,
    )
    assert absent.status_code == 404
    malformed = await client.get(
        request_route.replace("outcome-plan-0001", "short"), headers=headers
    )
    assert malformed.status_code == 400
    assert (await counts())[:2] == before[:2]
    # The client could lose this response; the read below identifies its exact link.
    confirmed = await client.post(
        "/v1/projects/links",
        headers=headers,
        json={
            "plan_id": plan["plan_id"],
            "plan_digest": plan["plan_digest"],
            "authorization_revision": revision,
            "idempotency_key": "outcome-confirm-0001",
        },
    )
    assert confirmed.status_code == 201, confirmed.text
    before = await counts()
    applied = await client.get(route, headers=headers)
    assert applied.status_code == 200, applied.text
    assert applied.json()["plan"] == plan
    assert applied.json()["state"] == "applied"
    assert applied.json()["link"] == confirmed.json()
    recovered = await client.get(request_route, headers=headers)
    assert recovered.status_code == 200
    assert recovered.json()["link"] == confirmed.json() and recovered.json()["plan"] == plan
    assert await counts() == before

    async with sessionmaker() as db:
        original = await db.get(ProjectLink, old_link_id)
        assert original is not None
        old_device = await db.get(Device, original.device_id)
        assert old_device is not None
        old_device.state = "revoked"
        replacement = Device(
            id=new_id("device"),
            account_id=original.actor_account_id,
            public_key="outcome-replacement-key",
            state="active",
        )
        db.add(replacement)
        await db.flush()
        issued = await issue_session(
            db, account_id=original.actor_account_id, device_id=replacement.id, ttl_seconds=3600
        )
        await db.commit()
    replacement_headers = {**headers, "Authorization": f"Bearer {issued.raw_token}"}
    assert (await client.get(route, headers=headers)).status_code == 403
    retained = await client.get(route, headers=replacement_headers)
    assert retained.status_code == 200, retained.text
    assert retained.json()["plan"] == plan and retained.json()["link"] == confirmed.json()
    recovered = await client.get(request_route, headers=replacement_headers)
    assert recovered.status_code == 200 and recovered.json()["plan"] == plan
    denied = await client.post(
        "/v1/projects/links",
        headers=replacement_headers,
        json={
            "plan_id": plan["plan_id"],
            "plan_digest": plan["plan_digest"],
            "authorization_revision": revision,
            "idempotency_key": "outcome-new-device-0001",
        },
    )
    assert denied.status_code == 403
    assert (await counts())[:2] == before[:2]
    before = await counts()  # Failed requests retain their standard security audit.
    async with sessionmaker() as db:
        retained_link = await db.get(ProjectLink, confirmed.json()["link_id"])
        assert retained_link is not None
        retained_link.state = "unlinked"
        retained_link.revision += 1
        await db.commit()
    unlinked = await client.get(route, headers=replacement_headers)
    assert unlinked.status_code == 200, unlinked.text
    assert unlinked.json()["state"] == "applied" and unlinked.json()["plan"] == plan
    assert unlinked.json()["link"]["link_id"] == confirmed.json()["link_id"]
    assert unlinked.json()["link"]["state"] == "unlinked"
    assert await counts() == before


async def test_link_plan_outcome_expiry_account_tenant_and_corruption_fences(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
) -> None:
    client, sessionmaker, token, organization, link_id, remote = project_harness
    headers = {"Authorization": f"Bearer {token}", "X-AI-STP-Organization-Id": organization}
    async with sessionmaker() as db:
        link = await db.get(ProjectLink, link_id)
        assert link is not None
        expires = datetime.now(UTC) - timedelta(seconds=1)
        plan = ProjectLinkPlan(
            id=new_id("link_plan"),
            organization_id=organization,
            actor_account_id=link.actor_account_id,
            device_id=link.device_id,
            local_project_id=new_id("project"),
            remote_project_id=remote,
            local_revision="local-1",
            remote_revision="initial",
            authorization_revision=f"personal:{organization}:1:1",
            idempotency_key="outcome-expired-0001",
            plan_digest="sha256:" + "b" * 64,
            state="ready",
            expires_at=expires,
        )
        db.add(plan)
        await db.commit()
        plan_id = plan.id
    route = f"/v1/organizations/{organization}/project-link-plans/{plan_id}/outcome"
    expired = await client.get(route, headers=headers)
    assert expired.status_code == 200, expired.text
    assert expired.json()["state"] == "expired" and expired.json()["link"] is None
    async with sessionmaker() as db:
        plan = await db.get(ProjectLinkPlan, plan_id)
        assert plan is not None and plan.state == "ready"  # Observation did not write expiry.
        plan.actor_account_id = new_id("account")
        db.add(Account(id=plan.actor_account_id))
        await db.flush()
        await db.commit()
    assert (await client.get(route, headers=headers)).status_code == 404
    lookup = f"/v1/organizations/{organization}/project-link-plan-requests/outcome-expired-0001"
    assert (await client.get(lookup, headers=headers)).status_code == 404
    wrong_tenant = route.replace(organization, new_id("organization"))
    assert (await client.get(wrong_tenant, headers=headers)).status_code in (403, 404)
    async with sessionmaker() as db:
        plan = await db.get(ProjectLinkPlan, plan_id)
        link = await db.get(ProjectLink, link_id)
        assert plan is not None and link is not None
        plan.actor_account_id = link.actor_account_id
        plan.state = "applied"
        plan.link_id = link_id  # Existing link belongs to another plan, never report success.
        await db.commit()
    assert (await client.get(route, headers=headers)).status_code == 412
    async with sessionmaker() as db:
        tenant = await db.get(Organization, organization)
        assert tenant is not None
        # A personal tenant must retain its one active owner membership.
        tenant.state = "suspended"
        await db.commit()
    assert (await client.get(route, headers=headers)).status_code == 403


async def test_link_target_metadata_is_fresh_read_only_and_device_qualified(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
) -> None:
    client, sessionmaker, token, organization, link_id, remote = project_harness
    headers = {"Authorization": f"Bearer {token}", "X-AI-STP-Organization-Id": organization}
    route = f"/v1/organizations/{organization}/project-link-targets/{remote}"
    initial = await client.get(route, headers=headers)
    assert initial.status_code == 200, initial.text
    assert initial.headers["cache-control"] == "private, no-store"
    assert initial.json()["remote_revision"] == "initial"
    assert initial.json()["providers"] == [] and initial.json()["observation_only"] is True
    revision = revision_payload(
        remote_project_id=remote,
        parents=[],
        expected=None,
        event_id="link-target-observed-head",
        idempotency_key="link-target-observed-head",
        authorization_revision=initial.json()["authorization_revision"],
    )
    pushed = await client.post(
        f"/v1/projects/links/{link_id}/revisions", headers=headers, json=revision
    )
    assert pushed.status_code == 200, pushed.text
    provider_id = new_id("provider_project")
    async with sessionmaker() as db:
        provider = ProjectIdentity(
            id=provider_id,
            organization_id=organization,
            namespace="provider",
            external_key="immutable-link-target-repo",
            display_name="Repository",
            provider_kind="github",
            immutable_repository_id="123456",
            revision=4,
        )
        db.add(provider)
        await db.flush()
        link = await db.get(ProjectLink, link_id)
        assert link is not None
        link.provider_project_id = provider_id
        await db.commit()
        before = [
            await db.scalar(select(func.count()).select_from(model))
            for model in (AuditEvent, ProjectLink, ProjectLinkPlan)
        ]
    observed = await client.get(route, headers=headers)
    assert observed.status_code == 200, observed.text
    assert observed.json()["remote_revision"] == revision["revision_id"]
    assert observed.json()["providers"] == [
        {
            "provider_project_id": provider_id,
            "provider": "github",
            "immutable_repository_id": "123456",
            "revision": 4,
        }
    ]
    async with sessionmaker() as db:
        after = [
            await db.scalar(select(func.count()).select_from(model))
            for model in (AuditEvent, ProjectLink, ProjectLinkPlan)
        ]
        assert after == before
        provider = await db.get(ProjectIdentity, provider_id)
        assert provider is not None
        provider.revision += 1
        await db.commit()
    refreshed = await client.get(route, headers=headers)
    assert refreshed.status_code == 200 and refreshed.json()["providers"][0]["revision"] == 5
    async with sessionmaker() as db:
        provider = await db.get(ProjectIdentity, provider_id)
        assert provider is not None
        provider.immutable_repository_id = None
        await db.commit()
    assert (await client.get(route, headers=headers)).status_code == 412
    async with sessionmaker() as db:
        link = await db.get(ProjectLink, link_id)
        assert link is not None
        device = await db.get(Device, link.device_id)
        assert device is not None
        device.state = "revoked"
        await db.commit()
    assert (await client.get(route, headers=headers)).status_code == 403


async def test_corporate_link_target_metadata_keeps_personal_context_and_tenant_boundaries(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
) -> None:
    client, sessionmaker, token, personal, link_id, personal_project = project_harness
    async with sessionmaker() as db:
        link = await db.get(ProjectLink, link_id)
        assert link is not None
        owner = link.actor_account_id
    bootstrapped = await client.post(
        "/v1/corporate/bootstrap",
        json={
            "organization_name": "Link targets",
            "superadmin_account_id": owner,
            "idempotency_key": "link-target-corporate-bootstrap",
        },
        headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
    )
    assert bootstrapped.status_code == 200, bootstrapped.text
    organization = bootstrapped.json()["organization_id"]
    headers = {"Authorization": f"Bearer {token}"}
    project = await client.post(
        f"/v1/corporate/organizations/{organization}/projects",
        headers=headers,
        json={
            "name": "Shared checkout",
            "authorization_revision": 1,
            "idempotency_key": "link-target-corporate-project",
        },
    )
    assert project.status_code == 200, project.text
    route = f"/v1/organizations/{organization}/project-link-targets/{project.json()['project_id']}"
    observed = await client.get(route, headers=headers)
    assert observed.status_code == 200, observed.text
    assert observed.json()["organization_id"] == organization
    assert observed.json()["authorization_revision"].startswith(f"corporate:{organization}:")
    wrong_tenant = await client.get(
        f"/v1/organizations/{personal}/project-link-targets/{project.json()['project_id']}",
        headers=headers,
    )
    assert wrong_tenant.status_code == 404
    scoped_headers = {**headers, "X-AI-STP-Organization-Id": organization}
    plan_payload = {
        "local_project_id": new_id("project"),
        "remote_project_id": project.json()["project_id"],
        "local_revision": "local-1",
        "remote_revision": observed.json()["remote_revision"],
        "authorization_revision": observed.json()["authorization_revision"],
        "idempotency_key": "corporate-link-target-plan",
    }
    planned = await client.post(
        f"/v1/organizations/{organization}/project-link-plans",
        headers=scoped_headers,
        json=plan_payload,
    )
    assert planned.status_code == 201, planned.text
    async with sessionmaker() as db:
        card = await db.get(CorporateProject, project.json()["project_id"])
        assert card is not None
        card.state = "archived"
        await db.commit()
    inactive = await client.get(route, headers=headers)
    assert inactive.status_code in (404, 412)
    new_plan = await client.post(
        f"/v1/organizations/{organization}/project-link-plans",
        headers=scoped_headers,
        json={**plan_payload, "idempotency_key": "archived-link-target-plan"},
    )
    assert new_plan.status_code == inactive.status_code, new_plan.text
    confirmation = await client.post(
        "/v1/projects/links",
        headers=scoped_headers,
        json={
            "plan_id": planned.json()["plan_id"],
            "plan_digest": planned.json()["plan_digest"],
            "authorization_revision": plan_payload["authorization_revision"],
            "idempotency_key": "archived-link-confirmation",
        },
    )
    assert confirmation.status_code == inactive.status_code, confirmation.text
    historical = await client.get(
        f"/v1/organizations/{organization}/project-link-plan-requests/corporate-link-target-plan",
        headers=scoped_headers,
    )
    assert historical.status_code == 200 and historical.json()["plan"] == planned.json()
    assert historical.json()["state"] == "ready" and historical.json()["link"] is None
    async with sessionmaker() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ProjectLinkPlan)
                .where(
                    ProjectLinkPlan.remote_project_id == project.json()["project_id"],
                )
            )
            == 1
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ProjectLink)
                .where(
                    ProjectLink.remote_project_id == project.json()["project_id"],
                )
            )
            == 0
        )
    async with sessionmaker() as db:
        membership = await db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization,
                OrganizationMembership.account_id == owner,
            )
        )
        assert membership is not None
        membership.state = "suspended"
        membership.revision += 1
        await db.commit()
    assert (await client.get(route, headers=headers)).status_code == 403
    personal_read = await client.get(
        f"/v1/organizations/{personal}/project-link-targets/{personal_project}", headers=headers
    )
    assert personal_read.status_code == 200


async def test_project_ledger_replay_fast_forward_conflict_and_resolution(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
) -> None:
    client, sessionmaker, token, organization_id, link_id, remote_project_id = project_harness
    headers = {
        "Authorization": f"Bearer {token}",
        "X-AI-STP-Organization-Id": organization_id,
    }
    authorization_revision = f"personal:{organization_id}:1:1"

    root = revision_payload(
        remote_project_id=remote_project_id,
        parents=[],
        expected=None,
        event_id="project-event-root",
        idempotency_key="project-idem-root",
        authorization_revision=authorization_revision,
    )
    first = await client.post(f"/v1/projects/links/{link_id}/revisions", headers=headers, json=root)
    assert first.status_code == 200, first.text
    root_id = first.json()["receipt"]["revision_id"]
    replay = await client.post(
        f"/v1/projects/links/{link_id}/revisions", headers=headers, json=root
    )
    assert replay.status_code == 200
    assert replay.json() == first.json()

    branch_a = revision_payload(
        remote_project_id=remote_project_id,
        parents=[root_id],
        expected=root_id,
        event_id="project-event-branch-a",
        idempotency_key="project-idem-branch-a",
        authorization_revision=authorization_revision,
    )
    accepted = await client.post(
        f"/v1/projects/links/{link_id}/revisions", headers=headers, json=branch_a
    )
    assert accepted.status_code == 200
    branch_a_id = accepted.json()["receipt"]["revision_id"]

    branch_b = revision_payload(
        remote_project_id=remote_project_id,
        parents=[root_id],
        expected=root_id,
        event_id="project-event-branch-b",
        idempotency_key="project-idem-branch-b",
        authorization_revision=authorization_revision,
    )
    # Make the content address different while retaining the real common root.
    branch_b_projection = cast(dict[str, object], branch_b["projection"])
    branch_b["projection"] = {**branch_b_projection, "file_count": 2}
    branch_b["content_digest"] = digest_canonical(
        "ai-stp:revision:v1",
        cast(JsonValue, branch_b["projection"]),
    )
    branch_b["revision_id"] = digest_canonical(
        "ai-stp:revision:v1",
        {
            "schema_version": 1,
            "remote_project_id": remote_project_id,
            "parent_revision_ids": [root_id],
            "operation": "upsert",
            "projection": cast(JsonValue, branch_b["projection"]),
        },
    )
    conflict = await client.post(
        f"/v1/projects/links/{link_id}/revisions", headers=headers, json=branch_b
    )
    assert conflict.status_code == 200
    assert conflict.json()["receipt"]["state"] == "conflict"
    assert conflict.json()["receipt"]["common_ancestor_revision_id"] == root_id
    branch_b_id = conflict.json()["receipt"]["revision_id"]

    link_view = await client.get(f"/v1/projects/links/{link_id}", headers=headers)
    assert link_view.status_code == 200
    assert link_view.json()["state"] == "conflict"
    assert link_view.json()["conflict_server_revision"] == branch_a_id
    assert link_view.json()["conflict_client_revision"] == branch_b_id
    assert link_view.json()["conflict_common_ancestor"] == root_id
    assert link_view.json()["revision"] == 4

    async with sessionmaker() as db:
        revisions_before_rejections = await db.scalar(
            select(func.count()).select_from(ProjectRevision)
        )

    invalid_resolution = revision_payload(
        remote_project_id=remote_project_id,
        parents=[branch_a_id, root_id],
        expected=branch_a_id,
        event_id="project-event-resolution-invalid",
        idempotency_key="project-idem-resolution-invalid",
        authorization_revision=authorization_revision,
    )
    invalid = await client.post(
        f"/v1/projects/links/{link_id}/conflict-resolutions",
        headers=headers,
        json=invalid_resolution,
    )
    assert invalid.status_code == 412
    async with sessionmaker() as db:
        assert (
            await db.scalar(select(func.count()).select_from(ProjectRevision))
            == revisions_before_rejections
        )

    resolution = revision_payload(
        remote_project_id=remote_project_id,
        parents=[branch_a_id, branch_b_id],
        expected=branch_a_id,
        event_id="project-event-resolution",
        idempotency_key="project-idem-resolution",
        authorization_revision=authorization_revision,
    )
    resolution_projection = cast(dict[str, object], resolution["projection"])
    resolution["projection"] = {**resolution_projection, "file_count": 3}
    resolution["content_digest"] = digest_canonical(
        "ai-stp:revision:v1",
        cast(JsonValue, resolution["projection"]),
    )
    resolution["revision_id"] = digest_canonical(
        "ai-stp:revision:v1",
        {
            "schema_version": 1,
            "remote_project_id": remote_project_id,
            "parent_revision_ids": [branch_a_id, branch_b_id],
            "operation": "upsert",
            "projection": cast(JsonValue, resolution["projection"]),
        },
    )
    merged = await client.post(
        f"/v1/projects/links/{link_id}/conflict-resolutions",
        headers=headers,
        json=resolution,
    )
    assert merged.status_code == 200, merged.text
    assert merged.json()["receipt"]["state"] == "accepted"

    replayed_merge = await client.post(
        f"/v1/projects/links/{link_id}/conflict-resolutions",
        headers=headers,
        json=resolution,
    )
    assert replayed_merge.status_code == 200
    assert replayed_merge.json() == merged.json()

    stale_resolution = {
        **resolution,
        "event_id": "project-event-resolution-stale",
        "idempotency_key": "project-idem-resolution-stale",
    }
    stale_merge = await client.post(
        f"/v1/projects/links/{link_id}/conflict-resolutions",
        headers=headers,
        json=stale_resolution,
    )
    assert stale_merge.status_code == 412

    resolved_link = await client.get(f"/v1/projects/links/{link_id}", headers=headers)
    assert resolved_link.json()["state"] == "linked"
    assert resolved_link.json()["conflict_server_revision"] is None

    pulled = await client.get(
        f"/v1/projects/links/{link_id}/revisions",
        headers={
            "Authorization": f"Bearer {token}",
            "X-AI-STP-Organization-Id": organization_id,
            "X-AI-STP-Authorization-Revision": authorization_revision,
        },
    )
    assert pulled.status_code == 200
    assert pulled.json()["head_revision_id"] == merged.json()["receipt"]["revision_id"]
    assert len(pulled.json()["items"]) == 4
    assert "file_count" in pulled.json()["items"][-1]["projection"]

    async with sessionmaker() as db:
        assert await db.scalar(select(func.count()).select_from(ProjectRevision)) == 4

        membership = await db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id
            )
        )
        assert membership is not None
        membership.revision += 1
        await db.commit()

    stale = await client.post(
        f"/v1/projects/links/{link_id}/revisions",
        headers=headers,
        json=root,
    )
    assert stale.status_code == 412
    assert stale.json()["error"]["details"]["reason"] == "capability_stale"

    async with sessionmaker() as db:
        assert await db.scalar(select(func.count()).select_from(ProjectRevision)) == 4
        personal_membership = await db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id
            )
        )
        assert personal_membership is not None
        suspended_organization = Organization(
            id=new_id("organization"),
            kind="corporate",
            owner_account_id=None,
            display_name="Suspended",
        )
        suspended_membership = OrganizationMembership(
            organization_id=suspended_organization.id,
            account_id=personal_membership.account_id,
            role="member",
            state="suspended",
        )
        db.add_all([suspended_organization, suspended_membership])
        await db.flush()
        suspended_organization_id = suspended_organization.id
        await db.commit()

    suspended = await client.get(
        f"/v1/organizations/{suspended_organization_id}/capabilities",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert suspended.status_code == 403


async def test_provider_identity_and_link_proposal_never_auto_link(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
) -> None:
    client, sessionmaker, token, organization_id, link_id, remote_project_id = project_harness
    headers = {
        "Authorization": f"Bearer {token}",
        "X-AI-STP-Organization-Id": organization_id,
    }
    authorization_revision = f"personal:{organization_id}:1:1"
    provider_project_id = new_id("provider_project")
    observation = {
        "schema_version": 1,
        "provider_project_id": provider_project_id,
        "provider_kind": "github",
        "installation_id": "installation-1",
        "namespace_id": "owner/repository",
        "immutable_repository_id": "github:12345",
        "current_url": "https://github.com/owner/repository",
        "observed_name": "repository",
        "authorization_revision": authorization_revision,
    }
    first = await client.post(
        f"/v1/organizations/{organization_id}/provider-project-observations",
        headers=headers,
        json=observation,
    )
    assert first.status_code == 201, first.text
    renamed = {
        **observation,
        "current_url": "https://github.com/owner/renamed",
        "observed_name": "renamed",
    }
    second = await client.post(
        f"/v1/organizations/{organization_id}/provider-project-observations",
        headers=headers,
        json=renamed,
    )
    assert second.status_code == 201
    assert second.json()["provider_project_id"] == provider_project_id
    assert second.json()["revision"] == first.json()["revision"] + 1

    async with sessionmaker() as db:
        link_row = await db.scalar(select(ProjectLink).where(ProjectLink.id == link_id))
        assert link_row is not None
        local_project_id = link_row.local_project_id

    proposal = await client.post(
        f"/v1/organizations/{organization_id}/project-link-proposals",
        headers=headers,
        json={
            "schema_version": 1,
            "local_project_id": local_project_id,
            "remote_project_id": remote_project_id,
            "provider_project_id": provider_project_id,
            "evidence": {"match": "immutable-repository"},
            "authorization_revision": authorization_revision,
        },
    )
    assert proposal.status_code == 201, proposal.text
    assert proposal.json()["state"] == "proposed"
    link = await client.get(f"/v1/projects/links/{link_id}", headers=headers)
    assert link.status_code == 200
    assert link.json()["state"] == "linked"
    async with sessionmaker() as db:
        stored = await db.scalar(
            select(ProjectLinkProposal).where(
                ProjectLinkProposal.id == proposal.json()["proposal_id"]
            )
        )
        assert stored is not None


async def test_link_confirmation_rejects_provider_evidence_changed_after_plan(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
) -> None:
    client, sessionmaker, token, organization_id, _link_id, remote_project_id = project_harness
    headers = {
        "Authorization": f"Bearer {token}",
        "X-AI-STP-Organization-Id": organization_id,
    }
    authorization_revision = f"personal:{organization_id}:1:1"
    provider_project_id = new_id("provider_project")
    observation = {
        "schema_version": 1,
        "provider_project_id": provider_project_id,
        "provider_kind": "github",
        "installation_id": "installation-1",
        "namespace_id": "owner/repository",
        "immutable_repository_id": "github:67890",
        "current_url": "https://github.com/owner/repository",
        "observed_name": "repository",
        "authorization_revision": authorization_revision,
    }
    observed = await client.post(
        f"/v1/organizations/{organization_id}/provider-project-observations",
        headers=headers,
        json=observation,
    )
    assert observed.status_code == 201, observed.text

    plan_payload = {
        "schema_version": 1,
        "local_project_id": new_id("project"),
        "remote_project_id": remote_project_id,
        "provider_project_id": provider_project_id,
        "local_revision": "local-1",
        "remote_revision": "initial",
        "provider_revision": str(observed.json()["revision"]),
        "authorization_revision": authorization_revision,
        "idempotency_key": "link-plan-provider-stale",
    }
    stale_remote = await client.post(
        f"/v1/organizations/{organization_id}/project-link-plans",
        headers=headers,
        json={
            **plan_payload,
            "remote_revision": "stale",
            "idempotency_key": "link-plan-stale-remote",
        },
    )
    assert stale_remote.status_code == 412

    plan = await client.post(
        f"/v1/organizations/{organization_id}/project-link-plans",
        headers=headers,
        json=plan_payload,
    )
    assert plan.status_code == 201, plan.text

    renamed = await client.post(
        f"/v1/organizations/{organization_id}/provider-project-observations",
        headers=headers,
        json={
            **observation,
            "current_url": "https://github.com/owner/renamed",
            "observed_name": "renamed",
        },
    )
    assert renamed.status_code == 201

    confirmed = await client.post(
        "/v1/projects/links",
        headers=headers,
        json={
            "schema_version": 1,
            "plan_id": plan.json()["plan_id"],
            "plan_digest": plan.json()["plan_digest"],
            "authorization_revision": authorization_revision,
            "idempotency_key": "link-confirm-provider-stale",
        },
    )
    assert confirmed.status_code == 412
    async with sessionmaker() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ProjectLink)
                .where(ProjectLink.plan_id == plan.json()["plan_id"])
            )
            == 0
        )


async def test_local_session_is_loopback_scoped_and_csrf_bound(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
) -> None:
    client, _sessionmaker, _token, organization_id, _link_id, _remote_project_id = project_harness
    started = await client.post("/v1/local/session")
    assert started.status_code == 200
    session = started.json()
    assert (
        session["session"]
        and session["csrf"]
        and session["api_base_url"].startswith("http://127.0.0.1:")
    )

    local_headers = {
        "X-AI-STP-Product-Mode": "local",
        "X-AI-STP-Local-Session": session["session"],
    }
    missing = await client.get("/v1/context", headers={"X-AI-STP-Product-Mode": "local"})
    assert missing.status_code == 401
    async with AsyncClient(base_url=session["api_base_url"]) as local_client:
        context = await local_client.get("/v1/context", headers=local_headers)
        local_remote = await local_client.get(
            "/v1/context",
            headers={**local_headers, "X-AI-STP-Organization-Id": organization_id},
        )
    assert context.status_code == 200
    assert context.json()["mode"] == "local"
    assert local_remote.status_code == 400

    invalid_stop = await client.delete(
        "/v1/local/session",
        headers={
            "X-AI-STP-Local-Session": session["session"],
            "X-AI-STP-Local-CSRF": "wrong",
        },
    )
    assert invalid_stop.status_code == 401
    stopped = await client.delete(
        "/v1/local/session",
        headers={
            "X-AI-STP-Local-Session": session["session"],
            "X-AI-STP-Local-CSRF": session["csrf"],
        },
    )
    assert stopped.status_code == 200


async def test_unlinked_project_rejects_push_pull_and_sync_without_side_effects(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
) -> None:
    client, sessionmaker, token, organization_id, link_id, remote_project_id = project_harness
    headers = {
        "Authorization": f"Bearer {token}",
        "X-AI-STP-Organization-Id": organization_id,
    }
    authorization_revision = f"personal:{organization_id}:1:1"
    async with sessionmaker() as db:
        link = await db.get(ProjectLink, link_id)
        assert link is not None
        link.state = "unlinked"
        link.revision += 1
        await db.commit()
        before_revisions = await db.scalar(select(func.count()).select_from(ProjectRevision))
        before_receipts = await db.scalar(select(func.count()).select_from(ProjectRevisionReceipt))

    payload = revision_payload(
        remote_project_id=remote_project_id,
        parents=[],
        expected=None,
        event_id="project-event-unlinked",
        idempotency_key="project-idem-unlinked",
        authorization_revision=authorization_revision,
    )
    pushed = await client.post(
        f"/v1/projects/links/{link_id}/revisions", headers=headers, json=payload
    )
    pulled = await client.get(
        f"/v1/projects/links/{link_id}/revisions",
        headers={**headers, "X-AI-STP-Authorization-Revision": authorization_revision},
    )
    planned = await client.post(
        f"/v1/projects/links/{link_id}/sync-plans",
        headers=headers,
        json={
            "schema_version": 1,
            "link_id": link_id,
            "expected_link_revision": 2,
            "local_revision": "initial",
            "remote_revision": "initial",
            "provider_revision": None,
            "authorization_revision": authorization_revision,
            "idempotency_key": "sync-idem-unlinked",
        },
    )
    assert pushed.status_code == pulled.status_code == planned.status_code == 412

    async with sessionmaker() as db:
        assert (
            await db.scalar(select(func.count()).select_from(ProjectRevision)) == before_revisions
        )
        assert (
            await db.scalar(select(func.count()).select_from(ProjectRevisionReceipt))
            == before_receipts
        )


async def test_confirmed_unlink_preserves_identities_history_and_audit(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
) -> None:
    client, sessionmaker, token, organization_id, link_id, remote_project_id = project_harness
    authorization_revision = f"personal:{organization_id}:1:1"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-AI-STP-Organization-Id": organization_id,
    }
    pushed = await client.post(
        f"/v1/projects/links/{link_id}/revisions",
        headers=headers,
        json=revision_payload(
            remote_project_id=remote_project_id,
            parents=[],
            expected=None,
            event_id="project-event-before-unlink",
            idempotency_key="project-idem-before-unlink",
            authorization_revision=authorization_revision,
        ),
    )
    assert pushed.status_code == 200, pushed.text

    planned = await client.post(
        f"/v1/organizations/{organization_id}/project-unlink-plans",
        headers=headers,
        json={
            "schema_version": 1,
            "link_id": link_id,
            "expected_link_revision": 2,
            "authorization_revision": authorization_revision,
            "idempotency_key": "unlink-plan-preserve-history",
        },
    )
    assert planned.status_code == 201, planned.text
    request = {
        "schema_version": 1,
        "plan_id": planned.json()["plan_id"],
        "plan_digest": planned.json()["plan_digest"],
        "authorization_revision": authorization_revision,
        "idempotency_key": "unlink-confirm-preserve-history",
    }
    unlinked = await client.request(
        "DELETE", f"/v1/projects/links/{link_id}", headers=headers, json=request
    )
    assert unlinked.status_code == 200, unlinked.text
    assert unlinked.json()["state"] == "unlinked"
    assert unlinked.json()["revision"] == 3
    replay = await client.request(
        "DELETE", f"/v1/projects/links/{link_id}", headers=headers, json=request
    )
    assert replay.status_code == 200
    assert replay.json() == unlinked.json()

    async with sessionmaker() as db:
        assert await db.get(ProjectIdentity, remote_project_id) is not None
        assert await db.scalar(select(func.count()).select_from(ProjectRevision)) == 1
        assert await db.scalar(select(func.count()).select_from(ProjectRevisionReceipt)) == 1
        assert (
            await db.scalar(
                select(func.count()).select_from(AuditEvent).where(AuditEvent.target_id == link_id)
            )
            or 0
        ) >= 1


async def test_sync_apply_rejects_exact_head_change_without_mutating_link(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
) -> None:
    client, sessionmaker, token, organization_id, link_id, remote_project_id = project_harness
    headers = {
        "Authorization": f"Bearer {token}",
        "X-AI-STP-Organization-Id": organization_id,
    }
    authorization_revision = f"personal:{organization_id}:1:1"
    plan_response = await client.post(
        f"/v1/projects/links/{link_id}/sync-plans",
        headers=headers,
        json={
            "schema_version": 1,
            "link_id": link_id,
            "expected_link_revision": 1,
            "local_revision": "initial",
            "remote_revision": "initial",
            "provider_revision": None,
            "authorization_revision": authorization_revision,
            "idempotency_key": "sync-idem-head-stale",
        },
    )
    assert plan_response.status_code == 201, plan_response.text
    plan = plan_response.json()
    async with sessionmaker() as db:
        db.add(
            ProjectRevisionHead(
                organization_id=organization_id,
                remote_project_id=remote_project_id,
                revision_id="sha256:" + "c" * 64,
            )
        )
        await db.commit()

    applied = await client.post(
        f"/v1/projects/links/{link_id}/sync-plans/{plan['plan_id']}/apply",
        headers=headers,
        json={
            "schema_version": 1,
            "plan_digest": plan["plan_digest"],
            "expected_link_revision": 1,
            "authorization_revision": authorization_revision,
            "idempotency_key": "sync-apply-head-stale",
        },
    )
    assert applied.status_code == 412, applied.text
    async with sessionmaker() as db:
        link = await db.get(ProjectLink, link_id)
        stored_plan = await db.get(ProjectSyncPlan, plan["plan_id"])
        assert link is not None and link.revision == 1
        assert stored_plan is not None and stored_plan.apply_idempotency_key is None


@pytest.mark.parametrize("action", ["noop", "local_to_remote"])
async def test_server_authored_sync_plan_applies_once_and_replays(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
    action: str,
) -> None:
    """The plan the server authored passes the server's own verification.

    Creation and application must hash one document. When they hash two, every
    fresh plan is rejected as stale and the whole synchronization path is dead,
    while each side looks correct on its own.
    """
    client, sessionmaker, token, organization_id, link_id, remote_project_id = project_harness
    headers = {
        "Authorization": f"Bearer {token}",
        "X-AI-STP-Organization-Id": organization_id,
    }
    authorization_revision = f"personal:{organization_id}:1:1"
    local_revision = "initial"
    if action == "local_to_remote":
        local_revision = "sha256:" + "1" * 64
        async with sessionmaker() as db:
            link = await db.get(ProjectLink, link_id)
            assert link is not None
            db.add(
                ProjectRevision(
                    organization_id=organization_id,
                    remote_project_id=remote_project_id,
                    revision_id=local_revision,
                    parent_revision_ids=[],
                    operation="upsert",
                    content_digest="sha256:" + "2" * 64,
                    projection={"schema_version": 1, "kind": "project"},
                    actor_account_id=link.actor_account_id,
                    device_id=link.device_id,
                    event_id=f"sync-apply-{action}",
                )
            )
            await db.commit()

    planned = await client.post(
        f"/v1/projects/links/{link_id}/sync-plans",
        headers=headers,
        json={
            "schema_version": 1,
            "link_id": link_id,
            "expected_link_revision": 1,
            "local_revision": local_revision,
            "remote_revision": "initial",
            "provider_revision": None,
            "authorization_revision": authorization_revision,
            "idempotency_key": f"sync-plan-idem-{action}",
        },
    )
    assert planned.status_code == 201, planned.text
    plan = planned.json()
    assert plan["state"] == "ready"
    assert plan["action"] == action
    assert plan["conflict_code"] is None

    apply_request = {
        "schema_version": 1,
        "plan_digest": plan["plan_digest"],
        "expected_link_revision": 1,
        "authorization_revision": authorization_revision,
        "idempotency_key": f"sync-apply-idem-{action}",
    }
    applied = await client.post(
        f"/v1/projects/links/{link_id}/sync-plans/{plan['plan_id']}/apply",
        headers=headers,
        json=apply_request,
    )
    assert applied.status_code == 200, applied.text
    body = applied.json()
    assert body["state"] == "applied"
    assert body["plan_digest"] == plan["plan_digest"]

    replayed = await client.post(
        f"/v1/projects/links/{link_id}/sync-plans/{plan['plan_id']}/apply",
        headers=headers,
        json=apply_request,
    )
    assert replayed.status_code == 200, replayed.text
    assert replayed.json() == body

    async with sessionmaker() as db:
        link = await db.get(ProjectLink, link_id)
        stored_plan = await db.get(ProjectSyncPlan, plan["plan_id"])
        head = await db.get(ProjectRevisionHead, (organization_id, remote_project_id))
        assert link is not None and stored_plan is not None
        # One remote effect for one plan, whether or not the retry was answered
        # from the receipt.
        assert link.revision == 2
        assert link.local_revision == local_revision
        assert link.remote_revision == "initial"
        assert stored_plan.state == "applied"
        assert stored_plan.result == {"link_revision": 2, "action": action}
        if action == "noop":
            assert head is None
        else:
            assert head is not None and head.revision_id == local_revision


async def test_a_conflict_plan_is_refused_as_a_conflict_and_not_as_a_stale_digest(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
) -> None:
    """The refusal has to name the thing the caller must resolve.

    While creation and verification hashed different documents, every plan —
    conflict or not — was refused for a stale digest, which says "plan again"
    about a state that planning cannot fix.
    """
    client, sessionmaker, token, organization_id, link_id, remote_project_id = project_harness
    headers = {
        "Authorization": f"Bearer {token}",
        "X-AI-STP-Organization-Id": organization_id,
    }
    authorization_revision = f"personal:{organization_id}:1:1"
    async with sessionmaker() as db:
        remote = await db.get(ProjectIdentity, remote_project_id)
        assert remote is not None
        remote.state = "archived"
        await db.commit()

    planned = await client.post(
        f"/v1/projects/links/{link_id}/sync-plans",
        headers=headers,
        json={
            "schema_version": 1,
            "link_id": link_id,
            "expected_link_revision": 1,
            "local_revision": "initial",
            "remote_revision": "initial",
            "provider_revision": None,
            "authorization_revision": authorization_revision,
            "idempotency_key": "sync-idem-conflict-plan",
        },
    )
    assert planned.status_code == 201, planned.text
    plan = planned.json()
    assert plan["state"] == "conflict"
    assert plan["conflict_code"] == "remote_missing"

    applied = await client.post(
        f"/v1/projects/links/{link_id}/sync-plans/{plan['plan_id']}/apply",
        headers=headers,
        json={
            "schema_version": 1,
            "plan_digest": plan["plan_digest"],
            "expected_link_revision": 1,
            "authorization_revision": authorization_revision,
            "idempotency_key": "sync-apply-conflict-plan",
        },
    )
    assert applied.status_code == 409, applied.text

    async with sessionmaker() as db:
        link = await db.get(ProjectLink, link_id)
        stored_plan = await db.get(ProjectSyncPlan, plan["plan_id"])
        assert link is not None and link.revision == 1
        assert stored_plan is not None and stored_plan.apply_idempotency_key is None


@pytest.mark.parametrize(
    "field,tampered",
    [
        ("conflict_code", "both_changed"),
        ("action", "remote_to_local"),
        ("expected_link_revision", 2),
        ("common_ancestor_revision", "sha256:" + "3" * 64),
    ],
)
async def test_sync_apply_rejects_a_plan_whose_bound_field_changed(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
    field: str,
    tampered: object,
) -> None:
    """Every field the digest binds is actually verified before any effect."""
    client, sessionmaker, token, organization_id, link_id, _remote_project_id = project_harness
    headers = {
        "Authorization": f"Bearer {token}",
        "X-AI-STP-Organization-Id": organization_id,
    }
    authorization_revision = f"personal:{organization_id}:1:1"
    planned = await client.post(
        f"/v1/projects/links/{link_id}/sync-plans",
        headers=headers,
        json={
            "schema_version": 1,
            "link_id": link_id,
            "expected_link_revision": 1,
            "local_revision": "initial",
            "remote_revision": "initial",
            "provider_revision": None,
            "authorization_revision": authorization_revision,
            "idempotency_key": f"sync-idem-tampered-{field}",
        },
    )
    assert planned.status_code == 201, planned.text
    plan = planned.json()

    async with sessionmaker() as db:
        stored_plan = await db.get(ProjectSyncPlan, plan["plan_id"])
        assert stored_plan is not None
        setattr(stored_plan, field, tampered)
        await db.commit()

    applied = await client.post(
        f"/v1/projects/links/{link_id}/sync-plans/{plan['plan_id']}/apply",
        headers=headers,
        json={
            "schema_version": 1,
            "plan_digest": plan["plan_digest"],
            "expected_link_revision": 1,
            "authorization_revision": authorization_revision,
            "idempotency_key": f"sync-apply-tampered-{field}",
        },
    )
    assert applied.status_code == 412, applied.text

    async with sessionmaker() as db:
        link = await db.get(ProjectLink, link_id)
        stored_plan = await db.get(ProjectSyncPlan, plan["plan_id"])
        assert link is not None and link.revision == 1
        assert stored_plan is not None and stored_plan.apply_idempotency_key is None


async def test_sync_plan_replay_requires_the_same_request(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
) -> None:
    """One idempotency key answers one exact request, not any later one."""
    client, sessionmaker, token, organization_id, link_id, remote_project_id = project_harness
    headers = {
        "Authorization": f"Bearer {token}",
        "X-AI-STP-Organization-Id": organization_id,
    }
    authorization_revision = f"personal:{organization_id}:1:1"
    local_revision = "sha256:" + "4" * 64
    async with sessionmaker() as db:
        link = await db.get(ProjectLink, link_id)
        assert link is not None
        db.add(
            ProjectRevision(
                organization_id=organization_id,
                remote_project_id=remote_project_id,
                revision_id=local_revision,
                parent_revision_ids=[],
                operation="upsert",
                content_digest="sha256:" + "5" * 64,
                projection={"schema_version": 1, "kind": "project"},
                actor_account_id=link.actor_account_id,
                device_id=link.device_id,
                event_id="sync-replay-identity",
            )
        )
        await db.commit()

    request = {
        "schema_version": 1,
        "link_id": link_id,
        "expected_link_revision": 1,
        "local_revision": "initial",
        "remote_revision": "initial",
        "provider_revision": None,
        "authorization_revision": authorization_revision,
        "idempotency_key": "sync-idem-replay-identity",
    }
    planned = await client.post(
        f"/v1/projects/links/{link_id}/sync-plans", headers=headers, json=request
    )
    assert planned.status_code == 201, planned.text
    plan = planned.json()

    identical = await client.post(
        f"/v1/projects/links/{link_id}/sync-plans", headers=headers, json=request
    )
    assert identical.status_code == 201, identical.text
    assert identical.json() == plan

    different = await client.post(
        f"/v1/projects/links/{link_id}/sync-plans",
        headers=headers,
        json={**request, "local_revision": local_revision},
    )
    assert different.status_code == 409, different.text

    async with sessionmaker() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ProjectSyncPlan)
                .where(ProjectSyncPlan.link_id == link_id)
            )
            == 1
        )


@pytest.mark.parametrize("side", ["local_revision", "remote_revision"])
async def test_sync_plan_rejects_unknown_single_side_revision(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
    side: str,
) -> None:
    client, sessionmaker, token, organization_id, link_id, _remote_project_id = project_harness
    authorization_revision = f"personal:{organization_id}:1:1"
    payload = {
        "schema_version": 1,
        "link_id": link_id,
        "expected_link_revision": 1,
        "local_revision": "initial",
        "remote_revision": "initial",
        "provider_revision": None,
        "authorization_revision": authorization_revision,
        "idempotency_key": f"sync-unknown-{side}",
    }
    payload[side] = "sha256:" + "d" * 64

    response = await client.post(
        f"/v1/projects/links/{link_id}/sync-plans",
        headers={
            "Authorization": f"Bearer {token}",
            "X-AI-STP-Organization-Id": organization_id,
        },
        json=payload,
    )

    assert response.status_code == 412, response.text
    async with sessionmaker() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ProjectSyncPlan)
                .where(ProjectSyncPlan.link_id == link_id)
            )
            == 0
        )


async def test_provider_change_cannot_hide_behind_a_known_local_change(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
) -> None:
    client, sessionmaker, token, organization_id, link_id, remote_project_id = project_harness
    provider_id = new_id("provider_project")
    local_revision = "sha256:" + "e" * 64
    async with sessionmaker() as db:
        link = await db.get(ProjectLink, link_id)
        assert link is not None
        db.add_all(
            [
                ProjectIdentity(
                    id=provider_id,
                    organization_id=organization_id,
                    namespace="provider",
                    external_key="provider-combined-change",
                    display_name="Provider project",
                ),
                ProjectRevision(
                    organization_id=organization_id,
                    remote_project_id=remote_project_id,
                    revision_id=local_revision,
                    parent_revision_ids=[],
                    operation="upsert",
                    content_digest="sha256:" + "f" * 64,
                    projection={"schema_version": 1, "kind": "project"},
                    actor_account_id=link.actor_account_id,
                    device_id=link.device_id,
                    event_id="provider-combined-change",
                ),
            ]
        )
        link.provider_project_id = provider_id
        link.provider_revision = "1"
        await db.commit()

    response = await client.post(
        f"/v1/projects/links/{link_id}/sync-plans",
        headers={
            "Authorization": f"Bearer {token}",
            "X-AI-STP-Organization-Id": organization_id,
        },
        json={
            "schema_version": 1,
            "link_id": link_id,
            "expected_link_revision": 1,
            "local_revision": local_revision,
            "remote_revision": "initial",
            "provider_revision": "2",
            "authorization_revision": f"personal:{organization_id}:1:1",
            "idempotency_key": "sync-provider-and-local-changed",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["state"] == "conflict"
    assert response.json()["conflict_code"] == "provider_mismatch"


@pytest.mark.parametrize("change", ["conflict", "unlinked", "provider_revision", "provider_state"])
async def test_sync_apply_rechecks_every_link_and_identity_precondition(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
    change: str,
) -> None:
    """A ready plan cannot write after any concurrent link/identity transition."""
    client, sessionmaker, token, organization_id, link_id, _remote_project_id = project_harness
    headers = {
        "Authorization": f"Bearer {token}",
        "X-AI-STP-Organization-Id": organization_id,
    }
    authorization_revision = f"personal:{organization_id}:1:1"
    provider_id: str | None = None
    if change.startswith("provider"):
        provider_id = new_id("provider_project")
        async with sessionmaker() as db:
            link = await db.get(ProjectLink, link_id)
            assert link is not None
            db.add(
                ProjectIdentity(
                    id=provider_id,
                    organization_id=organization_id,
                    namespace="provider",
                    external_key="provider-1",
                    display_name="Provider project",
                )
            )
            link.provider_project_id = provider_id
            link.provider_revision = "provider-1"
            await db.commit()

    planned = await client.post(
        f"/v1/projects/links/{link_id}/sync-plans",
        headers=headers,
        json={
            "schema_version": 1,
            "link_id": link_id,
            "expected_link_revision": 1,
            "local_revision": "initial",
            "remote_revision": "initial",
            "provider_revision": "provider-1" if provider_id else None,
            "authorization_revision": authorization_revision,
            "idempotency_key": f"sync-precondition-{change}",
        },
    )
    assert planned.status_code == 201, planned.text
    plan = planned.json()

    async with sessionmaker() as db:
        link = await db.get(ProjectLink, link_id)
        stored_plan = await db.get(ProjectSyncPlan, plan["plan_id"])
        assert link is not None and stored_plan is not None
        if change in {"conflict", "unlinked"}:
            link.state = change
            link.revision += 1
        else:
            provider = await db.get(ProjectIdentity, provider_id)
            assert provider is not None
            if change == "provider_revision":
                provider.revision += 1
            else:
                provider.state = "archived"
        await db.commit()
        # Snapshot committed concurrent changes before the rejected application.
        tables = (
            ProjectLink,
            ProjectSyncPlan,
            ProjectIdentity,
            ProjectRevision,
            ProjectRevisionHead,
            ProjectRevisionReceipt,
        )
        before = {
            model.__tablename__: list((await db.execute(select(model.__table__))).mappings())
            for model in tables
        }

    applied = await client.post(
        f"/v1/projects/links/{link_id}/sync-plans/{plan['plan_id']}/apply",
        headers=headers,
        json={
            "schema_version": 1,
            "plan_digest": plan["plan_digest"],
            "expected_link_revision": 1,
            "authorization_revision": authorization_revision,
            "idempotency_key": f"sync-apply-precondition-{change}",
        },
    )
    assert applied.status_code == 412, applied.text

    async with sessionmaker() as db:
        link = await db.get(ProjectLink, link_id)
        stored_plan = await db.get(ProjectSyncPlan, plan["plan_id"])
        assert link is not None and stored_plan is not None
        assert stored_plan.state == "ready"
        assert stored_plan.apply_idempotency_key is None
        if change in {"conflict", "unlinked"}:
            assert link.state == change and link.revision == 2
        else:
            assert link.revision == 1
        after = {
            model.__tablename__: list((await db.execute(select(model.__table__))).mappings())
            for model in tables
        }
        assert after == before
        failed_audits = list(
            (
                await db.scalars(
                    select(AuditEvent)
                    .where(AuditEvent.action == "http.post.failed")
                    .order_by(AuditEvent.id)
                )
            ).all()
        )
        assert len(failed_audits) == 1
        assert failed_audits[0].outcome == "failed"
        assert failed_audits[0].reason == "precondition"
        assert failed_audits[0].target_id == "redacted"
        assert failed_audits[0].payload == {
            "method": "POST",
            "http_status": 412,
            "error": "AI_STP_PRECONDITION_FAILED",
        }


async def test_sync_apply_refuses_a_plan_authored_for_another_device(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
) -> None:
    client, sessionmaker, token, organization_id, link_id, _remote_project_id = project_harness
    headers = {
        "Authorization": f"Bearer {token}",
        "X-AI-STP-Organization-Id": organization_id,
    }
    authorization_revision = f"personal:{organization_id}:1:1"
    planned = await client.post(
        f"/v1/projects/links/{link_id}/sync-plans",
        headers=headers,
        json={
            "schema_version": 1,
            "link_id": link_id,
            "expected_link_revision": 1,
            "local_revision": "initial",
            "remote_revision": "initial",
            "provider_revision": None,
            "authorization_revision": authorization_revision,
            "idempotency_key": "sync-idem-other-device",
        },
    )
    assert planned.status_code == 201, planned.text
    plan = planned.json()

    async with sessionmaker() as db:
        link = await db.get(ProjectLink, link_id)
        assert link is not None
        other = Device(
            id=new_id("device"),
            account_id=link.actor_account_id,
            public_key="b3RoZXItZGV2aWNlLWtleS1mb3Itc3luYw==",
            state="active",
        )
        db.add(other)
        await db.flush()
        issued = await issue_session(
            db, account_id=link.actor_account_id, device_id=other.id, ttl_seconds=3600
        )
        await db.commit()

    applied = await client.post(
        f"/v1/projects/links/{link_id}/sync-plans/{plan['plan_id']}/apply",
        headers={
            "Authorization": f"Bearer {issued.raw_token}",
            "X-AI-STP-Organization-Id": organization_id,
        },
        json={
            "schema_version": 1,
            "plan_digest": plan["plan_digest"],
            "expected_link_revision": 1,
            "authorization_revision": authorization_revision,
            "idempotency_key": "sync-apply-other-device",
        },
    )
    assert applied.status_code == 403, applied.text
    assert "another device" in applied.text


async def test_sync_apply_refuses_an_expired_plan(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
) -> None:
    client, sessionmaker, token, organization_id, link_id, _remote_project_id = project_harness
    headers = {
        "Authorization": f"Bearer {token}",
        "X-AI-STP-Organization-Id": organization_id,
    }
    authorization_revision = f"personal:{organization_id}:1:1"
    planned = await client.post(
        f"/v1/projects/links/{link_id}/sync-plans",
        headers=headers,
        json={
            "schema_version": 1,
            "link_id": link_id,
            "expected_link_revision": 1,
            "local_revision": "initial",
            "remote_revision": "initial",
            "provider_revision": None,
            "authorization_revision": authorization_revision,
            "idempotency_key": "sync-idem-expired",
        },
    )
    assert planned.status_code == 201, planned.text
    plan = planned.json()

    async with sessionmaker() as db:
        stored = await db.get(ProjectSyncPlan, plan["plan_id"])
        assert stored is not None
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        stored.plan_digest = _plan_digest(
            _sync_plan_preimage(stored, organization_id=organization_id)
        )
        digest = stored.plan_digest
        await db.commit()

    applied = await client.post(
        f"/v1/projects/links/{link_id}/sync-plans/{plan['plan_id']}/apply",
        headers=headers,
        json={
            "schema_version": 1,
            "plan_digest": digest,
            "expected_link_revision": 1,
            "authorization_revision": authorization_revision,
            "idempotency_key": "sync-apply-expired",
        },
    )
    assert applied.status_code == 412, applied.text
    assert "expired" in applied.text


async def test_concurrent_equal_sync_plan_creates_share_one_row(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
) -> None:
    client, sessionmaker, token, organization_id, link_id, _remote_project_id = project_harness
    headers = {
        "Authorization": f"Bearer {token}",
        "X-AI-STP-Organization-Id": organization_id,
    }
    payload = {
        "schema_version": 1,
        "link_id": link_id,
        "expected_link_revision": 1,
        "local_revision": "initial",
        "remote_revision": "initial",
        "provider_revision": None,
        "authorization_revision": f"personal:{organization_id}:1:1",
        "idempotency_key": "sync-idem-concurrent-equal",
    }

    async def create() -> Response:
        return await client.post(
            f"/v1/projects/links/{link_id}/sync-plans", headers=headers, json=payload
        )

    first, second = await asyncio.gather(create(), create())
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json() == second.json()

    async with sessionmaker() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ProjectSyncPlan)
                .where(ProjectSyncPlan.link_id == link_id)
            )
            == 1
        )


async def test_remote_to_local_apply_advances_the_link_to_the_ledger_head(
    project_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession], str, str, str, str],
) -> None:
    client, sessionmaker, token, organization_id, link_id, remote_project_id = project_harness
    headers = {
        "Authorization": f"Bearer {token}",
        "X-AI-STP-Organization-Id": organization_id,
    }
    authorization_revision = f"personal:{organization_id}:1:1"
    remote_revision = "sha256:" + "a" * 64
    async with sessionmaker() as db:
        link = await db.get(ProjectLink, link_id)
        assert link is not None
        db.add(
            ProjectRevision(
                organization_id=organization_id,
                remote_project_id=remote_project_id,
                revision_id=remote_revision,
                parent_revision_ids=[],
                operation="upsert",
                content_digest="sha256:" + "b" * 64,
                projection={"schema_version": 1, "kind": "project"},
                actor_account_id=link.actor_account_id,
                device_id=link.device_id,
                event_id="remote-to-local-head",
            )
        )
        db.add(
            ProjectRevisionHead(
                organization_id=organization_id,
                remote_project_id=remote_project_id,
                revision_id=remote_revision,
            )
        )
        await db.commit()

    planned = await client.post(
        f"/v1/projects/links/{link_id}/sync-plans",
        headers=headers,
        json={
            "schema_version": 1,
            "link_id": link_id,
            "expected_link_revision": 1,
            "local_revision": "initial",
            "remote_revision": remote_revision,
            "provider_revision": None,
            "authorization_revision": authorization_revision,
            "idempotency_key": "sync-idem-remote-to-local",
        },
    )
    assert planned.status_code == 201, planned.text
    plan = planned.json()
    assert plan["action"] == "remote_to_local"
    assert plan["state"] == "ready"

    applied = await client.post(
        f"/v1/projects/links/{link_id}/sync-plans/{plan['plan_id']}/apply",
        headers=headers,
        json={
            "schema_version": 1,
            "plan_digest": plan["plan_digest"],
            "expected_link_revision": 1,
            "authorization_revision": authorization_revision,
            "idempotency_key": "sync-apply-remote-to-local",
        },
    )
    assert applied.status_code == 200, applied.text
    async with sessionmaker() as db:
        link = await db.get(ProjectLink, link_id)
        assert link is not None
        assert link.remote_revision == remote_revision
        assert link.local_revision == "initial"
        assert link.state == "linked"
