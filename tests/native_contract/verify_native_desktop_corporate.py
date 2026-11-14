"""Installed native corporate profiles and checkout against actual API/PostgreSQL."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import shutil
import socket
import stat
import tempfile
from pathlib import Path
from typing import Any, cast

import uvicorn
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from tests.native_contract.verify_checkout import LostAcknowledgements
from tests.support.api_settings import close_api_log_files, make_settings, make_test_auth
from tests.support.corporate_fixture import create_checkout_fixture, seed_corporate
from tests.support.native_desktop_broker import PROTOCOL, run_owner
from tests.support.native_files import file_protection
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


CHECKOUT_CONTROLS = frozenset(
    {
        "committed_checkout_preview",
        "request_exact_plan_and_confirmation",
        "confirmation_exact_plan_and_confirmation",
        "committed_reply_lost",
        "original_operation_reconciled_after_restart",
        "binding_exact_plan_and_confirmation",
        "original_link_and_device_preserved",
        "unowned_checkout_bytes_and_identity_preserved",
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
    checkout = root / "checkout"
    canary = b"PRIVATE=installed-native-corporate-unowned\n"
    git = create_checkout_fixture(checkout, canary, dict(os.environ))
    original_root = (checkout.stat().st_dev, checkout.stat().st_ino)
    original_protection = file_protection(checkout / ".env")
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
            faults = LostAcknowledgements(app)
            faults.lose_next = "/v1/projects/links"
            server = uvicorn.Server(
                uvicorn.Config(faults, lifespan="off", access_log=False, log_level="error")
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
                    "checkout_root": str(checkout),
                    "git_executable": str(git),
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
                geometry = personal["normal_window_controls"]
                assert set(geometry) == {
                    "first_normal_window_within_work_area",
                    "oversized_normal_state_restored_within_work_area",
                    "context_and_preferences_survive_geometry_recovery",
                }
                assert all(value is True for value in geometry.values())
                assert observed["schema_version"] == 2 and observed["source_sha"] == source
                assert observed["desktop_process_stopped"] is True
                assert set(observed["controls"]) == CONTROLS
                assert all(value is True for value in observed["controls"].values())
                assert set(observed["checkout_controls"]) == CHECKOUT_CONTROLS
                assert all(value is True for value in observed["checkout_controls"].values())
                assert faults.committed_acknowledgements_lost == 1
                assert (checkout / ".env").read_bytes() == canary
                assert file_protection(checkout / ".env") == original_protection
                assert (checkout.stat().st_dev, checkout.stat().st_ino) == original_root
                binding = observed["checkout"]
                assert set(binding) == {
                    "request_operation_id",
                    "confirmation_operation_id",
                    "adoption_operation_id",
                    "context_id",
                    "local_project_id",
                    "link_id",
                }
                assert all(
                    isinstance(value, str) and 1 <= len(value) <= 128 for value in binding.values()
                )
                assert (
                    len(
                        {
                            binding[key]
                            for key in (
                                "request_operation_id",
                                "confirmation_operation_id",
                                "adoption_operation_id",
                            )
                        }
                    )
                    == 3
                )
                device_id = observed["enrolled_device_id"]
                assert isinstance(device_id, str) and 1 <= len(device_id) <= 128
                async with app.state.sessionmaker() as db:
                    device = await db.get(Device, device_id)
                    assert device is not None and device.account_id == account
                    assert device.state == "active"
                    await set_tenant_scope(db, organization)
                    assert await db.scalar(select(func.count()).select_from(ProjectLink)) == 1
                    link = await db.get(ProjectLink, binding["link_id"])
                    assert link is not None and link.state == "linked"
                    assert (
                        link.organization_id == organization and link.remote_project_id == project
                    )
                    assert link.actor_account_id == account and link.device_id == device_id
                    assert link.local_project_id == binding["local_project_id"]
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
                    "schema_version": 2,
                    "evidence_kind": "installed_native_corporate_profile_checkout_gui",
                    "source_sha": source,
                    "fixture_run_id": os.environ["GITHUB_RUN_ID"],
                    "fixture_run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
                    "platform": os.environ["RUNNER_OS"],
                    **{
                        key: personal[key]
                        for key in ["installer_sha256", "app_sha256", "cli_sha256", "cli_version"]
                    },
                    "normal_window_controls": geometry,
                    "corporate_profile_controls": observed["controls"],
                    "corporate_checkout_controls": observed["checkout_controls"],
                    "committed_acknowledgements_lost": faults.committed_acknowledgements_lost,
                    "synthetic_browser_approvals": approvals,
                    "actual_api_postgresql": True,
                    "reading_context_sends_no_heartbeat": True,
                    "desktop_process_stopped": True,
                    "live_sso_account_linking_qualified": False,
                    "native_corporate_checkout_gui_qualified": True,
                    "release_authorized": False,
                }
            finally:
                server.should_exit = True
                await asyncio.wait_for(serving, timeout=30)


def main() -> None:
    disposable_runner()
    assert os.environ["RUNNER_OS"] in {"macOS", "Windows"}
    assert os.environ["GITHUB_WORKFLOW"] in {"check", "desktop"}
    assert os.environ["GITHUB_EVENT_NAME"] in {"push", "workflow_dispatch"}
    assert not os.environ.get("AI_STP_DESKTOP_DIAGNOSTIC_SOURCE")
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
            shutil.rmtree(root, onexc=writable_and_retry)


def writable_and_retry(function: Any, path: str, _error: BaseException) -> None:
    """Git writes its objects read-only, which Windows refuses to unlink."""
    Path(path).chmod(stat.S_IWRITE)
    function(path)


if __name__ == "__main__":
    main()
