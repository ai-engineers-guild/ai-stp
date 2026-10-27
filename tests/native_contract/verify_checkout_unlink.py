"""Actual API unlink transactions, native original intent and unchanged local bindings."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from collections.abc import Awaitable, Callable
from contextlib import closing
from datetime import datetime, timedelta, tzinfo
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.native_contract.verify_ownership import native, native_result

from ai_stp_api.session import AuthContext
from ai_stp_api.slices.context import service as context_service
from ai_stp_contracts.context import ProjectUnlinkPlanOutcome
from ai_stp_foundation.envelope import ErrorEnvelope
from ai_stp_platform.models import Device
from ai_stp_platform.organization_models import (
    OrganizationMembership,
    ProjectLink,
    ProjectUnlinkPlan,
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
    context: str,
    connection: str,
    foreign_context: str,
    checkout: Callable[[str], Awaitable[Path]],
) -> None:
    registry = state / "ai-stp-v2-state" / "registry.sqlite3"
    active_context = context
    paths: list[Path] = []

    def local() -> tuple[int, list[tuple[Any, ...]], list[tuple[Any, ...]]]:
        with closing(sqlite3.connect(f"file:{registry}?mode=ro", uri=True)) as db:
            return (
                int(db.execute("PRAGMA user_version").fetchone()[0]),
                db.execute("SELECT * FROM project_link ORDER BY local_project_id").fetchall(),
                db.execute(
                    "SELECT * FROM native_checkout_reservation ORDER BY request_operation_id"
                ).fetchall(),
            )

    def native_rows() -> list[tuple[Any, ...]]:
        with closing(sqlite3.connect(f"file:{registry}?mode=ro", uri=True)) as db:
            return db.execute("SELECT * FROM operation ORDER BY operation_id").fetchall()

    def logical_registry() -> tuple[int, dict[str, list[tuple[Any, ...]]]]:
        with closing(sqlite3.connect(f"file:{registry}?mode=ro", uri=True)) as db:
            tables: list[tuple[str]] = db.execute(
                "SELECT name FROM sqlite_schema "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            rows: dict[str, list[tuple[Any, ...]]] = {}
            for (name,) in tables:
                quoted = '"' + name.replace('"', '""') + '"'
                rows[name] = sorted(db.execute("SELECT * FROM " + quoted).fetchall(), key=repr)
            return int(db.execute("PRAGMA user_version").fetchone()[0]), rows

    def reviewed(planned: dict[str, Any]) -> Path:
        path = (
            home / f"unlink-{planned['plan']['operation_id']}-{planned['plan_digest'][7:23]}.json"
        )
        value = json.dumps(planned["plan"])
        if path.exists():
            assert path.read_text(encoding="utf-8") == value
        else:
            path.write_text(value, encoding="utf-8")
            path.chmod(0o600)
        return path

    async def apply_once(
        planned: dict[str, Any],
        *,
        retire: bool = False,
        reader: str | None = None,
        link: bool = False,
    ) -> dict[str, Any]:
        arguments = [
            "corporate",
            "project",
            "link" if link else "unlink-retire" if retire else "unlink",
            "apply",
            "--plan",
            str(reviewed(planned)),
            "--plan-digest",
            planned["plan_digest"],
        ]
        if reader is not None:
            arguments.extend(["--context", reader])
        return await native(binary, home, arguments)

    async def reject(
        planned: dict[str, Any], *, retire: bool = False, reader: str | None = None
    ) -> ErrorEnvelope:
        arguments = [
            "corporate",
            "project",
            "unlink-retire" if retire else "unlink",
            "apply",
            "--plan",
            str(reviewed(planned)),
            "--plan-digest",
            planned["plan_digest"],
        ]
        if reader is not None:
            arguments.extend(["--context", reader])
        return await refused(binary, home, arguments)

    async def concurrent_apply(
        planned: dict[str, Any], *, route: str, link: bool = False
    ) -> dict[str, Any]:
        # Real processes must produce a positive receipt and only one first POST.
        planned_posts = faults.writes.count(route)
        arguments = [
            "corporate",
            "project",
            "link" if link else "unlink",
            "apply",
            "--plan",
            str(reviewed(planned)),
            "--plan-digest",
            planned["plan_digest"],
        ]
        results = await asyncio.gather(
            native_result(binary, home, arguments),
            native_result(binary, home, arguments),
        )
        planned_receipts: list[dict[str, Any]] = []
        for status, stdout, stderr in results:
            assert not stderr
            if status == 0:
                receipt: dict[str, Any] = json.loads(stdout)["data"]
                assert receipt["state"] == "completed"
                assert receipt["operation_id"] == planned["plan"]["operation_id"]
                planned_receipts.append(receipt)
            else:
                failure = ErrorEnvelope.model_validate_json(stdout)
                assert failure.error.details is not None
                if failure.error.code == "AI_STP_PRECONDITION_FAILED":
                    assert failure.error.details["reason"] == "concurrent_admission"
                    assert failure.error.details["operation_id"] == planned["plan"]["operation_id"]
                else:
                    assert failure.error.code == "AI_STP_DEPENDENCY_UNAVAILABLE"
                    assert failure.error.details["stage"] == "lock_timeout"
        assert planned_receipts and faults.writes.count(route) == planned_posts + 1
        assert await apply_once(planned, link=link) == planned_receipts[0]
        return planned_receipts[0]

    async def bind(label: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
        path = await checkout("unlink-" + label)
        paths.append(path)
        request = await run(
            "corporate",
            "project",
            "link-request",
            "plan",
            "--context",
            active_context,
            "--root",
            str(path),
            "--project",
            project,
            "--git-executable",
            git_executable,
        )
        if label == "committed":
            assert request["plan"]["registry_schema_before"] == 58
            assert request["plan"]["registry_schema_after"] == 58
            await concurrent_apply(
                request,
                route=f"/v1/organizations/{organization}/project-link-plans",
                link=True,
            )
        else:
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
        adoption = await run(
            "corporate",
            "project",
            "link-adopt",
            "plan",
            "--request-operation",
            request["plan"]["operation_id"],
            "--context",
            active_context,
            "--root",
            str(path),
            "--git-executable",
            git_executable,
        )
        receipt = await enact(adoption, "corporate", "project", "link", "apply")
        return path, adoption, receipt

    async def request(binding: dict[str, Any], reader: str | None = None) -> dict[str, Any]:
        return await run(
            "corporate",
            "project",
            "unlink-request",
            "plan",
            "--binding-operation",
            binding["plan"]["operation_id"],
            "--context",
            reader or active_context,
        )

    async def confirmation(original: dict[str, Any]) -> dict[str, Any]:
        return await run(
            "corporate",
            "project",
            "unlink-confirm",
            "plan",
            "--request-operation",
            original["plan"]["operation_id"],
        )

    async def remote(link_id: str) -> tuple[int, int]:
        async with app.state.sessionmaker() as db:
            plans = await db.scalar(
                select(func.count())
                .select_from(ProjectUnlinkPlan)
                .where(ProjectUnlinkPlan.link_id == link_id)
            )
            link = await db.get(ProjectLink, link_id)
            assert isinstance(plans, int) and link is not None
            return plans, link.revision

    selected = (await run("context", "list"))["selected"]
    assert selected["context_id"] == offline_context and local()[0] == 58
    foreign_view = (await run("context", "show", "--context", foreign_context))["context"]
    foreign_enrollment = foreign_view["authority"]["account"]["connection"]["connection_id"]
    refreshed_foreign = await run(
        "context",
        "create",
        "plan",
        "--label",
        "Unlink foreign actor control",
        "--connection",
        foreign_enrollment,
        "--organization",
        organization,
    )
    foreign_context = (await enact(refreshed_foreign, "context", "apply"))["context_id"]
    previous = Path(os.environ["AI_STP_TEST_PREVIOUS_CLI_BINARY"])
    assert (
        os.environ["AI_STP_TEST_PREVIOUS_CLI_SOURCE"] == "0f2589f40e7ebc3155a305965b1056fb6df63581"
    )
    assert previous.is_file()
    previous_sha = sha256(previous.read_bytes()).hexdigest()
    old_help = await native(previous, home, ["help", "--agent"])
    assert not any(
        row["path"] == ["corporate", "project", "unlink-request", "plan"]
        for row in old_help["commands"]
    )
    assert (await native(previous, home, ["context", "list", "--state-dir", str(state)]))[
        "selected"
    ] == selected
    _, binding, link_receipt = await bind("committed")
    before = local()
    await run("corporate", "teams", "--context", foreign_context)
    foreign_network = faults.network_requests
    await refused(
        binary,
        home,
        [
            "corporate",
            "project",
            "unlink-request",
            "plan",
            "--binding-operation",
            binding["plan"]["operation_id"],
            "--context",
            foreign_context,
            "--state-dir",
            str(state),
        ],
    )
    assert faults.network_requests == foreign_network and local() == before
    old_control = await native(
        previous,
        home,
        [
            "context",
            "create",
            "plan",
            "--label",
            "Schema58 write positive control",
            "--state-dir",
            str(state),
        ],
    )
    controlled = await native(
        previous,
        home,
        [
            "context",
            "apply",
            "--plan",
            str(reviewed(old_control)),
            "--plan-digest",
            old_control["plan_digest"],
        ],
    )
    assert controlled["context_id"] == old_control["plan"]["change"]["context"]["context_id"]
    old_plan = await native(
        previous,
        home,
        [
            "context",
            "create",
            "plan",
            "--label",
            "Unadmitted schema58 writer",
            "--state-dir",
            str(state),
        ],
    )
    # Server revision is independent of the immutable local adoption receipt.
    # Advance only fixture state; both unlink transactions still use the real API.
    async with app.state.sessionmaker() as db:
        original_link = link_receipt["effect"]["link"]["link_id"]
        linked = await db.get(ProjectLink, original_link)
        assert linked is not None
        cached_revision = linked.revision
        linked.revision += 2
        await db.commit()
    original = await request(binding)
    assert original["plan"]["change"]["snapshot"]["remote_link"]["revision"] == cached_revision + 2
    assert (
        original["plan"]["registry_schema_before"] == 58
        and original["plan"]["registry_schema_after"] == 59
    )
    link_id = original["plan"]["change"]["snapshot"]["remote_link"]["link_id"]
    plan_route = f"/v1/organizations/{organization}/project-unlink-plans"
    delete_route = f"/v1/projects/links/{link_id}"
    faults.lose_next = plan_route
    lost = await reject(original)
    assert lost.error.code == "AI_STP_DEPENDENCY_UNAVAILABLE"
    assert (
        lost.error.details is not None
        and lost.error.details["operation_id"] == original["plan"]["operation_id"]
    )
    assert faults.lose_next is None and local() == (59, before[1], before[2])
    assert await remote(link_id) == (
        1,
        original["plan"]["change"]["snapshot"]["remote_link"]["revision"],
    )

    # The same unused old writer was valid before the sole epoch transition.
    unchanged = logical_registry(), len(faults.writes)
    old_path = reviewed(old_plan)
    old_failure = await refused(
        previous,
        home,
        ["context", "apply", "--plan", str(old_path), "--plan-digest", old_plan["plan_digest"]],
    )
    assert (
        old_failure.error.code == "AI_STP_PRECONDITION_FAILED"
        and "schema" in old_failure.error.message.lower()
    )
    assert (logical_registry(), len(faults.writes)) == unchanged
    resumed = await apply_once(original)
    assert resumed["state"] == "completed" and resumed["effect"]["outcome_reader"] is not None
    network = faults.network_requests
    assert await apply_once(original) == resumed and faults.network_requests == network

    stale_session = await confirmation(original)
    refreshed = await run("account", "plan", "--action", "refresh")
    await enact(refreshed, "account", "apply")
    session_rows, session_writes = native_rows(), len(faults.writes)
    await reject(stale_session)
    assert native_rows() == session_rows and len(faults.writes) == session_writes
    frozen = await confirmation(original)
    assert frozen["plan"]["operation_id"] == stale_session["plan"]["operation_id"]
    assert frozen["plan_digest"] != stale_session["plan_digest"]
    competing = await confirmation(original)
    assert frozen["plan"]["operation_id"] == competing["plan"]["operation_id"]
    assert frozen["plan_digest"] != competing["plan_digest"]
    faults.lose_next = delete_route
    await reject(frozen)
    assert faults.lose_next is None
    writes = len(faults.writes)
    await reject(competing)
    assert len(faults.writes) == writes and local() == (59, before[1], before[2])
    await refused(
        binary,
        home,
        [
            "corporate",
            "project",
            "unlink-retire",
            "plan",
            "--operation",
            frozen["plan"]["operation_id"],
            "--context",
            active_context,
            "--state-dir",
            str(state),
        ],
    )
    settled = await apply_once(frozen)
    assert (
        settled["state"] == "completed"
        and settled["remote_outcome"] == "unlinked"
        and not settled["local_binding_retired"]
    )
    assert settled["effect"]["outcome_reader"] is not None
    assert faults.writes.count(delete_route) == 1 and await remote(link_id) == (
        1,
        original["plan"]["change"]["snapshot"]["remote_link"]["revision"] + 1,
    )
    network = faults.network_requests
    assert await apply_once(frozen) == settled and faults.network_requests == network
    assert local() == (59, before[1], before[2])

    pending_path, pending_binding, _ = await bind("unapplied")
    pending_before = local()
    displaced_review = await request(pending_binding)
    displaced = pending_path.with_name(pending_path.name + "-original")
    assert not displaced.exists()
    physical_rows, physical_network = native_rows(), faults.network_requests
    replacement_canary = pending_path / ".env"
    pending_path.rename(displaced)
    try:
        pending_path.mkdir()
        replacement_canary.write_bytes(b"PRIVATE=replacement-checkout-canary\n")
        replacement_canary.chmod(0o640)
        await reject(displaced_review)
        assert native_rows() == physical_rows and faults.network_requests == physical_network
        assert local() == pending_before
        assert replacement_canary.read_bytes() == b"PRIVATE=replacement-checkout-canary\n"
        assert replacement_canary.stat().st_mode & 0o777 == 0o640
    finally:
        # Only these two fixture-created entries can be removed.
        if pending_path.exists():
            replacement_canary.unlink(missing_ok=True)
            pending_path.rmdir()
        displaced.rename(pending_path)
    concurrent = await request(pending_binding)
    await concurrent_apply(concurrent, route=plan_route)
    assert local() == pending_before

    unknown = await request(pending_binding)
    faults.refuse_next = plan_route
    await reject(unknown)
    assert faults.refuse_next is None
    writes = len(faults.writes)
    await reject(unknown)  # Actual original-result404, without another POST.
    await refused(
        binary,
        home,
        [
            "corporate",
            "project",
            "unlink-request",
            "plan",
            "--binding-operation",
            pending_binding["plan"]["operation_id"],
            "--context",
            active_context,
            "--state-dir",
            str(state),
        ],
    )
    assert len(faults.writes) == writes
    network = faults.network_requests
    stopping = await run(
        "corporate",
        "project",
        "unlink-retire",
        "plan",
        "--operation",
        unknown["plan"]["operation_id"],
    )
    stopped = await apply_once(stopping, retire=True)
    assert stopped["remote_outcome"] == "unknown" and not stopped["local_binding_retired"]
    assert await apply_once(stopping, retire=True) == stopped
    assert (await apply_once(unknown))["state"] == "retired" and faults.network_requests == network
    assert local() == pending_before

    expiring = await request(pending_binding)
    await apply_once(expiring)
    expiry_confirmation = await confirmation(expiring)
    expiry_link = expiry_confirmation["plan"]["change"]["snapshot"]["remote_link"]["link_id"]
    expiry_delete = f"/v1/projects/links/{expiry_link}"
    faults.refuse_next = expiry_delete
    await reject(expiry_confirmation)
    assert faults.refuse_next is None
    retirement_args = [
        "corporate",
        "project",
        "unlink-retire",
        "plan",
        "--operation",
        expiry_confirmation["plan"]["operation_id"],
        "--context",
        active_context,
    ]
    await refused(binary, home, [*retirement_args, "--state-dir", str(state)])
    faults.unsupported_settlement = True
    await refused(binary, home, [*retirement_args, "--state-dir", str(state)])
    faults.unsupported_settlement = False
    faults.unavailable_reads = True
    await refused(binary, home, [*retirement_args, "--state-dir", str(state)])
    faults.unavailable_reads = False
    assert local() == pending_before
    expires = datetime.fromisoformat(
        expiry_confirmation["plan"]["change"]["server_plan"]["expires_at"].replace("Z", "+00:00")
    )
    advanced = expires + timedelta(seconds=1)

    class AfterExpiry(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Self:
            return cls.fromtimestamp(advanced.timestamp(), tz)

    original_settlement = context_service.read_project_unlink_plan_settlement

    async def after_expiry(
        db: AsyncSession, *, ctx: AuthContext, organization_id: str, plan_id: str
    ) -> ProjectUnlinkPlanOutcome:
        # Only the actual serialized settlement sees future server time;
        # capability observations and native wall clock retain their real time.
        with patch("ai_stp_api.slices.context.service.datetime", AfterExpiry):
            return await original_settlement(
                db, ctx=ctx, organization_id=organization_id, plan_id=plan_id
            )

    with patch.object(context_service, "read_project_unlink_plan_settlement", after_expiry):
        retiring = await run(*retirement_args)
    await reject(retiring, retire=True)  # Fresh actual settlement is ready again.
    assert local() == pending_before
    with patch.object(context_service, "read_project_unlink_plan_settlement", after_expiry):
        retired = await apply_once(retiring, retire=True)
    assert retired["remote_outcome"] == "expired_unapplied" and not retired["local_binding_retired"]
    network = faults.network_requests
    assert await apply_once(retiring, retire=True) == retired
    assert (await apply_once(expiry_confirmation))[
        "state"
    ] == "retired" and faults.network_requests == network
    assert local() == pending_before and faults.writes.count(expiry_delete) == 1

    # A reviewed old policy cannot admit another original request.
    policy_review = await request(pending_binding)
    async with app.state.sessionmaker() as db:
        member = await db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization,
                OrganizationMembership.account_id == account,
            )
        )
        assert member is not None
        member.revision += 1
        await db.commit()
    policy_rows, policy_writes = native_rows(), len(faults.writes)
    await reject(policy_review)
    assert native_rows() == policy_rows and len(faults.writes) == policy_writes
    await reject(await request(pending_binding), reader=offline_context)
    assert native_rows() == policy_rows and len(faults.writes) == policy_writes

    async def fresh_context(label: str, enrollment: str | None) -> str:
        arguments = ["context", "create", "plan", "--label", label, "--organization", organization]
        arguments += ["--legacy-account"] if enrollment is None else ["--connection", enrollment]
        return (await enact(await run(*arguments), "context", "apply"))["context_id"]

    # Lost create plus root replacement preserves the old actor, and a current
    # same-account context can only observe that original request afterward.
    _, root_binding, _ = await bind("root-recovery")
    root_request = await request(root_binding)
    faults.lose_next = plan_route
    await reject(root_request)
    assert faults.lose_next is None
    unused_confirmation = await confirmation(root_request)
    root_before, root_writes = local(), len(faults.writes)
    root_device = root_request["plan"]["change"]["snapshot"]["account"]["device_id"]
    async with app.state.sessionmaker() as db:
        device = await db.get(Device, root_device)
        assert device is not None
        device.state = "revoked"
        await db.commit()
    refresh = await run("account", "plan", "--action", "refresh")
    assert (await enact(refresh, "account", "apply"))["outcome"] == "revoked"
    recovery = await run("account", "plan", "--action", "recover")
    assert [
        item["operation_id"]
        for item in recovery["plan"]["recovery"]["interrupted_checkout_unlinks"]
    ] == [root_request["plan"]["operation_id"]]
    assert (await enact(recovery, "account", "apply"))["outcome"] == "device_replaced"
    interrupted = await run(
        "corporate",
        "project",
        "unlink",
        "show",
        "--operation",
        root_request["plan"]["operation_id"],
    )
    assert interrupted["state"] == "interrupted" and interrupted["remote_outcome"] == "unknown"
    assert local() == root_before
    await login(account, None)
    active_context = await fresh_context("Native unlink root replacement", None)
    held_rows = native_rows()
    await reject(unused_confirmation)
    await refused(
        binary,
        home,
        [
            "corporate",
            "project",
            "unlink-request",
            "plan",
            "--binding-operation",
            root_binding["plan"]["operation_id"],
            "--context",
            active_context,
            "--state-dir",
            str(state),
        ],
    )
    assert native_rows() == held_rows and len(faults.writes) == root_writes
    before_wrong_reader = faults.network_requests
    await reject(root_request, reader=offline_context)
    assert faults.network_requests == before_wrong_reader
    await run("corporate", "teams", "--context", foreign_context)
    foreign_network = faults.network_requests
    await reject(root_request, reader=foreign_context)
    assert faults.network_requests == foreign_network
    organizations = (await run("account", "organizations", "--legacy-account"))["organizations"][
        "items"
    ]
    other_company = next(
        item["organization_id"]
        for item in organizations
        if item["kind"] == "corporate" and item["organization_id"] != organization
    )
    another_company = await run(
        "context",
        "create",
        "plan",
        "--label",
        "Unlink same-account other company",
        "--legacy-account",
        "--organization",
        other_company,
    )
    other_context = (await enact(another_company, "context", "apply"))["context_id"]
    await run("corporate", "teams", "--context", other_context)
    other_network = faults.network_requests
    await reject(root_request, reader=other_context)
    await refused(
        binary,
        home,
        [
            "corporate",
            "project",
            "unlink-request",
            "plan",
            "--binding-operation",
            root_binding["plan"]["operation_id"],
            "--context",
            other_context,
            "--state-dir",
            str(state),
        ],
    )
    assert faults.network_requests == other_network
    root_observed = await apply_once(root_request, reader=active_context)
    assert (
        root_observed["state"] == "completed"
        and root_observed["original_interruption"] == interrupted["original_interruption"]
    )
    assert root_observed["effect"]["outcome_reader"]["device_id"] != root_device
    assert len(faults.writes) == root_writes and local() == root_before

    # Named recovery uses format6 on59 and cannot resubmit the lost DELETE.
    _, named_binding, _ = await bind("named-recovery")
    named_context = await fresh_context("Native unlink named actor", connection)
    named_request = await request(named_binding, named_context)
    await apply_once(named_request)
    named_confirmation = await confirmation(named_request)
    named_link = named_confirmation["plan"]["change"]["snapshot"]["remote_link"]["link_id"]
    named_delete = f"/v1/projects/links/{named_link}"
    faults.lose_next = named_delete
    await reject(named_confirmation)
    assert faults.lose_next is None
    named_before, named_writes = local(), len(faults.writes)
    named_device = named_confirmation["plan"]["change"]["snapshot"]["account"]["device_id"]
    async with app.state.sessionmaker() as db:
        device = await db.get(Device, named_device)
        assert device is not None
        device.state = "revoked"
        await db.commit()
    refresh = await run("account", "plan", "--action", "refresh", "--connection", connection)
    assert (await enact(refresh, "account", "apply"))["outcome"] == "revoked"
    named_recovery = await run(
        "account",
        "connections",
        "recovery",
        "plan",
        "--connection",
        connection,
        "--label",
        "Native unlink named replacement",
    )
    assert named_recovery["plan"]["schema_version"] == 6
    assert [
        item["operation_id"] for item in named_recovery["plan"]["interrupted_checkout_unlinks"]
    ] == [named_confirmation["plan"]["operation_id"]]
    prepared = await enact(named_recovery, "account", "connections", "recovery", "apply")
    named_interrupted = await run(
        "corporate",
        "project",
        "unlink",
        "show",
        "--operation",
        named_confirmation["plan"]["operation_id"],
    )
    assert named_interrupted["state"] == "interrupted" and local() == named_before
    replacement_connection = prepared["replacement_connection_id"]
    await login(account, replacement_connection)
    named_reader = await fresh_context("Native unlink replacement reader", replacement_connection)
    named_observed = await apply_once(named_confirmation, reader=named_reader)
    assert named_observed["state"] == "completed" and named_observed["remote_outcome"] == "unlinked"
    assert named_observed["original_interruption"] == named_interrupted["original_interruption"]
    assert named_observed["effect"]["outcome_reader"]["device_id"] != named_device
    assert (
        local() == named_before
        and len(faults.writes) == named_writes
        and faults.writes.count(named_delete) == 1
    )

    # Historical receipts require no account, checkout reopening or new write.
    for enrollment in (None, replacement_connection):
        arguments = ["account", "plan", "--action", "logout"]
        if enrollment is not None:
            arguments.extend(["--connection", enrollment])
        await enact(await run(*arguments), "account", "apply")
    network = faults.network_requests
    before_replay = local()
    assert await apply_once(original) == resumed
    assert await apply_once(frozen) == settled
    assert await apply_once(root_request) == root_observed
    assert await apply_once(named_confirmation) == named_observed
    assert await apply_once(stopping, retire=True) == stopped
    assert await apply_once(retiring, retire=True) == retired
    assert await enact(binding, "corporate", "project", "link", "apply") == link_receipt
    assert faults.network_requests == network and local() == before_replay
    assert (await run("context", "list"))["selected"] == selected
    for path in paths:
        assert (path / ".env").read_bytes() == b"PRIVATE=retirement-unowned-canary\n"
        assert (path / ".env").stat().st_mode & 0o777 == 0o640
    print(
        json.dumps(
            {
                "native_checkout_unlink_http": "passed",
                "registry_schema": 59,
                "actual_server_transactions": True,
                "lost_create_and_delete_replies": True,
                "original_result_reads_only": True,
                "competing_confirmation_slot": True,
                "concurrent_cli_first_write_submitted_once": True,
                "concurrent_legacy_checkout_post_submitted_once": True,
                "stale_session_refused_before_admission": True,
                "physical_checkout_replacement_refused_before_query": True,
                "current_remote_revision_not_cached_adoption": True,
                "request_unknown_retirement": True,
                "fresh_expired_confirmation_retirement": True,
                "active_bindings_and_reservations_retained": True,
                "wrong_actor_and_company_refused_before_query": True,
                "membership_revision_refused_before_admission": True,
                "root_and_named_replacement": True,
                "interrupted_request_blocks_new_nonce_after_replacement": True,
                "named_recovery_version": 6,
                "previous_writer_source": os.environ["AI_STP_TEST_PREVIOUS_CLI_SOURCE"],
                "previous_writer_sha256": previous_sha,
                "previous_writer_positive_control_and_refusal": True,
                "offline_exact_replay": True,
                "canary_bytes_and_modes_preserved": True,
                "harness_configuration_writes": 0,
                "installation_authority": False,
            }
        ),
        flush=True,
    )
