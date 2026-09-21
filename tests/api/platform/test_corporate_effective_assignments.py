"""Effective assignment resolution through the authenticated HTTP boundary."""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.session import issue_session
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, CatalogMetadata
from ai_stp_platform.organization_models import OrganizationMembership
from ai_stp_platform.technology_models import Technology

pytestmark = pytest.mark.platform

DIGEST_ONE = "sha256:" + "1" * 64
DIGEST_TWO = "sha256:" + "2" * 64


async def test_effective_catalog_assignment_http(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    client, sessionmaker, _ = db_api_client
    account_id = new_id("account")
    setup_id = new_id("setup")
    async with sessionmaker() as db:
        db.add(Account(id=account_id, status="active"))
        await db.flush()
        session = await issue_session(db, account_id=account_id, device_id=None, ttl_seconds=3600)
        await db.commit()
    auth = {"Authorization": f"Bearer {session.raw_token}"}
    bootstrap = await client.post(
        "/v1/corporate/bootstrap",
        json={
            "organization_name": "Effective acceptance",
            "superadmin_account_id": account_id,
            "idempotency_key": "effective-bootstrap-fixture",
        },
        headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
    )
    assert bootstrap.status_code == 200, bootstrap.text
    organization_id = bootstrap.json()["organization_id"]
    async with sessionmaker() as db:
        for version, digest in (("1.0", DIGEST_ONE), ("2.0", DIGEST_TWO)):
            db.add(
                CatalogMetadata(
                    owner_account_id=account_id,
                    organization_id=organization_id,
                    object_kind="setup",
                    stable_id=setup_id,
                    version=version,
                    current_revision_id=f"revision-{version}",
                    visibility="private",
                    lifecycle_state="active",
                    name="Effective Setup",
                    published_at=datetime.now(UTC),
                    passport_document={"fixture": True},
                    passport_digest=digest,
                    trust_lane="experimental",
                )
            )
        technology_id = new_id("technology")
        db.add(
            Technology(
                organization_id=organization_id,
                id=technology_id,
                name="Swift",
                provenance="manual",
                lifecycle="active",
            )
        )
        await db.commit()
    organization_base = f"/v1/corporate/organizations/{organization_id}"
    base = f"{organization_base}/catalog-assignments"
    effective_url = f"{base}/effective"
    effective_params = {
        "account_id": account_id,
        "object_kind": "setup",
        "stable_id": setup_id,
    }
    payload = {
        "object_kind": "setup",
        "stable_id": setup_id,
        "expected_revision": 0,
        "authorization_revision": 1,
    }
    # Organization scope accepts the `latest` selector without pinning a version.
    org_write = await client.put(
        base,
        headers=auth,
        json={
            **payload,
            "subject_kind": "organization",
            "subject_id": organization_id,
            "selector": "latest",
            "idempotency_key": "effective-org-latest-fixture",
        },
    )
    assert org_write.status_code == 200, org_write.text
    assert org_write.json()["selector"] == "latest"
    assert org_write.json()["version"] is None
    replay = await client.put(
        base,
        headers=auth,
        json={
            **payload,
            "subject_kind": "organization",
            "subject_id": organization_id,
            "selector": "latest",
            "idempotency_key": "effective-org-latest-fixture",
        },
    )
    assert replay.json() == org_write.json()
    # A foreign organization id is never accepted as the organization subject.
    foreign = await client.put(
        base,
        headers=auth,
        json={
            **payload,
            "subject_kind": "organization",
            "subject_id": new_id("organization"),
            "selector": "latest",
            "idempotency_key": "effective-org-foreign-fixture",
        },
    )
    assert foreign.status_code in {403, 404}, foreign.text
    team = await client.post(
        f"{organization_base}/teams",
        headers=auth,
        json={
            "name": "Effective",
            "authorization_revision": 1,
            "idempotency_key": "effective-team-fixture",
        },
    )
    assert team.status_code == 200, team.text
    team_id = team.json()["team_id"]
    context = (await client.get(f"{organization_base}/context", headers=auth)).json()
    member = await client.post(
        f"{organization_base}/membership-assignments",
        headers=auth,
        json={
            "account_id": account_id,
            "team_id": team_id,
            "team_role": "staff",
            "authorization_revision": context["organization"]["authorization_revision"],
            "idempotency_key": "effective-member-fixture",
        },
    )
    assert member.status_code == 200, member.text
    context = (await client.get(f"{organization_base}/context", headers=auth)).json()
    team_write = await client.put(
        base,
        headers=auth,
        json={
            **payload,
            "subject_kind": "team",
            "subject_id": team_id,
            "version": "1.0",
            "authorization_revision": context["organization"]["authorization_revision"],
            "idempotency_key": "effective-team-exact-fixture",
        },
    )
    assert team_write.status_code == 200, team_write.text
    # Team outranks organization; the exact pin resolves to its own coordinate.
    effective = await client.get(effective_url, params=effective_params, headers=auth)
    assert effective.status_code == 200, effective.text
    body = effective.json()
    assert body["state"] == "assigned"
    assert body["source_scope"] == "team"
    assert body["source_subject_id"] == team_id
    assert body["version"] == "1.0"
    assert body["passport_digest"] == DIGEST_ONE
    # A technology-scoped row applies only when the evaluation names it.
    technology_write = await client.put(
        base,
        headers=auth,
        json={
            **payload,
            "subject_kind": "technology",
            "subject_id": technology_id,
            "version": "1.0",
            "authorization_revision": context["organization"]["authorization_revision"],
            "idempotency_key": "effective-technology-exact-fixture",
        },
    )
    assert technology_write.status_code == 200, technology_write.text
    effective = await client.get(
        effective_url,
        params={**effective_params, "technology_id": technology_id},
        headers=auth,
    )
    assert effective.json()["source_scope"] == "technology"
    # An employee `latest` decision outranks every inherited assignment and
    # resolves to the newest eligible coordinate with its digest.
    employee_write = await client.put(
        base,
        headers=auth,
        json={
            **payload,
            "subject_kind": "employee",
            "subject_id": account_id,
            "selector": "latest",
            "authorization_revision": context["organization"]["authorization_revision"],
            "idempotency_key": "effective-employee-latest-fixture",
        },
    )
    assert employee_write.status_code == 200, employee_write.text
    effective = await client.get(effective_url, params=effective_params, headers=auth)
    body = effective.json()
    assert body["source_scope"] == "employee"
    assert body["selector"] == "latest"
    assert body["version"] == "2.0"
    assert body["passport_digest"] == DIGEST_TWO
    outcomes = {item["scope"]: item["outcome"] for item in body["candidates"]}
    assert outcomes["employee"] == "winner"
    assert outcomes["team"] == "overridden"
    assert outcomes["organization"] == "overridden"
    # Retiring the employee decision is an explicit revocation: it beats every
    # inherited assignment instead of silently falling through.
    retired = await client.put(
        base,
        headers=auth,
        json={
            **payload,
            "subject_kind": "employee",
            "subject_id": account_id,
            "selector": "latest",
            "state": "retired",
            "expected_revision": 1,
            "authorization_revision": context["organization"]["authorization_revision"],
            "idempotency_key": "effective-employee-revoke-fixture",
        },
    )
    assert retired.status_code == 200, retired.text
    effective = await client.get(effective_url, params=effective_params, headers=auth)
    assert effective.json()["state"] == "revoked"
    # A harness-conditioned assignment applies only when the harness matches.
    harness_write = await client.put(
        base,
        headers=auth,
        json={
            **payload,
            "subject_kind": "team",
            "subject_id": team_id,
            "version": "2.0",
            "harness": "claude-code",
            "authorization_revision": context["organization"]["authorization_revision"],
            "idempotency_key": "effective-team-harness-fixture",
        },
    )
    assert harness_write.status_code == 200, harness_write.text
    effective = await client.get(
        effective_url, params={**effective_params, "harness": "claude-code"}, headers=auth
    )
    assert effective.json()["state"] == "revoked"
    # A staff member cannot write or explain outside their authority.
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
    denied_write = await client.put(
        base,
        headers=staff_auth,
        json={
            **payload,
            "subject_kind": "organization",
            "subject_id": organization_id,
            "selector": "latest",
            "idempotency_key": "effective-staff-denied-fixture",
        },
    )
    assert denied_write.status_code == 403, denied_write.text
    denied_explain = await client.get(
        effective_url,
        params={**effective_params, "account_id": staff_id},
        headers=staff_auth,
    )
    assert denied_explain.status_code == 403, denied_explain.text
