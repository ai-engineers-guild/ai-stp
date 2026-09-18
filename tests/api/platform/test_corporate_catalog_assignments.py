"""Persist and replay exact assignments through the authenticated HTTP boundary."""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.session import issue_session
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, CatalogMetadata
from ai_stp_platform.organization_models import Organization, OrganizationMembership
from ai_stp_platform.technology_models import (
    Technology,
    TechnologyCategory,
    TechnologyClassification,
)

pytestmark = pytest.mark.platform


async def test_exact_catalog_assignment_http(
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
            "organization_name": "Assignments acceptance",
            "superadmin_account_id": account_id,
            "idempotency_key": "assignment-bootstrap-fixture",
        },
        headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
    )
    assert bootstrap.status_code == 200, bootstrap.text
    organization_id = bootstrap.json()["organization_id"]
    technology_id = new_id("technology")
    category_id = new_id("category")
    async with sessionmaker() as db:
        db.add(
            TechnologyCategory(
                organization_id=organization_id,
                id=category_id,
                name="Language",
                normalized_name="language",
                provenance="manual",
            )
        )
        db.add(
            Technology(
                organization_id=organization_id,
                id=technology_id,
                name="Swift",
                provenance="manual",
                lifecycle="active",
            )
        )
        await db.flush()
        db.add(
            TechnologyClassification(
                organization_id=organization_id,
                technology_id=technology_id,
                category_id=category_id,
            )
        )
        await db.commit()
    competence_path = f"/v1/corporate/organizations/{organization_id}/employee-technologies"
    competence_payload = {
        "account_id": account_id,
        "technology_id": technology_id,
        "expected_revision": 0,
        "authorization_revision": 1,
        "idempotency_key": "competence-http-fixture",
    }
    competence = await client.put(competence_path, json=competence_payload, headers=auth)
    assert competence.status_code == 200, competence.text
    replayed = await client.put(competence_path, json=competence_payload, headers=auth)
    assert replayed.json() == competence.json()
    stale_competence = await client.put(
        competence_path,
        json={**competence_payload, "idempotency_key": "competence-stale-fixture"},
        headers=auth,
    )
    assert stale_competence.status_code == 412, stale_competence.text
    retired = await client.put(
        competence_path,
        json={
            **competence_payload,
            "state": "retired",
            "expected_revision": 1,
            "idempotency_key": "competence-retire-fixture",
        },
        headers=auth,
    )
    assert retired.status_code == 200, retired.text
    restored = await client.put(
        competence_path,
        json={
            **competence_payload,
            "expected_revision": 2,
            "idempotency_key": "competence-restore-fixture",
        },
        headers=auth,
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["relation_id"] == competence.json()["relation_id"]
    assert restored.json()["revision"] == 3
    other_id = new_id("organization")
    async with sessionmaker() as db:
        db.add(Organization(id=other_id, kind="corporate", display_name="Other organization"))
        await db.flush()
        db.add(
            OrganizationMembership(
                organization_id=other_id,
                account_id=account_id,
                role="staff",
                display_name="Other organization name",
            )
        )
        await db.commit()
    profile_path = f"/v1/corporate/organizations/{organization_id}/members/{account_id}/profile"
    profile_payload = {
        "display_name": "Mobile lead",
        "expected_revision": 1,
        "authorization_revision": 1,
        "idempotency_key": "member-profile-fixture",
    }
    profile = await client.patch(profile_path, json=profile_payload, headers=auth)
    assert profile.status_code == 200, profile.text
    assert profile.json()["display_name"] == "Mobile lead"
    assert profile.json()["role"] == "superadmin"
    assert profile.json()["revision"] == 2
    profile_replay = await client.patch(profile_path, json=profile_payload, headers=auth)
    assert profile_replay.status_code == 200, profile_replay.text
    assert profile_replay.json() == profile.json()
    profile_stale = await client.patch(
        profile_path,
        json={
            **profile_payload,
            "display_name": "Changed",
            "idempotency_key": "member-profile-stale-fixture",
        },
        headers=auth,
    )
    assert profile_stale.status_code == 412, profile_stale.text
    context_before = await client.get(
        f"/v1/corporate/organizations/{organization_id}/context", headers=auth
    )
    assert context_before.json()["organization"]["authorization_revision"] == 1
    current_member = await client.get(
        f"/v1/corporate/organizations/{organization_id}/members/{account_id}", headers=auth
    )
    assert current_member.json()["display_name"] == "Mobile lead"
    async with sessionmaker() as db:
        other_member = await db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == other_id,
                OrganizationMembership.account_id == account_id,
            )
        )
        assert other_member is not None
        assert other_member.display_name == "Other organization name"
        global_account = await db.get(Account, account_id)
        assert global_account is not None
        assert global_account.display_name is None
    async with sessionmaker() as db:
        db.add(
            CatalogMetadata(
                owner_account_id=account_id,
                organization_id=organization_id,
                object_kind="setup",
                stable_id=setup_id,
                version="1.0",
                current_revision_id="revision-fixture",
                visibility="private",
                lifecycle_state="active",
                name="Mobile Development",
                published_at=datetime.now(UTC),
                passport_document={"fixture": True},
                passport_digest="sha256:" + "0" * 64,
                trust_lane="experimental",
            )
        )
        await db.commit()
    base = f"/v1/corporate/organizations/{organization_id}/catalog-assignments"
    payload = {
        "subject_kind": "employee",
        "subject_id": account_id,
        "object_kind": "setup",
        "stable_id": setup_id,
        "version": "1.0",
        "expected_revision": 0,
        "authorization_revision": 1,
        "idempotency_key": "assignment-write-fixture",
    }
    write = await client.put(base, json=payload, headers=auth)
    assert write.status_code == 200, write.text
    replay = await client.put(base, json=payload, headers=auth)
    assert replay.status_code == 200, replay.text
    assert replay.json() == write.json()
    listed = await client.get(
        base, params={"subject_kind": "employee", "subject_id": account_id}, headers=auth
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"][0]["display_name"] == "Mobile Development"
    stale = await client.put(
        base,
        json={
            **payload,
            "state": "retired",
            "expected_revision": 2,
            "idempotency_key": "assignment-stale-fixture",
        },
        headers=auth,
    )
    assert stale.status_code == 412, stale.text
    remove = await client.put(
        base,
        json={
            **payload,
            "state": "retired",
            "expected_revision": 1,
            "idempotency_key": "assignment-retire-fixture",
        },
        headers=auth,
    )
    assert remove.status_code == 200, remove.text
    listed = await client.get(
        base, params={"subject_kind": "employee", "subject_id": account_id}, headers=auth
    )
    assert listed.json()["items"] == []
    history = await client.get(
        base,
        params={"subject_kind": "employee", "subject_id": account_id, "include_retired": "true"},
        headers=auth,
    )
    assert history.status_code == 200, history.text
    assert history.json()["items"][0]["state"] == "retired"
    assert history.json()["items"][0]["revision"] == 2
    restored = await client.put(
        base,
        json={**payload, "expected_revision": 2, "idempotency_key": "assignment-restore-fixture"},
        headers=auth,
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["assignment_id"] == write.json()["assignment_id"]
    assert restored.json()["revision"] == 3
    assert restored.json()["state"] == "current"
    organization_base = f"/v1/corporate/organizations/{organization_id}"
    team = await client.post(
        f"{organization_base}/teams",
        headers=auth,
        json={
            "name": "Mobile",
            "authorization_revision": 1,
            "idempotency_key": "assignment-team-fixture",
        },
    )
    assert team.status_code == 200, team.text
    team_id = team.json()["team_id"]
    assert team_id.startswith("operation_")
    context = (await client.get(f"{organization_base}/context", headers=auth)).json()
    member = await client.post(
        f"{organization_base}/membership-assignments",
        headers=auth,
        json={
            "account_id": account_id,
            "team_id": team_id,
            "team_role": "lead",
            "authorization_revision": context["organization"]["authorization_revision"],
            "idempotency_key": "assignment-team-lead-fixture",
        },
    )
    assert member.status_code == 200, member.text
    context = (await client.get(f"{organization_base}/context", headers=auth)).json()
    assigned = await client.put(
        base,
        headers=auth,
        json={
            **payload,
            "subject_kind": "team",
            "subject_id": team_id,
            "authorization_revision": context["organization"]["authorization_revision"],
            "idempotency_key": "assignment-team-setup-fixture",
        },
    )
    assert assigned.status_code == 200, assigned.text
    derived = await client.get(
        base, params={"subject_kind": "employee", "subject_id": account_id}, headers=auth
    )
    assert derived.status_code == 200, derived.text
    assert any(item["source_team_id"] == team_id for item in derived.json()["items"])
    team_view = await client.get(f"{organization_base}/teams/{team_id}", headers=auth)
    assert team_view.status_code == 200, team_view.text
    effective = team_view.json()["effective_assignments"]
    assert any(
        item["subject_id"] == account_id and item["source_team_id"] is None for item in effective
    )
    assert any(
        item["subject_id"] == account_id and item["source_team_id"] == team_id for item in effective
    )
    context = (await client.get(f"{organization_base}/context", headers=auth)).json()
    governance = f"{organization_base}/catalog-governance"
    maintainer_payload = {
        "object_kind": "setup",
        "stable_id": setup_id,
        "version": "1.0",
        "subject_kind": "employee",
        "subject_id": account_id,
        "state": "current",
        "expected_revision": 0,
        "authorization_revision": context["organization"]["authorization_revision"],
        "reason": "acceptance maintainer",
        "idempotency_key": "governance-maintainer-fixture",
    }
    maintainer = await client.put(
        f"{governance}/maintainers", json=maintainer_payload, headers=auth
    )
    assert maintainer.status_code == 200, maintainer.text
    assert (
        await client.put(f"{governance}/maintainers", json=maintainer_payload, headers=auth)
    ).json() == maintainer.json()
    verification = await client.put(
        f"{governance}/verification",
        json={
            "object_kind": "setup",
            "stable_id": setup_id,
            "version": "1.0",
            "state": "verified",
            "expected_revision": 0,
            "authorization_revision": context["organization"]["authorization_revision"],
            "reason": "acceptance verification",
            "idempotency_key": "governance-verification-fixture",
        },
        headers=auth,
    )
    assert verification.status_code == 200, verification.text
    lifecycle = await client.put(
        f"{governance}/lifecycle",
        json={
            "object_kind": "setup",
            "stable_id": setup_id,
            "version": "1.0",
            "state": "visible",
            "expected_revision": 0,
            "authorization_revision": context["organization"]["authorization_revision"],
            "reason": "acceptance visibility",
            "idempotency_key": "governance-lifecycle-visible-fixture",
        },
        headers=auth,
    )
    assert lifecycle.status_code == 200, lifecycle.text
    hidden = await client.put(
        f"{governance}/lifecycle",
        json={
            "object_kind": "setup",
            "stable_id": setup_id,
            "version": "1.0",
            "state": "hidden",
            "expected_revision": 1,
            "authorization_revision": context["organization"]["authorization_revision"],
            "reason": "acceptance moderation",
            "idempotency_key": "governance-lifecycle-hidden-fixture",
        },
        headers=auth,
    )
    assert hidden.status_code == 200, hidden.text
    consolidated = await client.get(
        f"{governance}/setup/{setup_id}/versions/1.0",
        params={"include_history": "true"},
        headers=auth,
    )
    assert consolidated.status_code == 200, consolidated.text
    assert consolidated.json()["maintainers"][0]["subject_id"] == account_id
    assert consolidated.json()["verification"]["state"] == "verified"
    assert consolidated.json()["lifecycle"]["state"] == "hidden"
    assert any(
        item["action"] == "catalog_lifecycle.write" for item in consolidated.json()["history"]
    )
    restored_lifecycle = await client.put(
        f"{governance}/lifecycle",
        json={
            "object_kind": "setup",
            "stable_id": setup_id,
            "version": "1.0",
            "state": "visible",
            "expected_revision": 2,
            "authorization_revision": context["organization"]["authorization_revision"],
            "reason": "acceptance restore",
            "idempotency_key": "governance-lifecycle-restore-fixture",
        },
        headers=auth,
    )
    assert restored_lifecycle.status_code == 200, restored_lifecycle.text
    retired_team = await client.put(
        base,
        headers=auth,
        json={
            **payload,
            "subject_kind": "team",
            "subject_id": team_id,
            "state": "retired",
            "expected_revision": 1,
            "authorization_revision": context["organization"]["authorization_revision"],
            "idempotency_key": "assignment-team-retire-fixture",
        },
    )
    assert retired_team.status_code == 200, retired_team.text
    employee_history = await client.get(
        base,
        params={"subject_kind": "employee", "subject_id": account_id, "include_retired": "true"},
        headers=auth,
    )
    assert employee_history.status_code == 200, employee_history.text
    assert all(item["source_team_id"] is None for item in employee_history.json()["items"])
