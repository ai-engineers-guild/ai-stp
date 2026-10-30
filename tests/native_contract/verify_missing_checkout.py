"""Actual project.link-only retirement, released61 writer fence and offline replay."""

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

from httpx import AsyncClient
from sqlalchemy import select
from tests.native_contract.verify_ownership import native, native_result

from ai_stp_api.session import issue_session
from ai_stp_foundation.envelope import ErrorEnvelope
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Device
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
    context: str,
    actor: str,
    lead_context: str,
    checkout_root: Path,
    adoption: dict[str, Any],
    adopted: dict[str, Any],
    connection: dict[str, Any],
    git_executable: str,
) -> None:
    registry = state / "ai-stp-v2-state" / "registry.sqlite3"
    binding_id = adoption["plan"]["operation_id"]
    link_id = adopted["effect"]["link"]["link_id"]

    def rows() -> tuple[int, dict[str, list[tuple[Any, ...]]]]:
        with closing(sqlite3.connect(f"file:{registry}?mode=ro", uri=True)) as db:
            result: dict[str, list[tuple[Any, ...]]] = {}
            for (name,) in db.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall():
                quoted = '"' + name.replace('"', '""') + '"'
                result[name] = sorted(db.execute("SELECT * FROM " + quoted).fetchall(), key=repr)
            return int(db.execute("PRAGMA user_version").fetchone()[0]), result

    def reviewed(planned: dict[str, Any], label: str) -> Path:
        path = home / f"missing-checkout-{label}-{planned['plan']['operation_id']}.json"
        encoded = json.dumps(planned["plan"])
        if path.exists():
            assert path.read_text() == encoded
        else:
            path.write_text(encoded)
            path.chmod(0o600)
        return path

    def arguments(planned: dict[str, Any]) -> list[str]:
        return [
            "corporate",
            "project",
            "binding-retire-missing",
            "apply",
            "--plan",
            str(reviewed(planned, "apply")),
            "--plan-digest",
            planned["plan_digest"],
        ]

    def plan_arguments(reader: str = context) -> list[str]:
        return [
            "corporate",
            "project",
            "binding-retire-missing",
            "plan",
            "--context",
            reader,
            "--binding-operation",
            binding_id,
        ]

    assert rows()[0] == 61
    selected = (await run("context", "list"))["selected"]
    authority = (await run("corporate", "teams", "--context", context))["observation"]
    capabilities = authority["observation"]["capabilities"]["capabilities"]
    assert "project.link" in capabilities and "project.unlink" not in capabilities
    previous = Path(os.environ["AI_STP_TEST_PREVIOUS_MISSING_CHECKOUT_CLI_BINARY"])
    previous_source = os.environ["AI_STP_TEST_PREVIOUS_MISSING_CHECKOUT_CLI_SOURCE"]
    previous_digest = sha256(previous.read_bytes()).hexdigest()
    assert previous_source == "1327533ccbfb8d1aa92ccdd346790246f8eac28c"
    assert previous_digest == "047f806ba78dce3cab36caaa109a9c0209af7678ba4a5abbe8a4ab7aff150491"
    positive = await native(
        previous,
        home,
        [
            "context",
            "create",
            "plan",
            "--label",
            "Released61 positive",
            "--state-dir",
            str(state),
        ],
    )
    positive_receipt = await native(
        previous,
        home,
        [
            "context",
            "apply",
            "--plan",
            str(reviewed(positive, "released-positive")),
            "--plan-digest",
            positive["plan_digest"],
        ],
    )
    assert positive_receipt["context_id"] == positive["plan"]["change"]["context"]["context_id"]
    held = await native(
        previous,
        home,
        [
            "context",
            "create",
            "plan",
            "--label",
            "Released61 held",
            "--state-dir",
            str(state),
        ],
    )
    before, network = rows(), faults.network_requests
    await refused(binary, home, [*plan_arguments(), "--state-dir", str(state)])
    assert (
        rows() == before and faults.network_requests == network
    )  # Present leaf refuses before GET.
    preserved = checkout_root.with_name(checkout_root.name + "-preserved")
    canaries = ((checkout_root / ".env").read_bytes(), (checkout_root / ".env").stat().st_mode)
    marker = (checkout_root / ".ai-stp-v2-project/project-id").read_bytes()
    checkout_root.rename(
        preserved
    )  # Owned fixture simulates an external move, not product cleanup.
    before, network = rows(), faults.network_requests
    await refused(binary, home, [*plan_arguments(lead_context), "--state-dir", str(state)])
    assert (
        rows() == before and faults.network_requests == network
    )  # Different account cannot inspect.
    await refused(binary, home, [*plan_arguments(), "--state-dir", str(state)])
    assert rows() == before  # A missing name never substitutes for a remote unlink.

    lead = (await run("context", "show", "--context", lead_context))["context"]["authority"][
        "account"
    ]
    async with app.state.sessionmaker() as db:
        issued = await issue_session(
            db, account_id=lead["account_id"], device_id=lead["device_id"], ttl_seconds=3600
        )
        token = issued.raw_token
        await db.commit()
    observation = (await run("corporate", "teams", "--context", lead_context))["observation"]
    revision = observation["observation"]["capabilities"]["authorization_revision"]
    async with AsyncClient(base_url=lead["origin"], trust_env=False, timeout=15) as client:
        headers = {
            "Authorization": "Bearer " + token,
            "X-AI-STP-Organization-Id": organization,
            "X-AI-STP-Authorization-Revision": revision,
        }
        current = await client.get(f"/v1/projects/links/{link_id}", headers=headers)
        assert current.status_code == 200
        remote = await client.post(
            f"/v1/organizations/{organization}/project-unlink-plans",
            headers=headers,
            json={
                "schema_version": 1,
                "link_id": link_id,
                "expected_link_revision": current.json()["revision"],
                "authorization_revision": revision,
                "idempotency_key": new_id("operation"),
            },
        )
        assert remote.status_code == 201
        decision = remote.json()
        stopped = await client.request(
            "DELETE",
            f"/v1/projects/links/{link_id}",
            headers=headers,
            json={
                "schema_version": 1,
                "plan_id": decision["plan_id"],
                "plan_digest": decision["plan_digest"],
                "authorization_revision": decision["authorization_revision"],
                "idempotency_key": new_id("operation"),
            },
        )
        assert stopped.status_code == 200

    planned = await run(*plan_arguments())
    assert planned["plan"]["kind"] == "corporate.project_binding.retire_missing"
    assert (
        planned["plan"]["registry_schema_before"] == 61
        and planned["plan"]["registry_schema_after"] == 62
    )
    assert planned["plan"]["snapshot"]["reader"]["account"]["account_id"] == actor
    before = rows()
    # A final dangling symlink is present, including when its target is absent.
    checkout_root.symlink_to(
        checkout_root.with_name("uncreated-link-target"), target_is_directory=True
    )
    network = faults.network_requests
    await refused(binary, home, arguments(planned))
    assert rows() == before and faults.network_requests == network
    assert checkout_root.is_symlink() and not checkout_root.exists()
    # Remove only this test-created symlink; the moved checkout stays intact.
    checkout_root.unlink()
    checkout_root.mkdir()
    (checkout_root / "unowned").write_bytes(b"reappeared-directory-canary\n")
    await refused(binary, home, arguments(planned))
    assert (
        rows() == before
        and (checkout_root / "unowned").read_bytes() == b"reappeared-directory-canary\n"
    )
    checkout_root.rename(checkout_root.with_name(checkout_root.name + "-reappeared"))
    faults.unavailable_reads = True
    try:
        await refused(binary, home, arguments(planned))
        assert rows() == before
    finally:
        faults.unavailable_reads = False
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
    await refused(binary, home, arguments(planned))  # Changed authority invalidates the old review.
    assert rows() == before
    planned = await run(*plan_arguments())
    before, writes = rows(), len(faults.writes)
    results = await asyncio.gather(
        native_result(binary, home, arguments(planned)),
        native_result(binary, home, arguments(planned)),
    )
    receipts: list[dict[str, Any]] = []
    for status, stdout, stderr in results:
        assert not stderr
        if status == 0:
            receipts.append(json.loads(stdout)["data"])
        else:
            failure = ErrorEnvelope.model_validate_json(stdout)
            assert failure.error.code in {
                "AI_STP_PRECONDITION_FAILED",
                "AI_STP_DEPENDENCY_UNAVAILABLE",
            }
    assert receipts and all(receipt == receipts[0] for receipt in receipts)
    retired = receipts[0]
    assert (
        retired["outcome"] == "missing_checkout_binding_retired"
        and retired["checkout_observation"] == "absent"
    )
    assert retired["installation_authority"] is False and len(faults.writes) == writes
    after = rows()
    assert after[0] == 62
    for table, records in before[1].items():
        if table not in {
            "operation",
            "project_link",
            "native_checkout_reservation",
            "native_binding_retirement",
        }:
            assert after[1][table] == records, table
    assert len(after[1]["operation"]) == len(before[1]["operation"]) + 1
    assert (
        len(after[1]["native_checkout_reservation"])
        == len(before[1]["native_checkout_reservation"]) - 1
    )
    assert (
        len(after[1]["native_binding_retirement"])
        == len(before[1]["native_binding_retirement"]) + 1
    )
    await refused(
        previous,
        home,
        [
            "context",
            "apply",
            "--plan",
            str(reviewed(held, "released-held")),
            "--plan-digest",
            held["plan_digest"],
        ],
    )
    assert rows() == after
    network = faults.network_requests
    assert await native(binary, home, arguments(planned)) == retired
    assert await enact(adoption, "corporate", "project", "link", "apply") == adopted
    assert (
        await run(
            "corporate",
            "project",
            "binding-retire-missing",
            "show",
            "--operation",
            planned["plan"]["operation_id"],
        )
    ) == retired
    history = await run("corporate", "project", "link", "show", "--operation", binding_id)
    assert history["binding_retirement"] == retired
    assert rows() == after and faults.network_requests == network

    # A reused pathname does not make the original receipt authority over a future binding.
    preserved.rename(checkout_root)
    assert (
        (checkout_root / ".env").read_bytes(),
        (checkout_root / ".env").stat().st_mode,
    ) == canaries
    assert (checkout_root / ".ai-stp-v2-project/project-id").read_bytes() == marker
    target = adoption["plan"]["change"]["snapshot"]["target"]["remote_project_id"]
    source = await run(
        "corporate",
        "project",
        "link-request",
        "plan",
        "--context",
        context,
        "--root",
        str(checkout_root),
        "--project",
        target,
        "--git-executable",
        git_executable,
    )
    assert source["plan"]["registry_schema_before"] == source["plan"]["registry_schema_after"] == 62
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
    future_plan = await run(
        "corporate",
        "project",
        "link-adopt",
        "plan",
        "--context",
        context,
        "--root",
        str(checkout_root),
        "--request-operation",
        source["plan"]["operation_id"],
        "--git-executable",
        git_executable,
    )
    future_receipt = await enact(future_plan, "corporate", "project", "link", "apply")
    assert future_receipt["effect"]["link"]["link_id"] != link_id
    future = rows()
    network = faults.network_requests
    assert await native(binary, home, arguments(planned)) == retired
    assert rows() == future and faults.network_requests == network
    assert (
        await run(
            "corporate",
            "project",
            "link",
            "show",
            "--operation",
            future_plan["plan"]["operation_id"],
        )
    )["binding_retirement"] is None
    # Both actual replacement flows must retain the explicit epoch and all original markers.
    root_status = await run("account", "status")
    root_account = {
        "device_id": root_status["device_id"],
        "account_id": root_status["session"]["account_id"],
    }
    async with app.state.sessionmaker() as db:
        device = await db.get(Device, root_account["device_id"])
        assert device is not None
        device.state = "revoked"
        await db.commit()
    refreshed = await enact(await run("account", "plan", "--action", "refresh"), "account", "apply")
    assert refreshed["outcome"] == "revoked"
    recovery = await run("account", "plan", "--action", "recover")
    assert (await enact(recovery, "account", "apply"))["outcome"] == "device_replaced"
    await login(root_account["account_id"], None)
    assert rows()[0] == 62
    async with app.state.sessionmaker() as db:
        device = await db.get(Device, connection["device_id"])
        assert device is not None
        device.state = "revoked"
        await db.commit()
    assert (
        await enact(
            await run(
                "account",
                "plan",
                "--action",
                "refresh",
                "--connection",
                connection["connection_id"],
            ),
            "account",
            "apply",
        )
    )["outcome"] == "revoked"
    recovery = await run(
        "account",
        "connections",
        "recovery",
        "plan",
        "--connection",
        connection["connection_id"],
        "--label",
        "Missing62 replacement",
    )
    assert (
        recovery["plan"]["schema_version"] == 6 and recovery["plan"]["registry_schema_before"] == 62
    )
    prepared = await enact(recovery, "account", "connections", "recovery", "apply")
    await login(actor, prepared["replacement_connection_id"])
    await enact(recovery, "account", "connections", "recovery", "apply")
    before, network = rows(), faults.network_requests
    assert before[0] == 62
    faults.unavailable_reads = True
    try:
        assert await native(binary, home, arguments(planned)) == retired
        assert (await run("corporate", "project", "link", "show", "--operation", binding_id))[
            "binding_retirement"
        ] == retired
        assert await enact(adoption, "corporate", "project", "link", "apply") == adopted
        assert await enact(future_plan, "corporate", "project", "link", "apply") == future_receipt
    finally:
        faults.unavailable_reads = False
    assert rows() == before and faults.network_requests == network
    assert (await run("context", "list"))["selected"]["context_id"] == selected["context_id"]
    assert (
        (checkout_root / ".env").read_bytes(),
        (checkout_root / ".env").stat().st_mode,
    ) == canaries
    print(
        json.dumps(
            {
                "native_missing_checkout_retirement_http": "passed",
                "registry_schema": 62,
                "project_link_without_unlink_capability": True,
                "external_authorized_unlink_actor": True,
                "present_reappeared_and_dangling_leaf_refused": True,
                "membership_and_authorization_cas": True,
                "two_real_retirement_processes": True,
                "all_unrelated_logical_tables_preserved": True,
                "previous_writer_source": previous_source,
                "previous_writer_sha256": previous_digest,
                "previous61_positive_then_refusal": True,
                "root_and_named_replacement_preserve62": True,
                "offline_exact_replay_after_path_reuse_and_recovery": True,
                "new_binding_survives_old_retirement_replay": True,
                "original_adoption_receipt_preserved": True,
                "canary_bytes_and_modes_preserved": True,
                "harness_configuration_writes": 0,
                "installation_authority": False,
            }
        ),
        flush=True,
    )
