"""Installed Linux UI and bundled CLI against disposable actual API/PostgreSQL.

Only synthetic browser approval is supplied by this fixture. WebDriver uses
normal controls; no IPC interception, JavaScript mutation or app test hook.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import runpy
import socket
import sqlite3
import subprocess
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Any, cast

import uvicorn
from alembic import command
from alembic.config import Config
from httpx import AsyncClient
from sqlalchemy import func, select
from tests.native_contract.verify_checkout import LostAcknowledgements
from tests.support.api_settings import make_settings, make_test_auth
from tests.support.postgres import isolated_database

from ai_stp_api.app import create_app
from ai_stp_api.slices.auth.device_flow import approve_device_authorization
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import (
    CorporateProject,
    CorporateProjectMember,
    ProjectIdentity,
    ProjectLink,
    ProjectLinkPlan,
)

PROFILE_REVIEW = 'section[aria-label="Review native profile plan"]'
CHECKOUT_REVIEW = 'section[aria-label="Review corporate checkout change"]'
HISTORY = 'section[aria-label="Corporate checkout history"]'


def field(driver: Any, label: str, *, kind: str = "input", scope: str = "main") -> Any:
    return driver.wait(
        lambda: driver.read(
            "const root=document.querySelector(arguments[0]);"
            "const labels=[...(root?.querySelectorAll('label')??[])]"
            ".filter(label=>{"
            "const walker=document.createTreeWalker(label,NodeFilter.SHOW_TEXT);"
            "const text=[];let node;while(node=walker.nextNode()){"
            "if(!node.parentElement.closest('select,textarea,svg,button'))"
            "text.push(node.textContent);}"
            "return text.join(' ').replace(/\\s+/g,' ').trim()===arguments[1];});"
            "const input=labels.length===1?labels[0].querySelector(arguments[2]):null;"
            "return input&&!input.disabled&&"
            "(arguments[2]!=='select'||input.options.length)?input:null;",
            scope,
            label,
            kind,
        ),
        label,
    )


def fill(driver: Any, label: str, value: str, *, scope: str = "main") -> None:
    element = field(driver, label, scope=scope)
    driver.command("POST", f"/element/{element['element-6066-11e4-a52e-4f735466cecf']}/clear", {})
    driver.command(
        "POST", f"/element/{element['element-6066-11e4-a52e-4f735466cecf']}/value", {"text": value}
    )


def choose(driver: Any, label: str, value: str, *, scope: str = "main") -> None:
    select_element = field(driver, label, kind="select", scope=scope)
    option = driver.wait(
        lambda: driver.read(
            "return [...arguments[0].options].find(x=>x.value===arguments[1]);",
            select_element,
            value,
        ),
        label,
    )
    driver.click(option)
    # Dismiss the native select popup through a real key event before leaving
    # the control; reading its selected value alone does not close that popup.
    driver.command(
        "POST",
        f"/element/{select_element['element-6066-11e4-a52e-4f735466cecf']}/value",
        {"text": "\ue00c"},
    )


def public_plan(driver: Any, scope: str) -> dict[str, Any]:
    driver.find(scope)
    driver.click(driver.find(scope + " details summary"))
    value = json.loads(
        driver.read("return document.querySelector(arguments[0]+' pre').textContent;", scope)
    )
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def authorize(driver: Any, scope: str, button: str) -> None:
    checkbox = driver.find(scope + ' input[type="checkbox"]')
    assert not driver.read("return arguments[0].checked;", checkbox)
    driver.click(checkbox)
    driver.click(driver.button(button, scope))


def profile_review(driver: Any, check: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    plan = public_plan(driver, PROFILE_REVIEW)
    check(plan)
    authorize(driver, PROFILE_REVIEW, "Apply reviewed change")
    driver.wait(
        lambda: driver.read("return !document.querySelector(arguments[0]);", PROFILE_REVIEW),
        "profile commit",
    )
    return plan


async def seed(app: Any, origin: str) -> tuple[str, str, str]:
    account, project = new_id("account"), new_id("remote_project")
    async with app.state.sessionmaker() as db:
        db.add(Account(id=account))
        await db.commit()
    async with AsyncClient(base_url=origin, timeout=15, trust_env=False) as client:
        response = await client.post(
            "/v1/corporate/bootstrap",
            json={
                "organization_name": "Installed fixture company",
                "superadmin_account_id": account,
                "idempotency_key": "installed-desktop-corporate-bootstrap",
            },
            headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
        )
        assert response.status_code == 200
        organization = response.json()["organization_id"]
        assert isinstance(organization, str)
    async with app.state.sessionmaker() as db:
        db.add(
            ProjectIdentity(
                id=project,
                organization_id=organization,
                namespace="remote",
                external_key="installed-desktop:shared-project",
                display_name="Installed shared project",
            )
        )
        await db.flush()
        db.add(
            CorporateProject(
                id=project, organization_id=organization, name="Installed shared project"
            )
        )
        await db.flush()
        db.add(
            CorporateProjectMember(
                organization_id=organization, project_id=project, account_id=account, role="owner"
            )
        )
        await db.commit()
    return account, organization, project


def installed_journey(
    *,
    root: Path,
    origin: str,
    account: str,
    organization: str,
    project: str,
    driver_path: Path,
    approve: Callable[[str], None],
    lose_confirmation: Callable[[], None],
) -> dict[str, Any]:
    # Reuse the already qualified persistent HTTP/1 driver and fixed diagnostics.
    helpers = runpy.run_path(
        str(Path(".github/scripts/qualify-installed-desktop.py").resolve(strict=True))
    )
    driver_type, native = helpers["Driver"], helpers["native"]
    home, cache = root / "home", root / "cache"
    home.mkdir(mode=0o700)
    cache.mkdir(mode=0o700)
    canary = home / "AGENTS.md"
    canary.write_bytes(b"# Unowned installed corporate canary\n")
    canary.chmod(0o640)
    environment = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "XDG_CACHE_HOME": str(cache),
        "TAURI_WEBVIEW_AUTOMATION": "true",
        **{
            name: os.environ[name]
            for name in (
                "DISPLAY",
                "XAUTHORITY",
                "DBUS_SESSION_BUS_ADDRESS",
                "XDG_RUNTIME_DIR",
                "XDG_CONFIG_HOME",
                "XDG_DATA_HOME",
            )
        },
    }
    files = subprocess.check_output(["dpkg-query", "--listfiles", "ai-stp-desktop"], text=True)
    binaries = [
        Path(line) for line in files.splitlines() if line.endswith("/cli/ai-stp-desktop-cli")
    ]
    assert len(binaries) == 1 and binaries[0].is_file()
    binary = binaries[0].resolve(strict=True)
    assert native(binary, environment, ["version"])["runtime"] == "rust"
    driver = driver_type(driver_path, environment, root / "corporate-driver.log")
    try:
        driver.start()
        driver.navigate("settings")
        storage = field(driver, "Credential storage", kind="select")
        assert driver.read("return arguments[0].value;", storage) == "os_keyring"
        driver.click(driver.find('main form input[type="checkbox"]'))
        driver.click(driver.button("Initialize workspace"))
        driver.wait(
            lambda: driver.read(
                "return document.querySelector('main').textContent.includes('Initialized');"
            ),
            "native vault initialization",
        )
        identity = native(binary, environment, ["device", "show"])
        assert identity["credential_store"] == "os_keyring"
        driver.navigate("profiles")
        offline = driver.create_context("Installed offline personal")
        driver.select_context("Installed offline personal", offline)
        fill(driver, "Connection label", "Installed company connection")
        fill(driver, "Server origin", origin)
        driver.click(driver.button("Check server sign-in methods"))
        choose(driver, "Sign-in method", "github")
        driver.click(driver.button("Review connection creation"))

        def connection_plan(plan: dict[str, Any]) -> None:
            assert plan["label"] == "Installed company connection" and plan["origin"] == origin

        created = profile_review(driver, connection_plan)
        connection = created["connection_id"]
        driver.click(driver.find(f'main a[href="#/auth?connection={connection}"]'))
        driver.click(driver.button("GitHub"))
        driver.click(driver.button("Start sign-in"))
        driver.wait(
            lambda: driver.read(
                "return document.querySelector('main').textContent"
                ".includes('Approve this device in your browser');"
            ),
            "actual pending device authorization",
        )
        pending = native(binary, environment, ["account", "status", "--connection", connection])[
            "session"
        ]
        assert pending["state"] == "pending"
        approve(pending["user_code"])
        driver.click(driver.button("Open browser and confirm"))
        driver.wait(
            lambda: driver.read(
                "return document.querySelector('main').textContent.includes('Signed in');"
            ),
            "actual native device poll",
        )
        assert (
            native(binary, environment, ["account", "status", "--connection", connection])[
                "session"
            ]["account_id"]
            == account
        )
        driver.navigate("profiles")
        fill(driver, "Context label", "Installed corporate context")
        choose(driver, "Context connection", connection)
        driver.click(driver.button("Read available organizations"))
        choose(driver, "Organization", organization)
        driver.click(driver.button("Review context creation"))

        def company_plan(plan: dict[str, Any]) -> None:
            context = plan["change"]["context"]
            assert context["authority"]["organization"]["organization_id"] == organization
            assert context["authority"]["account"]["account_id"] == account

        company = profile_review(driver, company_plan)["change"]["context"]["context_id"]
        choose(driver, "Selected context view", company, scope='section[aria-label="Context view"]')
        driver.selected(company)
        checkout = root / "registered-checkout"
        checkout.mkdir()
        (checkout / ".env").write_bytes(b"PRIVATE=installed-corporate-unowned\n")
        (checkout / ".env").chmod(0o640)
        for args in (
            ["init", "--initial-branch=main"],
            ["commit", "--allow-empty", "-m", "installed corporate fixture"],
        ):
            subprocess.run(
                [
                    "/usr/bin/git",
                    "-C",
                    str(checkout),
                    "-c",
                    "user.name=Installed fixture",
                    "-c",
                    "user.email=installed@example.invalid",
                    *args,
                ],
                check=True,
                capture_output=True,
                env={**environment, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull},
                timeout=15,
            )
        passport = native(
            binary, environment, ["project", "passport", "plan", "--root", str(checkout)]
        )
        plan_file = root / "registered-passport.json"
        plan_file.write_text(json.dumps(passport["plan"]), encoding="utf-8")
        native(
            binary,
            environment,
            ["local", "apply", "--plan", str(plan_file), "--plan-digest", passport["plan_digest"]],
        )
        driver.navigate("corporate")
        driver.click(driver.button("Read projects"))
        driver.click(driver.button("Review local checkout"))
        fill(driver, "Checkout directory", str(checkout))
        fill(driver, "Git executable (optional)", "/usr/bin/git")
        driver.click(driver.button("Preview checkout"))
        driver.wait(
            lambda: driver.read(
                "return !!document.querySelector(arguments[0]);",
                'section[aria-label="Corporate checkout preview"] '
                '[aria-label="Verified checkout observation"]',
            ),
            "actual checkout preview",
        )
        driver.click(driver.button("Review link request"))
        request = public_plan(driver, CHECKOUT_REVIEW)
        assert request["change"]["snapshot"]["target"]["remote_project_id"] == project
        authorize(driver, CHECKOUT_REVIEW, "Apply reviewed checkout change")
        driver.click(driver.button("Review link confirmation"))
        confirmation = public_plan(driver, CHECKOUT_REVIEW)
        assert confirmation["change"]["request_operation_id"] == request["operation_id"]
        lose_confirmation()
        authorize(driver, CHECKOUT_REVIEW, "Apply reviewed checkout change")
        driver.wait(
            lambda: driver.read("return !!document.querySelector('main [role=alert]');"),
            "unconfirmed committed response",
        )
        current = native(
            binary,
            environment,
            ["corporate", "project", "link", "show", "--operation", confirmation["operation_id"]],
        )
        assert current["state"] == "applying"
    finally:
        driver.close()
    driver = driver_type(driver_path, environment, root / "corporate-restarted-driver.log")
    try:
        driver.start()
        driver.selected(company)
        driver.navigate("tasks")
        driver.click(driver.button("Inspect " + confirmation["operation_id"], HISTORY))
        scope = HISTORY + ' [aria-label="Original checkout operation"]'
        authorize(driver, scope, "Reconcile original outcome")
        driver.click(driver.button("Review original local binding", HISTORY))
        next_scope = HISTORY + ' [aria-label="Review retained checkout next change"]'
        adoption = public_plan(driver, next_scope)
        assert adoption["change"]["request_operation_id"] == request["operation_id"]
        authorize(driver, next_scope, "Apply reviewed original checkout change")
        driver.wait(
            lambda: driver.read(
                "return document.querySelector(arguments[0]).textContent"
                ".includes('Corporate project binding saved.');",
                HISTORY,
            ),
            "actual local binding adoption",
        )
        adopted = native(
            binary,
            environment,
            ["corporate", "project", "link", "show", "--operation", adoption["operation_id"]],
        )
        assert adopted["state"] == "completed" and adopted["effect"]["link"]["state"] == "linked"
        assert native(binary, environment, ["device", "show"]) == identity
        listed = native(binary, environment, ["context", "list"])
        assert listed["selected"]["context_id"] == company and len(listed["contexts"]) == 2
        assert (
            canary.read_bytes() == b"# Unowned installed corporate canary\n"
            and canary.stat().st_mode & 0o777 == 0o640
        )
        assert (checkout / ".env").read_bytes() == b"PRIVATE=installed-corporate-unowned\n"
        assert (checkout / ".env").stat().st_mode & 0o777 == 0o640
        registry = Path(passport["plan"]["state_parent"]) / "ai-stp-v2-state" / "registry.sqlite3"
        with closing(sqlite3.connect(f"file:{registry}?mode=ro", uri=True)) as db:
            row = db.execute(
                "SELECT p.state,p.organization_id,p.remote_project_id,r.request_operation_id,"
                "r.confirmation_operation_id,r.binding_operation_id,r.context_id "
                "FROM project_link p JOIN native_checkout_reservation r "
                "ON r.local_project_id=p.local_project_id"
            ).fetchone()
            assert row == (
                "linked",
                organization,
                project,
                request["operation_id"],
                confirmation["operation_id"],
                adoption["operation_id"],
                company,
            )
        return {
            "schema_version": 1,
            "evidence_type": "installed_linux_corporate_checkout",
            "consumer_commit": os.environ["GITHUB_SHA"],
            "installed_cli_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "actual_release_package": True,
            "actual_bundled_cli_ipc": True,
            "native_os_keyring": True,
            "corporate_onboarding": True,
            "browser_approval": "synthetic_fixture_only",
            "live_sso_account_linking_qualified": False,
            "personal_and_corporate_coexistence": True,
            "lost_committed_confirmation": True,
            "restart_and_original_reconciliation": True,
            "active_binding_adoption": True,
            "unowned_files_preserved": True,
            "installation_authority": False,
            "harness_activation_qualified": False,
        }
    finally:
        driver.close()


async def prove(driver_path: Path, out: Path, database_url: str, root: Path) -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
        app = create_app(
            make_settings(
                root / "api", database_url=database_url, auth=make_test_auth(public_base_url=origin)
            )
        )
        faults = LostAcknowledgements(app)
        async with app.router.lifespan_context(app):
            server = uvicorn.Server(
                uvicorn.Config(faults, lifespan="off", access_log=False, log_level="error")
            )
            serving = asyncio.create_task(server.serve(sockets=[listener]))
            loop = asyncio.get_running_loop()

            async def approve_code(code: str) -> None:
                async with app.state.sessionmaker() as db:
                    await approve_device_authorization(db, user_code=code, account_id=account)
                    await db.commit()

            async def lose() -> None:
                assert faults.lose_next is None
                faults.lose_next = "/v1/projects/links"

            def approve(code: str) -> None:
                asyncio.run_coroutine_threadsafe(approve_code(code), loop).result(timeout=15)

            def lose_confirmation() -> None:
                asyncio.run_coroutine_threadsafe(lose(), loop).result(timeout=15)

            try:
                async with asyncio.timeout(15):
                    while not server.started:
                        if serving.done():
                            await serving
                            raise AssertionError("fixture API stopped before readiness")
                        await asyncio.sleep(0.01)
                account, organization, project = await seed(app, origin)
                proof = await asyncio.to_thread(
                    installed_journey,
                    root=root,
                    origin=origin,
                    account=account,
                    organization=organization,
                    project=project,
                    driver_path=driver_path,
                    approve=approve,
                    lose_confirmation=lose_confirmation,
                )
                assert faults.lose_next is None
                assert faults.writes == [
                    f"/v1/organizations/{organization}/project-link-plans",
                    "/v1/projects/links",
                ]
                async with app.state.sessionmaker() as db:
                    assert await db.scalar(select(func.count()).select_from(ProjectLinkPlan)) == 1
                    assert await db.scalar(select(func.count()).select_from(ProjectLink)) == 1
                    link = await db.scalar(select(ProjectLink))
                    assert (
                        link is not None
                        and link.state == "linked"
                        and link.organization_id == organization
                    )
                proof.update(actual_api_postgresql=True, committed_mutation_posts=2)
                out.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
                print(
                    "Installed corporate UI, actual API, original lost-reply recovery "
                    "and native binding passed."
                )
            finally:
                server.should_exit = True
                await asyncio.wait_for(serving, timeout=30)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--driver", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("RUNNER_OS") == "Linux"
    assert os.environ.get("AI_STP_TEST_SECRET_SERVICE") == "isolated"
    root = Path(os.environ["AI_STP_TEST_SECRET_SERVICE_ROOT"]).resolve(strict=True)
    temporary = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    assert root.is_relative_to(temporary) and args.out.resolve().is_relative_to(temporary)
    saved = os.environ.get("AI_STP_DB_URL")
    with isolated_database(
        "AI_STP_TEST_DB_URL is required for installed corporate qualification"
    ) as url:
        try:
            os.environ["AI_STP_DB_URL"] = url
            command.upgrade(Config("alembic.ini"), "head")
            asyncio.run(prove(args.driver.resolve(strict=True), args.out, url, root))
        finally:
            if saved is None:
                os.environ.pop("AI_STP_DB_URL", None)
            else:
                os.environ["AI_STP_DB_URL"] = saved


if __name__ == "__main__":
    main()
