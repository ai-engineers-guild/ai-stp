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
from ai_stp_foundation.envelope import ErrorEnvelope
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, CatalogMetadata, Device
from ai_stp_platform.organization_models import (
    CorporateAssignmentDistribution,
    CorporateProject,
    CorporateProjectMember,
    CorporateRoleBinding,
    CorporateTeam,
    OrganizationMembership,
    ProjectIdentity,
)
from ai_stp_platform.technology_models import Technology


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
        project, team, technology = new_id("remote_project"), new_id("team"), new_id("technology")
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
            db.add(
                ProjectIdentity(
                    id=project,
                    organization_id=organization,
                    namespace="remote",
                    external_key=f"native:{project}",
                    display_name="Native shared project",
                )
            )
            await db.flush()
            db.add(
                CorporateProject(
                    id=project, organization_id=organization, name="Native shared project"
                )
            )
            db.add(CorporateTeam(id=team, organization_id=organization, name="Native team"))
            db.add(
                Technology(
                    id=technology,
                    organization_id=organization,
                    name="Native technology",
                    provenance="manual",
                )
            )
            await db.flush()
            db.add(
                CorporateProjectMember(
                    organization_id=organization,
                    project_id=project,
                    account_id=accounts[0],
                    role="owner",
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

    async def login(account: str, connection: str | None) -> None:
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
        assert receipt["outcome"] == "authorized" and receipt["account_id"] == account

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
    assert (await observe("project", "show", "--project", project))["project_id"] == project
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
    assert FIXTURE_SETUP_ID in {item["stable_id"] for item in catalog["items"]}
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
        assert item["version"] == "1.0" and item["passport_digest"] == setup_digest
        assert item["installed_version"] is None and item["action"] == "install"
    assert not (await observe("projects", "--membership-only", context=contexts[1]))["items"]
    await observe("teams", context=legacy["plan"]["change"]["context"]["context_id"])
    assert (await run("corporate", "projects", "--membership-only"))["observation"]["context"][
        "context_id"
    ] == contexts[1]
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
    await observe("projects", "--membership-only", context=contexts[1])
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
    print(
        json.dumps(
            {
                "native_corporate_http": "passed",
                "independent_accounts": 2,
                "harness_previews": len(harnesses),
                "legacy_session": "preserved",
                "membership_revocation": "refused",
                "read_operations_added": 0,
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
