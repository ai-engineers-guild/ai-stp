"""Installed Linux UI and bundled CLI against disposable actual API/PostgreSQL.

Only synthetic browser approval is supplied by this fixture. WebDriver uses
normal controls; no IPC interception, DOM mutation or app test hook. A passive
test-owned event observer records whether one real activation reached its control.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import runpy
import socket
import sqlite3
import subprocess
import unicodedata
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
    ProjectUnlinkPlan,
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
    # Context switching disables this control until its native plan/apply and
    # refresh finish. Observe completion before sending another real key event.
    select_element = field(driver, label, kind="select", scope=scope)
    assert driver.read("return arguments[0].value;", select_element) == value
    # Dismiss the native select popup through a real key event before leaving
    # the control; reading its selected value alone does not close that popup.
    driver.command(
        "POST",
        f"/element/{select_element['element-6066-11e4-a52e-4f735466cecf']}/value",
        {"text": "\ue00c"},
    )


def public_plan(driver: Any, scope: str) -> dict[str, Any]:
    def ready() -> bool:
        observed = driver.read(
            "return {ready:!!document.querySelector(arguments[0]),"
            "codes:[...document.querySelectorAll('main [role=alert]')]"
            ".flatMap(x=>x.textContent.match(/\\b(?:AI_STP_|DESKTOP_)[A-Z_]+|\\bCONTEXT_VIEW\\b/g)??[])};",
            scope,
        )
        if observed["ready"]:
            return True
        if observed["codes"]:
            raise ValueError("Public native review refused: " + observed["codes"][0])
        return False

    driver.wait(ready, "public native plan review")
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


def installed_locations(
    driver: Any,
    *,
    root: Path,
    checkout: Path,
    registry: Path,
    binary: Path,
    environment: dict[str, str],
    company: str,
    project: str,
    driver_path: Path,
    driver_type: Callable[[Path, dict[str, str], Path], Any],
    native: Any,
) -> tuple[Any, dict[str, Any]]:
    """Add actual UI location61 acceptance after the unchanged retirement60 journey."""
    location_scope = HISTORY + ' section[aria-label="Checkout location"]'
    review_scope = location_scope + ' section[aria-label="Review checkout location"]'
    receipt_scope = location_scope + ' [aria-label="Recorded location receipt"]'
    marker = ".ai-stp-v2-project/project-id"
    before_marker = (checkout / marker).read_bytes()
    before_canary = (checkout / ".env").read_bytes()
    before_mode = (checkout / ".env").stat().st_mode
    physical = (checkout.stat().st_dev, checkout.stat().st_ino)

    def run(*arguments: str) -> dict[str, Any]:
        return cast(dict[str, Any], native(binary, environment, list(arguments)))

    def apply(planned: dict[str, Any], noun: str) -> dict[str, Any]:
        path = root / f"installed-{noun}-{planned['plan']['operation_id']}.json"
        path.write_text(json.dumps(planned["plan"]), encoding="utf-8")
        path.chmod(0o600)
        arguments = [
            "corporate",
            "project",
            noun,
            "apply",
            "--plan",
            str(path),
            "--plan-digest",
            planned["plan_digest"],
        ]
        if noun == "link":
            arguments.extend(["--git-executable", "/usr/bin/git"])
        return run(*arguments)

    # A distinct new request follows the completed release. Do not reinterpret
    # the original retired adoption or modify its receipt for the new journey.
    requested = run(
        "corporate",
        "project",
        "link-request",
        "plan",
        "--context",
        company,
        "--root",
        str(checkout),
        "--project",
        project,
        "--git-executable",
        "/usr/bin/git",
    )
    apply(requested, "link")
    confirmed = run(
        "corporate",
        "project",
        "link-confirm",
        "plan",
        "--request-operation",
        requested["plan"]["operation_id"],
        "--git-executable",
        "/usr/bin/git",
    )
    apply(confirmed, "link")
    adopted = run(
        "corporate",
        "project",
        "link-adopt",
        "plan",
        "--request-operation",
        requested["plan"]["operation_id"],
        "--context",
        company,
        "--root",
        str(checkout),
        "--git-executable",
        "/usr/bin/git",
    )
    applied = apply(adopted, "link")
    binding = applied["operation_id"]
    original = run("corporate", "project", "link", "show", "--operation", binding)
    assert original["binding_retirement"] is None
    assert {key: value for key, value in original.items() if key != "binding_retirement"} == applied

    def inspect_binding() -> None:
        driver.navigate("tasks", keyboard=True)
        driver.click(driver.button("Read checkout history", HISTORY))
        driver.click(driver.button("Inspect " + binding, HISTORY))
        driver.button("Read location history", location_scope)

    def visible(text: str) -> bool:
        return bool(
            driver.read(
                "return document.querySelector(arguments[0])?.textContent.includes(arguments[1]);",
                location_scope,
                text,
            )
        )

    try:
        inspect_binding()
        fill(
            driver,
            "Trusted Git executable for location review (optional)",
            "/usr/bin/git",
            scope=location_scope,
        )
        driver.click(driver.button("Review checkout anchor", location_scope))
        anchor = public_plan(driver, review_scope)
        assert anchor["action"] == "anchor" and anchor["original"] == original["plan"]
        assert anchor["registry_schema_before"] == 60 and anchor["registry_schema_after"] == 61
        assert base64.b64decode(anchor["destination"]["utf8_base64"], validate=True) == os.fsencode(
            checkout
        )
        assert (
            run("corporate", "project", "location", "list", "--binding-operation", binding)[
                "locations"
            ]
            == []
        )
        authorize(driver, review_scope, "Apply reviewed checkout location")
        driver.wait(lambda: visible("Checkout anchor receipt saved."), "installed location anchor")
        anchored = run(
            "corporate", "project", "location", "show", "--operation", anchor["operation_id"]
        )
        assert anchored["plan"] == anchor and anchored["outcome"] == "location_anchored"
        recorded = [anchored]
        current = checkout
        for index in (1, 2):
            # The app and its own process group are closed before the fixture,
            # acting as the user, moves the directory. No UI or engine rename.
            driver.close()
            destination = root / unicodedata.normalize("NFD", f"café-moved-{index}")
            current.rename(destination)
            assert not current.exists()
            assert (destination.stat().st_dev, destination.stat().st_ino) == physical
            driver = driver_type(driver_path, environment, root / f"location-{index}-driver.log")
            driver.start()
            driver.selected(company)
            inspect_binding()
            driver.click(driver.button("Read location history", location_scope))
            assert visible("Original adoption directory:")
            fill(
                driver,
                "Trusted Git executable for location review (optional)",
                "/usr/bin/git",
                scope=location_scope,
            )
            fill(
                driver, "Existing moved checkout directory", str(destination), scope=location_scope
            )
            driver.click(driver.button("Review moved checkout", location_scope))
            moved = public_plan(driver, review_scope)
            assert moved["action"] == "relocate" and moved["original"] == original["plan"]
            assert moved["registry_schema_before"] == moved["registry_schema_after"] == 61
            assert base64.b64decode(
                moved["destination"]["utf8_base64"], validate=True
            ) == os.fsencode(destination)
            assert base64.b64decode(
                moved["binding"]["checkout_root"]["utf8_base64"], validate=True
            ) == os.fsencode(current)
            assert moved["physical"] == anchor["physical"]
            authorize(driver, review_scope, "Apply reviewed checkout location")
            driver.wait(
                lambda: visible("Checkout relocation receipt saved."),
                "installed reviewed relocation",
            )
            completed = run(
                "corporate", "project", "location", "show", "--operation", moved["operation_id"]
            )
            assert completed["plan"] == moved and completed["outcome"] == "checkout_relocated"
            assert all(
                completed[field] is False
                for field in (
                    "remote_write_submitted",
                    "harness_files_changed",
                    "tasks_changed",
                    "installation_authority",
                )
            )
            recorded.append(completed)
            assert run("corporate", "project", "link", "show", "--operation", binding) == original
            assert (destination / marker).read_bytes() == before_marker
            assert (destination / ".env").read_bytes() == before_canary
            assert (destination / ".env").stat().st_mode == before_mode
            current = destination

        driver.click(driver.button("Read location history", location_scope))
        driver.click(driver.button("Inspect location " + anchor["operation_id"], location_scope))
        assert public_plan(driver, receipt_scope) == anchor
        for retained in recorded:
            assert (
                run(
                    "corporate",
                    "project",
                    "location",
                    "show",
                    "--operation",
                    retained["operation_id"],
                )
                == retained
            )
        history = run("corporate", "project", "location", "list", "--binding-operation", binding)
        assert [item["operation_id"] for item in history["locations"]] == [
            item["operation_id"] for item in reversed(recorded)
        ]

        unrequested = run(
            "corporate",
            "project",
            "unlink-request",
            "plan",
            "--context",
            company,
            "--binding-operation",
            binding,
        )
        apply(unrequested, "unlink")
        unconfirmed = run(
            "corporate",
            "project",
            "unlink-confirm",
            "plan",
            "--request-operation",
            unrequested["plan"]["operation_id"],
        )
        assert apply(unconfirmed, "unlink")["effect"]["link"]["state"] == "unlinked"
        driver.click(driver.button("Review local binding retirement", HISTORY))
        retirement_scope = HISTORY + ' [aria-label="Review local binding retirement"]'
        retirement = public_plan(driver, retirement_scope)
        assert retirement["registry_schema_before"] == retirement["registry_schema_after"] == 61
        assert base64.b64decode(
            retirement["snapshot"]["binding"]["checkout_root"]["utf8_base64"], validate=True
        ) == os.fsencode(current)
        authorize(driver, retirement_scope, "Apply reviewed local binding retirement")
        driver.wait(
            lambda: driver.read(
                "return document.querySelector(arguments[0]).textContent.includes("
                "'This original local binding was retired. Its adoption receipt is preserved.');",
                HISTORY,
            ),
            "installed relocated binding retirement61",
        )
        retired = run("corporate", "project", "link", "show", "--operation", binding)
        assert retired["binding_retirement"]["plan"] == retirement
        assert retired["plan"] == original["plan"] and retired["effect"] == original["effect"]
        with closing(sqlite3.connect(f"file:{registry}?mode=ro", uri=True)) as db:
            assert db.execute("PRAGMA user_version").fetchone() == (61,)
            assert db.execute("SELECT count(*) FROM native_checkout_reservation").fetchone() == (0,)
            assert db.execute("SELECT count(*) FROM native_binding_retirement").fetchone() == (2,)
            assert db.execute("SELECT count(*) FROM native_checkout_location").fetchone() == (1,)
        driver.close()
        driver = driver_type(driver_path, environment, root / "location-retired-driver.log")
        driver.start()
        driver.selected(company)
        inspect_binding()
        driver.click(driver.button("Inspect location " + anchor["operation_id"], location_scope))
        assert public_plan(driver, receipt_scope) == anchor
        assert run("corporate", "project", "link", "show", "--operation", binding) == retired
        assert (
            run("corporate", "project", "location", "list", "--binding-operation", binding)
            == history
        )
        assert (current / marker).read_bytes() == before_marker
        assert (current / ".env").read_bytes() == before_canary
        assert (current / ".env").stat().st_mode == before_mode
        return driver, {
            "location_link_id": original["effect"]["link"]["link_id"],
            "location_writer_epoch": 61,
            "installed_reviewed_location_anchor": True,
            "installed_two_same_object_relocations": True,
            "location_original_receipts_after_future_move_and_restart": True,
            "location_retirement61_and_offline_history": True,
            "location_canary_marker_bytes_and_modes_preserved": True,
        }
    except BaseException:
        driver.close()
        raise


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
        checkout = root / unicodedata.normalize("NFD", "café-checkout")
        neighbor = root / unicodedata.normalize("NFC", "café-checkout")
        assert str(checkout) != str(neighbor)
        assert unicodedata.normalize("NFC", str(checkout)) == str(neighbor)
        project_ids: list[str] = []
        for index, directory in enumerate((checkout, neighbor)):
            directory.mkdir()
            (directory / ".env").write_bytes(
                b"PRIVATE=installed-corporate-unowned\n"
                if index == 0
                else b"PRIVATE=installed-nfc-neighbor\n"
            )
            (directory / ".env").chmod(0o640)
            for args in (
                ["init", "--initial-branch=main"],
                ["commit", "--allow-empty", "-m", f"installed corporate fixture {index}"],
            ):
                subprocess.run(
                    [
                        "/usr/bin/git",
                        "-C",
                        str(directory),
                        "-c",
                        "user.name=Installed fixture",
                        "-c",
                        "user.email=installed@example.invalid",
                        *args,
                    ],
                    check=True,
                    capture_output=True,
                    env={
                        **environment,
                        "GIT_CONFIG_NOSYSTEM": "1",
                        "GIT_CONFIG_GLOBAL": os.devnull,
                    },
                    timeout=15,
                )
            passport = native(
                binary, environment, ["project", "passport", "plan", "--root", str(directory)]
            )
            project_id = passport["plan"]["operation"]["passport"]["stable_id"]
            assert isinstance(project_id, str)
            project_ids.append(project_id)
            plan_file = root / f"registered-passport-{index}.json"
            plan_file.write_text(json.dumps(passport["plan"]), encoding="utf-8")
            native(
                binary,
                environment,
                [
                    "local",
                    "apply",
                    "--plan",
                    str(plan_file),
                    "--plan-digest",
                    passport["plan_digest"],
                ],
            )
        assert len(set(project_ids)) == 2
        physical = [(path.stat().st_dev, path.stat().st_ino) for path in (checkout, neighbor)]
        assert physical[0] != physical[1]

        def original_path(plan: dict[str, Any]) -> None:
            for path in (
                plan["checkout_root"],
                plan["change"]["snapshot"]["local_project"]["root"]["path"],
            ):
                assert path["display"] == str(neighbor)
                assert base64.b64decode(path["utf8_base64"], validate=True) == os.fsencode(checkout)
            assert plan["change"]["snapshot"]["local_project"]["local_project_id"] == project_ids[0]

        driver.navigate("corporate", keyboard=True)
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
        original_path(request)
        assert request["change"]["snapshot"]["target"]["remote_project_id"] == project
        authorize(driver, CHECKOUT_REVIEW, "Apply reviewed checkout change")
        driver.click(driver.button("Review link confirmation"))
        confirmation = public_plan(driver, CHECKOUT_REVIEW)
        original_path(confirmation)
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
        driver.navigate("tasks", keyboard=True)
        driver.click(driver.button("Inspect " + confirmation["operation_id"], HISTORY))
        scope = HISTORY + ' [aria-label="Original checkout operation"]'
        authorize(driver, scope, "Reconcile original outcome")
        root_field = field(driver, "Registered checkout for binding", scope=HISTORY)
        assert driver.read("return arguments[0].value;", root_field) == str(checkout)
        fill(driver, "Registered checkout for binding", str(neighbor), scope=HISTORY)
        driver.click(driver.button("Review original local binding", HISTORY))
        codes = driver.wait(
            lambda: driver.read(
                "return [...document.querySelectorAll(arguments[0]+' [role=alert]')]"
                ".flatMap(x=>x.textContent.match(/\\b(?:AI_STP_|DESKTOP_)[A-Z_]+|\\bCONTEXT_VIEW\\b/g)??[]);",
                HISTORY,
            ),
            "same-display physical checkout refusal",
        )
        assert set(codes) == {"AI_STP_PRECONDITION_FAILED"}
        # Reinspect through the actual read control, clearing the refusal and
        # proving that the original byte-preserving root is prefilled again.
        driver.click(driver.button("Inspect " + confirmation["operation_id"], HISTORY))
        root_field = field(driver, "Registered checkout for binding", scope=HISTORY)
        assert driver.read("return arguments[0].value;", root_field) == str(checkout)
        driver.click(driver.button("Review original local binding", HISTORY))
        next_scope = HISTORY + ' [aria-label="Review retained checkout next change"]'
        adoption = public_plan(driver, next_scope)
        original_path(adoption)
        assert adoption["change"]["request_operation_id"] == request["operation_id"]
        authorize(driver, next_scope, "Apply reviewed original checkout change")
        driver.wait(
            lambda: driver.read(
                "return document.querySelector(arguments[0]).textContent"
                ".includes('Original corporate project binding receipt saved.');",
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
        assert (neighbor / ".env").read_bytes() == b"PRIVATE=installed-nfc-neighbor\n"
        assert (neighbor / ".env").stat().st_mode & 0o777 == 0o640
        state_directory = native(binary, environment, ["state", "path"])["state_dir"]
        assert isinstance(state_directory, str) and Path(state_directory).is_absolute()
        registry = Path(state_directory) / "ai-stp-v2-state" / "registry.sqlite3"
        with closing(sqlite3.connect(f"file:{registry}?mode=ro", uri=True)) as db:
            row = db.execute(
                "SELECT p.state,p.organization_id,p.remote_project_id,r.request_operation_id,"
                "r.confirmation_operation_id,r.binding_operation_id,r.context_id,"
                "r.root_device,r.root_inode,p.local_project_id "
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
                str(physical[0][0]),
                str(physical[0][1]),
                project_ids[0],
            )
            assert db.execute(
                "SELECT count(*) FROM native_checkout_reservation WHERE local_project_id=?",
                (project_ids[1],),
            ).fetchone() == (0,)
            assert db.execute(
                "SELECT count(*) FROM project_link WHERE local_project_id=?", (project_ids[1],)
            ).fetchone() == (0,)
            assert db.execute(
                "SELECT count(*) FROM operation WHERE kind='corporate.project_link'"
            ).fetchone() == (3,)

        # Prepare an actual server-terminal link through the installed native
        # engine. The UI's separate local retirement never submits that unlink.
        def apply_unlink(planned: dict[str, Any]) -> dict[str, Any]:
            plan_path = root / f"installed-unlink-{planned['plan']['operation_id']}.json"
            plan_path.write_text(json.dumps(planned["plan"]), encoding="utf-8")
            plan_path.chmod(0o600)
            return cast(
                dict[str, Any],
                native(
                    binary,
                    environment,
                    [
                        "corporate",
                        "project",
                        "unlink",
                        "apply",
                        "--plan",
                        str(plan_path),
                        "--plan-digest",
                        planned["plan_digest"],
                    ],
                ),
            )

        unlink_request = native(
            binary,
            environment,
            [
                "corporate",
                "project",
                "unlink-request",
                "plan",
                "--context",
                company,
                "--binding-operation",
                adoption["operation_id"],
            ],
        )
        apply_unlink(unlink_request)
        unlink_confirmation = native(
            binary,
            environment,
            [
                "corporate",
                "project",
                "unlink-confirm",
                "plan",
                "--request-operation",
                unlink_request["plan"]["operation_id"],
            ],
        )
        assert apply_unlink(unlink_confirmation)["effect"]["link"]["state"] == "unlinked"
        driver.click(driver.button("Read checkout history", HISTORY))
        driver.click(driver.button("Inspect " + adoption["operation_id"], HISTORY))
        driver.click(driver.button("Review local binding retirement", HISTORY))
        retirement_scope = HISTORY + ' [aria-label="Review local binding retirement"]'
        retirement = public_plan(driver, retirement_scope)
        assert (
            retirement["snapshot"]["binding"]["source"]["operation_id"] == adoption["operation_id"]
        )
        assert (
            retirement["snapshot"]["remote_link"]["link_id"] == adopted["effect"]["link"]["link_id"]
        )
        assert retirement["snapshot"]["remote_link"]["state"] == "unlinked"
        assert (
            retirement["registry_schema_before"] == 59 and retirement["registry_schema_after"] == 60
        )
        authorize(driver, retirement_scope, "Apply reviewed local binding retirement")

        def retirement_visible() -> bool:
            return bool(
                driver.read(
                    "return document.querySelector(arguments[0]).textContent.includes("
                    "'This original local binding was retired. "
                    "Its adoption receipt is preserved.');",
                    HISTORY,
                )
            )

        driver.wait(retirement_visible, "actual local binding retirement")
        retired_history = native(
            binary,
            environment,
            [
                "corporate",
                "project",
                "link",
                "show",
                "--operation",
                adoption["operation_id"],
            ],
        )
        retired = retired_history["binding_retirement"]
        assert retired["operation_id"] == retirement["operation_id"]
        assert retired["state"] == "verified" and retired["local_binding_retired"]
        assert retired["remote_write_submitted"] is False and retired["tasks_changed"] is False
        assert retired["harness_files_changed"] is False
        assert retired_history["effect"] == adopted["effect"]
        with closing(sqlite3.connect(f"file:{registry}?mode=ro", uri=True)) as db:
            assert db.execute("PRAGMA user_version").fetchone() == (60,)
            assert db.execute("SELECT count(*) FROM native_checkout_reservation").fetchone() == (0,)
            assert db.execute("SELECT state FROM project_link").fetchone() == ("unlinked",)
            assert db.execute(
                "SELECT binding_operation_id,retirement_operation_id FROM native_binding_retirement"
            ).fetchone() == (
                adoption["operation_id"],
                retirement["operation_id"],
            )
        driver.close()
        driver = driver_type(driver_path, environment, root / "corporate-retired-driver.log")
        driver.start()
        driver.selected(company)
        assert (
            native(
                binary,
                environment,
                ["corporate", "project", "link", "show", "--operation", adoption["operation_id"]],
            )
            == retired_history
        )
        driver.navigate("tasks", keyboard=True)
        inspection = driver.button("Inspect " + adoption["operation_id"], HISTORY)
        # Observe one real WebDriver activation without replaying it or replacing
        # the UI/IPC. A successful WebDriver reply alone is not a DOM-event proof.
        driver.read(
            "const node=arguments[0];window.__installedRetirementInspection={"
            "clicks:0,trusted:0,disabledAtClick:false,contextLoadingAtClick:false};"
            "node.addEventListener('click',event=>{"
            "const count=window.__installedRetirementInspection;"
            "count.clicks=Math.min(16,count.clicks+1);"
            "if(event.isTrusted)count.trusted=Math.min(16,count.trusted+1);"
            "count.disabledAtClick=node.disabled;"
            "count.contextLoadingAtClick=!!document.querySelector("
            "'section[aria-label=\"Context view\"] select')?.disabled;"
            "},{capture:true,passive:true});",
            inspection,
        )
        driver.click(inspection)
        try:
            driver.wait(retirement_visible, "retirement history after installed app restart")
        except ValueError:
            # Print closed categories/booleans only, never private DOM, IDs,
            # paths, plans, replies or the driver's free-form error message.
            if driver.last_response_ok:
                observed = driver.read(
                    "const root=document.querySelector(arguments[0]);"
                    "const exact=root?.querySelector("
                    "'[aria-label=\"Original checkout operation\"]');"
                    "const retired='This original local binding was retired. '"
                    "+'Its adoption receipt is preserved.';"
                    "const codes=[...root?.querySelectorAll('[role=alert] span')||[]]"
                    ".slice(0,4).map(node=>arguments[2].includes(node.textContent.trim())"
                    "?node.textContent.trim():'other');"
                    "return {click:window.__installedRetirementInspection,"
                    "historyPresent:!!root,originalPresent:!!exact,"
                    "originalMatches:!!exact?.querySelector('p')?.textContent.includes(arguments[1]),"
                    "retirementVisible:!!root?.textContent.includes(retired),"
                    "originalBindingVisible:!!root?.textContent.includes("
                    "'Original corporate project binding receipt saved.'),"
                    "pending:!!root?.textContent.includes("
                    "'Reading the original checkout operation'),"
                    "refused:!!root?.querySelector('[role=alert]'),errorCodes:codes};",
                    HISTORY,
                    adoption["operation_id"],
                    [
                        "CONTEXT_VIEW",
                        "IPC_THROW",
                        "DESKTOP_TRANSPORT",
                        "AI_STP_VALIDATION_ERROR",
                        "AI_STP_NOT_FOUND",
                        "AI_STP_PRECONDITION_FAILED",
                        "AI_STP_CONFLICT",
                        "AI_STP_DEPENDENCY_UNAVAILABLE",
                        "AI_STP_INTERNAL",
                    ],
                )
                print(json.dumps({"diagnostic": "installed_retirement_restart", "state": observed}))
            raise
        actual_click = driver.read("return window.__installedRetirementInspection;")
        assert actual_click == {
            "clicks": 1,
            "trusted": 1,
            "disabledAtClick": False,
            "contextLoadingAtClick": False,
        }
        assert not driver.read(
            "return [...document.querySelectorAll(arguments[0]+' button')]"
            ".some(x=>x.textContent==='Review local binding retirement');",
            HISTORY,
        )
        assert (
            native(
                binary,
                environment,
                ["corporate", "project", "link", "show", "--operation", adoption["operation_id"]],
            )
            == retired_history
        )
        for directory, expected in [
            (checkout, b"PRIVATE=installed-corporate-unowned\n"),
            (neighbor, b"PRIVATE=installed-nfc-neighbor\n"),
        ]:
            assert (directory / ".env").read_bytes() == expected
            assert (directory / ".env").stat().st_mode & 0o777 == 0o640
        assert canary.read_bytes() == b"# Unowned installed corporate canary\n"
        assert canary.stat().st_mode & 0o777 == 0o640
        assert (checkout.stat().st_dev, checkout.stat().st_ino) == physical[0]
        driver, location_proof = installed_locations(
            driver,
            root=root,
            checkout=checkout,
            registry=registry,
            binary=binary,
            environment=environment,
            company=company,
            project=project,
            driver_path=driver_path,
            driver_type=driver_type,
            native=native,
        )
        return {
            **location_proof,
            "schema_version": 1,
            "evidence_type": "installed_linux_corporate_checkout",
            "consumer_commit": os.environ["GITHUB_SHA"],
            "installed_cli_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "link_id": adopted["effect"]["link"]["link_id"],
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
            "exact_terminal_native_unlink": True,
            "separately_reviewed_local_binding_retirement": True,
            "retirement_receipt_after_installed_restart": True,
            "retirement_restart_trusted_inspection": True,
            "restart_native_retirement_readback_matches": True,
            "original_adoption_evidence_preserved": True,
            "writer_epoch": 60,
            "unowned_files_preserved": True,
            "distinct_nfd_nfc_roots": True,
            "same_display_checkout_substitution_refused": True,
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
                    f"/v1/organizations/{organization}/project-unlink-plans",
                    f"/v1/projects/links/{proof['link_id']}",
                    f"/v1/organizations/{organization}/project-link-plans",
                    "/v1/projects/links",
                    f"/v1/organizations/{organization}/project-unlink-plans",
                    f"/v1/projects/links/{proof['location_link_id']}",
                ]
                async with app.state.sessionmaker() as db:
                    assert await db.scalar(select(func.count()).select_from(ProjectLinkPlan)) == 2
                    assert await db.scalar(select(func.count()).select_from(ProjectLink)) == 2
                    assert await db.scalar(select(func.count()).select_from(ProjectUnlinkPlan)) == 2
                    links = (await db.scalars(select(ProjectLink))).all()
                    assert {link.id for link in links} == {
                        proof["link_id"],
                        proof["location_link_id"],
                    }
                    assert all(
                        link.state == "unlinked" and link.organization_id == organization
                        for link in links
                    )
                proof.update(
                    actual_api_postgresql=True,
                    committed_mutation_posts=6,
                    committed_mutation_requests=8,
                )
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
