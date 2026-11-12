"""Installed native corporate profile GUI against actual API and PostgreSQL."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any, cast

import uvicorn
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from tests.support.api_settings import close_api_log_files, make_settings, make_test_auth
from tests.support.corporate_fixture import seed_corporate
from tests.support.native_desktop_broker import PROTOCOL, run_owner
from tests.support.native_postgres import cluster
from tests.support.native_runner import disposable_runner, report_stage
from tests.support.postgres import isolated_database

from ai_stp_api.app import create_app
from ai_stp_api.slices.auth.device_flow import approve_device_authorization
from ai_stp_platform.heartbeat_models import InstallationHeartbeat, InstallationHeartbeatEvent
from ai_stp_platform.models import Device
from ai_stp_platform.organization_models import ProjectLink
from ai_stp_platform.tenant_scope import set_tenant_scope

CONTROLS = frozenset(
    {
        "installed_personal_journey_retained",
        "connection_exact_plan_and_confirmation",
        "original_pending_confirmation_after_navigation",
        "device_bound_account_session",
        "corporate_context_exact_plan_and_confirmation",
        "personal_and_corporate_contexts_coexist",
        "context_view_selection_explicit",
        "corporate_context_survives_restart",
        "original_device_survives_restart",
        "original_account_and_origin_preserved",
    }
)


def read_result(path: Path) -> dict[str, Any]:
    assert path.is_file() and not path.is_symlink(), "Native owner did not retain its result"
    with path.open("rb") as source:
        payload = source.read(64 * 1024 + 1)
    assert len(payload) <= 64 * 1024, "Native owner result exceeded its bound"
    value = json.loads(payload)
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


async def prove(root: Path, database_url: str) -> dict[str, Any]:
    source = os.environ["GITHUB_SHA"]
    nonce = secrets.token_hex(32)
    private_result = root / "native-corporate-journey.json"
    personal_result = Path(os.environ["RUNNER_TEMP"]) / "installed-personal-desktop.json"
    assert not personal_result.exists() and not private_result.exists()
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
                            raise AssertionError("Native corporate API stopped before readiness")
                        await asyncio.sleep(0.01)
                account, organization, project = await seed_corporate(app, origin)
                configuration = {
                    "protocol": PROTOCOL,
                    "nonce": nonce,
                    "source_sha": source,
                    "origin": origin,
                    "account_id": account,
                    "organization_id": organization,
                    "project_id": project,
                    "result_path": str(private_result),
                }
                fixture = root / "native-owner.json"
                with fixture.open("x", encoding="utf-8") as output:
                    json.dump(configuration, output)
                fixture.chmod(0o600)
                loop = asyncio.get_running_loop()

                async def approve(code: str) -> None:
                    async with app.state.sessionmaker() as db:
                        await approve_device_authorization(db, user_code=code, account_id=account)
                        await db.commit()

                def approve_from_owner(code: str) -> None:
                    asyncio.run_coroutine_threadsafe(approve(code), loop).result(timeout=15)

                environment = dict(os.environ)
                for name in ["AI_STP_TEST_DB_URL", "AI_STP_DB_URL"]:
                    environment.pop(name, None)
                environment["AI_STP_NATIVE_DESKTOP_FIXTURE"] = str(fixture)
                report_stage("native-installed-personal-and-corporate-gui")
                if os.environ["RUNNER_OS"] == "Windows":
                    arguments = [
                        "pwsh",
                        "-STA",
                        "-NoProfile",
                        "-NonInteractive",
                        "-File",
                        str(
                            Path(".github/scripts/qualify-installed-windows-desktop.ps1").resolve()
                        ),
                        "-Bundle",
                        str(Path("apps/desktop/src-tauri/target/release/bundle").resolve()),
                        "-Source",
                        source,
                        "-Output",
                        str(personal_result),
                    ]
                else:
                    arguments = ["/bin/bash", ".github/scripts/qualify-installed-native-desktop.sh"]
                approvals = await asyncio.to_thread(
                    run_owner,
                    arguments,
                    environment=environment,
                    errors=root / "native-owner-private.log",
                    nonce=nonce,
                    approve=approve_from_owner,
                )
                assert approvals == 1
                observed = read_result(private_result)
                personal = read_result(personal_result)
                assert personal["source_sha"] == source
                assert personal["installed_personal_workspace_restart"] is True
                assert len(personal["personal_controls"]) == 10
                assert all(value is True for value in personal["personal_controls"].values())
                assert observed["schema_version"] == 1 and observed["source_sha"] == source
                assert observed["desktop_process_stopped"] is True
                assert set(observed["controls"]) == CONTROLS
                assert all(value is True for value in observed["controls"].values())
                device_id = observed["enrolled_device_id"]
                assert isinstance(device_id, str) and 1 <= len(device_id) <= 128
                async with app.state.sessionmaker() as db:
                    device = await db.get(Device, device_id)
                    assert device is not None and device.account_id == account
                    assert device.state == "active"
                    assert await db.scalar(select(func.count()).select_from(ProjectLink)) == 0
                    await set_tenant_scope(db, organization)
                    for model in [InstallationHeartbeat, InstallationHeartbeatEvent]:
                        assert (
                            await db.scalar(
                                select(func.count())
                                .select_from(model)
                                .where(model.organization_id == organization)
                            )
                            == 0
                        )
                return {
                    "schema_version": 1,
                    "evidence_kind": "installed_native_corporate_profile_gui",
                    "source_sha": source,
                    "fixture_run_id": os.environ["GITHUB_RUN_ID"],
                    "fixture_run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
                    "platform": os.environ["RUNNER_OS"],
                    **{
                        key: personal[key]
                        for key in ["installer_sha256", "app_sha256", "cli_sha256", "cli_version"]
                    },
                    "corporate_profile_controls": observed["controls"],
                    "synthetic_browser_approvals": approvals,
                    "actual_api_postgresql": True,
                    "reading_context_sends_no_heartbeat": True,
                    "desktop_process_stopped": True,
                    "live_sso_account_linking_qualified": False,
                    "native_corporate_checkout_gui_qualified": False,
                    "release_authorized": False,
                }
            finally:
                server.should_exit = True
                await asyncio.wait_for(serving, timeout=30)


def check_native_controller() -> None:
    """Expose compiler/parser diagnostics before private runtime output begins."""
    if os.environ["RUNNER_OS"] == "macOS":
        arguments = [
            "swiftc",
            "-typecheck",
            ".github/scripts/qualify-installed-macos-desktop.swift",
        ]
    else:
        arguments = [
            "pwsh",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "$tokens = $null; $errors = $null; "
            "[void][System.Management.Automation.Language.Parser]::ParseFile("
            "(Join-Path (Get-Location) '.github/scripts/qualify-installed-windows-desktop.ps1'),"
            "[ref]$tokens,[ref]$errors); "
            "if ($errors.Count) { $errors | ForEach-Object { Write-Error $_ }; exit 1 }",
        ]
    subprocess.run(arguments, check=True, timeout=120)


def main() -> None:
    disposable_runner()
    assert os.environ["RUNNER_OS"] in {"macOS", "Windows"}
    assert os.environ["GITHUB_WORKFLOW"] in {"check", "desktop"}
    assert os.environ["GITHUB_EVENT_NAME"] in {"push", "workflow_dispatch"}
    assert not os.environ.get("AI_STP_DESKTOP_DIAGNOSTIC_SOURCE")
    check_native_controller()
    temporary = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    root = Path(tempfile.mkdtemp(prefix="ai-stp-native-desktop-corporate-", dir=temporary))
    root.chmod(0o700)
    saved = {key: os.environ.get(key) for key in ["AI_STP_TEST_DB_URL", "AI_STP_DB_URL"]}
    complete = False
    try:
        with cluster() as (template, database):
            os.environ["AI_STP_TEST_DB_URL"] = template
            with isolated_database("The owned native PostgreSQL cluster is required") as url:
                os.environ["AI_STP_DB_URL"] = url
                command.upgrade(Config("alembic.ini"), "head")
                proof = asyncio.run(prove(root, url))
        proof["database"] = database
        proof["database_process_stopped"] = True
        target = temporary / "installed-native-corporate-desktop.json"
        assert not target.exists()
        with target.open("x", encoding="utf-8") as output:
            json.dump(proof, output, indent=2)
            output.write("\n")
        complete = True
        report_stage("native-corporate-profile-gui-passed")
    finally:
        close_api_log_files(root / "api")
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        # Refused ownership never authorizes deleting potentially live fixture state.
        if complete:
            shutil.rmtree(root)


if __name__ == "__main__":
    main()
