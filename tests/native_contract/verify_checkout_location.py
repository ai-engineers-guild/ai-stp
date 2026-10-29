"""Actual current authority, competing location processes and released writer60."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from collections.abc import Awaitable, Callable
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from tests.native_contract.verify_ownership import native, native_result

from ai_stp_foundation.envelope import ErrorEnvelope
from ai_stp_platform.organization_models import OrganizationMembership

if TYPE_CHECKING:
    from tests.native_contract.verify_checkout import LostAcknowledgements, Native


async def qualify(
    *,
    binary: Path,
    home: Path,
    state: Path,
    app: Any,
    faults: LostAcknowledgements,
    run: Native,
    enact: Native,
    login: Callable[..., Awaitable[None]],
    refused: Callable[..., Awaitable[ErrorEnvelope]],
    organization: str,
    project: str,
    account: str,
    git_executable: str,
    foreign_context: str,
    checkout: Callable[[str], Awaitable[Path]],
) -> None:
    registry = state / "ai-stp-v2-state" / "registry.sqlite3"

    def rows() -> tuple[int, dict[str, list[tuple[Any, ...]]]]:
        with closing(sqlite3.connect(f"file:{registry}?mode=ro", uri=True)) as db:
            names: list[tuple[str]] = db.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            result: dict[str, list[tuple[Any, ...]]] = {}
            for (name,) in names:
                quoted = '"' + name.replace('"', '""') + '"'
                result[name] = sorted(db.execute("SELECT * FROM " + quoted).fetchall(), key=repr)
            return int(db.execute("PRAGMA user_version").fetchone()[0]), result

    def reviewed(planned: dict[str, Any], label: str) -> Path:
        path = home / f"location-{label}-{planned['plan']['operation_id']}.json"
        encoded = json.dumps(planned["plan"])
        if path.exists():
            assert path.read_text(encoding="utf-8") == encoded
        else:
            path.write_text(encoded, encoding="utf-8")
            path.chmod(0o600)
        return path

    def arguments(planned: dict[str, Any]) -> list[str]:
        return [
            "corporate",
            "project",
            "location",
            "apply",
            "--plan",
            str(reviewed(planned, "current")),
            "--plan-digest",
            planned["plan_digest"],
            "--git-executable",
            git_executable,
        ]

    async def plan_location(binding: str, context: str, path: Path | None = None) -> dict[str, Any]:
        arguments = [
            "corporate",
            "project",
            "location-anchor" if path is None else "location-relocate",
            "plan",
            "--context",
            context,
            "--binding-operation",
            binding,
            "--git-executable",
            git_executable,
        ]
        if path is not None:
            arguments.extend(["--root", str(path)])
        return await run(*arguments)

    async def competing(planned: dict[str, Any]) -> dict[str, Any]:
        results = await asyncio.gather(
            native_result(binary, home, arguments(planned)),
            native_result(binary, home, arguments(planned)),
        )
        receipts: list[dict[str, Any]] = []
        for status, stdout, stderr in results:
            assert not stderr
            if status == 0:
                receipt = json.loads(stdout)["data"]
                assert receipt["state"] == "verified"
                assert receipt["operation_id"] == planned["plan"]["operation_id"]
                receipts.append(receipt)
            else:
                failure = ErrorEnvelope.model_validate_json(stdout)
                assert failure.error.code in {
                    "AI_STP_PRECONDITION_FAILED",
                    "AI_STP_DEPENDENCY_UNAVAILABLE",
                }
        assert receipts, "both actual location processes refused"
        assert all(receipt == receipts[0] for receipt in receipts)
        assert await native(binary, home, arguments(planned)) == receipts[0]
        return receipts[0]

    assert rows()[0] == 60
    await login(account, None)
    selected = (await run("context", "list"))["selected"]
    context_plan = await run(
        "context",
        "create",
        "plan",
        "--legacy-account",
        "--label",
        "Current location authority",
        "--organization",
        organization,
    )
    context = (await enact(context_plan, "context", "apply"))["context_id"]
    authority = (await run("corporate", "teams", "--context", context))["observation"]
    capabilities = authority["observation"]["capabilities"]["capabilities"]
    assert "project.link" in capabilities and "project.unlink" not in capabilities
    path = await checkout("reviewed-location")
    marker = ".ai-stp-v2-project/project-id"
    marker_bytes = (path / marker).read_bytes()
    canary_bytes = (path / ".env").read_bytes()
    canary_mode = (path / ".env").stat().st_mode
    source = await run(
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
    await enact(source, "corporate", "project", "link", "apply")
    confirmation = await run(
        "corporate",
        "project",
        "link-confirm",
        "plan",
        "--request-operation",
        source["plan"]["operation_id"],
        "--git-executable",
        git_executable,
    )
    await enact(confirmation, "corporate", "project", "link", "apply")
    adoption = await run(
        "corporate",
        "project",
        "link-adopt",
        "plan",
        "--context",
        context,
        "--request-operation",
        source["plan"]["operation_id"],
        "--root",
        str(path),
        "--git-executable",
        git_executable,
    )
    adopted = await enact(adoption, "corporate", "project", "link", "apply")
    binding = adoption["plan"]["operation_id"]
    assert rows()[0] == 60
    previous = Path(os.environ["AI_STP_TEST_PREVIOUS_LOCATION_CLI_BINARY"])
    assert os.environ["AI_STP_TEST_PREVIOUS_LOCATION_CLI_SOURCE"] == (
        "3221fe08dc70630987c81997ede5af6454c988d2"
    )
    previous_digest = sha256(previous.read_bytes()).hexdigest()
    assert previous_digest == "5c19e71a6c21bac22decc19e717628d2564572465609914d30cede49625c103a"
    positive = await native(
        previous,
        home,
        [
            "context",
            "create",
            "plan",
            "--label",
            "Released60 positive",
            "--state-dir",
            str(state),
        ],
    )
    previous_arguments = [
        "context",
        "apply",
        "--plan",
        str(reviewed(positive, "released-positive")),
        "--plan-digest",
        positive["plan_digest"],
    ]
    positive_receipt = await native(previous, home, previous_arguments)
    assert positive_receipt["context_id"] == positive["plan"]["change"]["context"]["context_id"]
    held = await native(
        previous,
        home,
        [
            "context",
            "create",
            "plan",
            "--label",
            "Released60 held otherwise valid",
            "--state-dir",
            str(state),
        ],
    )
    held_arguments = [
        "context",
        "apply",
        "--plan",
        str(reviewed(held, "released-held")),
        "--plan-digest",
        held["plan_digest"],
    ]
    planned = await plan_location(binding, context)
    before = rows()
    network = faults.network_requests
    await refused(
        binary,
        home,
        [
            "corporate",
            "project",
            "location-anchor",
            "plan",
            "--context",
            foreign_context,
            "--binding-operation",
            binding,
            "--state-dir",
            str(state),
            "--git-executable",
            git_executable,
        ],
    )
    assert rows() == before and faults.network_requests == network
    async with app.state.sessionmaker() as db:
        membership = await db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization,
                OrganizationMembership.account_id == account,
            )
        )
        assert membership is not None
        membership.state, membership.revision = "suspended", membership.revision + 1
        await db.commit()
    await refused(binary, home, arguments(planned))
    assert rows() == before
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
    await refused(binary, home, arguments(planned))
    assert rows() == before
    planned = await plan_location(binding, context)
    before, writes = rows(), len(faults.writes)
    anchored = await competing(planned)
    after = rows()
    assert after[0] == 61 and len(faults.writes) == writes
    for table, records in before[1].items():
        if table != "operation":
            assert after[1][table] == records, table
    assert len(after[1]["operation"]) == len(before[1]["operation"]) + 1
    assert len(after[1]["native_checkout_location"]) == 1
    before_bytes = registry.read_bytes()
    failure = await refused(previous, home, held_arguments)
    assert failure.error.code == "AI_STP_PRECONDITION_FAILED"
    assert rows() == after and registry.read_bytes() == before_bytes
    assert await native(binary, home, previous_arguments) == positive_receipt
    assert rows() == after

    destination = path.with_name(path.name + "-cafe\u0301")
    path.rename(destination)
    moved = await plan_location(binding, context, destination)
    before, writes = rows(), len(faults.writes)
    relocated = await competing(moved)
    after = rows()
    assert relocated["outcome"] == "checkout_relocated" and len(faults.writes) == writes
    changed = {
        "operation",
        "native_checkout_location",
        "revision",
        "revision_parent",
        "head",
        "project_root",
    }
    for table, records in before[1].items():
        if table not in changed:
            assert after[1][table] == records, table
    assert (destination / marker).read_bytes() == marker_bytes
    assert (destination / ".env").read_bytes() == canary_bytes
    assert (destination / ".env").stat().st_mode == canary_mode
    network, before = faults.network_requests, rows()
    assert await native(binary, home, arguments(planned)) == anchored
    assert await native(binary, home, arguments(moved)) == relocated
    assert await enact(adoption, "corporate", "project", "link", "apply") == adopted
    assert rows() == before and faults.network_requests == network
    future = destination.with_name(destination.name + "-future")
    destination.rename(future)
    future_plan = await plan_location(binding, context, future)
    await enact(future_plan, "corporate", "project", "location", "apply")
    network, before = faults.network_requests, rows()
    assert await native(binary, home, arguments(planned)) == anchored
    assert await native(binary, home, arguments(moved)) == relocated
    assert rows() == before and faults.network_requests == network
    assert (await run("context", "list"))["selected"] == selected
    assert (future / marker).read_bytes() == marker_bytes
    assert (future / ".env").read_bytes() == canary_bytes
    assert (future / ".env").stat().st_mode == canary_mode
    print(
        json.dumps(
            {
                "native_checkout_location_http": "passed",
                "registry_schema": 61,
                "actual_server_transactions": True,
                "two_real_anchor_and_move_processes": True,
                "project_link_without_unlink_capability": True,
                "membership_and_authorization_cas": True,
                "immutable_original_adoption": True,
                "previous_writer_source": os.environ["AI_STP_TEST_PREVIOUS_LOCATION_CLI_SOURCE"],
                "previous_writer_sha256": previous_digest,
                "previous60_positive_then_refusal": True,
                "all_unrelated_logical_tables_preserved": True,
                "offline_replay_cannot_retarget_future_location": True,
                "canary_bytes_and_modes_preserved": True,
                "harness_configuration_writes": 0,
                "installation_authority": False,
            }
        ),
        flush=True,
    )
