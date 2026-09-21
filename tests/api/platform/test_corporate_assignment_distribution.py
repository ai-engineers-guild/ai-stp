"""Bulk assignment distribution through the authenticated HTTP boundary."""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.session import issue_session
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, CatalogMetadata
from ai_stp_platform.organization_models import (
    CorporateAssignmentDistribution,
    OrganizationMembership,
)

pytestmark = pytest.mark.platform

DIGEST = "sha256:" + "3" * 64


async def test_corporate_assignment_distribution_http(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    client, sessionmaker, _ = db_api_client
    account_id = new_id("account")
    member_id = new_id("account")
    setup_id = new_id("setup")
    async with sessionmaker() as db:
        db.add(Account(id=account_id, status="active"))
        db.add(Account(id=member_id, status="active"))
        await db.flush()
        session = await issue_session(db, account_id=account_id, device_id=None, ttl_seconds=3600)
        await db.commit()
    auth = {"Authorization": f"Bearer {session.raw_token}"}
    bootstrap = await client.post(
        "/v1/corporate/bootstrap",
        json={
            "organization_name": "Distribution acceptance",
            "superadmin_account_id": account_id,
            "idempotency_key": "distribution-bootstrap-fixture",
        },
        headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
    )
    assert bootstrap.status_code == 200, bootstrap.text
    organization_id = bootstrap.json()["organization_id"]
    async with sessionmaker() as db:
        db.add(
            OrganizationMembership(
                organization_id=organization_id,
                account_id=member_id,
                role="staff",
                display_name="Member",
            )
        )
        db.add(
            CatalogMetadata(
                owner_account_id=account_id,
                organization_id=organization_id,
                object_kind="setup",
                stable_id=setup_id,
                version="1.0",
                current_revision_id="revision-1.0",
                visibility="private",
                lifecycle_state="active",
                name="Distributed Setup",
                published_at=datetime.now(UTC),
                passport_document={"fixture": True},
                passport_digest=DIGEST,
                trust_lane="experimental",
            )
        )
        await db.commit()
    organization_base = f"/v1/corporate/organizations/{organization_id}"
    base = f"{organization_base}/catalog-assignments"
    distribution_url = f"{base}/distribution"
    context = (await client.get(f"{organization_base}/context", headers=auth)).json()
    authorization_revision = context["organization"]["authorization_revision"]
    # A team-scoped source assignment expands to its members and owned projects.
    team = await client.post(
        f"{organization_base}/teams",
        headers=auth,
        json={
            "name": "Distribution",
            "authorization_revision": authorization_revision,
            "idempotency_key": "distribution-team-fixture",
        },
    )
    assert team.status_code == 200, team.text
    team_id = team.json()["team_id"]
    context = (await client.get(f"{organization_base}/context", headers=auth)).json()
    membership = await client.post(
        f"{organization_base}/membership-assignments",
        headers=auth,
        json={
            "account_id": member_id,
            "team_id": team_id,
            "team_role": "staff",
            "authorization_revision": context["organization"]["authorization_revision"],
            "idempotency_key": "distribution-member-fixture",
        },
    )
    assert membership.status_code == 200, membership.text
    context = (await client.get(f"{organization_base}/context", headers=auth)).json()
    admin_membership = await client.post(
        f"{organization_base}/membership-assignments",
        headers=auth,
        json={
            "account_id": account_id,
            "team_id": team_id,
            "team_role": "staff",
            "authorization_revision": context["organization"]["authorization_revision"],
            "idempotency_key": "distribution-admin-member-fixture",
        },
    )
    assert admin_membership.status_code == 200, admin_membership.text
    context = (await client.get(f"{organization_base}/context", headers=auth)).json()
    source = await client.put(
        base,
        headers=auth,
        json={
            "subject_kind": "team",
            "subject_id": team_id,
            "object_kind": "setup",
            "stable_id": setup_id,
            "version": "1.0",
            "expected_revision": 0,
            "authorization_revision": context["organization"]["authorization_revision"],
            "idempotency_key": "distribution-source-fixture",
        },
    )
    assert source.status_code == 200, source.text
    source_assignment_id = source.json()["assignment_id"]
    # An individual employee exception stays authoritative over the bulk wave.
    context = (await client.get(f"{organization_base}/context", headers=auth)).json()
    exception = await client.put(
        base,
        headers=auth,
        json={
            "subject_kind": "employee",
            "subject_id": member_id,
            "object_kind": "setup",
            "stable_id": setup_id,
            "version": "1.0",
            "expected_revision": 0,
            "authorization_revision": context["organization"]["authorization_revision"],
            "idempotency_key": "distribution-exception-fixture",
        },
    )
    assert exception.status_code == 200, exception.text
    exception_id = exception.json()["assignment_id"]
    request_body = {
        "source_assignment_id": source_assignment_id,
        "expected_revision": 1,
        "idempotency_key": "distribution-apply-fixture",
    }

    async def distribute(action: str, *, dry_run: bool, key: str):
        context = (await client.get(f"{organization_base}/context", headers=auth)).json()
        return await client.post(
            distribution_url,
            headers=auth,
            json={
                **request_body,
                "action": action,
                "dry_run": dry_run,
                "authorization_revision": context["organization"]["authorization_revision"],
                "idempotency_key": key,
            },
        )

    # Dry-run previews the expansion without persisting a single row.
    preview = await distribute("assign", dry_run=True, key="distribution-preview-fixture")
    assert preview.status_code == 200, preview.text
    preview_body = preview.json()
    assert preview_body["dry_run"] is True
    assert preview_body["distribution_id"] is None
    member_target = next(item for item in preview_body["targets"] if item["target_id"] == member_id)
    assert member_target["result"] == "conflicted"
    assert member_target["overriding_assignment_id"] == exception_id
    assert preview_body["counts"]["conflicted"] == 1
    async with sessionmaker() as db:
        stored = (
            await db.execute(
                CorporateAssignmentDistribution.__table__.select().where(
                    CorporateAssignmentDistribution.organization_id == organization_id
                )
            )
        ).all()
    assert stored == []
    # Apply persists one derived row per resolved target and keeps partials.
    applied = await distribute("assign", dry_run=False, key="distribution-apply-fixture")
    assert applied.status_code == 200, applied.text
    applied_body = applied.json()
    assert applied_body["dry_run"] is False
    assert applied_body["distribution_id"] == "distribution-apply-fixture"
    results = {item["target_id"]: item for item in applied_body["targets"]}
    assert results[member_id]["result"] == "conflicted"
    assert results[account_id]["result"] == "applied"
    assert results[account_id]["state"] == "pending"
    assert applied_body["counts"]["applied"] == 1
    # The durable state read reports the latest lifecycle per target.
    state = await client.get(
        distribution_url,
        params={"source_assignment_id": source_assignment_id},
        headers=auth,
    )
    assert state.status_code == 200, state.text
    state_body = state.json()
    assert state_body["source_revision"] == 1
    assert state_body["source_state"] == "current"
    items = {item["target_id"]: item for item in state_body["items"]}
    assert items[account_id]["state"] == "pending"
    assert items[member_id]["result"] == "conflicted"
    assert items[member_id]["state"] is None
    # A retry with the same key returns the durable result without new rows.
    replay = await distribute("assign", dry_run=False, key="distribution-apply-fixture")
    assert replay.status_code == 200, replay.text
    assert replay.json() == applied_body
    async with sessionmaker() as db:
        rows = (
            await db.execute(
                CorporateAssignmentDistribution.__table__.select().where(
                    CorporateAssignmentDistribution.organization_id == organization_id
                )
            )
        ).all()
    assert len(rows) == len(applied_body["targets"])
    # Revoking retires the source and marks live targets revoked; the conflicted
    # exception target is skipped because nothing was ever distributed to it.
    context = (await client.get(f"{organization_base}/context", headers=auth)).json()
    revoked = await client.post(
        distribution_url,
        headers=auth,
        json={
            **request_body,
            "action": "revoke",
            "dry_run": False,
            "authorization_revision": context["organization"]["authorization_revision"],
            "idempotency_key": "distribution-revoke-fixture",
        },
    )
    assert revoked.status_code == 200, revoked.text
    revoked_body = revoked.json()
    results = {item["target_id"]: item for item in revoked_body["targets"]}
    assert results[account_id]["result"] == "applied"
    assert results[account_id]["state"] == "revoked"
    assert results[member_id]["result"] == "skipped"
    state = await client.get(
        distribution_url,
        params={"source_assignment_id": source_assignment_id},
        headers=auth,
    )
    state_body = state.json()
    assert state_body["source_state"] == "retired"
    items = {item["target_id"]: item for item in state_body["items"]}
    assert items[account_id]["state"] == "revoked"
    # A retired source cannot be distributed again.
    context = (await client.get(f"{organization_base}/context", headers=auth)).json()
    stale = await client.post(
        distribution_url,
        headers=auth,
        json={
            **request_body,
            "action": "assign",
            "dry_run": False,
            "authorization_revision": context["organization"]["authorization_revision"],
            "idempotency_key": "distribution-stale-fixture",
        },
    )
    assert stale.status_code == 409, stale.text
    # A staff member cannot preview or apply outside their authority.
    staff_id = new_id("account")
    async with sessionmaker() as db:
        db.add(Account(id=staff_id, status="active"))
        db.add(
            OrganizationMembership(
                organization_id=organization_id,
                account_id=staff_id,
                role="staff",
                display_name="Staff",
            )
        )
        await db.flush()
        staff_session = await issue_session(
            db, account_id=staff_id, device_id=None, ttl_seconds=3600
        )
        await db.commit()
    staff_auth = {"Authorization": f"Bearer {staff_session.raw_token}"}
    denied = await client.post(
        distribution_url,
        headers=staff_auth,
        json={
            **request_body,
            "action": "assign",
            "dry_run": True,
            "authorization_revision": 1,
            "idempotency_key": "distribution-denied-fixture",
        },
    )
    assert denied.status_code == 403, denied.text
    denied_state = await client.get(
        distribution_url,
        params={"source_assignment_id": source_assignment_id},
        headers=staff_auth,
    )
    assert denied_state.status_code == 403, denied_state.text
