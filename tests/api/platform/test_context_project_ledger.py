"""Executable acceptance evidence for the organization-scoped project DAG."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.app import create_app
from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, AuditEvent, Device
from ai_stp_platform.organization_models import (
    Organization,
    OrganizationMembership,
    ProjectIdentity,
    ProjectLink,
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
            AuditEvent,
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
