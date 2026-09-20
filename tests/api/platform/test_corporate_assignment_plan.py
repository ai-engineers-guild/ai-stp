"""The corporate assignment plan evaluates through the authenticated HTTP boundary."""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.session import issue_session
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, CatalogMetadata
from ai_stp_platform.organization_models import (
    CorporateAssignmentDistribution,
    CorporateCatalogAssignment,
)

pytestmark = pytest.mark.platform

DIGEST = "sha256:" + "5" * 64


async def test_corporate_assignment_plan_http(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    client, sessionmaker, _ = db_api_client
    account_id = new_id("account")
    outsider_id = new_id("account")
    setup_id = new_id("setup")
    async with sessionmaker() as db:
        db.add(Account(id=account_id, status="active"))
        db.add(Account(id=outsider_id, status="active"))
        await db.flush()
        session = await issue_session(db, account_id=account_id, device_id=None, ttl_seconds=3600)
        outsider = await issue_session(db, account_id=outsider_id, device_id=None, ttl_seconds=3600)
        await db.commit()
    auth = {"Authorization": f"Bearer {session.raw_token}"}
    outsider_auth = {"Authorization": f"Bearer {outsider.raw_token}"}
    bootstrap = await client.post(
        "/v1/corporate/bootstrap",
        json={
            "organization_name": "Plan acceptance",
            "superadmin_account_id": account_id,
            "idempotency_key": "plan-bootstrap-fixture",
        },
        headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
    )
    assert bootstrap.status_code == 200, bootstrap.text
    organization_id = bootstrap.json()["organization_id"]
    async with sessionmaker() as db:
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
                name="Planned Setup",
                published_at=datetime.now(UTC),
                passport_document={"fixture": True},
                passport_digest=DIGEST,
                trust_lane="experimental",
            )
        )
        await db.commit()
    base = f"/v1/corporate/organizations/{organization_id}/catalog-assignments"
    context = (
        await client.get(f"/v1/corporate/organizations/{organization_id}/context", headers=auth)
    ).json()
    source = await client.put(
        base,
        headers=auth,
        json={
            "subject_kind": "organization",
            "subject_id": organization_id,
            "object_kind": "setup",
            "stable_id": setup_id,
            "version": "1.0",
            "expected_revision": 0,
            "authorization_revision": context["organization"]["authorization_revision"],
            "idempotency_key": "plan-source-fixture",
        },
    )
    assert source.status_code == 200, source.text
    plan_url = f"{base}/plan"

    async def plan(body: dict[str, object], headers: dict[str, str] = auth):
        return await client.post(
            plan_url,
            headers=headers,
            json={"account_id": account_id, "harness": "claude-code", **body},
        )

    missing = await plan({})
    assert missing.status_code == 200, missing.text
    payload = missing.json()
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["stable_id"] == setup_id
    assert item["outcome"] == "missing"
    assert item["action"] == "install"
    assert item["source_scope"] == "organization"
    assert item["version"] == "1.0"
    assert item["passport_digest"] == DIGEST
    assert item["installed_version"] is None

    installed = await plan(
        {
            "materialized": [
                {
                    "object_kind": "setup",
                    "stable_id": setup_id,
                    "version": "1.0",
                    "passport_digest": DIGEST,
                },
                {
                    "object_kind": "component",
                    "stable_id": new_id("component"),
                    "version": "2.0",
                },
            ]
        }
    )
    assert installed.status_code == 200, installed.text
    by_line = {(i["object_kind"], i["stable_id"]): i for i in installed.json()["items"]}
    current = by_line[("setup", setup_id)]
    assert current["outcome"] == "installed"
    assert current["action"] == "none"
    assert current["installed_version"] == "1.0"
    foreign = next(i for i in installed.json()["items"] if i["outcome"] == "unassigned")
    assert foreign["action"] == "remove"
    assert foreign["installed_version"] == "2.0"

    outdated = await plan(
        {"materialized": [{"object_kind": "setup", "stable_id": setup_id, "version": "0.9"}]}
    )
    assert outdated.status_code == 200, outdated.text
    stale = outdated.json()["items"][0]
    assert stale["outcome"] == "outdated"
    assert stale["action"] == "update"
    assert stale["installed_version"] == "0.9"

    denied = await plan({}, headers=outsider_auth)
    assert denied.status_code == 403, denied.text

    repeated = await plan({})
    assert repeated.status_code == 200, repeated.text
    assert repeated.json() == missing.json()
    async with sessionmaker() as db:
        assignments = await db.scalar(
            select(func.count())
            .select_from(CorporateCatalogAssignment)
            .where(CorporateCatalogAssignment.organization_id == organization_id)
        )
        distributions = await db.scalar(
            select(func.count())
            .select_from(CorporateAssignmentDistribution)
            .where(CorporateAssignmentDistribution.organization_id == organization_id)
        )
    assert assignments == 1
    assert distributions == 0
