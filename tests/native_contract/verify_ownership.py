"""Real PostgreSQL, HTTP and native exact-setup acquisition after ownership transfer."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import tempfile
from pathlib import Path
from typing import Any

import uvicorn
from alembic import command
from alembic.config import Config
from tests.api.platform.conftest import make_settings
from tests.support.catalog_seed import (
    FIXTURE_COMPONENT_ID,
    FIXTURE_SETUP_ID,
    SEED_OWNER_ACCOUNT_ID,
    load_fixture_seed,
)
from tests.support.native_catalog import store_fixture_artifacts
from tests.support.native_runner import cli_environment
from tests.support.postgres import isolated_database

from ai_stp_api.app import create_app
from ai_stp_foundation.ids import new_id
from ai_stp_platform.catalog_transfer import transfer_catalog_line
from ai_stp_platform.models import (
    Account,
    CatalogIdentity,
    CatalogMetadata,
    ReportCase,
)
from ai_stp_platform.storage import ImmutableObjectStore, MemoryObjectClient

ARTIFACT_DOMAIN = "ai-stp:artifact:v1"
PASSPORT_DOMAIN = "ai-stp:passport:v1"


class ObservedObjects(MemoryObjectClient):
    def __init__(self) -> None:
        super().__init__()
        self.reads: set[tuple[str, str]] = set()

    async def get_object_bytes(self, *, bucket: str, key: str) -> bytes | None:
        self.reads.add((bucket, key))
        return await super().get_object_bytes(bucket=bucket, key=key)


async def native_result(binary: Path, home: Path, arguments: list[str]) -> tuple[int, bytes, bytes]:
    process = await asyncio.create_subprocess_exec(
        str(binary),
        *arguments,
        "--json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=cli_environment(home),
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise
    assert process.returncode is not None
    return process.returncode, stdout, stderr


async def native(binary: Path, home: Path, arguments: list[str]) -> dict[str, Any]:
    status, stdout, stderr = await native_result(binary, home, arguments)
    assert status == 0, (arguments, stdout.decode(), stderr.decode())
    assert not stderr, stderr.decode()
    return json.loads(stdout)["data"]


async def apply(
    binary: Path, home: Path, planned: dict[str, Any], prefix: list[str]
) -> dict[str, Any]:
    plan_path = home / "plan.json"
    plan_path.write_text(json.dumps(planned["plan"]), encoding="utf-8")
    return await native(
        binary, home, [*prefix, "--plan", str(plan_path), "--plan-digest", planned["plan_digest"]]
    )


async def prove(
    binary: Path, database_url: str, root: Path, *, credential_store: str = "file"
) -> None:
    settings = make_settings(root / "api", database_url=database_url)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        objects = ObservedObjects()
        app.state.object_client = objects
        store = ImmutableObjectStore(settings=settings.storage, client=objects)
        async with app.state.sessionmaker() as db:
            await load_fixture_seed(db)
            fixture = await store_fixture_artifacts(db, store, harness="codex")
            component, document = fixture.component, fixture.component_document
            stored, setup_bytes = fixture.stored, fixture.setup_bytes
            if await db.get(CatalogIdentity, FIXTURE_COMPONENT_ID) is None:
                db.add(
                    CatalogIdentity(
                        stable_id=FIXTURE_COMPONENT_ID,
                        owner_account_id=SEED_OWNER_ACCOUNT_ID,
                        canonical_name="fixture-component",
                        canonical_name_normalized="fixture-component",
                    )
                )
            await db.commit()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
            server = uvicorn.Server(
                uvicorn.Config(app, lifespan="off", access_log=False, log_level="error")
            )
            serving = asyncio.create_task(server.serve(sockets=[listener]))
            try:
                async with asyncio.timeout(15):
                    while not server.started:
                        await asyncio.sleep(0.01)
                owner, revision_id = SEED_OWNER_ACCOUNT_ID, ""
                for transfer_count in range(3):
                    if transfer_count:
                        async with app.state.sessionmaker() as db:
                            recipient = Account(id=new_id("account"))
                            db.add(recipient)
                            await db.flush()
                            case = ReportCase(
                                id=new_id("report"),
                                reporter_account_id=recipient.id,
                                topic="ownership_transfer",
                                object_kind="component",
                                stable_id=FIXTURE_COMPONENT_ID,
                                state="submitted",
                                payload={"recipient_account_id": recipient.id},
                                group_key=f"native-transfer:{recipient.id}",
                                idempotency_key=f"native-transfer-{transfer_count}",
                            )
                            db.add(case)
                            await db.flush()
                            revision = await transfer_catalog_line(
                                db,
                                case_id=case.id,
                                expected_owner_account_id=owner,
                                expected_ownership_revision_id=revision_id,
                                recipient_account_id=recipient.id,
                                reason="Verified native acquisition regression",
                                operator_account_id=SEED_OWNER_ACCOUNT_ID,
                            )
                            owner, revision_id = recipient.id, revision.id
                            await db.commit()
                    home = root / f"consumer-{transfer_count}"
                    home.mkdir()
                    state = home / "state"
                    state.mkdir()
                    config = home / "config.yml"
                    config.write_text(
                        f"catalog:\n  url: http://127.0.0.1:{port}\n", encoding="utf-8"
                    )
                    identity = await native(
                        binary,
                        home,
                        [
                            "device",
                            "initialize",
                            "plan",
                            "--state-dir",
                            str(state),
                            "--credential-store",
                            credential_store,
                        ],
                    )
                    await apply(binary, home, identity, ["device", "initialize", "apply"])
                    objects.reads.clear()
                    planned = await native(
                        binary,
                        home,
                        [
                            "registry",
                            "acquire",
                            "plan",
                            "--state-dir",
                            str(state),
                            "--config",
                            str(config),
                            "--id",
                            FIXTURE_SETUP_ID,
                            "--version",
                            "1.0",
                        ],
                    )
                    acquired = await apply(binary, home, planned, ["local", "apply"])
                    replay = await apply(binary, home, planned, ["local", "apply"])
                    assert replay == acquired
                    assert {
                        (artifact.bucket, artifact.key) for artifact in [*stored, setup_bytes]
                    } <= objects.reads
                    async with app.state.sessionmaker() as db:
                        held = await db.get(CatalogMetadata, component.id)
                        assert held is not None and held.passport_document == document
                        assert held.owner_account_id == owner
                        assert held.passport_digest == component.passport_digest
                    print(
                        json.dumps(
                            {
                                "transfers": transfer_count,
                                "native_exact_setup_acquisition": "passed",
                                "original_namespace_bytes_verified": len(stored) + 1,
                                "replay": "passed",
                            }
                        ),
                        flush=True,
                    )
            finally:
                server.should_exit = True
                await serving


def main() -> None:
    binary = Path(sys.argv[1]).resolve(strict=True)
    saved = os.environ.get("AI_STP_DB_URL")
    with (
        tempfile.TemporaryDirectory(prefix="ai-stp-ownership-") as temporary,
        isolated_database(
            "AI_STP_TEST_DB_URL is required for native ownership qualification"
        ) as url,
    ):
        try:
            os.environ["AI_STP_DB_URL"] = url
            command.upgrade(Config("alembic.ini"), "head")
            asyncio.run(prove(binary, url, Path(temporary)))
        finally:
            if saved is None:
                os.environ.pop("AI_STP_DB_URL", None)
            else:
                os.environ["AI_STP_DB_URL"] = saved


if __name__ == "__main__":
    main()
