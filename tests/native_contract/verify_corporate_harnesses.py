"""Corporate setups for all seven harnesses installed into one enrolled checkout.

The company server publishes one project-scope skill setup per harness and assigns
each to the employee. The native engine acquires and installs every one into the
same physical checkout through the same binding. Each lands in its harness's own
project namespace. Codex and Antigravity share `.agents/skills`, so the second of
those two with a different file is refused before any write, and installs once
the first is removed. The server keeps one project, and unowned files survive.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from tests.native_contract.verify_ownership import native
from tests.support.native_catalog import native_surface, store_harness_setup

from ai_stp_api.session import issue_session
from ai_stp_platform.organization_models import ProjectIdentity, ProjectLink
from ai_stp_platform.storage import ImmutableObjectStore

HARNESSES = ("claude-code", "codex", "cursor", "grok-build", "opencode", "pi", "antigravity")


def skill_path(checkout: Path, harness: str) -> Path:
    namespace = next(
        name
        for name in native_surface(harness, "project")["native_namespaces"]
        if name.endswith("skills")
    )
    return checkout / namespace / "demo" / "SKILL.md"


async def qualify(
    *,
    binary: Path,
    home: Path,
    state: Path,
    app: Any,
    organization: str,
    project: str,
    account: str,
    context: str,
    connection: str,
    binding: str,
    checkout: Path,
) -> dict[str, Any]:
    async def run(*arguments: str) -> dict[str, Any]:
        return await native(binary, home, [*arguments, "--state-dir", str(state)])

    async def plan_file(planned: dict[str, Any], name: str) -> list[str]:
        path = home / f"harness-{name}.json"
        path.write_text(json.dumps(planned["plan"]), encoding="utf-8")
        return ["--plan", str(path), "--plan-digest", planned["plan_digest"]]

    async def enact(planned: dict[str, Any], *prefix: str) -> dict[str, Any]:
        return await native(binary, home, [*prefix, *await plan_file(planned, "apply")])

    store = ImmutableObjectStore(
        settings=app.state.settings.storage, client=app.state.object_client
    )
    setups: dict[str, str] = {}
    async with app.state.sessionmaker() as db:
        for index, harness in enumerate(HARNESSES, start=1):
            await store_harness_setup(db, store, harness=harness, index=index)
            setups[harness] = f"setup_01JQZK7B8N4M6P2R9T5V0X{index:04d}"
        await db.commit()
        issued = await issue_session(db, account_id=account, device_id=None, ttl_seconds=600)
        await db.commit()
    auth = {"Authorization": f"Bearer {issued.raw_token}"}
    base = f"/v1/corporate/organizations/{organization}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://api") as api:
        for harness, setup in setups.items():
            current = await api.get(f"{base}/context", headers=auth)
            assert current.status_code == 200, current.text
            assigned = await api.put(
                f"{base}/catalog-assignments",
                headers=auth,
                json={
                    "subject_kind": "employee",
                    "subject_id": account,
                    "object_kind": "setup",
                    "stable_id": setup,
                    "version": "1.0",
                    "harness": harness,
                    "state": "current",
                    "expected_revision": 0,
                    "authorization_revision": current.json()["organization"][
                        "authorization_revision"
                    ],
                    "idempotency_key": f"native-harness-assignment-{harness}",
                },
            )
            assert assigned.status_code == 200, (harness, assigned.text)

    async def projects() -> tuple[int, int]:
        async with app.state.sessionmaker() as db:
            identities = await db.scalar(select(func.count()).select_from(ProjectIdentity))
            links = await db.scalar(select(func.count()).select_from(ProjectLink))
            return int(identities or 0), int(links or 0)

    projects_before = await projects()

    origin = (await run("account", "status", "--connection", connection))["origin"]
    config = home / "corporate-harness-config.yml"
    config.write_text(f"catalog:\n  url: {origin}\n", encoding="utf-8")
    unowned = checkout / ".agents" / "skills" / "user-skill" / "SKILL.md"
    unowned.parent.mkdir(parents=True, exist_ok=True)
    unowned.write_bytes(b"unowned user skill remains\n")

    acquired_setups: set[str] = set()

    async def review(harness: str) -> dict[str, Any]:
        setup = setups[harness]
        preview = await run(
            "corporate",
            "assignments",
            "preview",
            "--harness",
            harness,
            "--project",
            project,
            "--context",
            context,
        )
        item = next(
            entry
            for entry in preview["observation"]["data"]["items"]
            if entry["stable_id"] == setup
        )
        assert item["action"] == "install", (harness, item)
        if harness not in acquired_setups:
            acquired_setups.add(harness)
            acquired = await run(
                "registry",
                "acquire",
                "plan",
                "--id",
                setup,
                "--version",
                item["version"],
                "--private",
                "--connection",
                connection,
                "--config",
                str(config),
            )
            await enact(acquired, "local", "apply")
        request = home / f"harness-{harness}-native.json"
        request.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "setup": {
                        "stable_id": setup,
                        "version": item["version"],
                        "passport_digest": item["passport_digest"],
                    },
                    "harness_id": harness,
                    "operation": "install",
                    "roots": {"project": str(checkout)},
                    "corporate_binding": binding,
                    "trust": "exact_setup",
                }
            ),
            encoding="utf-8",
        )
        return await run(
            "configuration", "native", "plan", "--context", context, "--input", str(request)
        )

    async def apply(planned: dict[str, Any], name: str) -> dict[str, Any]:
        await run("configuration", "native", "prepare", *await plan_file(planned, name))
        return await run(
            "configuration",
            "native",
            "apply",
            "--operation",
            planned["plan"]["operation_id"],
            "--plan-digest",
            planned["plan_digest"],
        )

    async def remove(receipt: dict[str, Any], operation: str, name: str) -> None:
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
        removed = await apply(removal, f"remove-{name}")
        assert removed["configuration_changed"] is True, removed

    installed: dict[str, tuple[dict[str, Any], str]] = {}
    import hashlib, os, stat
    for control in sorted(checkout.glob(".*-setup-system")):
        for item in sorted(control.rglob("*")):
            mode = stat.S_IMODE(item.stat().st_mode)
            digest = hashlib.sha256(item.read_bytes()).hexdigest()[:12] if item.is_file() else "-"
            print(json.dumps({"debug_control": str(item.relative_to(checkout)), "mode": oct(mode), "size": item.stat().st_size if item.is_file() else 0, "sha": digest}), flush=True)
    print(json.dumps({"debug_top": sorted(os.listdir(checkout))}), flush=True)
    for harness in HARNESSES:
        if harness == "antigravity":
            continue
        planned = await review(harness)
        receipt = await apply(planned, harness)
        assert receipt["configuration_changed"] is True, (harness, receipt)
        assert receipt["original_context"]["context_id"] == context
        path = skill_path(checkout, harness)
        assert f"# {harness} skill".encode() in path.read_bytes(), harness
        installed[harness] = (receipt, planned["plan"]["operation_id"])

    # Antigravity shares Codex's project namespace with a different file: refused
    # before any write while Codex owns it, then installed once Codex is removed.
    shared = skill_path(checkout, "codex")
    assert shared == skill_path(checkout, "antigravity")
    before = shared.read_bytes()
    try:
        await apply(await review("antigravity"), "antigravity-conflict")
        refused_before_write = False
    except AssertionError as refusal:
        refused_before_write = True
        print(json.dumps({"shared_namespace_refusal": str(refusal)[:400]}), flush=True)
    assert refused_before_write
    assert shared.read_bytes() == before
    receipt, operation = installed.pop("codex")
    await remove(receipt, operation, "codex")
    assert not shared.exists()
    planned = await review("antigravity")
    receipt = await apply(planned, "antigravity")
    assert b"# antigravity skill" in shared.read_bytes()
    installed["antigravity"] = (receipt, planned["plan"]["operation_id"])

    # Seven harness installations through one binding add no server project or link.
    assert await projects() == projects_before

    for harness, (receipt, operation) in installed.items():
        await remove(receipt, operation, harness)
        assert not skill_path(checkout, harness).exists(), harness
    assert unowned.read_bytes() == b"unowned user skill remains\n"
    return {
        "native_seven_harness_checkout_http": "passed",
        "harnesses": list(HARNESSES),
        "one_checkout_one_binding": True,
        "own_project_namespace_per_harness": True,
        "shared_namespace_conflict_refused_before_write": True,
        "shared_namespace_installs_after_owner_removal": True,
        "server_projects_and_links_unchanged": True,
        "unowned_preserved": True,
    }
