"""Native enrollment and company reads against disposable PostgreSQL and real HTTP.

Only the browser approval step is supplied by the fixture, for synthetic accounts.
The native binary performs discovery, start/poll, key binding and every company
request itself. No live SSO identity, provider process or harness files are used.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sqlite3
import sys
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import uvicorn
from alembic import command
from alembic.config import Config
from httpx import AsyncClient
from sqlalchemy import func, select
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
from ai_stp_platform.models import Account, CatalogMetadata, Device
from ai_stp_platform.organization_models import (
    CorporateAssignmentDistribution,
    CorporateProject,
    CorporateProjectMember,
    CorporateRoleBinding,
    CorporateTeam,
    CorporateTeamMember,
    OrganizationMembership,
    ProjectIdentity,
)
from ai_stp_platform.technology_models import Technology, TechnologyAlias


async def refused(binary: Path, home: Path, arguments: list[str]) -> None:
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
    ErrorEnvelope.model_validate_json(stdout)


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
    selected = await run("context", "select", "plan", "--context", contexts[1])
    await enact(selected, "context", "apply")
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
                "enrollment_recovery": "same_account_only",
                "missing_key_recovery": "active_previous_device_refused_before_revocation",
            }
        ),
        flush=True,
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
        async with app.router.lifespan_context(app):
            server = uvicorn.Server(
                uvicorn.Config(app, lifespan="off", access_log=False, log_level="error")
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
