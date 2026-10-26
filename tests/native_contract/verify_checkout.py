"""Real native checkout mutations, lost acknowledgements and device replacement.

The wrapper withholds a response only after the actual API transaction commits.
It supplies neither authorization nor a project-link result to the native client.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from collections.abc import Awaitable, Callable
from contextlib import closing
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from tests.native_contract.verify_ownership import apply

from ai_stp_foundation.envelope import ErrorEnvelope
from ai_stp_platform.models import Device
from ai_stp_platform.organization_models import (
    CorporateAssignmentDistribution,
    OrganizationMembership,
    ProjectLink,
    ProjectLinkPlan,
)

Native = Callable[..., Awaitable[dict[str, Any]]]


class LostAcknowledgements:
    """Bounded fixture faults outside the unchanged production ASGI application."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.lose_next: str | None = None
        self.hide_outcome = False
        self.writes: list[str] = []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path, method = scope["path"], scope["method"]
        if self.hide_outcome and method == "GET" and "/project-link-plan-requests/" in path:
            await JSONResponse(
                {"schema_version": 1, "ok": False, "error": {"code": "AI_STP_NOT_FOUND"}},
                status_code=404,
            )(scope, receive, send)
            return
        mutation = method == "POST" and (
            path.endswith("/project-link-plans") or path == "/v1/projects/links"
        )
        if not mutation:
            await self.app(scope, receive, send)
            return
        self.writes.append(path)
        if self.lose_next != path:
            await self.app(scope, receive, send)
            return
        self.lose_next = None
        messages: list[Message] = []

        async def retain(message: Message) -> None:
            messages.append(message)
            assert sum(len(item.get("body", b"")) for item in messages) <= 65536

        await self.app(scope, receive, retain)
        assert messages and 200 <= messages[0]["status"] < 300
        # Db's function-scoped dependency committed before response.start.
        await JSONResponse({}, status_code=503)(scope, receive, send)


