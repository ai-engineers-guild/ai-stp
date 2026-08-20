#!/usr/bin/env python3
"""Package a local skill directory, store artifact, create publication plan, confirm validate.

Intended for local/dev stacks with AI_STP_STORAGE_* and a live API on :8000.
Does not print secrets.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import time
import zipfile
from pathlib import Path

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Prefer installed packages (worker/api image). Fall back to monorepo checkout.
try:
    ROOT = Path(__file__).resolve().parents[2]
except IndexError:
    ROOT = Path("/app")
if (ROOT / "apps" / "platform" / "src").is_dir():
    sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))
    sys.path.insert(0, str(ROOT / "apps" / "platform" / "src"))
    sys.path.insert(0, str(ROOT / "packages" / "foundation" / "src"))
    sys.path.insert(0, str(ROOT / "packages" / "passports" / "src"))
    sys.path.insert(0, str(ROOT / "packages" / "contracts" / "src"))

from ai_stp_api.session import issue_session
from ai_stp_foundation.digests import digest_bytes
from ai_stp_foundation.ids import new_id
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_platform.models import Account, Device
from ai_stp_platform.settings import StorageSettings
from ai_stp_platform.storage import ImmutableObjectStore, S3ObjectClient
from ai_stp_platform.storage.object_store import ARTIFACT_DIGEST_DOMAIN

SKIP_DIR_NAMES = {".git", ".serena", "__pycache__", "node_modules", ".venv", ".pytest_cache"}
SKIP_FILE_SUFFIXES = {".pyc", ".pyo"}


def pack_skill(src: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src.rglob("*")):
            if not path.is_file():
                continue
            rel_parts = path.relative_to(src).parts
            if any(part in SKIP_DIR_NAMES for part in rel_parts):
                continue
            if path.suffix in SKIP_FILE_SUFFIXES:
                continue
            # Keep skill content lean: skip huge local planning dumps if present.
            if (
                rel_parts
                and rel_parts[0] in {"plans"}
                and path.suffix in {".txt", ".json"}
                and path.stat().st_size > 200_000
            ):
                continue
            zf.write(path, path.relative_to(src).as_posix())
    return buf.getvalue()


def build_passport(
    *,
    owner_id: str,
    stable_id: str,
    version: str,
    digest: str,
    size: int,
    name: str,
    description: str,
    repository: str,
    commit: str,
) -> dict[str, object]:
    passport: dict[str, object] = {
        "schema_version": 1,
        "kind": "component",
        "stable_id": stable_id,
        "revision_id": "revision_" + "0" * 64,
        "parent_revision_ids": [],
        "owner_id": owner_id,
        "created_at": "2026-08-12T00:00:00.000Z",
        "visibility": "public",
        "facts": {},
        "name": name,
        "description": description[:500],
        "version": version,
        "tags": ["skill", "resume", "manager", "ats"],
        "license": {"spdx_id": "MIT", "redistribution_allowed": True},
        "source": {
            "repository": repository,
            "commit": commit,
            "path": ".",
        },
        "artifact": {"digest": digest, "size_bytes": size},
        "requires_credentials": False,
        "requires_authorization": "none",
        "permissions": {"filesystem": [], "network": [], "process": []},
        "external_endpoints": [],
        "compatibility_evidence_refs": [],
        "harness_id": "claude-code",
        "required_env": [],
        "component_type": "skill",
        "projection_kind": "native_files",
        "variant_id": None,
        "provides_capabilities": [],
        "requires_components": [],
        "requires_capabilities": [],
        "conflicts": {
            "paths": [],
            "commands": [],
            "hooks": [],
            "mcp": [],
            "agents": [],
            "plugins": [],
        },
        "managed_paths": [],
        "native_ids": [],
    }
    passport["revision_id"] = derive_revision_id(passport)  # type: ignore[arg-type]
    return passport


async def ensure_session(db_url: str, *, account_id: str) -> tuple[str, str, str]:
    engine = create_async_engine(db_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as db:
        account = await db.get(Account, account_id)
        if account is None:
            raise ValueError(f"account does not exist: {account_id}")
        device = await db.scalar(
            select(Device).where(Device.account_id == account.id, Device.state == "active").limit(1)
        )
        if device is None:
            device = Device(
                id=new_id("device"),
                account_id=account.id,
                public_key="ZGV2LXB1YmxpYy1rZXktc2FmZXR5LXB1Ymxpc2g=",
                state="active",
            )
            db.add(device)
            await db.flush()
        issued = await issue_session(
            db, account_id=account.id, device_id=device.id, ttl_seconds=7200
        )
        await db.commit()
        out = (account.id, device.id, issued.raw_token)
    await engine.dispose()
    return out


async def store_artifact(payload: bytes, digest: str) -> None:
    settings = StorageSettings()
    async with S3ObjectClient(settings) as client:
        await client.ensure_bucket()
        store = ImmutableObjectStore(settings=settings, client=client)
        stored = await store.put_immutable(
            payload, expected_digest=digest, expected_size=len(payload)
        )
        print(
            json.dumps(
                {
                    "stored": True,
                    "bucket": stored.bucket,
                    "key": stored.key,
                    "digest": stored.digest,
                    "size_bytes": stored.size_bytes,
                    "created": stored.created,
                },
                indent=2,
            )
        )


async def run_safety_locally(payload: bytes, digest: str) -> dict[str, object]:
    from ai_stp_platform.safety.orchestrator import clear_safety_cache, run_safety_suite

    clear_safety_cache()
    result = await run_safety_suite(
        passport={"component_type": "skill", "artifact": {"digest": digest}},
        content_digest=digest,
        artifact_bytes=payload,
        use_cache=False,
    )
    outcomes = [
        {
            "check_id": o.check_id,
            "result": o.result,
            "mandatory": o.mandatory,
            "findings": len(o.findings),
            "tool": o.tool_name,
        }
        for o in result.outcomes
    ]
    mandatory_failed = [
        o["check_id"] for o in outcomes if o["result"] == "failed" and o["mandatory"]
    ]
    return {
        "wall_ms": result.wall_ms,
        "profile": result.profile,
        "mandatory_failed": mandatory_failed,
        "outcomes": outcomes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill-dir", required=True)
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument(
        "--db-url",
        default="postgresql+asyncpg://ai_stp:ai_stp_dev@localhost:5432/ai_stp",
    )
    parser.add_argument("--version", default="1.0")
    parser.add_argument(
        "--account-id",
        help=(
            "Exact owner account. Required for API publication; never inferred from database order."
        ),
    )
    parser.add_argument(
        "--stable-id",
        help=(
            "Existing component identity. Required for API publication and reused across versions."
        ),
    )
    parser.add_argument("--skip-api", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=90)
    args = parser.parse_args()

    skill_dir = Path(args.skill_dir).resolve()
    if not skill_dir.is_dir():
        print(f"skill dir missing: {skill_dir}", file=sys.stderr)
        return 2
    if not (skill_dir / "SKILL.md").is_file():
        print("SKILL.md required", file=sys.stderr)
        return 2

    payload = pack_skill(skill_dir)
    digest = digest_bytes(ARTIFACT_DIGEST_DOMAIN, payload)
    print(
        json.dumps(
            {
                "skill_dir": str(skill_dir),
                "zip_bytes": len(payload),
                "content_digest": digest,
            },
            indent=2,
        )
    )

    local = asyncio.run(run_safety_locally(payload, digest))
    print(json.dumps({"local_safety": local}, indent=2, ensure_ascii=False))

    # Storage env for host: point to published rustfs if needed.
    import os

    os.environ.setdefault("AI_STP_STORAGE_ENDPOINT", "http://localhost:9000")
    # rustfs is internal-only in compose; use docker network via exec preferably.
    # When running inside worker container, endpoint is http://rustfs:9000.

    if args.skip_api:
        return 0 if not local["mandatory_failed"] else 1

    if not args.account_id or not args.stable_id:
        print("--account-id and --stable-id are required for API publication", file=sys.stderr)
        return 2

    # Prefer in-container network: caller should exec this inside worker/api.
    asyncio.run(store_artifact(payload, digest))

    try:
        account_id, device_id, token = asyncio.run(
            ensure_session(args.db_url, account_id=args.account_id)
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    stable_id = args.stable_id
    passport = build_passport(
        owner_id=account_id,
        stable_id=stable_id,
        version=args.version,
        digest=digest,
        size=len(payload),
        name="grill-my-resume-as-manager",
        description=(
            "Critical resume review for PM/Delivery/Tech/Product managers: "
            "XYZ evidence, anti-persona filters, ATS/10s, vacancy pool match."
        ),
        repository="https://github.com/letya999/grill-my-resume-as-manager",
        commit="a" * 40,
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Idempotency-Key": new_id("operation")[10:40],
    }
    create_body = {
        "schema_version": 1,
        "object_kind": "component",
        "stable_id": stable_id,
        "version": args.version,
        "content_digest": digest,
        "policy_version": "safety-1",
        "passport": passport,
        "attestations": [],
        "idempotency_key": "pub-" + digest[-24:],
        "device_id": device_id,
    }

    with httpx.Client(base_url=args.api, timeout=60.0) as client:
        create = client.post("/v1/publications/plans", headers=headers, json=create_body)
        print("create", create.status_code, create.text[:800])
        if create.status_code not in {200, 201}:
            return 1
        plan = create.json()
        plan_id = plan["plan_id"]
        plan_hash = plan["plan_hash"]
        confirm = client.post(
            f"/v1/publications/plans/{plan_id}/confirm",
            headers={**headers, "Idempotency-Key": "confirm-" + digest[-24:]},
            json={
                "schema_version": 1,
                "plan_hash": plan_hash,
                "confirmed": True,
                "idempotency_key": "confirm-" + digest[-24:],
            },
        )
        print("confirm", confirm.status_code, confirm.text[:800])
        if confirm.status_code not in {200, 201}:
            return 1

        deadline = time.time() + args.poll_seconds
        last = None
        while time.time() < deadline:
            status = client.get(f"/v1/publications/plans/{plan_id}", headers=headers)
            last = status.json()
            state = last.get("state")
            evidence = last.get("evidence") or []
            print(f"poll state={state} evidence={len(evidence)}")
            if state in {"publish_planned", "published", "failed", "cancelled", "stale"}:
                break
            if evidence:
                break
            time.sleep(2)

        print(json.dumps({"final_plan": last}, indent=2, ensure_ascii=False)[:4000])

        # DB evidence dump for safety bindings when API evidence list is sparse.
        engine = create_async_engine(args.db_url)

        async def dump() -> None:
            async with engine.connect() as conn:
                rows = (
                    (
                        await conn.execute(
                            text(
                                """
                            select e.check_id, e.result, e.source, e.mandatory
                            from evidence_binding e
                            join validation_snapshot s on s.id = e.snapshot_id
                            where s.plan_id = :plan_id
                            order by e.check_id
                            """
                            ),
                            {"plan_id": plan_id},
                        )
                    )
                    .mappings()
                    .all()
                )
                print(json.dumps({"evidence_bindings": [dict(r) for r in rows]}, indent=2))
                safety = (
                    (
                        await conn.execute(
                            text(
                                """
                            select id, content_digest, policy_version, profile, state, wall_ms
                            from safety_scan_run
                            where content_digest = :d
                            order by id desc
                            limit 3
                            """
                            ),
                            {"d": digest},
                        )
                    )
                    .mappings()
                    .all()
                )
                print(json.dumps({"safety_scan_runs": [dict(r) for r in safety]}, indent=2))
            await engine.dispose()

        try:
            asyncio.run(dump())
        except Exception as exc:
            print(f"db dump skipped: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
