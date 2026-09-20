# pyright: reportUnusedFunction=false

"""Private distribution journeys: CLI commands against the real `/v1` app.

Replaces the `#71`-mock journeys in
`tests/unit/test_cli_private_distribution.py`. `publication plan` and
`visibility plan/confirm` run through the same ASGI app and PostgreSQL the
production server serves — including the locally-authored component passport
the command actually sends.

The visibility leg uses the seeded catalog's published component owned by
`SEED_OWNER_ACCOUNT_ID`, so the session for it is issued for that account
directly (the device row is registered server-side, then persisted locally —
the same state `auth complete` leaves).
"""

from __future__ import annotations

import secrets
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from tests.support.asgi_sync import SyncAsgiServer
from tests.support.catalog_seed import FIXTURE_COMPONENT_ID, SEED_OWNER_ACCOUNT_ID
from tests.support.publication_artifacts import (
    ARTIFACT_BY_DIGEST,
    PROJECTION_ARTIFACT,
    PROJECTION_DIGEST,
)
from tests.unit.test_cli_install_commands import _confirmed  # pyright: ignore[reportPrivateUsage]

from ai_stp_api.session import issue_session
from ai_stp_cli.cloud import publication as publication_transport
from ai_stp_cli.cloud import session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.cloud.session import Session as CliSession
from ai_stp_cli.commands import visibility
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import selection
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_cli.secrets import open_store
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Device
from ai_stp_platform.settings import StorageSettings
from ai_stp_platform.storage.memory import MemoryObjectClient
from ai_stp_platform.storage.object_store import ImmutableObjectStore


@pytest.fixture(autouse=True)
def _object_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Content-addressed bytes — S3 is the external seam."""
    client = MemoryObjectClient()
    settings = StorageSettings(
        endpoint="http://memory.test",
        bucket="test",
        access_key_id="test",
        secret_access_key="test",
    )
    store = ImmutableObjectStore(settings=settings, client=client)

    for digest, payload in [
        *ARTIFACT_BY_DIGEST.items(),
        (PROJECTION_DIGEST, PROJECTION_ARTIFACT),
    ]:
        key = store.key_for_digest(digest)
        client.objects[(settings.bucket, key)] = {
            "body": payload,
            "metadata": {
                "ai-stp-digest": digest,
                "ai-stp-size-bytes": str(len(payload)),
                "ai-stp-content-id": digest,
            },
            "size_bytes": len(payload),
        }

    async def _open() -> ImmutableObjectStore:
        return store

    async def _close(_store: ImmutableObjectStore | None) -> None:
        return None

    monkeypatch.setattr(
        "ai_stp_platform.publication_logic.open_env_object_store",
        _open,
    )
    monkeypatch.setattr(
        "ai_stp_platform.publication_logic.close_env_object_store",
        _close,
    )


def _component(connection: sqlite3.Connection, tmp_path: Path, suffix: str) -> str:
    """A locally authored component carrying full publication provenance."""
    proposal = _confirmed(
        connection,
        tmp_path,
        suffix,
        source=("https://github.com/example/demo", "a" * 40, "skills/demo"),
    )
    selected = selection.held(connection, proposal)
    assert selected is not None
    return selected.members[0].stable_id


def _seed_owner_session(cli_server: SyncAsgiServer) -> CliSession:
    """A device-bound session for the seeded catalog object's owner."""
    sessionmaker = cli_server.app.state.sessionmaker

    async def issue() -> tuple[str, str]:
        async with sessionmaker() as db:
            device = Device(
                id=new_id("device"),
                account_id=SEED_OWNER_ACCOUNT_ID,
                public_key="dGVzdC1wdWJsaWMta2V5LXB1Ymxpc2g=",
                state="active",
            )
            db.add(device)
            await db.flush()
            issued = await issue_session(
                db, account_id=SEED_OWNER_ACCOUNT_ID, device_id=device.id, ttl_seconds=3600
            )
            await db.commit()
            return device.id, issued.raw_token

    device_id, token = cli_server.call(issue)
    held = CliSession(
        account_id=SEED_OWNER_ACCOUNT_ID,
        device_id=device_id,
        access_token=token,
        refresh_token="",
        expires_at=session.expiry(3600),
    )
    store, _warning = open_store()
    session.save(store, held)
    return held


def _published_version(cli_server: SyncAsgiServer) -> str:
    """The newest published version of the seeded component."""
    sessionmaker = cli_server.app.state.sessionmaker

    async def read() -> str:
        from sqlalchemy import select

        from ai_stp_platform.models import CatalogMetadata

        async with sessionmaker() as db:
            row = await db.scalar(
                select(CatalogMetadata.version)
                .where(
                    CatalogMetadata.stable_id == FIXTURE_COMPONENT_ID,
                    CatalogMetadata.published_at.is_not(None),
                )
                .order_by(CatalogMetadata.version.desc())
            )
            assert row is not None
            return str(row)

    return cli_server.call(read)


def test_plan_defaults_to_private_for_a_locally_authored_component(
    cli_endpoint: Endpoint,
    device_session: CliSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`publication plan` sends the real local passport; the server creates it."""
    from ai_stp_cli.application import publication as publication_service
    from ai_stp_cli.commands import publication

    with closing(open_registry(configured_path(), create=True)) as connection:
        component_id = _component(connection, tmp_path, "8")

    monkeypatch.setattr(publication_service, "endpoint", lambda: cli_endpoint)
    monkeypatch.setattr(publication_service, "_session", lambda: device_session)

    planned = publication.plan({"id": component_id, "version": "1.0"}).payload
    assert planned.visibility == "private"
    assert planned.stable_id == component_id

    # The plan exists server-side under the session's account.
    shown = publication_transport.status(cli_endpoint, device_session.access_token, planned.plan_id)
    assert shown.stable_id == component_id
    assert shown.visibility == "private"


def test_visibility_plan_and_confirm_apply_the_exact_decision(
    cli_endpoint: Endpoint,
    cli_server: SyncAsgiServer,
    seeded_catalog: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Owner opens then re-closes a published version; confirm replays once."""
    _seed_owner_session(cli_server)
    version = _published_version(cli_server)
    monkeypatch.setattr(visibility, "endpoint", lambda: cli_endpoint)

    coordinates = {"kind": "component", "id": FIXTURE_COMPONENT_ID, "version": version}
    planned = visibility.plan({**coordinates, "visibility": "private"}).payload
    assert planned.state == "planned"
    assert planned.visibility == "private"

    # Without the explicit decision the command refuses before any wire call.
    with pytest.raises(CliFailure, match="explicit confirmation"):
        visibility.confirm({"plan-id": planned.plan_id, "plan-hash": planned.plan_hash})

    completed = visibility.confirm(
        {
            "plan-id": planned.plan_id,
            "plan-hash": planned.plan_hash,
            "confirm": True,
        }
    ).payload
    assert completed.state == "applied"

    # Confirm is idempotent: the same decision replays the stored answer.
    again = visibility.confirm(
        {
            "plan-id": planned.plan_id,
            "plan-hash": planned.plan_hash,
            "confirm": True,
            "idempotency-key": secrets.token_hex(8),
        }
    ).payload
    assert again.state == "applied"

    # And the owner can open the exact version again afterwards.
    reopened = visibility.plan({**coordinates, "visibility": "public"}).payload
    assert reopened.visibility == "public"
