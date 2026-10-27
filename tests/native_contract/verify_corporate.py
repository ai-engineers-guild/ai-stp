"""Native enrollment and company reads against disposable PostgreSQL and real HTTP.

Only the browser approval step is supplied by the fixture, for synthetic accounts.
The native binary performs discovery, start/poll, key binding and every company
request itself. No live SSO identity, provider process or harness files are used.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import sqlite3
import sys
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import uvicorn
from alembic import command
from alembic.config import Config
from httpx import AsyncClient
from sqlalchemy import func, select
from tests.native_contract import verify_checkout
from tests.native_contract.verify_ownership import apply, native
from tests.support.api_settings import make_settings, make_test_auth
from tests.support.catalog_seed import FIXTURE_SETUP_ID, load_fixture_seed
from tests.support.postgres import isolated_database

from ai_stp_api.app import create_app
from ai_stp_api.session import issue_session
from ai_stp_api.slices.auth.device_flow import approve_device_authorization
from ai_stp_api.slices.devices.crypto import normalize_public_key
from ai_stp_contracts.technology import normalize_technology_name
from ai_stp_foundation.envelope import ErrorEnvelope
from ai_stp_foundation.ids import new_id
from ai_stp_platform.catalog_search import upsert_catalog_search_projection
from ai_stp_platform.models import Account, AuditEvent, CatalogMetadata, Device
from ai_stp_platform.organization_models import (
    CorporateAssignmentDistribution,
    CorporateProject,
    CorporateProjectMember,
    CorporateRole,
    CorporateRoleBinding,
    CorporateRolePermission,
    CorporateTeam,
    CorporateTeamMember,
    Organization,
    OrganizationMembership,
    ProjectIdentity,
    ProjectLink,
    ProjectLinkPlan,
    ProjectUnlinkPlan,
)
from ai_stp_platform.technology_models import Technology, TechnologyAlias


async def refused(binary: Path, home: Path, arguments: list[str]) -> ErrorEnvelope:
    process = await asyncio.create_subprocess_exec(
        str(binary),
        *arguments,
        "--json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=dict(os.environ, HOME=str(home), XDG_DATA_HOME=str(home), XDG_CONFIG_HOME=str(home)),
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise
    assert process.returncode != 0 and not stderr
    return ErrorEnvelope.model_validate_json(stdout)


async def journeys(binary: Path, root: Path, app: Any, origin: str) -> None:
    home, state = root / "consumer", root / "state"
    home.mkdir()
    state.mkdir()
    scoped = ["--state-dir", str(state)]

    async def run(*arguments: str) -> dict[str, Any]:
        return await native(binary, home, [*arguments, *scoped])

    async def enact(planned: dict[str, Any], *prefix: str) -> dict[str, Any]:
        result = await apply(binary, home, planned, list(prefix))
        assert await apply(binary, home, planned, list(prefix)) == result
        return result

    initialization = await run("device", "initialize", "plan", "--credential-store", "file")
    await enact(initialization, "device", "initialize", "apply")
    original = await run("device", "show")
    offline = await run("context", "create", "plan", "--label", "Offline personal")
    await enact(offline, "context", "apply")

    accounts = [new_id("account"), new_id("account")]
    async with app.state.sessionmaker() as db:
        db.add_all([Account(id=account) for account in accounts])
        await db.flush()
        fixture_session = await issue_session(
            db, account_id=accounts[0], device_id=None, ttl_seconds=3600
        )
        await load_fixture_seed(db)
        await db.commit()
    async with AsyncClient(base_url=origin, timeout=15, trust_env=False) as client:
        response = await client.post(
            "/v1/corporate/bootstrap",
            json={
                "organization_name": "Native interop fixture",
                "superadmin_account_id": accounts[0],
                "idempotency_key": "native-corporate-bootstrap",
            },
            headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
        )
        assert response.status_code == 200, response.text

        organization = response.json()["organization_id"]
        second_organization, second_team = new_id("organization"), new_id("operation")
        auth = {"Authorization": f"Bearer {fixture_session.raw_token}"}
        project, team, technology = (
            new_id("remote_project"),
            new_id("operation"),
            new_id("technology"),
        )
        unjoined_project = new_id("remote_project")
        project_rows = [
            (project, "Native shared project"),
            (unjoined_project, "Visible nonmember project"),
        ]
        async with app.state.sessionmaker() as db:
            # Bootstrap is intentionally closed after its first tenant. Seed a
            # second isolated tenant to exercise the existing multi-membership
            # model; no production bootstrap or account-linking rule changes.
            db.add(
                Organization(
                    id=second_organization,
                    kind="corporate",
                    owner_account_id=None,
                    display_name="Second native fixture company",
                    state="active",
                    policy_revision=1,
                )
            )
            await db.flush()
            db.add(CorporateRole(organization_id=second_organization, name="staff"))
            db.add(
                OrganizationMembership(
                    organization_id=second_organization, account_id=accounts[0], role="staff"
                )
            )
            db.add(
                CorporateTeam(
                    id=second_team, organization_id=second_organization, name="Second native team"
                )
            )
            await db.flush()
            permissions = list(
                await db.scalars(
                    select(CorporateRolePermission.permission).where(
                        CorporateRolePermission.organization_id == organization,
                        CorporateRolePermission.role == "staff",
                    )
                )
            )
            assert permissions
            db.add_all(
                CorporateRolePermission(
                    organization_id=second_organization, role="staff", permission=permission
                )
                for permission in permissions
            )
            db.add(
                CorporateRoleBinding(
                    id=new_id("operation"),
                    organization_id=second_organization,
                    account_id=accounts[0],
                    role="staff",
                    scope_kind="organization",
                    scope_id=second_organization,
                    origin="membership",
                    coverage="descendants",
                )
            )
            db.add(
                CorporateTeamMember(
                    organization_id=second_organization, team_id=second_team, account_id=accounts[0]
                )
            )
            db.add(
                OrganizationMembership(
                    organization_id=organization, account_id=accounts[1], role="staff"
                )
            )
            await db.flush()
            db.add(
                CorporateRoleBinding(
                    id=new_id("operation"),
                    organization_id=organization,
                    account_id=accounts[1],
                    role="staff",
                    scope_kind="organization",
                    scope_id=organization,
                    origin="membership",
                )
            )
            for project_id, name in project_rows:
                db.add(
                    ProjectIdentity(
                        id=project_id,
                        organization_id=organization,
                        namespace="remote",
                        external_key=f"native:{project_id}",
                        display_name=name,
                    )
                )
            await db.flush()
            for project_id, name in project_rows:
                db.add(CorporateProject(id=project_id, organization_id=organization, name=name))
            db.add(CorporateTeam(id=team, organization_id=organization, name="Native team"))
            db.add(
                Technology(
                    id=technology,
                    organization_id=organization,
                    name="Native technology",
                    provenance="manual",
                    lifecycle="active",
                )
            )
            await db.flush()
            db.add(
                TechnologyAlias(
                    organization_id=organization,
                    technology_id=technology,
                    name="Native technology",
                    normalized_name=normalize_technology_name("Native technology"),
                    canonical=True,
                )
            )
            db.add(
                CorporateProjectMember(
                    organization_id=organization,
                    project_id=project,
                    account_id=accounts[0],
                    role="owner",
                )
            )
            db.add(
                CorporateTeamMember(
                    organization_id=organization, team_id=team, account_id=accounts[0]
                )
            )
            setup = await db.scalar(
                select(CatalogMetadata).where(
                    CatalogMetadata.stable_id == FIXTURE_SETUP_ID, CatalogMetadata.version == "1.0"
                )
            )
            assert setup is not None
            setup.organization_id, setup.owner_account_id, setup.visibility = (
                organization,
                accounts[0],
                "private",
            )
            setup_digest = setup.passport_digest
            await db.flush()
            await upsert_catalog_search_projection(
                db, object_kind="setup", stable_id=FIXTURE_SETUP_ID
            )
            await db.commit()
        response = await client.put(
            f"/v1/corporate/organizations/{organization}/catalog-assignments",
            headers=auth,
            json={
                "subject_kind": "organization",
                "subject_id": organization,
                "object_kind": "setup",
                "stable_id": FIXTURE_SETUP_ID,
                "version": "1.0",
                "harness": "claude-code",
                "expected_revision": 0,
                "authorization_revision": 1,
                "idempotency_key": "native-corporate-assignment",
            },
        )
        assert response.status_code == 200, response.text

        response = await client.put(
            f"/v1/corporate/organizations/{organization}/technology-mappings/native-fixture-v1",
            headers=auth,
            json={
                "authorization_revision": 1,
                "idempotency_key": "native-corporate-mapping",
                "entries": [
                    {
                        "kind": "package",
                        "coordinate": "npm:native-fixture",
                        "technology_id": technology,
                        "provenance": "fixture/native",
                    }
                ],
            },
        )
        assert response.status_code == 200, response.text

    async def login(account: str, connection: str | None, *, authorized: bool = True) -> None:
        qualifier = ["--connection", connection] if connection else []
        start = await run(
            "account",
            "plan",
            "--action",
            "start",
            "--api-url",
            origin,
            "--provider",
            "github",
            *qualifier,
        )
        await enact(start, "account", "apply")
        status = await run("account", "status", *qualifier)
        pending = status["session"]
        assert pending["state"] == "pending"
        async with app.state.sessionmaker() as db:
            await approve_device_authorization(
                db, user_code=pending["user_code"], account_id=account
            )
            await db.commit()
        next_poll = datetime.fromisoformat(pending["next_poll_at"].replace("Z", "+00:00"))
        delay = (next_poll - datetime.now(UTC)).total_seconds()
        assert delay < 10
        await asyncio.sleep(max(0, delay) + 0.02)
        poll = await run("account", "plan", "--action", "poll", *qualifier)
        receipt = await enact(poll, "account", "apply")
        if authorized:
            assert receipt["outcome"] == "authorized" and receipt["account_id"] == account
        else:
            assert receipt["outcome"] != "authorized" and receipt["account_id"] is None

    connections: list[dict[str, Any]] = []
    contexts: list[str] = []
    for index, account in enumerate(accounts):
        planned = await run(
            "account",
            "connections",
            "plan",
            "--label",
            f"Fixture {index}",
            "--api-url",
            origin,
            "--provider",
            "github",
        )
        connected = (await enact(planned, "account", "connections", "apply"))["connection"]
        connections.append(connected)
        await login(account, connected["connection_id"])
        organizations = await run(
            "account", "organizations", "--connection", connected["connection_id"]
        )
        assert organization in {
            item["organization_id"] for item in organizations["organizations"]["items"]
        }
        context = await run(
            "context",
            "create",
            "plan",
            "--label",
            f"Company {index}",
            "--connection",
            connected["connection_id"],
            "--organization",
            organization,
        )
        await enact(context, "context", "apply")
        contexts.append(context["plan"]["change"]["context"]["context_id"])
    assert connections[0]["public_key"] != connections[1]["public_key"]
    assert connections[0]["device_id"] != connections[1]["device_id"]
    await login(accounts[0], None)
    legacy = await run(
        "context",
        "create",
        "plan",
        "--label",
        "Legacy company",
        "--legacy-account",
        "--organization",
        organization,
    )
    await enact(legacy, "context", "apply")
    personal = await run(
        "context",
        "create",
        "plan",
        "--label",
        "Signed-in personal",
        "--connection",
        connections[0]["connection_id"],
    )
    assert personal["plan"]["change"]["context"]["authority"]["organization"]["kind"] == "personal"
    await enact(personal, "context", "apply")
    retained_session = await run(
        "account", "status", "--connection", connections[0]["connection_id"]
    )
    second_company = await run(
        "context",
        "create",
        "plan",
        "--label",
        "Second company, same account",
        "--connection",
        connections[0]["connection_id"],
        "--organization",
        second_organization,
    )
    await enact(second_company, "context", "apply")
    second_context = second_company["plan"]["change"]["context"]["context_id"]
    shared_account = second_company["plan"]["change"]["context"]["authority"]["account"]
    assert shared_account["account_id"] == accounts[0]
    assert shared_account["connection"]["connection_id"] == connections[0]["connection_id"]
    views = [
        offline["plan"]["change"]["context"]["context_id"],
        personal["plan"]["change"]["context"]["context_id"],
        contexts[0],
        second_context,
    ]
    assert len(set(views)) == 4
    frozen_views = [await run("context", "show", "--context", view) for view in views]
    for view in views:
        await enact(await run("context", "select", "plan", "--context", view), "context", "apply")
        selected_view = await run("context", "list")
        assert selected_view["selected"]["context_id"] == view
        assert not selected_view["selection_changes_harness_files"]
    assert [await run("context", "show", "--context", view) for view in views] == frozen_views
    assert (
        await run("account", "status", "--connection", connections[0]["connection_id"])
        == retained_session
    )
    selected = await run("context", "select", "plan", "--context", contexts[1])
    await enact(selected, "context", "apply")
    checkout = root / "native-checkout"
    checkout.mkdir()
    git_executable = shutil.which("git")
    assert git_executable is not None

    async def git(*arguments: str) -> None:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
        }
        environment.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        process = await asyncio.create_subprocess_exec(
            git_executable,
            "-C",
            str(checkout),
            "-c",
            "user.name=Native checkout fixture",
            "-c",
            "user.email=checkout@example.invalid",
            *arguments,
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(process.communicate(), timeout=10)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise
        assert process.returncode == 0

    await git("init", "--initial-branch=main")
    await git("commit", "--allow-empty", "-m", "native checkout fixture")
    await git("config", "remote.origin.url", "https://native-checkout-secret@example.invalid/repo")
    passport = await run("project", "passport", "plan", "--root", str(checkout))
    await enact(passport, "local", "apply")
    local_passport = passport["plan"]["operation"]["passport"]
    snapshot = await run("context", "list")
    registry = state / "ai-stp-v2-state" / "registry.sqlite3"
    with closing(sqlite3.connect(f"file:{registry}?mode=ro", uri=True)) as local:
        before = local.execute("SELECT count(*) FROM operation").fetchone()

    async def observe(*arguments: str, context: str = contexts[0]) -> dict[str, Any]:
        result = await run("corporate", *arguments, "--context", context)
        observation = result["observation"]
        assert observation["context"]["context_id"] == context
        assert observation["organization"]["organization_id"] == organization
        assert observation["observation_only"] and not observation["installation_authority"]
        assert observation["materialized_inventory"] == "none"
        return observation["data"]

    async def observe_second_company() -> None:
        result = await run("corporate", "teams", "--context", second_context)
        observation = result["observation"]
        assert observation["organization"]["organization_id"] == second_organization
        assert observation["account"]["account_id"] == accounts[0]
        assert observation["account"]["device_id"] == connections[0]["device_id"]
        assert observation["context"]["context_id"] == second_context
        assert observation["observation_only"] and not observation["installation_authority"]
        assert {item["team_id"] for item in observation["data"]["items"]} == {second_team}
        assert team not in {item["team_id"] for item in observation["data"]["items"]}

    await observe_second_company()

    projects = await observe("projects", "--membership-only")
    assert [item["project_id"] for item in projects["items"]] == [project]
    assert {item["project_id"] for item in (await observe("projects"))["items"]} == {
        project,
        unjoined_project,
    }
    assert (await observe("project", "show", "--project", project))["project_id"] == project
    target = await observe("project", "link-target", "--project", project)
    assert target["remote_project_id"] == project and target["remote_revision"] == "initial"
    assert target["providers"] == [] and target["observation_only"] is True
    async with app.state.sessionmaker() as db:
        business_before = (
            await db.scalar(select(func.count()).select_from(ProjectLinkPlan)),
            await db.scalar(select(func.count()).select_from(ProjectLink)),
        )
    preview_args = [
        "corporate",
        "project",
        "link-preview",
        "--project",
        project,
        "--root",
        str(checkout),
        "--context",
        contexts[0],
        "--git-executable",
        git_executable,
    ]
    preview = (await run(*preview_args))["preview"]
    assert preview["context"]["context_id"] == contexts[0]
    assert preview["account"]["account_id"] == accounts[0]
    assert preview["local_project"]["local_project_id"] == local_passport["stable_id"]
    assert preview["local_project"]["owner_account_id"] == local_passport["owner_id"]
    assert preview["request_coordinates"]["local_revision"] == local_passport["revision_id"]
    assert preview["request_coordinates"]["remote_project_id"] == project
    assert preview["request_coordinates"]["provider_project_id"] is None
    assert preview["online_verified"] and preview["observation_only"]
    assert not any(
        preview[field]
        for field in (
            "link_created",
            "binding_created",
            "request_admitted",
            "installation_authority",
            "provider_identity_verified",
        )
    )
    assert "native-checkout-secret" not in json.dumps(preview)
    await refused(
        binary, home, [*preview_args, "--provider-project", new_id("provider_project"), *scoped]
    )
    await git("checkout", "--detach")
    await refused(binary, home, [*preview_args, *scoped])
    await git("checkout", "main")
    async with app.state.sessionmaker() as db:
        assert (
            await db.scalar(select(func.count()).select_from(ProjectLinkPlan)),
            await db.scalar(select(func.count()).select_from(ProjectLink)),
        ) == business_before
    async with app.state.sessionmaker() as db:
        link_session = await issue_session(
            db, account_id=accounts[0], device_id=connections[0]["device_id"], ttl_seconds=3600
        )
        await db.commit()
    link_headers = {
        "Authorization": f"Bearer {link_session.raw_token}",
        "X-AI-STP-Organization-Id": organization,
    }
    async with AsyncClient(base_url=origin, timeout=15, trust_env=False) as client:
        planned = await client.post(
            f"/v1/organizations/{organization}/project-link-plans",
            headers=link_headers,
            json={
                "local_project_id": new_id("project"),
                "remote_project_id": project,
                "local_revision": "native-outcome-fixture",
                "remote_revision": target["remote_revision"],
                "authorization_revision": target["authorization_revision"],
                "idempotency_key": "native-link-outcome-plan",
            },
        )
        assert planned.status_code == 201, planned.text
        link_plan = planned.json()
        ready = await observe("project", "link-outcome", "--plan-id", link_plan["plan_id"])
        assert ready["state"] == "ready" and ready["link"] is None
        assert ready["plan"] == link_plan and ready["observation_only"]
        request_outcome = await observe(
            "project", "link-request-outcome", "--request-key", "native-link-outcome-plan"
        )
        assert request_outcome["plan"] == link_plan and request_outcome["state"] == "ready"
        confirmed = await client.post(
            "/v1/projects/links",
            headers=link_headers,
            json={
                "plan_id": link_plan["plan_id"],
                "plan_digest": link_plan["plan_digest"],
                "authorization_revision": target["authorization_revision"],
                "idempotency_key": "native-link-outcome-confirm",
            },
        )
        assert confirmed.status_code == 201, confirmed.text
    applied = await observe("project", "link-outcome", "--plan-id", link_plan["plan_id"])
    assert applied["state"] == "applied" and applied["plan"] == link_plan
    assert applied["link"] == confirmed.json()
    request_outcome = await observe(
        "project", "link-request-outcome", "--request-key", "native-link-outcome-plan"
    )
    assert request_outcome["plan"] == link_plan and request_outcome["link"] == confirmed.json()

    # The fixture creates/confirms one unlink; every native command below is a
    # read. Observe counts around those reads rather than treating a fixture POST
    # as native mutation or active local-binding retirement acceptance.
    async def unlink_counts() -> tuple[int, ...]:
        async with app.state.sessionmaker() as db:
            counts: list[int] = []
            for model in (ProjectLinkPlan, ProjectLink, ProjectUnlinkPlan, AuditEvent):
                count = await db.scalar(select(func.count()).select_from(model))
                assert isinstance(count, int)
                counts.append(count)
            return tuple(counts)

    async with AsyncClient(base_url=origin, timeout=15, trust_env=False) as client:
        current_response = await client.get(
            f"/v1/projects/links/{confirmed.json()['link_id']}", headers=link_headers
        )
        assert current_response.status_code == 200, current_response.text
        assert current_response.headers["cache-control"] == "private, no-store"
        current_counts = await unlink_counts()
        current = await observe("project", "link-current", "--link-id", confirmed.json()["link_id"])
        assert current == confirmed.json() and current["state"] == "linked"
        assert await unlink_counts() == current_counts
        planned = await client.post(
            f"/v1/organizations/{organization}/project-unlink-plans",
            headers=link_headers,
            json={
                "link_id": confirmed.json()["link_id"],
                "expected_link_revision": confirmed.json()["revision"],
                "authorization_revision": target["authorization_revision"],
                "idempotency_key": "native-unlink-outcome-plan",
            },
        )
        assert planned.status_code == 201, planned.text
        unlink_plan = planned.json()
        readers = [
            ["unlink-outcome", "--plan-id", unlink_plan["plan_id"]],
            ["unlink-settlement", "--plan-id", unlink_plan["plan_id"]],
            ["unlink-request-outcome", "--request-key", "native-unlink-outcome-plan"],
        ]
        counts = await unlink_counts()
        for reader in readers:
            result = await observe("project", *reader)
            assert result["plan"] == unlink_plan and result["state"] == "ready"
            assert result["link"] is None and result["observation_only"]
        assert await unlink_counts() == counts
        async with app.state.sessionmaker() as db:
            audit_before = await db.scalar(select(func.max(AuditEvent.id))) or 0
        denial_readers = [
            *readers,
            ["link-current", "--link-id", confirmed.json()["link_id"]],
        ]
        for reader in denial_readers:
            await refused(
                binary,
                home,
                ["corporate", "project", *reader, "--context", contexts[1], *scoped],
            )
            await refused(
                binary,
                home,
                ["corporate", "project", *reader, "--context", second_context, *scoped],
            )
        missing_keys = ["native-unlink-missing-request", "n" * 128]
        for key in missing_keys:
            absent = await refused(
                binary,
                home,
                [
                    "corporate",
                    "project",
                    "unlink-request-outcome",
                    "--request-key",
                    key,
                    "--context",
                    contexts[0],
                    *scoped,
                ],
            )
            assert absent.error.code == "AI_STP_NOT_FOUND", absent.error.code
        after_refusals = await unlink_counts()
        assert after_refusals[:3] == counts[:3]
        async with app.state.sessionmaker() as db:
            audits = list(await db.scalars(select(AuditEvent).where(AuditEvent.id > audit_before)))
        # The global HTTP error handler deliberately audits rejected requests.
        # Successful observations stay audit-free; denials retain their own
        # security evidence without creating any project business rows.
        assert len(missing_keys) <= len(audits) <= 2 * len(denial_readers) + len(missing_keys)
        assert len(audits) == after_refusals[3] - counts[3]
        for audit in audits:
            assert audit.target_table == "http_route" and audit.actor_account_id in accounts
            assert audit.payload["method"] == "GET"
            assert (
                audit.action,
                audit.outcome,
                audit.reason,
                audit.payload["http_status"],
                audit.payload["error"],
            ) in {
                ("http.get.failed", "failed", "not_found", 404, "AI_STP_NOT_FOUND"),
                (
                    "http.get.denied",
                    "denied",
                    "capability_forbidden",
                    403,
                    "AI_STP_PERMISSION_DENIED",
                ),
            }
        for key in missing_keys:
            path = f"/v1/organizations/{organization}/project-unlink-plan-requests/{key}"
            audit_target = (
                path if len(path) <= 128 else f"sha256:{sha256(path.encode()).hexdigest()}"
            )
            assert (
                sum(
                    audit.actor_account_id == accounts[0]
                    and audit.organization_id == organization
                    and audit.target_id == audit_target
                    and audit.payload["error"] == "AI_STP_NOT_FOUND"
                    for audit in audits
                )
                == 1
            )
        unlinked = await client.request(
            "DELETE",
            f"/v1/projects/links/{confirmed.json()['link_id']}",
            headers=link_headers,
            json={
                "plan_id": unlink_plan["plan_id"],
                "plan_digest": unlink_plan["plan_digest"],
                "authorization_revision": target["authorization_revision"],
                "idempotency_key": "native-unlink-outcome-confirm",
            },
        )
        assert unlinked.status_code == 200, unlinked.text
        counts = await unlink_counts()
        current = await observe("project", "link-current", "--link-id", confirmed.json()["link_id"])
        assert current == unlinked.json() and current["state"] == "unlinked"
        for reader in readers:
            result = await observe("project", *reader)
            assert result["plan"] == unlink_plan and result["state"] == "applied"
            assert result["link"] == unlinked.json()
            assert result["link"]["revision"] == unlink_plan["expected_link_revision"] + 1
            assert result["link"]["state"] == "unlinked"
        assert await unlink_counts() == counts
    await refused(
        binary,
        home,
        [
            "corporate",
            "project",
            "link-outcome",
            "--plan-id",
            link_plan["plan_id"],
            "--context",
            contexts[1],
            *scoped,
        ],
    )
    await refused(
        binary,
        home,
        [
            "corporate",
            "project",
            "link-request-outcome",
            "--request-key",
            "native-link-outcome-plan",
            "--context",
            contexts[1],
            *scoped,
        ],
    )
    assert team in {item["team_id"] for item in (await observe("teams"))["items"]}
    assert technology in {
        item["technology_id"]
        for item in (await observe("technologies", "--query", "Native technology"))["items"]
    }
    mappings = await observe("mappings", "list")
    assert "native-fixture-v1" in {mapping["version"] for mapping in mappings["items"]}
    for mapping in mappings["items"]:
        assert (await observe("mappings", "show", "--version", mapping["version"]))[
            "digest"
        ] == mapping["digest"]
    catalog = await observe("catalog", "search", "--kind", "setup")
    # Corporate catalog filters project the public catalog. Authentication and
    # assignment do not put a private version into that index or promote the
    # unverified public seed into its default authoritative lane. The private
    # assigned coordinate is resolved separately by the preview below.
    assert not catalog["items"] and not catalog["experimental"]
    help_data = await native(binary, home, ["help", "--agent"])
    descriptor = next(
        item
        for item in help_data["commands"]
        if item["path"] == ["corporate", "assignments", "preview"]
    )
    harnesses = next(
        item["choices"] for item in descriptor["parameters"] if item["name"] == "harness"
    )
    assert len(harnesses) == 7 and len(set(harnesses)) == 7
    for harness in harnesses:
        preview = await observe(
            "assignments", "preview", "--harness", harness, "--project", project
        )
        item = next(item for item in preview["items"] if item["stable_id"] == FIXTURE_SETUP_ID)
        assert item["installed_version"] is None
        if harness == "claude-code":
            assert item["version"] == "1.0" and item["passport_digest"] == setup_digest
            assert item["action"] == "install" and item["source_scope"] == "organization"
        else:
            assert item["version"] is None and item["action"] == "none"

    # The native preview must retain the real resolver's authority order rather
    # than recomputing it from its local technology seed or the selected view.
    async with AsyncClient(base_url=origin, timeout=15, trust_env=False) as client:

        async def assign(
            scope: str,
            subject: str,
            *,
            harness: str | None = None,
            latest: bool = False,
            revision: int = 0,
            retired: bool = False,
        ) -> dict[str, Any]:
            context = await client.get(
                f"/v1/corporate/organizations/{organization}/context", headers=auth
            )
            assert context.status_code == 200, context.text
            authorization = context.json()["organization"]["authorization_revision"]
            body: dict[str, Any] = {
                "subject_kind": scope,
                "subject_id": subject,
                "object_kind": "setup",
                "stable_id": FIXTURE_SETUP_ID,
                "harness": harness,
                "expected_revision": revision,
                "authorization_revision": authorization,
                "state": "retired" if retired else "current",
                "idempotency_key": (f"native-precedence-{scope}-{harness or 'all'}-{revision}"),
                **({"selector": "latest"} if latest else {"version": "1.0"}),
            }
            response = await client.put(
                f"/v1/corporate/organizations/{organization}/catalog-assignments",
                headers=auth,
                json=body,
            )
            assert response.status_code == 200, response.text
            result: dict[str, Any] = response.json()
            replay = await client.put(
                f"/v1/corporate/organizations/{organization}/catalog-assignments",
                headers=auth,
                json=body,
            )
            assert replay.status_code == 200 and replay.json() == result
            return result

        async def decision(
            *, harness: str = "claude-code", scoped_technology: bool = True
        ) -> dict[str, Any]:
            extra = ["--technology", technology] if scoped_technology else []
            preview = await observe(
                "assignments", "preview", "--harness", harness, "--project", project, *extra
            )
            return next(item for item in preview["items"] if item["stable_id"] == FIXTURE_SETUP_ID)

        def assigned(item: dict[str, Any], row: dict[str, Any], scope: str) -> None:
            assert item["state"] == "assigned" and item["outcome"] == "missing"
            assert item["action"] == "install" and item["installed_version"] is None
            assert item["assignment_id"] == row["assignment_id"]
            assert item["source_scope"] == scope
            assert item["version"] == "1.0" and item["passport_digest"] == setup_digest

        organization_generic = await assign("organization", organization, latest=True)
        # A newer generic decision cannot override a harness-specific decision
        # within the same scope. Both still resolve to exact immutable bytes.
        organization_generic = await assign("organization", organization, latest=True, revision=1)
        specific = await decision()
        assert specific["source_scope"] == "organization" and specific["harness"] == "claude-code"
        assert specific["assignment_id"] != organization_generic["assignment_id"]
        assigned(await decision(harness="codex"), organization_generic, "organization")

        for scope, subject in (
            ("team", team),
            ("technology", technology),
            ("project", project),
            ("employee", accounts[0]),
        ):
            row = await assign(scope, subject, latest=scope == "employee")
            assigned(await decision(), row, scope)
            if scope == "technology":
                assert (await decision(scoped_technology=False))["source_scope"] == "team"

        employee_generic = await assign("employee", accounts[0], latest=True, revision=1)
        employee_specific = await assign("employee", accounts[0], harness="claude-code")
        specific = await decision()
        assigned(specific, employee_specific, "employee")
        assert specific["selector"] == "exact"
        generic = await decision(harness="codex")
        assigned(generic, employee_generic, "employee")
        assert generic["selector"] == "latest"
        assert [candidate["scope"] for candidate in specific["candidates"]] == [
            "employee",
            "employee",
            "project",
            "technology",
            "team",
            "organization",
            "organization",
        ]
        assert specific["candidates"][0]["outcome"] == "winner"
        assert all(candidate["outcome"] == "overridden" for candidate in specific["candidates"][1:])

        await assign("employee", accounts[0], harness="claude-code", revision=1, retired=True)
        revoked = await decision()
        assert revoked["state"] == revoked["outcome"] == "revoked"
        assert revoked["action"] == "none" and revoked["installed_version"] is None
        assert revoked["version"] is None and revoked["passport_digest"] is None
        assert revoked["assignment_id"] is None and revoked["source_scope"] is None
        assert revoked["candidates"][0]["assignment_id"] == employee_specific["assignment_id"]
        assert revoked["candidates"][0]["outcome"] == "revoked"
        assert not any(candidate["outcome"] == "winner" for candidate in revoked["candidates"])
        assigned(await decision(harness="codex"), employee_generic, "employee")

        await assign("employee", accounts[0], latest=True, revision=2, retired=True)
        for harness in harnesses:
            revoked = await decision(harness=harness)
            assert revoked["state"] == "revoked" and revoked["action"] == "none"
            assert revoked["installed_version"] is None
    assert not (await observe("projects", context=contexts[1]))["items"]
    await refused(
        binary,
        home,
        [
            "corporate",
            "assignments",
            "preview",
            "--harness",
            "claude-code",
            "--project",
            unjoined_project,
            "--context",
            contexts[0],
            *scoped,
        ],
    )
    await observe("teams", context=legacy["plan"]["change"]["context"]["context_id"])
    default_read = await run("corporate", "projects")
    assert default_read["observation"]["context"]["context_id"] == contexts[1]
    await refused(
        binary,
        home,
        [
            "corporate",
            "project",
            "show",
            "--project",
            new_id("remote_project"),
            "--context",
            contexts[0],
            *scoped,
        ],
    )
    async with app.state.sessionmaker() as db:
        member = await db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization,
                OrganizationMembership.account_id == accounts[0],
            )
        )
        assert member is not None
        member.state, member.revision = "suspended", member.revision + 1
        await db.commit()
    await refused(binary, home, ["corporate", "teams", "--context", contexts[0], *scoped])
    await refused(binary, home, [*preview_args, *scoped])
    await observe_second_company()
    await observe("projects", context=contexts[1])
    assert await run("context", "list") == snapshot
    assert await run("device", "show") == original
    with closing(sqlite3.connect(f"file:{registry}?mode=ro", uri=True)) as local:
        assert local.execute("SELECT count(*) FROM operation").fetchone() == before
    async with app.state.sessionmaker() as db:
        assert (
            await db.scalar(select(func.count()).select_from(CorporateAssignmentDistribution)) == 0
        )
        devices = list(await db.scalars(select(Device).where(Device.account_id.in_(accounts))))
        assert len(devices) == 3 and len({device.public_key for device in devices}) == 3
    assert not any(
        (home / name).exists() for name in (".codex", ".claude", ".cursor", ".config/opencode")
    )

    # Recover only one server-revoked enrollment. Original company views and
    # the native/legacy identity remain frozen while the child authenticates.
    async with app.state.sessionmaker() as db:
        device = await db.get(Device, connections[0]["device_id"])
        assert device is not None
        device.state = "revoked"
        await db.commit()
    refresh = await run(
        "account", "plan", "--action", "refresh", "--connection", connections[0]["connection_id"]
    )
    assert (await enact(refresh, "account", "apply"))["outcome"] == "revoked"
    recovery = await run(
        "account",
        "connections",
        "recovery",
        "plan",
        "--connection",
        connections[0]["connection_id"],
        "--label",
        "Recovered company",
    )
    prepared = await enact(recovery, "account", "connections", "recovery", "apply")
    assert prepared["state"] == "sign_in_required" and prepared["account_id"] == accounts[0]
    replacement = prepared["replacement_connection_id"]
    child = recovery["plan"]["replacement"]
    assert child["connection_id"] == replacement
    assert child["device_id"] != connections[0]["device_id"]
    # Approval by a different synthetic person must fail at the actual server
    # exchange, without registering a device or completing the local recovery.
    await login(accounts[1], replacement, authorized=False)
    async with app.state.sessionmaker() as db:
        assert await db.get(Device, child["device_id"]) is None
    pending_recoveries = await run("account", "connections", "recovery", "list")
    assert pending_recoveries["recoveries"][0]["state"] == "sign_in_required"
    await login(accounts[0], replacement)
    completed = await run("account", "connections", "recovery", "list")
    assert completed["recoveries"][0]["state"] == "authorized"
    assert completed["recoveries"][0]["confirmation"]["account_id"] == accounts[0]
    assert (await apply(binary, home, recovery, ["account", "connections", "recovery", "apply"]))[
        "state"
    ] == "authorized"
    await refused(
        binary,
        home,
        [
            "account",
            "plan",
            "--action",
            "start",
            "--connection",
            connections[0]["connection_id"],
            *scoped,
        ],
    )
    assert await run("context", "list") == snapshot
    assert await run("device", "show") == original
    assert (await run("account", "status"))["session"]["account_id"] == accounts[0]
    assert (await run("account", "status", "--connection", connections[1]["connection_id"]))[
        "session"
    ]["account_id"] == accounts[1]
    with closing(sqlite3.connect(f"file:{registry}?mode=ro", uri=True)) as local:
        assert local.execute("PRAGMA user_version").fetchone() == (56,)
    async with app.state.sessionmaker() as db:
        old = await db.get(Device, connections[0]["device_id"])
        new = await db.get(Device, child["device_id"])
        assert old is not None and new is not None
        assert old.state == "revoked" and old.public_key == normalize_public_key(
            connections[0]["public_key"]
        )
        assert new.state == "active" and new.account_id == accounts[0]
        assert new.public_key not in {
            normalize_public_key(connections[0]["public_key"]),
            normalize_public_key(original["public_key"]),
        }
        assert (
            await db.scalar(select(func.count()).select_from(CorporateAssignmentDistribution)) == 0
        )
    # Losing a local key permits preparation, never proof of server revocation.
    # The real exchange must refuse while that previous server device is active.
    retained = await run("account", "status", "--connection", replacement)
    missing_key = state / "ai-stp-v2-connections" / f"device-key.{child['device_id']}"
    assert missing_key.is_file() and not missing_key.is_symlink()
    missing_key.unlink()
    missing = await run(
        "account",
        "connections",
        "recovery",
        "plan",
        "--connection",
        replacement,
        "--label",
        "Missing-key company",
    )
    assert missing["plan"]["schema_version"] == 2
    assert "revoked_receipt_digest" not in missing["plan"]
    assert missing["plan"]["missing_key"]["session_receipt_digest"].startswith("sha256:")
    pending = await enact(missing, "account", "connections", "recovery", "apply")
    assert pending["state"] == "sign_in_required"
    assert pending["preparation_reason"] == "missing_enrollment_key"
    assert pending["server_preconditions"] == [
        "same_account",
        "revoked_previous_key",
        "distinct_new_key",
    ]
    next_connection = pending["replacement_connection_id"]
    next_child = missing["plan"]["replacement"]
    await login(accounts[0], next_connection, authorized=False)
    async with app.state.sessionmaker() as db:
        previous = await db.get(Device, child["device_id"])
        assert previous is not None and previous.state == "active"
        assert await db.get(Device, next_child["device_id"]) is None
        previous.state = "revoked"
        await db.commit()
    pending_recoveries = await run("account", "connections", "recovery", "list")
    assert (
        next(
            recovery
            for recovery in pending_recoveries["recoveries"]
            if recovery["replacement_connection_id"] == next_connection
        )["state"]
        == "sign_in_required"
    )
    await login(accounts[0], next_connection)
    assert (await enact(missing, "account", "connections", "recovery", "apply"))[
        "state"
    ] == "authorized"
    assert await run("account", "status", "--connection", replacement) == retained
    assert await run("context", "list") == snapshot
    assert await run("device", "show") == original
    assert (await run("account", "status"))["session"]["account_id"] == accounts[0]
    assert (await run("account", "status", "--connection", connections[1]["connection_id"]))[
        "session"
    ]["account_id"] == accounts[1]
    async with app.state.sessionmaker() as db:
        previous = await db.get(Device, child["device_id"])
        newest = await db.get(Device, next_child["device_id"])
        assert previous is not None and previous.state == "revoked"
        assert newest is not None and newest.state == "active"
        assert newest.account_id == accounts[0] and newest.public_key != previous.public_key
        assert (
            await db.scalar(select(func.count()).select_from(CorporateAssignmentDistribution)) == 0
        )
    print(
        json.dumps(
            {
                "native_corporate_http": "passed",
                "independent_accounts": 2,
                "one_account_coexisting_views": [
                    "offline_personal",
                    "authenticated_personal",
                    "corporate_first",
                    "corporate_second",
                ],
                "corporate_membership_revocation": "other_company_preserved",
                "harness_previews": len(harnesses),
                "assignment_precedence": [
                    "employee",
                    "project",
                    "technology",
                    "team",
                    "organization",
                ],
                "harness_specificity": "passed",
                "retired_employee_override": "refused_inherited_fallback",
                "legacy_session": "preserved",
                "membership_revocation": "refused",
                "read_operations_added": 0,
                "link_plan_outcome": "exact_ready_and_applied_account_bound_reads",
                "link_current": "linked_unlinked_and_tenant_fences_without_admission",
                "unlink_plan_readers": "ready_applied_settlement_unknown_and_account_tenant_fences",
                "link_preview": "registered_checkout_and_current_context_without_writes",
                "enrollment_recovery": "same_account_only",
                "missing_key_recovery": "active_previous_device_refused_before_revocation",
            }
        ),
        flush=True,
    )

    await verify_checkout.qualify(
        binary=binary,
        home=home,
        state=state,
        root=root,
        app=app,
        faults=app.state.checkout_faults,
        run=run,
        enact=enact,
        login=login,
        refused=refused,
        organization=organization,
        project=project,
        account=accounts[0],
        connection=next_connection,
        device=next_child["device_id"],
        offline_context=offline["plan"]["change"]["context"]["context_id"],
        git_executable=git_executable,
        old_recoveries=[recovery, missing],
        foreign_context=contexts[1],
    )


async def prove(binary: Path, database_url: str, root: Path) -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
        app = create_app(
            make_settings(
                root / "api", database_url=database_url, auth=make_test_auth(public_base_url=origin)
            )
        )
        faults = verify_checkout.LostAcknowledgements(app)
        app.state.checkout_faults = faults
        async with app.router.lifespan_context(app):
            server = uvicorn.Server(
                uvicorn.Config(faults, lifespan="off", access_log=False, log_level="error")
            )
            serving = asyncio.create_task(server.serve(sockets=[listener]))
            try:
                async with asyncio.timeout(15):
                    while not server.started:
                        if serving.done():
                            await serving
                            raise AssertionError("fixture API stopped before readiness")
                        await asyncio.sleep(0.01)
                await journeys(binary, root, app, origin)
            finally:
                server.should_exit = True
                await asyncio.wait_for(serving, timeout=30)


def main() -> None:
    binary = Path(sys.argv[1]).resolve(strict=True)
    saved = os.environ.get("AI_STP_DB_URL")
    with (
        tempfile.TemporaryDirectory(prefix="ai-stp-corporate-") as temporary,
        isolated_database(
            "AI_STP_TEST_DB_URL is required for native corporate qualification"
        ) as url,
    ):
        try:
            os.environ["AI_STP_DB_URL"] = url
            command.upgrade(Config("alembic.ini"), "head")
            asyncio.run(prove(binary, url, Path(temporary)))
        finally:
            if saved is None:
                os.environ.pop("AI_STP_DB_URL", None)
            else:
                os.environ["AI_STP_DB_URL"] = saved


if __name__ == "__main__":
    main()