async def journey(
    *,
    binary: Path,
    home: Path,
    state: Path,
    root: Path,
    app: Any,
    faults: LostAcknowledgements,
    run: Native,
    enact: Native,
    login: Callable[..., Awaitable[None]],
    refused: Callable[..., Awaitable[ErrorEnvelope]],
    organization: str,
    project: str,
    account: str,
    connection: str | None,
    device: str,
    offline_context: str,
    git_executable: str,
    label: str,
) -> None:
    checkout = root / f"checkout-{label}"
    checkout.mkdir()
    canary = checkout / ".env"
    canary.write_bytes(b"PRIVATE=checkout-unowned-canary\n")
    canary.chmod(0o640)
    environment = dict(
        os.environ,
        HOME=str(home),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
    )
    for arguments in (
        ["init", "--initial-branch=main"],
        ["commit", "--allow-empty", "-m", "native checkout mutation fixture"],
    ):
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
            await asyncio.wait_for(process.communicate(), timeout=15)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise
        assert process.returncode == 0
    passport = await run("project", "passport", "plan", "--root", str(checkout))
    await enact(passport, "local", "apply")
    local_project = passport["plan"]["operation"]["passport"]["stable_id"]
    qualifier = ["--connection", connection] if connection else ["--legacy-account"]
    context_plan = await run(
        "context",
        "create",
        "plan",
        "--label",
        label,
        *qualifier,
        "--organization",
        organization,
    )
    context = (await enact(context_plan, "context", "apply"))["context_id"]
    selected = await run("context", "select", "plan", "--context", offline_context)
    await enact(selected, "context", "apply")
    selected_before = (await run("context", "list"))["selected"]
    original_identity = await run("device", "show")
    writes_before = len(faults.writes)

    async def reject_plan(planned: dict[str, Any], *, reader: str | None = None) -> None:
        path = home / "checkout-plan.json"
        path.write_text(json.dumps(planned["plan"]), encoding="utf-8")
        await refused(
            binary,
            home,
            [
                "corporate",
                "project",
                "link",
                "apply",
                "--plan",
                str(path),
                "--plan-digest",
                planned["plan_digest"],
                *(["--context", reader] if reader else []),
            ],
        )

    async def counts() -> tuple[int, int]:
        async with app.state.sessionmaker() as db:
            values = (
                await db.scalar(select(func.count()).select_from(ProjectLinkPlan)),
                await db.scalar(select(func.count()).select_from(ProjectLink)),
            )
            assert isinstance(values[0], int) and isinstance(values[1], int)
            return values[0], values[1]

    before = await counts()
    planned = await run(
        "corporate",
        "project",
        "link-request",
        "plan",
        "--root",
        str(checkout),
        "--context",
        context,
        "--project",
        project,
        "--git-executable",
        git_executable,
    )
    assert await counts() == before and len(faults.writes) == writes_before
    original_request = planned["plan"]["operation_id"]
    faults.lose_next = f"/v1/organizations/{organization}/project-link-plans"
    await reject_plan(planned)
    assert faults.lose_next is None
    assert await counts() == (before[0] + 1, before[1])
    status = await run("corporate", "project", "link", "show", "--operation", original_request)
    assert status["state"] == "applying" and status["plan"] == planned["plan"]
    faults.hide_outcome = True
    try:
        await reject_plan(planned)
    finally:
        faults.hide_outcome = False
    assert (await run("corporate", "project", "link", "show", "--operation", original_request))[
        "state"
    ] == "applying"
    requested = await enact(planned, "corporate", "project", "link", "apply")
    assert requested["state"] == "completed" and len(faults.writes) == writes_before + 1
    server_plan = requested["effect"]["server_plan"]
    ready = await run(
        "corporate",
        "project",
        "link-settlement",
        "--context",
        context,
        "--plan-id",
        server_plan["plan_id"],
    )
    assert ready["observation"]["data"]["plan"] == server_plan
    assert ready["observation"]["data"]["state"] == "ready"
    assert ready["observation"]["data"]["link"] is None
    assert await counts() == (before[0] + 1, before[1])
    confirmation = await run(
        "corporate",
        "project",
        "link-confirm",
        "plan",
        "--request-operation",
        original_request,
        "--git-executable",
        git_executable,
    )
    unadmitted = await run(
        "corporate",
        "project",
        "link-confirm",
        "plan",
        "--request-operation",
        original_request,
        "--git-executable",
        git_executable,
    )
    confirmation_id = confirmation["plan"]["operation_id"]
    faults.lose_next = "/v1/projects/links"
    await reject_plan(confirmation)
    assert faults.lose_next is None and await counts() == (before[0] + 1, before[1] + 1)
    registry = state / "ai-stp-v2-state" / "registry.sqlite3"

    def reservation() -> tuple[Any, ...]:
        with closing(sqlite3.connect(f"file:{registry}?mode=ro", uri=True)) as db:
            assert db.execute("PRAGMA user_version").fetchone() == (57,)
            value = db.execute(
                "SELECT request_operation_id,confirmation_operation_id,binding_operation_id "
                "FROM native_checkout_reservation WHERE local_project_id=?",
                (local_project,),
            ).fetchone()
            assert value is not None
            return value

    assert reservation() == (original_request, confirmation_id, None)
    async with app.state.sessionmaker() as db:
        remote = await db.get(Device, device)
        assert remote is not None
        remote.state = "revoked"
        await db.commit()
    selector = ["--connection", connection] if connection else []
    refresh = await run("account", "plan", "--action", "refresh", *selector)
    assert (await enact(refresh, "account", "apply"))["outcome"] == "revoked"
    if connection:
        recovery = await run(
            "account",
            "connections",
            "recovery",
            "plan",
            "--connection",
            connection,
            "--label",
            f"Recovered {label}",
        )
        assert recovery["plan"]["schema_version"] == 4
        checkpoints = recovery["plan"]["interrupted_checkout_links"]
        prepared = await enact(recovery, "account", "connections", "recovery", "apply")
        assert prepared["state"] == "sign_in_required"
        replacement = prepared["replacement_connection_id"]
        recovery_prefix = ["account", "connections", "recovery", "apply"]
    else:
        recovery = await run("account", "plan", "--action", "recover")
        checkpoints = recovery["plan"]["recovery"]["interrupted_checkout_links"]
        assert (await enact(recovery, "account", "apply"))["outcome"] == "device_replaced"
        replacement = None
        recovery_prefix = ["account", "apply"]
    assert [item["operation_id"] for item in checkpoints] == [confirmation_id]
    stopped = await run("corporate", "project", "link", "show", "--operation", confirmation_id)
    assert stopped["state"] == "interrupted" and stopped["interrupted"]
    assert reservation() == (original_request, confirmation_id, None)
    await reject_plan(unadmitted)
    await reject_plan(confirmation)
    await login(account, replacement)
    next_qualifier = ["--connection", replacement] if replacement else ["--legacy-account"]
    replacement_plan = await run(
        "context",
        "create",
        "plan",
        "--label",
        f"Replacement {label}",
        *next_qualifier,
        "--organization",
        organization,
    )
    reader = (await enact(replacement_plan, "context", "apply"))["context_id"]
    # A replacement context may read an admitted original effect, never admit
    # the unused confirmation plan belonging to the previous device.
    await reject_plan(unadmitted, reader=reader)
    displaced = checkout.with_name(checkout.name + "-displaced")
    checkout.rename(displaced)
    try:
        settled = await apply(
            binary,
            home,
            confirmation,
            ["corporate", "project", "link", "apply", "--context", reader],
        )
        assert settled["state"] == "completed" and settled["interrupted"]
        assert settled["effect"]["outcome_reader"]["device_id"] != device
        assert await enact(confirmation, "corporate", "project", "link", "apply") == settled
        assert not checkout.exists()
        # Replaying the original recovery still validates its retained first
        # interruption after the unknown effect has been positively reconciled.
        await enact(recovery, *recovery_prefix)
    finally:
        displaced.rename(checkout)
    adoption = await run(
        "corporate",
        "project",
        "link-adopt",
        "plan",
        "--request-operation",
        original_request,
        "--root",
        str(checkout),
        "--context",
        reader,
        "--git-executable",
        git_executable,
    )
    adopted = await enact(adoption, "corporate", "project", "link", "apply")
    assert adopted["state"] == "completed" and not adopted["installation_authority"]
    assert reservation() == (original_request, confirmation_id, adoption["plan"]["operation_id"])
    applied = await run(
        "corporate",
        "project",
        "link-settlement",
        "--context",
        reader,
        "--plan-id",
        server_plan["plan_id"],
    )
    assert applied["observation"]["data"]["plan"] == server_plan
    assert applied["observation"]["data"]["state"] == "applied"
    assert applied["observation"]["data"]["link"] == adopted["effect"]["link"]
    assert reservation() == (original_request, confirmation_id, adoption["plan"]["operation_id"])
    assert len(faults.writes) == writes_before + 2
    assert await counts() == (before[0] + 1, before[1] + 1)
    assert (await run("context", "list"))["selected"] == selected_before
    if connection:
        assert await run("device", "show") == original_identity
    else:
        assert (await run("device", "show"))["device_id"] != original_identity["device_id"]
    assert canary.read_bytes() == b"PRIVATE=checkout-unowned-canary\n"
    assert canary.stat().st_mode & 0o777 == 0o640
    async with app.state.sessionmaker() as db:
        assert (
            await db.scalar(select(func.count()).select_from(CorporateAssignmentDistribution)) == 0
        )
    print(
        json.dumps(
            {
                "native_checkout_recovery": label,
                "result": "passed",
                "committed_mutation_posts": 2,
                "installation_authority": False,
            }
        ),
        flush=True,
    )


