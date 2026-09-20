"""CLI↔API boundary fixtures: the real app served to the real client code.

`cli_server` builds the FastAPI app over an isolated migrated PostgreSQL
database and exposes it as a sync `httpx` transport on a dedicated loop, so
`ai_stp_cli.cloud` calls run against the deployed contract rather than the
`#71` corpus mock. Fixture names match `_PG_FIXTURES` in the root conftest so
`pg` marking stays automatic.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from tests.support.api_settings import make_settings, make_test_auth
from tests.support.asgi_sync import SyncAsgiServer
from tests.support.postgres import (
    TEST_DB_ENV,
    isolated_database,
    migrated_database,
    migrated_template,
)

from ai_stp_api.app import create_app
from ai_stp_api.session import issue_session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account

pytestmark = pytest.mark.cli


@pytest.fixture()
def isolated_database_url() -> Iterator[str]:
    """Create a temporary PostgreSQL database and remove it after one test."""
    with isolated_database(f"{TEST_DB_ENV} is required for PostgreSQL API tests") as url:
        yield url


@pytest.fixture(scope="session")
def pg_migrated_template() -> Iterator[str | None]:
    """One fully migrated database per xdist worker; individual tests clone it."""
    with migrated_template() as database:
        yield database


@pytest.fixture()
def migrated_database_url(
    pg_migrated_template: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[str]:
    """Clone the per-worker migrated template into a disposable database."""
    with migrated_database(
        pg_migrated_template,
        monkeypatch,
        skip_reason=f"{TEST_DB_ENV} is required for PostgreSQL API tests",
    ) as url:
        yield url


@pytest.fixture()
def cli_server(tmp_path: Path, migrated_database_url: str) -> Iterator[SyncAsgiServer]:
    """The real `/v1` app over the isolated database, reachable synchronously."""
    # `public_base_url` must satisfy the contract's verification-URI pattern:
    # https or http://localhost only.
    auth = make_test_auth(public_base_url="http://localhost:3000")
    settings = make_settings(tmp_path, database_url=migrated_database_url, auth=auth)
    app = create_app(settings)
    with SyncAsgiServer(app) as server:
        yield server


@pytest.fixture()
def cli_endpoint(cli_server: SyncAsgiServer) -> Endpoint:
    """The endpoint the CLI cloud layer calls; loopback HTTP is permitted."""
    assert cli_server.transport is not None
    return Endpoint("http://127.0.0.1", transport=cli_server.transport)


@dataclass(frozen=True)
class WebApprover:
    """The browser side of device auth: an account holding a web session."""

    account_id: str
    token: str
    approve: Callable[[str], httpx.Response]


@pytest.fixture()
def web_approver(cli_server: SyncAsgiServer) -> Callable[[], WebApprover]:
    """Factory: seed `account_id` + a web session; `approve(user_code)` binds it."""

    def build() -> WebApprover:
        account_id = new_id("account")
        sessionmaker = cli_server.app.state.sessionmaker

        async def seed() -> str:
            async with sessionmaker() as db:
                db.add(Account(id=account_id))
                issued = await issue_session(
                    db, account_id=account_id, device_id=None, ttl_seconds=3600
                )
                await db.commit()
                return issued.raw_token

        token = cli_server.call(seed)

        def approve(user_code: str) -> httpx.Response:
            assert cli_server.transport is not None
            with httpx.Client(
                transport=cli_server.transport,
                base_url="http://127.0.0.1",
                headers={"Authorization": f"Bearer {token}"},
            ) as web:
                return web.post("/v1/auth/device/approve", json={"user_code": user_code})

        return WebApprover(account_id=account_id, token=token, approve=approve)

    return build
