"""Real API settlement, native retirement and exact forward-registry recovery."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from collections.abc import Awaitable, Callable
from contextlib import closing
from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self
from unittest.mock import patch

from sqlalchemy import func, select

from ai_stp_foundation.envelope import ErrorEnvelope
from ai_stp_platform.models import Device
from ai_stp_platform.organization_models import ProjectLink, ProjectLinkPlan

if TYPE_CHECKING:
    from tests.native_contract.verify_checkout import LostAcknowledgements, Native


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
    offline_context: str,
    git_executable: str,
    context: str,
    connection: str,
) -> None:
    registry = state / "ai-stp-v2-state" / "registry.sqlite3"

    def reservations() -> list[tuple[Any, ...]]:
        with closing(sqlite3.connect(f"file:{registry}?mode=ro", uri=True)) as db:
            return db.execute(
                "SELECT * FROM native_checkout_reservation ORDER BY request_operation_id"
            ).fetchall()

    def schema() -> int:
        with closing(sqlite3.connect(f"file:{registry}?mode=ro", uri=True)) as db:
            return int(db.execute("PRAGMA user_version").fetchone()[0])

    async def counts() -> tuple[int, int]:
        async with app.state.sessionmaker() as db:
            plans = await db.scalar(select(func.count()).select_from(ProjectLinkPlan))
            links = await db.scalar(select(func.count()).select_from(ProjectLink))
            assert isinstance(plans, int) and isinstance(links, int)
            return plans, links

    async def reject(planned: dict[str, Any], *, retirement: bool = True) -> ErrorEnvelope:
        path = home / "checkout-retirement-reviewed.json"
        path.write_text(json.dumps(planned["plan"]), encoding="utf-8")
        return await refused(
            binary,
            home,
            [
                "corporate",
                "project",
                "link-retire" if retirement else "link",
                "apply",
                "--plan",
                str(path),
                "--plan-digest",
                planned["plan_digest"],
            ],
        )

    async def checkout(label: str) -> Path:
        path = root / ("retirement-" + label)
        path.mkdir()
        (path / ".env").write_bytes(b"PRIVATE=retirement-unowned-canary\n")
        (path / ".env").chmod(0o640)
        for arguments in (
            ["init", "--initial-branch=main"],
            ["commit", "--allow-empty", "-m", "native retirement fixture"],
        ):
            process = await asyncio.create_subprocess_exec(
                git_executable,
                "-C",
                str(path),
                "-c",
                "user.name=Native checkout fixture",
                "-c",
                "user.email=checkout@example.invalid",
                *arguments,
                env={
                    **os.environ,
                    "HOME": str(home),
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": os.devnull,
                },
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
        await enact(await run("project", "passport", "plan", "--root", str(path)), "local", "apply")
        return path

    async def request(path: Path) -> dict[str, Any]:
        return await run(
            "corporate",
            "project",
            "link-request",
            "plan",
            "--context",
            context,
            "--root",
            str(path),
            "--project",
            project,
            "--git-executable",
            git_executable,
        )

    before_reservations, before_counts, before_writes = (
        reservations(),
        await counts(),
        len(faults.writes),
    )
    selected = (await run("context", "list"))["selected"]
    assert selected["context_id"] == offline_context
    old_recoveries = (await run("account", "connections", "recovery", "list"))["recoveries"]
    assert schema() == 57

    unknown = await checkout("unknown-request")
    original = await request(unknown)
    original_id = original["plan"]["operation_id"]
    faults.lose_next = f"/v1/organizations/{organization}/project-link-plans"
    await reject(original, retirement=False)
    assert faults.lose_next is None
    stopping = await run("corporate", "project", "link-retire", "plan", "--operation", original_id)
    stopped = await enact(stopping, "corporate", "project", "link-retire", "apply")
    assert stopped["remote_outcome"] == "unknown" and not stopped["reservation_released"]
    assert schema() == 58 and reservations() == before_reservations
    assert await counts() == (before_counts[0] + 1, before_counts[1])
    assert await enact(stopping, "corporate", "project", "link-retire", "apply") == stopped
    assert (await enact(original, "corporate", "project", "link", "apply"))["state"] == "retired"
    assert len(faults.writes) == before_writes + 1

    expiring = await checkout("confirmation")
    source = await request(expiring)
    assert source["plan"]["schema_version"] == 2 and source["plan"]["registry_schema_after"] == 58
    await enact(source, "corporate", "project", "link", "apply")
    source_id = source["plan"]["operation_id"]
    confirmation = await run(
        "corporate",
        "project",
        "link-confirm",
        "plan",
        "--request-operation",
        source_id,
        "--git-executable",
        git_executable,
    )
    confirmation_id = confirmation["plan"]["operation_id"]
    faults.refuse_next = "/v1/projects/links"
    await reject(confirmation, retirement=False)
    assert faults.refuse_next is None
    reserved = reservations()
    assert len(reserved) == len(before_reservations) + 1
    assert await counts() == (before_counts[0] + 2, before_counts[1])

    original_device = confirmation["plan"]["change"]["snapshot"]["account"]["device_id"]
    async with app.state.sessionmaker() as db:
        remote_device = await db.get(Device, original_device)
        assert remote_device is not None
        remote_device.state = "revoked"
        await db.commit()
    root_refresh = await run("account", "plan", "--action", "refresh")
    assert (await enact(root_refresh, "account", "apply"))["outcome"] == "revoked"
    root_recovery = await run("account", "plan", "--action", "recover")
    assert [
        item["operation_id"]
        for item in root_recovery["plan"]["recovery"]["interrupted_checkout_links"]
    ] == [confirmation_id]
    assert (await enact(root_recovery, "account", "apply"))["outcome"] == "device_replaced"
    assert (await run("corporate", "project", "link", "show", "--operation", confirmation_id))[
        "state"
    ] == "interrupted"
    assert reservations() == reserved and schema() == 58
    await login(account, None)
    replacement_context = await run(
        "context",
        "create",
        "plan",
        "--legacy-account",
        "--label",
        "Retirement epoch root replacement",
        "--organization",
        organization,
    )
    context = (await enact(replacement_context, "context", "apply"))["context_id"]

    retirement_arguments = [
        "corporate",
        "project",
        "link-retire",
        "plan",
        "--operation",
        confirmation_id,
        "--context",
        context,
    ]
    await refused(binary, home, retirement_arguments)
    faults.unsupported_settlement = True
    try:
        unavailable = await refused(binary, home, retirement_arguments)
        assert unavailable.error.code == "AI_STP_DEPENDENCY_UNAVAILABLE"
    finally:
        faults.unsupported_settlement = False
    assert reservations() == reserved
    expires = datetime.fromisoformat(
        confirmation["plan"]["change"]["server_plan"]["expires_at"].replace("Z", "+00:00")
    )
    advanced = expires + timedelta(seconds=1)

    class AfterExpiry(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Self:
            return cls.fromtimestamp(advanced.timestamp(), tz)

    # Only the isolated service clock advances; auth/session clocks and the
    # original plan/digest/database rows remain unchanged.
    with patch("ai_stp_api.slices.context.service.datetime", AfterExpiry):
        retiring = await run(*retirement_arguments)
    await reject(retiring)  # Fresh barrier says ready again: preserve reservation.
    assert reservations() == reserved
    displaced = expiring.with_name(expiring.name + "-displaced")
    expiring.rename(displaced)
    try:
        with patch("ai_stp_api.slices.context.service.datetime", AfterExpiry):
            retired = await enact(retiring, "corporate", "project", "link-retire", "apply")
        assert not expiring.exists()
        assert (
            retired["reservation_released"] and retired["remote_outcome"] == "expired_without_link"
        )
        assert reservations() == before_reservations
        assert await enact(retiring, "corporate", "project", "link-retire", "apply") == retired
        assert (await enact(confirmation, "corporate", "project", "link", "apply"))[
            "state"
        ] == "retired"
    finally:
        displaced.rename(expiring)
    assert await counts() == (before_counts[0] + 2, before_counts[1])
    await refused(
        binary,
        home,
        [
            "corporate",
            "project",
            "link-confirm",
            "plan",
            "--request-operation",
            source_id,
            "--git-executable",
            git_executable,
        ],
    )

    # Reuse the freed physical checkout only with a new exact request. A stale
    # retirement replay must not remove the new reservation or active binding.
    replacement = await request(expiring)
    await enact(replacement, "corporate", "project", "link", "apply")
    replacement_id = replacement["plan"]["operation_id"]
    confirming = await run(
        "corporate",
        "project",
        "link-confirm",
        "plan",
        "--request-operation",
        replacement_id,
        "--git-executable",
        git_executable,
    )
    await enact(confirming, "corporate", "project", "link", "apply")
    adoption = await run(
        "corporate",
        "project",
        "link-adopt",
        "plan",
        "--request-operation",
        replacement_id,
        "--context",
        context,
        "--root",
        str(expiring),
        "--git-executable",
        git_executable,
    )
    await enact(adoption, "corporate", "project", "link", "apply")
    active = reservations()
    assert len(active) == len(before_reservations) + 1
    assert await enact(retiring, "corporate", "project", "link-retire", "apply") == retired
    assert reservations() == active
    await refused(
        binary,
        home,
        [
            "corporate",
            "project",
            "link-retire",
            "plan",
            "--operation",
            confirming["plan"]["operation_id"],
            "--context",
            context,
        ],
    )
    assert (await run("context", "list"))["selected"] == selected
    assert (await run("account", "connections", "recovery", "list"))["recoveries"] == old_recoveries
    for path in (unknown, expiring):
        assert (path / ".env").read_bytes() == b"PRIVATE=retirement-unowned-canary\n"
        assert (path / ".env").stat().st_mode & 0o777 == 0o640
    assert await counts() == (before_counts[0] + 3, before_counts[1] + 1)
    assert len(faults.writes) == before_writes + 5

    # New enrollment recovery is explicitly format5 on epoch58. Its original
    # named actor is revoked through the actual database/auth refresh path.
    named = await run(
        "context",
        "create",
        "plan",
        "--connection",
        connection,
        "--label",
        "Retirement epoch named reader",
        "--organization",
        organization,
    )
    await enact(named, "context", "apply")
    named_device = named["plan"]["change"]["context"]["authority"]["account"]["device_id"]
    async with app.state.sessionmaker() as db:
        device = await db.get(Device, named_device)
        assert device is not None
        device.state = "revoked"
        await db.commit()
    refresh = await run("account", "plan", "--action", "refresh", "--connection", connection)
    assert (await enact(refresh, "account", "apply"))["outcome"] == "revoked"
    recovery = await run(
        "account",
        "connections",
        "recovery",
        "plan",
        "--connection",
        connection,
        "--label",
        "Recovered epoch58 named reader",
    )
    assert recovery["plan"]["schema_version"] == 5
    prepared = await enact(recovery, "account", "connections", "recovery", "apply")
    await login(account, prepared["replacement_connection_id"])
    assert (await enact(recovery, "account", "connections", "recovery", "apply"))[
        "state"
    ] == "authorized"
    assert schema() == 58 and reservations() == active
    assert (await run("context", "list"))["selected"] == selected
    print(
        json.dumps(
            {
                "native_checkout_retirement_http": "passed",
                "registry_schema": 58,
                "actual_server_transactions": True,
                "unknown_request_kept_unknown": True,
                "fresh_expired_settlement_required": True,
                "unsupported_server_retains_reservation": True,
                "reused_checkout_stale_replay_preserves_new_binding": True,
                "old_receipts_preserved": True,
                "enrollment_recovery_version": 5,
                "root_recovery_retained_pending_confirmation": True,
                "mutation_post_attempts": 5,
                "harness_configuration_writes": 0,
                "installation_authority": False,
            }
        ),
        flush=True,
    )
