"""Actual two-actor HTTP unlink, local atomic retirement and future-binding preservation."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from collections.abc import Awaitable, Callable
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from httpx import AsyncClient, Response
from sqlalchemy import select
from tests.native_contract.verify_ownership import native, native_result

from ai_stp_api.session import issue_session
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.envelope import ErrorEnvelope
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Device
from ai_stp_platform.organization_models import (
    CorporateRoleBinding,
    Organization,
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
    account: str,
    offline_context: str,
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

    def reviewed(planned: dict[str, Any]) -> Path:
        path = home / f"binding-retirement-{planned['plan']['operation_id']}.json"
        value = json.dumps(planned["plan"])
        if path.exists():
            assert path.read_text() == value
        else:
            path.write_text(value)
            path.chmod(0o600)
        return path

    def apply_arguments(planned: dict[str, Any], route: str = "binding-retire") -> list[str]:
        return [
            "corporate",
            "project",
            route,
            "apply",
            "--plan",
            str(reviewed(planned)),
            "--plan-digest",
            planned["plan_digest"],
        ]

    async def reject(planned: dict[str, Any], route: str = "binding-retire") -> ErrorEnvelope:
        return await refused(binary, home, apply_arguments(planned, route))

    assert rows()[0] == 59
    await login(account, None)
    selected = (await run("context", "list"))["selected"]
    assert selected["context_id"] == offline_context
    foreign = (await run("context", "show", "--context", foreign_context))["context"]["authority"][
        "account"
    ]
    # Give only this synthetic second participant an explicit authorized role.
    # Staff intentionally has neither project.update nor project.unlink.
    async with app.state.sessionmaker() as db:
        company = await db.get(Organization, organization)
        assert company is not None
        company.policy_revision += 1
        db.add(
            CorporateRoleBinding(
                id=new_id("operation"),
                organization_id=organization,
                account_id=foreign["account_id"],
                role="lead",
                scope_kind="organization",
                scope_id=organization,
                origin="direct",
                coverage="descendants",
            )
        )
        await db.commit()
    planned_context = await run(
        "context",
        "create",
        "plan",
        "--legacy-account",
        "--label",
        "Binding retirement actor",
        "--organization",
        organization,
    )
    context = (await enact(planned_context, "context", "apply"))["context_id"]
    original_actor = planned_context["plan"]["change"]["context"]["authority"]["account"]
    assert foreign["account_id"] != account and original_actor["account_id"] == account
    origin = original_actor["origin"]
    tokens: dict[str, str] = {}
    async with app.state.sessionmaker() as db:
        for name, actor in [("original", original_actor), ("external", foreign)]:
            issued = await issue_session(
                db, account_id=actor["account_id"], device_id=actor["device_id"], ttl_seconds=3600
            )
            tokens[name] = issued.raw_token
        await db.commit()

    async def authorization(reader: str) -> str:
        report = await run("corporate", "teams", "--context", reader)
        return cast(
            str, report["observation"]["observation"]["capabilities"]["authorization_revision"]
        )

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

    async def bind(path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        source = await request(path)
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
            "--request-operation",
            source["plan"]["operation_id"],
            "--context",
            context,
            "--root",
            str(path),
            "--git-executable",
            git_executable,
        )
        return source, adoption, await enact(adoption, "corporate", "project", "link", "apply")

    async def retire_plan(adoption: dict[str, Any]) -> dict[str, Any]:
        return await run(
            "corporate",
            "project",
            "binding-retire",
            "plan",
            "--context",
            context,
            "--binding-operation",
            adoption["plan"]["operation_id"],
        )

    path = await checkout("binding-retirement-original")
    source, adoption, original_receipt = await bind(path)
    link_id = original_receipt["effect"]["link"]["link_id"]
    unchanged = rows()
    await refused(
        binary,
        home,
        [
            "corporate",
            "project",
            "binding-retire",
            "plan",
            "--context",
            context,
            "--binding-operation",
            adoption["plan"]["operation_id"],
            "--state-dir",
            str(state),
        ],
    )
    assert rows() == unchanged
    network = faults.network_requests
    await refused(
        binary,
        home,
        [
            "corporate",
            "project",
            "binding-retire",
            "plan",
            "--context",
            foreign_context,
            "--binding-operation",
            adoption["plan"]["operation_id"],
            "--state-dir",
            str(state),
        ],
    )
    assert rows() == unchanged and faults.network_requests == network

    # The same physical project has two other unknown native writes. A fresh
    # terminal remote link does not erase either retained local intent.
    another_checkout = await request(path)
    faults.lose_next = f"/v1/organizations/{organization}/project-link-plans"
    await reject(another_checkout, "link")
    assert faults.lose_next is None
    pending_unlink = await run(
        "corporate",
        "project",
        "unlink-request",
        "plan",
        "--context",
        context,
        "--binding-operation",
        adoption["plan"]["operation_id"],
    )
    faults.lose_next = f"/v1/organizations/{organization}/project-unlink-plans"
    await reject(pending_unlink, "unlink")
    assert faults.lose_next is None

    async with AsyncClient(base_url=origin, trust_env=False, timeout=15) as client:
        push_sequence = 0

        async def api(
            method: str, route: str, actor: str = "external", payload: dict[str, Any] | None = None
        ) -> Response:
            reader = context if actor == "original" else foreign_context
            return await client.request(
                method,
                route,
                json=payload,
                headers={
                    "Authorization": "Bearer " + tokens[actor],
                    "X-AI-STP-Organization-Id": organization,
                    "X-AI-STP-Authorization-Revision": await authorization(reader),
                },
            )

        async def current(identity: str = link_id) -> dict[str, Any]:
            response = await api("GET", f"/v1/projects/links/{identity}")
            assert response.status_code == 200
            return cast(dict[str, Any], response.json())

        async def push_payload(
            identity: str, *, actor: str = "external", parent: str | None = None
        ) -> dict[str, Any]:
            nonlocal push_sequence
            push_sequence += 1
            response = await api("GET", f"/v1/projects/links/{identity}/revisions", actor)
            assert response.status_code == 200
            head = response.json()["head_revision_id"] if parent is None else parent
            projection = {
                "schema_version": 1,
                "kind": "project",
                "remote_project_id": project,
                "file_count": push_sequence,
            }
            parents = [head] if head is not None else []
            document = {
                "schema_version": 1,
                "remote_project_id": project,
                "parent_revision_ids": parents,
                "operation": "upsert",
                "projection": projection,
            }
            return {
                "schema_version": 1,
                "event_id": new_id("operation"),
                "revision_id": digest_canonical("ai-stp:revision:v1", cast(JsonValue, document)),
                "parent_revision_ids": parents,
                "operation": "upsert",
                "projection": projection,
                "content_digest": digest_canonical(
                    "ai-stp:revision:v1", cast(JsonValue, projection)
                ),
                "expected_head_revision_id": head,
                "authorization_revision": await authorization(
                    context if actor == "original" else foreign_context
                ),
                "idempotency_key": new_id("operation"),
            }

        async def unlink_payload(identity: str) -> dict[str, Any]:
            observed = await current(identity)
            response = await api(
                "POST",
                f"/v1/organizations/{organization}/project-unlink-plans",
                payload={
                    "schema_version": 1,
                    "link_id": identity,
                    "expected_link_revision": observed["revision"],
                    "authorization_revision": await authorization(foreign_context),
                    "idempotency_key": new_id("operation"),
                },
            )
            assert response.status_code == 201
            plan = response.json()
            return {
                "schema_version": 1,
                "plan_id": plan["plan_id"],
                "plan_digest": plan["plan_digest"],
                "authorization_revision": plan["authorization_revision"],
                "idempotency_key": new_id("operation"),
            }

        first_push = await push_payload(link_id)
        positive = await api("POST", f"/v1/projects/links/{link_id}/revisions", payload=first_push)
        assert positive.status_code == 200 and positive.json()["receipt"]["state"] == "accepted"
        sync_link = await current()
        sync = await api(
            "POST",
            f"/v1/projects/links/{link_id}/sync-plans",
            payload={
                "schema_version": 1,
                "link_id": link_id,
                "expected_link_revision": sync_link["revision"],
                "local_revision": sync_link["local_revision"],
                "remote_revision": sync_link["remote_revision"],
                "provider_revision": sync_link["provider_revision"],
                "authorization_revision": await authorization(foreign_context),
                "idempotency_key": new_id("operation"),
            },
        )
        assert sync.status_code == 201
        sync_plan = sync.json()
        second_push = await push_payload(link_id)
        positive = await api("POST", f"/v1/projects/links/{link_id}/revisions", payload=second_push)
        assert positive.status_code == 200 and positive.json()["receipt"]["state"] == "accepted"
        divergent = await push_payload(link_id, parent=first_push["revision_id"])
        conflicted = await api("POST", f"/v1/projects/links/{link_id}/revisions", payload=divergent)
        assert conflicted.status_code == 200 and conflicted.json()["receipt"]["state"] == "conflict"
        before_unlink = await current()
        assert before_unlink["state"] == "conflict"
        assert before_unlink["revision"] > original_receipt["effect"]["link"]["revision"]
        assert before_unlink["conflict_server_revision"] is not None
        payload = await unlink_payload(link_id)
        unlinked = await api("DELETE", f"/v1/projects/links/{link_id}", payload=payload)
        assert unlinked.status_code == 200
        terminal = unlinked.json()
        assert terminal["state"] == "unlinked"
        assert terminal["plan_id"] == original_receipt["effect"]["link"]["plan_id"]
        assert terminal["plan_digest"] == original_receipt["effect"]["link"]["plan_digest"]

        await refused(
            binary,
            home,
            [
                "corporate",
                "project",
                "binding-retire",
                "plan",
                "--context",
                context,
                "--binding-operation",
                adoption["plan"]["operation_id"],
                "--state-dir",
                str(state),
            ],
        )
        await enact(another_checkout, "corporate", "project", "link", "apply")
        await refused(
            binary,
            home,
            [
                "corporate",
                "project",
                "binding-retire",
                "plan",
                "--context",
                context,
                "--binding-operation",
                adoption["plan"]["operation_id"],
                "--state-dir",
                str(state),
            ],
        )
        await enact(pending_unlink, "corporate", "project", "unlink", "apply")
        planned = await retire_plan(adoption)
        assert planned["plan"]["snapshot"]["remote_link"] == terminal
        assert planned["plan"]["registry_schema_before"] == 59
        assert planned["plan"]["registry_schema_after"] == 60

        # A server-terminal link must reject even a retained push replay or pull.
        for method, route, value in [
            ("POST", f"/v1/projects/links/{link_id}/revisions", first_push),
            ("GET", f"/v1/projects/links/{link_id}/revisions", None),
            (
                "POST",
                f"/v1/projects/links/{link_id}/sync-plans",
                {
                    "schema_version": 1,
                    "link_id": link_id,
                    "expected_link_revision": terminal["revision"],
                    "local_revision": terminal["local_revision"],
                    "remote_revision": terminal["remote_revision"],
                    "provider_revision": terminal["provider_revision"],
                    "authorization_revision": await authorization(foreign_context),
                    "idempotency_key": new_id("operation"),
                },
            ),
            (
                "POST",
                f"/v1/projects/links/{link_id}/sync-plans/{sync_plan['plan_id']}/apply",
                {
                    "schema_version": 1,
                    "plan_digest": sync_plan["plan_digest"],
                    "expected_link_revision": sync_plan["expected_link_revision"],
                    "authorization_revision": await authorization(foreign_context),
                    "idempotency_key": new_id("operation"),
                },
            ),
        ]:
            response = await api(method, route, payload=value)
            assert response.status_code == 412
        assert await current() == terminal

        # A replaced physical root refuses before querying the server.
        moved = path.with_name(path.name + "-held")
        path.rename(moved)
        path.mkdir()
        try:
            network = faults.network_requests
            unchanged = rows()
            await reject(planned)
            assert rows() == unchanged and faults.network_requests == network
        finally:
            path.rmdir()
            moved.rename(path)

        # Changed membership must refuse and must not migrate or release anything.
        async with app.state.sessionmaker() as db:
            member = await db.scalar(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == organization,
                    OrganizationMembership.account_id == account,
                )
            )
            assert member is not None
            member.state, member.revision = "suspended", member.revision + 1
            await db.commit()
        unchanged = rows()
        await reject(planned)
        assert rows() == unchanged
        async with app.state.sessionmaker() as db:
            member = await db.scalar(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == organization,
                    OrganizationMembership.account_id == account,
                )
            )
            assert member is not None
            member.state, member.revision = "active", member.revision + 1
            await db.commit()
        await reject(planned)
        planned = await retire_plan(adoption)

        # A changed local cache is not a fresh CAS match, even when the remote
        # terminal observation remains the same. No failed apply may upgrade60.
        with closing(sqlite3.connect(registry)) as db:
            db.execute(
                "UPDATE project_link SET link_revision=link_revision+1 WHERE link_id=?", (link_id,)
            )
            db.commit()
        unchanged = rows()
        await reject(planned)
        assert rows() == unchanged and rows()[0] == 59
        with closing(sqlite3.connect(registry)) as db:
            db.execute(
                "UPDATE project_link SET link_revision=link_revision-1 WHERE link_id=?", (link_id,)
            )
            db.commit()
        changed_source = path / "owned-fixture.rs"
        changed_source.write_text("// owned native retirement fixture\n")
        await enact(await run("project", "passport", "plan", "--root", str(path)), "local", "apply")
        unchanged = rows()
        await reject(planned)
        assert rows() == unchanged
        planned = await retire_plan(adoption)

        previous = Path(os.environ["AI_STP_TEST_PREVIOUS_BINDING_CLI_BINARY"])
        assert (
            os.environ["AI_STP_TEST_PREVIOUS_BINDING_CLI_SOURCE"]
            == "b44d1b606f9564741fe2c7eda7aa9ee005d9fa02"
        )
        previous_digest = sha256(previous.read_bytes()).hexdigest()
        positive = await native(
            previous, home, ["context", "create", "plan", "--label", "Previous59 positive"]
        )
        previous_plan = reviewed(positive)
        positive_receipt = await native(
            previous,
            home,
            [
                "context",
                "apply",
                "--plan",
                str(previous_plan),
                "--plan-digest",
                positive["plan_digest"],
            ],
        )
        assert positive_receipt["context_id"] == positive["plan"]["change"]["context"]["context_id"]
        # This unrelated completed context admission does not retarget the view.
        before = rows()
        writes = len(faults.writes)
        results = await asyncio.gather(
            native_result(binary, home, apply_arguments(planned)),
            native_result(binary, home, apply_arguments(planned)),
        )
        receipts: list[dict[str, Any]] = []
        for status, stdout, stderr in results:
            assert not stderr
            if status == 0:
                receipt = json.loads(stdout)["data"]
                assert receipt["state"] == "verified" and receipt["local_binding_retired"]
                receipts.append(receipt)
            else:
                failure = ErrorEnvelope.model_validate_json(stdout)
                assert failure.error.code in {
                    "AI_STP_PRECONDITION_FAILED",
                    "AI_STP_DEPENDENCY_UNAVAILABLE",
                }
        assert receipts and rows()[0] == 60 and len(faults.writes) == writes
        retired = receipts[0]
        assert await enact(planned, "corporate", "project", "binding-retire", "apply") == retired
        after = rows()
        for table, records in before[1].items():
            if table not in {"operation", "project_link", "native_checkout_reservation"}:
                assert after[1][table] == records, table
        assert len(after[1]["operation"]) == len(before[1]["operation"]) + 1
        assert (
            len(after[1]["native_checkout_reservation"])
            == len(before[1]["native_checkout_reservation"]) - 1
        )
        assert len(after[1]["native_binding_retirement"]) == 1
        unchanged = rows(), len(faults.writes), faults.network_requests
        await refused(previous, home, ["context", "list", "--state-dir", str(state)])
        assert (rows(), len(faults.writes), faults.network_requests) == unchanged
        await refused(
            binary,
            home,
            [
                "corporate",
                "project",
                "link-adopt",
                "plan",
                "--request-operation",
                source["plan"]["operation_id"],
                "--context",
                context,
                "--root",
                str(path),
                "--git-executable",
                git_executable,
                "--state-dir",
                str(state),
            ],
        )
        assert await enact(adoption, "corporate", "project", "link", "apply") == original_receipt

        # A fresh, independent request may bind the same physical project.
        _, future_adoption, future_receipt = await bind(path)
        future_link = future_receipt["effect"]["link"]["link_id"]
        assert future_link != link_id
        future = rows()
        assert await enact(planned, "corporate", "project", "binding-retire", "apply") == retired
        assert rows() == future

        # Serialize actual requests from two actors at the link row, rather than
        # relying on one device's lock to manufacture a race-free result.
        racing_push = await push_payload(future_link, actor="original")
        racing_unlink = await unlink_payload(future_link)
        pushed, stopped = await asyncio.gather(
            api("POST", f"/v1/projects/links/{future_link}/revisions", "original", racing_push),
            api("DELETE", f"/v1/projects/links/{future_link}", payload=racing_unlink),
        )
        assert sorted([pushed.status_code, stopped.status_code]) == [200, 412]
        if stopped.status_code == 412:
            stopped = await api(
                "DELETE",
                f"/v1/projects/links/{future_link}",
                payload=await unlink_payload(future_link),
            )
            assert stopped.status_code == 200
        assert (await current(future_link))["state"] == "unlinked"
        response = await api(
            "POST", f"/v1/projects/links/{future_link}/revisions", "original", racing_push
        )
        assert response.status_code == 412

    def binding_state() -> dict[str, list[tuple[Any, ...]]]:
        return {
            key: value
            for key, value in rows()[1].items()
            if key in {"project_link", "native_checkout_reservation", "native_binding_retirement"}
        }

    retained_bindings = binding_state()
    # Completed retirement has no intermediate checkpoint to invent. Both real
    # replacement flows must preserve60 and its marker using existing formats.
    async with app.state.sessionmaker() as db:
        device = await db.get(Device, original_actor["device_id"])
        assert device is not None
        device.state = "revoked"
        await db.commit()
    refresh = await run("account", "plan", "--action", "refresh")
    assert (await enact(refresh, "account", "apply"))["outcome"] == "revoked"
    recovery = await run("account", "plan", "--action", "recover")
    assert recovery["plan"]["recovery"]["interrupted_checkout_unlinks"] == []
    assert (await enact(recovery, "account", "apply"))["outcome"] == "device_replaced"
    await login(account, None)
    assert rows()[0] == 60 and binding_state() == retained_bindings
    assert await enact(planned, "corporate", "project", "binding-retire", "apply") == retired
    assert await enact(future_adoption, "corporate", "project", "link", "apply") == future_receipt

    named_plan = await run(
        "account",
        "connections",
        "plan",
        "--label",
        "Binding60 named actor",
        "--api-url",
        origin,
        "--provider",
        "github",
    )
    named = (await enact(named_plan, "account", "connections", "apply"))["connection"]
    await login(account, named["connection_id"])
    async with app.state.sessionmaker() as db:
        device = await db.get(Device, named["device_id"])
        assert device is not None
        device.state = "revoked"
        await db.commit()
    refresh = await run(
        "account", "plan", "--action", "refresh", "--connection", named["connection_id"]
    )
    assert (await enact(refresh, "account", "apply"))["outcome"] == "revoked"
    named_recovery = await run(
        "account",
        "connections",
        "recovery",
        "plan",
        "--connection",
        named["connection_id"],
        "--label",
        "Binding60 replacement",
    )
    assert named_recovery["plan"]["schema_version"] == 6
    assert named_recovery["plan"]["registry_schema_before"] == 60
    assert named_recovery["plan"]["interrupted_checkout_unlinks"] == []
    prepared = await enact(named_recovery, "account", "connections", "recovery", "apply")
    replacement = prepared["replacement_connection_id"]
    await login(account, replacement)
    await enact(named_recovery, "account", "connections", "recovery", "apply")
    assert rows()[0] == 60 and binding_state() == retained_bindings

    for enrollment in [None, replacement]:
        arguments = ["account", "plan", "--action", "logout"]
        if enrollment is not None:
            arguments.extend(["--connection", enrollment])
        await enact(await run(*arguments), "account", "apply")
    network, future = faults.network_requests, rows()
    assert await enact(planned, "corporate", "project", "binding-retire", "apply") == retired
    assert await enact(adoption, "corporate", "project", "link", "apply") == original_receipt
    assert rows() == future and faults.network_requests == network
    assert (await run("context", "list"))["selected"] == selected
    assert (path / ".env").read_bytes() == b"PRIVATE=retirement-unowned-canary\n"
    assert (path / ".env").stat().st_mode & 0o777 == 0o640
    assert changed_source.read_text() == "// owned native retirement fixture\n"
    print(
        json.dumps(
            {
                "native_active_binding_retirement_http": "passed",
                "registry_schema": 60,
                "external_authorized_unlink_actor": True,
                "advanced_heads_and_conflict_fields": True,
                "pending_checkout_and_unlink_intents_block_release": True,
                "two_real_retirement_processes": True,
                "actual_two_actor_push_unlink_race": True,
                "terminal_link_refuses_push_replay_pull_sync_creation_and_sync_apply": True,
                "stale_local_cache_and_private_passport_refused": True,
                "physical_root_and_membership_fences": True,
                "all_unrelated_logical_tables_preserved": True,
                "original_adoption_receipt_preserved": True,
                "previous_writer_source": os.environ["AI_STP_TEST_PREVIOUS_BINDING_CLI_SOURCE"],
                "previous_writer_sha256": previous_digest,
                "previous59_positive_then_refusal": True,
                "old_request_cannot_adopt_new_nonce": True,
                "new_binding_survives_old_retirement_replay": True,
                "root_and_named_replacement_preserve60_and_original_markers": True,
                "named_recovery_format": 6,
                "offline_exact_replay": True,
                "canary_bytes_and_modes_preserved": True,
                "harness_configuration_writes": 0,
                "installation_authority": False,
            }
        ),
        flush=True,
    )
