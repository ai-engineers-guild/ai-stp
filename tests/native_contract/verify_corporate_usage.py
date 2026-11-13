"""Native hook usage from an owned corporate installation to the real API.

A corporate Claude Code installation in an enrolled checkout is applied through
the native engine. The documented SessionStart hook entry then queues content-free
load signals under the original context and its consent, and delivery reaches the
production router and PostgreSQL. Refusals and removal keep their exact effects.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from tests.native_contract.verify_ownership import cli_environment
from tests.support.catalog_seed import FIXTURE_SETUP_ID

from ai_stp_api.session import issue_session
from ai_stp_platform.organization_models import CorporateCatalogAssignment
from ai_stp_platform.runtime_usage_models import RuntimeUsageEvent

Native = Any


async def hook(binary: Path, home: Path, state: Path, event: dict[str, Any]) -> bytes:
    """Run the harness hook entry exactly as a vendor does: event on stdin, no flags."""
    process = await asyncio.create_subprocess_exec(
        str(binary),
        "corporate",
        "usage",
        "hook",
        "--harness",
        "claude-code",
        "--state-dir",
        str(state),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=cli_environment(home),
    )
    stdout, stderr = await asyncio.wait_for(
        process.communicate(json.dumps(event).encode()), timeout=60
    )
    # A hook never fails its harness and never writes model context.
    assert process.returncode == 0 and stdout == b"" and stderr == b"", (stdout, stderr)
    return stdout


async def qualify(
    *,
    binary: Path,
    home: Path,
    state: Path,
    app: Any,
    run: Native,
    enact: Native,
    organization: str,
    project: str,
    account: str,
    context: str,
    connection: str,
    binding: str,
    checkout: Path,
) -> dict[str, Any]:
    async with app.state.sessionmaker() as db:
        issued = await issue_session(db, account_id=account, device_id=None, ttl_seconds=600)
        await db.commit()
    auth = {"Authorization": f"Bearer {issued.raw_token}"}
    base = f"/v1/corporate/organizations/{organization}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://api") as api:

        async def revision() -> int:
            current = await api.get(f"{base}/context", headers=auth)
            assert current.status_code == 200, current.text
            return int(current.json()["organization"]["authorization_revision"])

        current = await api.get(f"{base}/telemetry/policy", headers=auth)
        policy_revision = current.json()["policy_revision"] if current.status_code == 200 else 0
        saved = await api.put(
            f"{base}/telemetry/policy",
            headers=auth,
            json={
                "schema_version": 1,
                "raw_retention_days": 90,
                "aggregate_retention_days": 365,
                "legal_basis": "consent",
                "notice_revision": 0,
                "heartbeat_enabled": False,
                "usage_collection_enabled": True,
                "expected_policy_revision": policy_revision,
                "authorization_revision": await revision(),
                "idempotency_key": "native-usage-policy-enable",
            },
        )
        assert saved.status_code == 200, saved.text
        # Earlier precedence controls retire the employee's Claude Code decision;
        # put that exact decision back for this installation.
        async with app.state.sessionmaker() as db:
            held = await db.scalar(
                select(CorporateCatalogAssignment).where(
                    CorporateCatalogAssignment.organization_id == organization,
                    CorporateCatalogAssignment.account_id == account,
                    CorporateCatalogAssignment.harness == "claude-code",
                    CorporateCatalogAssignment.stable_id == FIXTURE_SETUP_ID,
                )
            )
            expected = held.revision if held is not None else 0
        assigned = await api.put(
            f"{base}/catalog-assignments",
            headers=auth,
            json={
                "subject_kind": "employee",
                "subject_id": account,
                "object_kind": "setup",
                "stable_id": FIXTURE_SETUP_ID,
                "version": "1.0",
                "harness": "claude-code",
                "state": "current",
                "expected_revision": expected,
                "authorization_revision": await revision(),
                "idempotency_key": "native-usage-employee-assignment",
            },
        )
        assert assigned.status_code == 200, assigned.text

    preview = await run(
        "corporate",
        "assignments",
        "preview",
        "--harness",
        "claude-code",
        "--project",
        project,
        "--context",
        context,
    )
    item = next(
        item
        for item in preview["observation"]["data"]["items"]
        if item["stable_id"] == FIXTURE_SETUP_ID
    )
    version = item["version"]
    acquired = await run(
        "registry",
        "acquire",
        "plan",
        "--id",
        FIXTURE_SETUP_ID,
        "--version",
        version,
        "--private",
        "--connection",
        connection,
    )
    await enact(acquired, "local", "apply")
    request = home / "corporate-usage-native.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "setup": {
                    "stable_id": FIXTURE_SETUP_ID,
                    "version": version,
                    "passport_digest": item["passport_digest"],
                },
                "harness_id": "claude-code",
                "operation": "install",
                "roots": {"project": str(checkout)},
                "corporate_binding": binding,
                "trust": "exact_setup",
            }
        ),
        encoding="utf-8",
    )
    review = await run(
        "configuration", "native", "plan", "--context", context, "--input", str(request)
    )
    await enact(review, "configuration", "native", "prepare")
    operation, digest = review["plan"]["operation_id"], review["plan_digest"]
    receipt = await run(
        "configuration", "native", "apply", "--operation", operation, "--plan-digest", digest
    )
    assert receipt["configuration_changed"] is True
    assert receipt["original_context"]["context_id"] == context

    session = "native-usage-session-0001"
    event = {"session_id": session, "cwd": str(checkout / "src"), "hook_event_name": "SessionStart"}
    (checkout / "src").mkdir(exist_ok=True)

    async def rows() -> int:
        async with app.state.sessionmaker() as db:
            return int(await db.scalar(select(func.count()).select_from(RuntimeUsageEvent)) or 0)

    # Without consent the hook records nothing and still succeeds.
    await hook(binary, home, state, event)
    assert (await run("corporate", "usage", "status", "--context", context))["pending"] == 0

    consent = await run("corporate", "usage", "consent", "plan", "--context", context)
    await enact(consent, "corporate", "usage", "consent", "apply")
    await hook(binary, home, state, event)
    queued = (await run("corporate", "usage", "status", "--context", context))["pending"]
    assert queued >= 1
    # The same vendor session is one observation per component, never a second event.
    await hook(binary, home, state, event)
    assert (await run("corporate", "usage", "status", "--context", context))["pending"] == queued
    # A directory outside the enrolled checkout belongs to no owned installation.
    await hook(
        binary, home, state, {**event, "session_id": "native-usage-elsewhere", "cwd": str(home)}
    )
    assert (await run("corporate", "usage", "status", "--context", context))["pending"] == queued

    before = await rows()
    delivered = await run("corporate", "usage", "flush", "--context", context)
    assert delivered["pending"] == 0, delivered
    assert await rows() == before + queued
    async with app.state.sessionmaker() as db:
        stored = list(
            (
                await db.scalars(
                    select(RuntimeUsageEvent).where(
                        RuntimeUsageEvent.organization_id == organization
                    )
                )
            ).all()
        )
    native_rows = [row for row in stored if row.source == "native_hook"]
    assert len(native_rows) == queued
    assert {row.harness for row in native_rows} == {"claude-code"}
    assert {row.project_id for row in native_rows} == {project}
    assert {row.activity_kind for row in native_rows} == {"load"}
    # Replaying a delivered session adds nothing on the server.
    await hook(binary, home, state, event)
    await run("corporate", "usage", "flush", "--context", context)
    assert await rows() == before + queued

    removal = await run(
        "configuration",
        "native",
        "remove",
        "plan",
        "--operation",
        operation,
        "--plan-digest",
        receipt["review_digest"],
    )
    await enact(removal, "configuration", "native", "prepare")
    await run(
        "configuration",
        "native",
        "apply",
        "--operation",
        removal["plan"]["operation_id"],
        "--plan-digest",
        removal["plan_digest"],
    )
    # After removal the session belongs to no owned component.
    await hook(binary, home, state, {**event, "session_id": "native-usage-after-removal"})
    assert (await run("corporate", "usage", "status", "--context", context))["pending"] == 0
    assert (await run("corporate", "usage", "disable", "--context", context))["enabled"] is False
    return {
        "native_hook_usage_http": "passed",
        "harness": "claude-code",
        "components_reported": queued,
        "consent_required": True,
        "session_idempotent": True,
        "outside_checkout_ignored": True,
        "removed_installation_ignored": True,
        "hook_stdout_bytes": 0,
    }