async def qualify(
    *,
    binary: Path,
    home: Path,
    state: Path,
    root: Path,
    app: Any,
    faults: LostAcknowledgements,
    run: Native,
    enact: Native,
    login: Callable[..., Awaitable[None]],
    refused: Callable[..., Awaitable[ErrorEnvelope]],
    organization: str,
    project: str,
    account: str,
    connection: str,
    device: str,
    offline_context: str,
    git_executable: str,
    old_recoveries: list[dict[str, Any]],
) -> None:
    async with app.state.sessionmaker() as db:
        membership = await db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization,
                OrganizationMembership.account_id == account,
            )
        )
        assert membership is not None
        membership.state, membership.revision = "active", membership.revision + 1
        await db.commit()
    # The older fixture deliberately removed the first replacement's key.
    # Capture its refusal at format 56: a format upgrade must neither hide
    # its completed receipt nor silently regenerate that missing key.
    missing_recovery = old_recoveries[0]
    old_key = (
        state
        / "ai-stp-v2-connections"
        / ("device-key." + missing_recovery["plan"]["replacement"]["device_id"])
    )
    assert not old_key.exists()
    old_plan = home / "older-recovery-plan.json"
    old_plan.write_text(json.dumps(missing_recovery["plan"]), encoding="utf-8")
    old_arguments = [
        "account",
        "connections",
        "recovery",
        "apply",
        "--plan",
        str(old_plan),
        "--plan-digest",
        missing_recovery["plan_digest"],
    ]
    baseline_refusal = await refused(binary, home, old_arguments)
    assert baseline_refusal.error.code == "AI_STP_PRECONDITION_FAILED"
    before_receipts = {
        item["plan"]["operation_id"]: item
        for item in (await run("account", "connections", "recovery", "list"))["recoveries"]
    }
    common: dict[str, Any] = {
        "binary": binary,
        "home": home,
        "state": state,
        "root": root,
        "app": app,
        "faults": faults,
        "run": run,
        "enact": enact,
        "login": login,
        "refused": refused,
        "organization": organization,
        "project": project,
        "account": account,
        "offline_context": offline_context,
        "git_executable": git_executable,
    }
    await journey(**common, connection=connection, device=device, label="named")
    after_refusal = await refused(binary, home, old_arguments)
    assert after_refusal.error == baseline_refusal.error and not old_key.exists()
    after_receipts = {
        item["plan"]["operation_id"]: item
        for item in (await run("account", "connections", "recovery", "list"))["recoveries"]
    }
    for operation, receipt in before_receipts.items():
        assert after_receipts[operation] == receipt
    # Plans with their retained key still present keep their original digest
    # and replay successfully after format57; key absence keeps its refusal.
    for recovery in old_recoveries[1:]:
        assert (await enact(recovery, "account", "connections", "recovery", "apply"))[
            "state"
        ] == "authorized"
    legacy_device = (await run("device", "show"))["device_id"]
    await journey(**common, connection=None, device=legacy_device, label="root")
    print(
        json.dumps(
            {
                "native_checkout_http": "passed",
                "registry_schema": 57,
                "actual_server_transactions": True,
                "lost_create_and_confirm_replies": 4,
                "new_checkout_mutation_posts": 4,
                "unknown_404_remains_pending": True,
                "recovery": ["named_enrollment", "root_device"],
                "replacement_reads_original_only": True,
                "old_format56_receipts_preserved": True,
                "old_present_key_replay": True,
                "old_missing_key_replay": "same_refusal_no_recreation",
                "active_binding_adoption": True,
                "harness_configuration_writes": 0,
                "installation_authority": False,
            }
        ),
        flush=True,
    )
