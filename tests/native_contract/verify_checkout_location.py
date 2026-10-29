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
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import (
    CorporateProjectMember,
    CorporateRoleBinding,
    OrganizationMembership,
)

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
    selected = (await run("context", "list"))["selected"]
    # The original bootstrap account is privileged. A separate synthetic staff
    # member proves project.link-only authority through a named enrollment,
    # without relabeling the private native owner or changing prior role grants.
    actor = new_id("account")
    async with app.state.sessionmaker() as db:
        db.add(Account(id=actor))
        await db.flush()
        db.add(OrganizationMembership(organization_id=organization, account_id=actor, role="staff"))
        await db.flush()
        db.add(
            CorporateRoleBinding(
                id=new_id("operation"),
                organization_id=organization,
                account_id=actor,
                role="staff",
                scope_kind="organization",
                scope_id=organization,
                origin="membership",
                coverage="descendants",
            )
        )
        db.add(
            CorporateProjectMember(
                organization_id=organization,
                project_id=project,
                account_id=actor,
                role="staff",
            )
        )
        await db.commit()
    reference = (await run("context", "show", "--context", foreign_context))["context"]
    connection_plan = await run(
        "account",
        "connections",
        "plan",
        "--label",
        "Location staff member",
        "--api-url",
        reference["authority"]["account"]["origin"],
        "--provider",
        "github",
    )
    connection = (await enact(connection_plan, "account", "connections", "apply"))["connection"]
    await login(actor, connection["connection_id"])
    context_plan = await run(
        "context",
        "create",
        "plan",
        "--connection",
        connection["connection_id"],
        "--label",
        "Current location authority",
        "--organization",
        organization,
    )
    context = (await enact(context_plan, "context", "apply"))["context_id"]
    assert context_plan["plan"]["change"]["context"]["local_identity"]["account_id"] != actor
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
                OrganizationMembership.account_id == actor,
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
                OrganizationMembership.account_id == actor,
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
    assert (
        await run(
            "corporate",
            "project",
            "location",
            "show",
            "--operation",
            planned["plan"]["operation_id"],
        )
    ) == anchored
    history = await run("corporate", "project", "location", "list", "--binding-operation", binding)
    assert len(history["locations"]) == 2 and history["next_cursor"] is None
    continuation = await run(
        "corporate",
        "project",
        "location",
        "list",
        "--binding-operation",
        binding,
        "--cursor",
        history["locations"][0]["operation_id"],
    )
    assert continuation["locations"] == history["locations"][1:]
    assert await enact(adoption, "corporate", "project", "link", "apply") == adopted
    assert rows() == before and faults.network_requests == network
    future = destination.with_name(destination.name + "-future")
    destination.rename(future)
    future_plan = await plan_location(binding, context, future)
    await enact(future_plan, "corporate", "project", "location", "apply")
    network, before = faults.network_requests, rows()
    assert await native(binary, home, arguments(planned)) == anchored
    assert await native(binary, home, arguments(moved)) == relocated
    assert (
        await run(
            "corporate",
            "project",
            "location",
            "show",
            "--operation",
            moved["plan"]["operation_id"],
        )
    ) == relocated
    assert (
        len(
            (
                await run(
                    "corporate",
                    "project",
                    "location",
                    "list",
                    "--binding-operation",
                    binding,
                )
            )["locations"]
        )
        == 3
    )
    assert rows() == before and faults.network_requests == network
    assert (await run("context", "list"))["selected"] == selected
    assert (future / marker).read_bytes() == marker_bytes
    assert (future / ".env").read_bytes() == canary_bytes
    assert (future / ".env").stat().st_mode == canary_mode

    # Keep the project.link-only actor above unchanged. The existing independent
    # authorized lead now exercises unlink/retirement61 for their own binding,
    # including the current locator in the plan consumed by Desktop.
    releasing = await checkout("location-retirement61")
    release_canaries = (
        (releasing / marker).read_bytes(),
        (releasing / ".env").read_bytes(),
        (releasing / ".env").stat().st_mode,
    )
    request = await run(
        "corporate",
        "project",
        "link-request",
        "plan",
        "--context",
        foreign_context,
        "--root",
        str(releasing),
        "--project",
        project,
        "--git-executable",
        git_executable,
    )
    await enact(request, "corporate", "project", "link", "apply")
    confirmation = await run(
        "corporate",
        "project",
        "link-confirm",
        "plan",
        "--request-operation",
        request["plan"]["operation_id"],
        "--git-executable",
        git_executable,
    )
    await enact(confirmation, "corporate", "project", "link", "apply")
    original = await run(
        "corporate",
        "project",
        "link-adopt",
        "plan",
        "--context",
        foreign_context,
        "--root",
        str(releasing),
        "--request-operation",
        request["plan"]["operation_id"],
        "--git-executable",
        git_executable,
    )
    original_receipt = await enact(original, "corporate", "project", "link", "apply")
    releasing_binding = original["plan"]["operation_id"]
    anchor = await plan_location(releasing_binding, foreign_context)
    await enact(anchor, "corporate", "project", "location", "apply")
    released_root = releasing.with_name(releasing.name + "-moved")
    releasing.rename(released_root)
    move = await plan_location(releasing_binding, foreign_context, released_root)
    moved_receipt = await enact(move, "corporate", "project", "location", "apply")
    unlink = await run(
        "corporate",
        "project",
        "unlink-request",
        "plan",
        "--context",
        foreign_context,
        "--binding-operation",
        releasing_binding,
    )
    await enact(unlink, "corporate", "project", "unlink", "apply")
    confirmation = await run(
        "corporate",
        "project",
        "unlink-confirm",
        "plan",
        "--request-operation",
        unlink["plan"]["operation_id"],
    )
    await enact(confirmation, "corporate", "project", "unlink", "apply")
    retirement = await run(
        "corporate",
        "project",
        "binding-retire",
        "plan",
        "--context",
        foreign_context,
        "--binding-operation",
        releasing_binding,
    )
    assert retirement["plan"]["registry_schema_before"] == 61
    assert retirement["plan"]["registry_schema_after"] == 61
    retained_binding = retirement["plan"]["snapshot"]["binding"]
    assert retained_binding["checkout_root"] == move["plan"]["destination"]
    assert retained_binding["location"]["operation_id"] == move["plan"]["operation_id"]
    assert retained_binding["location"]["plan_digest"] == move["plan_digest"]
    retired = await enact(retirement, "corporate", "project", "binding-retire", "apply")
    assert retired["outcome"] == "local_binding_retired" and rows()[0] == 61
    network, before = faults.network_requests, rows()
    assert await enact(retirement, "corporate", "project", "binding-retire", "apply") == retired
    assert await enact(original, "corporate", "project", "link", "apply") == original_receipt
    assert await enact(move, "corporate", "project", "location", "apply") == moved_receipt
    history = await run("corporate", "project", "link", "show", "--operation", releasing_binding)
    assert history["binding_retirement"] == retired
    assert rows() == before and faults.network_requests == network
    assert (
        (released_root / marker).read_bytes(),
        (released_root / ".env").read_bytes(),
        (released_root / ".env").stat().st_mode,
    ) == release_canaries
    assert (await run("context", "list"))["selected"] == selected
    print(
        json.dumps(
            {
                "native_checkout_location_http": "passed",
                "registry_schema": 61,
                "actual_server_transactions": True,
                "two_real_anchor_and_move_processes": True,
                "project_link_without_unlink_capability": True,
                "private_owner_and_corporate_actor_distinct": True,
                "offline_receipt_lookup_and_history_cursor": True,
                "membership_and_authorization_cas": True,
                "immutable_original_adoption": True,
                "previous_writer_source": os.environ["AI_STP_TEST_PREVIOUS_LOCATION_CLI_SOURCE"],
                "previous_writer_sha256": previous_digest,
                "previous60_positive_then_refusal": True,
                "schema61_native_unlink_retirement_and_offline_history": True,
                "all_unrelated_logical_tables_preserved": True,
                "offline_replay_cannot_retarget_future_location": True,
                "canary_bytes_and_modes_preserved": True,
                "harness_configuration_writes": 0,
                "installation_authority": False,
            }
        ),
        flush=True,
    )
